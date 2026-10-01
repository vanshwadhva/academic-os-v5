"""
Sync Manager — Orchestrates end-to-end Lumen LMS data synchronisation.

This is the single entry point that Academic OS calls to:

  1. Verify (or initiate) a student's Lumen authentication.
  2. Fetch every academic data domain from the Brightspace API.
  3. Normalise and upsert records into the local/cloud store.
  4. Emit a structured SyncResult that the dashboard and ML pipeline consume.

Authentication strategy
-----------------------
The PRD mandates that Lumen login is **compulsory** after Academic OS login.
SyncManager enforces this gate: ``run_full_sync()`` raises
``LumenAuthRequired`` if no valid Lumen connection exists for the student.

Brightspace URL:  https://lumen.bitspilani-digital.edu.in
API version:      LE 1.55  (validated against Brightspace community docs)

Integration path priority (matches PRD §Integration Strategy):
  A. Official Brightspace OAuth2 (preferred — requires tenant app registration)
  B. Session-based credential flow (fallback — requires institutional approval)

Both paths produce an authenticated ``LumenClient`` instance that all domain
fetchers consume.  SyncManager itself does not care which path was used.

Sync lifecycle
--------------
::

    QUEUED → RUNNING → SUCCESS | PARTIAL | FAILED

Failure handling follows the PRD:
  - Per-domain failures are caught and logged; the sync continues.
  - Last-known-good data is preserved on failure.
  - ``SyncResult.domain_errors`` maps every failed domain to its error.
  - Retries are the caller's responsibility (``scheduler/sync_jobs.py``).

Usage
-----
::

    manager = SyncManager.from_env()           # picks up config from env vars

    # Force Lumen login gate — raises LumenAuthRequired if not linked
    result = await manager.run_full_sync(
        student_id="google_uid_abc123",
        lumen_token=stored_encrypted_token,    # None → raises LumenAuthRequired
        trigger="login",
    )

    if result.status == SyncStatus.SUCCESS:
        dashboard_data = result.to_dashboard_payload()
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .lumen_client import LumenClient
from .lumen_courses import LumenCourses
from .lumen_grades import LumenGrades
from .lumen_modules import LumenModules
from .lumen_assignments import LumenAssignments
from .lumen_quizzes import QuizService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LUMEN_BASE_URL = os.getenv(
    "LUMEN_BASE_URL",
    "https://lumen.bitspilani-digital.edu.in",
)
LUMEN_LE_VERSION = "1.55"

# Per-student sync lock — prevents duplicate concurrent syncs (PRD §FR-13)
_SYNC_LOCKS: Dict[str, threading.Lock] = {}
_SYNC_LOCKS_META: Dict[str, Any] = {}
_LOCK_REGISTRY_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LumenAuthRequired(Exception):
    """
    Raised when a sync is attempted without a valid Lumen connection.

    This is the gate that makes Lumen login compulsory after Academic OS login.
    The API layer should translate this into HTTP 403 with reason
    ``lms_not_linked`` so the frontend shows the Connect Lumen prompt.
    """

    def __init__(
        self,
        message: str = (
            "Lumen LMS authentication is required. "
            "Please connect your BITS Lumen account to continue."
        ),
    ) -> None:
        super().__init__(message)
        self.reason = "lms_not_linked"


class SyncAlreadyRunning(Exception):
    """Raised when a sync is requested while one is already in progress."""

    def __init__(self, student_id: str) -> None:
        super().__init__(
            f"A sync is already in progress for student {student_id}. "
            "Wait for it to complete before triggering a new one."
        )
        self.student_id = student_id


class SyncError(Exception):
    """General sync failure with structured metadata."""

    def __init__(self, message: str, correlation_id: str = "", domain: str = "") -> None:
        super().__init__(message)
        self.correlation_id = correlation_id
        self.domain = domain


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class SyncStatus(str, Enum):
    QUEUED  = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"   # some domains failed, others succeeded
    FAILED  = "failed"    # entire sync failed (usually auth)


class SyncTrigger(str, Enum):
    LOGIN     = "login"
    MANUAL    = "manual"
    SCHEDULED = "scheduled"
    BACKFILL  = "backfill"


@dataclass
class CourseSnapshot:
    """Aggregated LMS data for one course offering."""

    course_id: str
    course_name: str
    course_code: str

    # Domain data — each list is the normalised output from the respective fetcher
    modules:     List[Dict[str, Any]] = field(default_factory=list)
    grades:      List[Dict[str, Any]] = field(default_factory=list)
    assignments: List[Dict[str, Any]] = field(default_factory=list)
    quizzes:     List[Dict[str, Any]] = field(default_factory=list)
    attendance:  Optional[Dict[str, Any]] = None   # None if not exposed by tenant

    # Derived summary
    overall_progress_pct: Optional[float] = None
    modules_completed:    int = 0
    modules_total:        int = 0
    module_progress_available: bool = False

    synced_at: str = field(default_factory=lambda: _utcnow())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SyncResult:
    """
    Complete result of one synchronisation run.

    Used by:
    - Dashboard service to build the student-facing overview.
    - Feature engineering to compute ML feature vectors.
    - Scheduler to decide on retries.
    - Audit log to record what happened.
    """

    # Identity
    sync_job_id:    str
    student_id:     str
    correlation_id: str

    # Status
    status:         SyncStatus
    trigger:        SyncTrigger
    started_at:     str
    ended_at:       Optional[str] = None

    # Payload
    courses:           List[CourseSnapshot] = field(default_factory=list)
    lms_user_id:       Optional[str] = None

    # Diagnostics
    records_fetched:   int = 0
    domain_errors:     Dict[str, str] = field(default_factory=dict)
    error_message:     Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.ended_at:
            try:
                start = datetime.fromisoformat(self.started_at)
                end   = datetime.fromisoformat(self.ended_at)
                return (end - start).total_seconds()
            except Exception:
                return None
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"]  = self.status.value
        d["trigger"] = self.trigger.value
        d["duration_seconds"] = self.duration_seconds
        return d

    def to_dashboard_payload(self) -> Dict[str, Any]:
        """
        Produce the dict that ``DashboardService`` expects.

        Shape is designed to be directly serialisable to JSON for the
        ``GET /api/dashboard/overview`` endpoint.
        """
        return {
            "sync_status":     self.status.value,
            "last_synced_at":  self.ended_at or self.started_at,
            "sync_job_id":     self.sync_job_id,
            "lms_user_id":     self.lms_user_id,
            "courses":         [c.to_dict() for c in self.courses],
            "records_fetched": self.records_fetched,
            "has_errors":      bool(self.domain_errors),
            "domain_errors":   self.domain_errors,
        }


# ---------------------------------------------------------------------------
# Token / credential container
# ---------------------------------------------------------------------------


@dataclass
class LumenCredential:
    """
    Carries all auth material needed to build a ``LumenClient``.

    Produced by the OAuth callback handler and stored (encrypted) in
    Firestore under the student's UID.  SyncManager accepts this object
    so it stays decoupled from any specific storage backend.

    Fields
    ------
    access_token:
        Plain-text bearer token.  Never log this value.
    expires_in:
        Token lifetime in seconds from the moment it was issued.
    refresh_token:
        Optional — present when the Brightspace app has offline_access scope.
    lms_user_id:
        The Brightspace UserId (``/d2l/api/lp/1.0/users/whoami``).
    auth_type:
        ``"oauth2"`` or ``"session"`` — for audit purposes only.
    issued_at:
        ISO timestamp when the credential was acquired.
    """

    access_token:  str
    expires_in:    int
    lms_user_id:   Optional[str] = None
    refresh_token: Optional[str] = None
    auth_type:     str = "oauth2"
    issued_at:     str = field(default_factory=lambda: _utcnow())

    def is_expired(self) -> bool:
        """Return True if the token is past its lifetime (with 5-min buffer)."""
        try:
            issued = datetime.fromisoformat(self.issued_at)
            age    = (datetime.now(tz=timezone.utc) - issued).total_seconds()
            return age >= (self.expires_in - 300)
        except Exception:
            return True

    @classmethod
    def from_oauth_response(cls, data: Dict[str, Any]) -> "LumenCredential":
        """Build a credential from a raw Brightspace token response dict."""
        return cls(
            access_token  = data["access_token"],
            expires_in    = int(data.get("expires_in", 3600)),
            refresh_token = data.get("refresh_token"),
            lms_user_id   = data.get("user_id") or data.get("sub"),
        )


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


def _acquire_sync_lock(student_id: str) -> bool:
    """
    Try to acquire the per-student sync lock.

    Returns True on success, False if another sync is running.
    Thread-safe; uses a double-checked registry pattern.
    """
    with _LOCK_REGISTRY_LOCK:
        if student_id not in _SYNC_LOCKS:
            _SYNC_LOCKS[student_id] = threading.Lock()
        lock = _SYNC_LOCKS[student_id]

    acquired = lock.acquire(blocking=False)
    if acquired:
        _SYNC_LOCKS_META[student_id] = {"acquired_at": _utcnow()}
    return acquired


def _release_sync_lock(student_id: str) -> None:
    """Release the per-student sync lock if held."""
    with _LOCK_REGISTRY_LOCK:
        lock = _SYNC_LOCKS.get(student_id)
    if lock:
        try:
            lock.release()
            _SYNC_LOCKS_META.pop(student_id, None)
        except RuntimeError:
            pass  # already released


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Core SyncManager
# ---------------------------------------------------------------------------


class SyncManager:
    """
    Orchestrates a full or incremental Lumen LMS data synchronisation.

    Design principles
    -----------------
    * **Lumen auth is mandatory** — ``run_full_sync()`` raises
      ``LumenAuthRequired`` if no credential is supplied.  This enforces the
      PRD requirement that Lumen login is compulsory after Academic OS login.

    * **Per-student concurrency guard** — at most one sync runs per student
      at a time.  Duplicate requests raise ``SyncAlreadyRunning``.

    * **Graceful degradation per domain** — a failure fetching attendance
      does not abort the modules or grades fetch.  The result carries
      ``domain_errors`` so callers can surface actionable UI states.

    * **No storage coupling** — SyncManager returns ``SyncResult``.
      Persisting to Firestore, SQLite, or any other store is the caller's
      responsibility.  This keeps the integration layer testable without
      a database.

    Args:
        base_url:    Lumen instance base URL.
        client_id:   Brightspace OAuth2 client ID (empty string in session mode).
        client_secret: Brightspace OAuth2 client secret.
        encryption_key: Optional Fernet key for token encryption in LumenClient.
    """

    def __init__(
        self,
        base_url: str = LUMEN_BASE_URL,
        client_id: str = "",
        client_secret: str = "",
        encryption_key: Optional[str] = None,
    ) -> None:
        self.base_url       = base_url.rstrip("/")
        self.client_id      = client_id
        self.client_secret  = client_secret
        self.encryption_key = encryption_key

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "SyncManager":
        """
        Construct a SyncManager from environment variables.

        Environment variables
        ----------------------
        LUMEN_BASE_URL        — Brightspace instance URL
        LUMEN_CLIENT_ID       — OAuth2 client ID
        LUMEN_CLIENT_SECRET   — OAuth2 client secret
        LUMEN_ENCRYPTION_KEY  — Optional Fernet key (base64 url-safe, 32 bytes)
        """
        return cls(
            base_url       = os.getenv("LUMEN_BASE_URL", LUMEN_BASE_URL),
            client_id      = os.getenv("LUMEN_CLIENT_ID", ""),
            client_secret  = os.getenv("LUMEN_CLIENT_SECRET", ""),
            encryption_key = os.getenv("LUMEN_ENCRYPTION_KEY"),
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_full_sync(
        self,
        student_id: str,
        credential: Optional[LumenCredential],
        trigger: SyncTrigger = SyncTrigger.LOGIN,
    ) -> SyncResult:
        """
        Execute a full synchronisation for one student.

        This is the authoritative sync entry point.  Call it:
        - On every Academic OS login (trigger=LOGIN).
        - When the student clicks "Sync Now" (trigger=MANUAL).
        - From the scheduler (trigger=SCHEDULED).

        Lumen auth gate
        ---------------
        If ``credential`` is ``None`` or expired with no refresh token, this
        method raises ``LumenAuthRequired``.  The caller should catch this
        and redirect the student to the Lumen Connect flow.

        Concurrency guard
        -----------------
        Raises ``SyncAlreadyRunning`` if a sync is already in progress for
        this student.  The scheduler should treat this as a no-op and not
        retry immediately.

        Args:
            student_id:  Academic OS / Firebase UID.
            credential:  Authenticated Lumen credential.  ``None`` means the
                         student has not linked Lumen → ``LumenAuthRequired``.
            trigger:     What initiated this sync.

        Returns:
            ``SyncResult`` with status, course data, and any domain errors.

        Raises:
            LumenAuthRequired:  No valid Lumen credential.
            SyncAlreadyRunning: Duplicate concurrent sync.
        """
        # ── Gate 1: Lumen auth is mandatory ────────────────────────────────
        if credential is None:
            logger.warning(
                "Sync blocked for student %s — no Lumen credential", student_id
            )
            raise LumenAuthRequired()

        # ── Gate 2: Token freshness ─────────────────────────────────────────
        if credential.is_expired() and not credential.refresh_token:
            logger.warning(
                "Sync blocked for student %s — token expired, no refresh token",
                student_id,
            )
            raise LumenAuthRequired(
                "Your Lumen session has expired. "
                "Please reconnect your BITS Lumen account."
            )

        # ── Gate 3: Concurrency guard ───────────────────────────────────────
        if not _acquire_sync_lock(student_id):
            raise SyncAlreadyRunning(student_id)

        correlation_id = str(uuid.uuid4())
        sync_job_id    = f"sync_{student_id[:8]}_{int(time.time())}"

        result = SyncResult(
            sync_job_id    = sync_job_id,
            student_id     = student_id,
            correlation_id = correlation_id,
            status         = SyncStatus.RUNNING,
            trigger        = trigger,
            started_at     = _utcnow(),
            lms_user_id    = credential.lms_user_id,
        )

        logger.info(
            "Sync started — student=%s job=%s trigger=%s cid=%s",
            student_id, sync_job_id, trigger.value, correlation_id,
        )

        try:
            client = self._build_client(credential)
            self._maybe_resolve_lms_user_id(client, result)
            self._sync_all_courses(client, result)
            result.status = (
                SyncStatus.PARTIAL if result.domain_errors else SyncStatus.SUCCESS
            )

        except LumenAuthRequired:
            raise  # re-raise so callers can redirect to connect flow

        except Exception as exc:
            logger.exception(
                "Sync failed — job=%s cid=%s: %s",
                sync_job_id, correlation_id, exc,
            )
            result.status        = SyncStatus.FAILED
            result.error_message = str(exc)

        finally:
            result.ended_at = _utcnow()
            _release_sync_lock(student_id)
            logger.info(
                "Sync complete — job=%s status=%s records=%d duration=%.1fs",
                sync_job_id,
                result.status.value,
                result.records_fetched,
                result.duration_seconds or 0,
            )

        return result

    # ------------------------------------------------------------------
    # Client construction
    # ------------------------------------------------------------------

    def _build_client(self, credential: LumenCredential) -> LumenClient:
        """
        Construct an authenticated ``LumenClient`` from a credential.

        The client handles token refresh internally; we just seed it with
        the current access token and expiry.
        """
        client = LumenClient(
            base_url      = self.base_url,
            client_id     = self.client_id,
            client_secret = self.client_secret,
            encryption_key= self.encryption_key,
        )
        # Seed the token — LumenClient will refresh when it expires
        client.set_access_token(
            access_token  = credential.access_token,
            expires_in    = max(1, credential.expires_in - 300),  # 5-min safety buffer
            refresh_token = credential.refresh_token,
        )
        return client

    def _maybe_resolve_lms_user_id(
        self, client: LumenClient, result: SyncResult
    ) -> None:
        """
        Fetch the Brightspace UserId if the credential didn't include it.

        ``/d2l/api/lp/1.0/users/whoami`` returns the current user's profile.
        We need the numeric UserId for admin-scoped endpoints.
        """
        if result.lms_user_id:
            return

        try:
            whoami = client.request("GET", "/d2l/api/lp/1.0/users/whoami")
            result.lms_user_id = str(whoami.get("UserId") or whoami.get("Identifier", ""))
            logger.debug("Resolved LMS user ID: %s", result.lms_user_id)
        except Exception as exc:
            logger.warning("Could not resolve LMS user ID: %s", exc)
            result.domain_errors["whoami"] = str(exc)

    # ------------------------------------------------------------------
    # Course-level orchestration
    # ------------------------------------------------------------------

    def _sync_all_courses(
        self, client: LumenClient, result: SyncResult
    ) -> None:
        """
        Fetch the course list then sync every domain for each course.

        Each course is processed independently so a failure in one course
        does not abort the others.
        """
        courses_service = LumenCourses(client)

        try:
            raw_courses = courses_service.get_enrolled_courses(
                user_id=result.lms_user_id or None
            )
        except Exception as exc:
            logger.error("Failed to fetch course list: %s", exc)
            result.domain_errors["courses"] = str(exc)
            result.status = SyncStatus.FAILED
            raise SyncError(
                f"Cannot proceed without course list: {exc}",
                correlation_id=result.correlation_id,
                domain="courses",
            )

        logger.info(
            "Found %d enrolled courses for student %s",
            len(raw_courses), result.student_id,
        )

        for raw_course in raw_courses:
            course_id   = str(raw_course.get("course_id", ""))
            course_name = raw_course.get("course_name", "Unknown")
            course_code = raw_course.get("course_code", "")

            if not course_id:
                logger.warning("Skipping course with no ID: %s", raw_course)
                continue

            snapshot = CourseSnapshot(
                course_id   = course_id,
                course_name = course_name,
                course_code = course_code,
            )

            self._sync_course_domains(client, snapshot, result)
            result.courses.append(snapshot)

    def _sync_course_domains(
        self,
        client: LumenClient,
        snapshot: CourseSnapshot,
        result: SyncResult,
    ) -> None:
        """
        Fetch all data domains for a single course.

        Failures are captured per-domain so partial data is always preserved.
        The domain error key format is ``{domain}:{course_id}``.
        """
        course_id   = snapshot.course_id
        domain_pfx  = course_id

        # ── Modules / content completion ────────────────────────────────────
        try:
            modules_service = LumenModules(client)
            modules         = modules_service.get_course_modules(course_id)
            topic_progress_available = False
            try:
                topic_progress = modules_service.get_course_topic_progress(
                    course_id,
                    user_id=result.lms_user_id,
                )
                modules = modules_service.apply_topic_progress(modules, topic_progress)
                topic_progress_available = True
            except Exception as progress_exc:
                result.domain_errors[f"module_progress:{domain_pfx}"] = str(progress_exc)

            completion      = modules_service.get_content_completion(
                course_id, user_id=result.lms_user_id
            )
            snapshot.modules = modules
            snapshot.module_progress_available = topic_progress_available
            snapshot.modules_total     = len(modules)
            completion_info = completion.get("completion_info", {})
            aggregate_completed = int(completion_info.get("CompletedItems", 0) or 0)
            if topic_progress_available:
                snapshot.modules_completed = sum(
                    1 for module in modules
                    if module.get("visited") or module.get("is_read") or module.get("completed")
                )
            else:
                snapshot.modules_completed = aggregate_completed
                completion_total = int(completion_info.get("TotalItems", 0) or 0)
                if completion_total > snapshot.modules_total:
                    snapshot.modules_total = completion_total
            if snapshot.modules_total > 0:
                snapshot.overall_progress_pct = round(
                    (snapshot.modules_completed / snapshot.modules_total) * 100, 2
                )
            result.records_fetched += len(modules)
            logger.debug(
                "Modules synced — course=%s count=%d completed=%d",
                course_id, len(modules), snapshot.modules_completed,
            )
        except Exception as exc:
            logger.warning("Modules sync failed for %s: %s", course_id, exc)
            result.domain_errors[f"modules:{domain_pfx}"] = str(exc)

        # ── Grades ──────────────────────────────────────────────────────────
        try:
            grades_service = LumenGrades(client)
            grade_values   = grades_service.get_grade_values(
                course_id, user_id=result.lms_user_id
            )
            snapshot.grades = grade_values
            result.records_fetched += len(grade_values)
            logger.debug(
                "Grades synced — course=%s count=%d", course_id, len(grade_values)
            )
        except Exception as exc:
            logger.warning("Grades sync failed for %s: %s", course_id, exc)
            result.domain_errors[f"grades:{domain_pfx}"] = str(exc)

        # ── Assignments ─────────────────────────────────────────────────────
        try:
            assignments_service = LumenAssignments(client)
            assignments         = assignments_service.get_course_assignments(course_id)
            for assignment in assignments:
                assignment_id = assignment.get("assignment_id")
                if assignment_id is None:
                    assignment["submission_status"] = "unavailable"
                    assignment["submissions"] = []
                    continue

                try:
                    submissions = assignments_service.get_assignment_submissions(
                        course_id,
                        str(assignment_id),
                        user_id=result.lms_user_id,
                    )
                    assignment["submissions"] = submissions
                    submitted_entries = [
                        submission for submission in submissions
                        if submission.get("is_submitted") or submission.get("submission_date")
                    ]
                    assignment["is_submitted"] = bool(submitted_entries)
                    assignment["submission_status"] = "submitted" if submitted_entries else "pending"
                    assignment["submitted_at"] = max(
                        (submission.get("submission_date") for submission in submitted_entries if submission.get("submission_date")),
                        default=None,
                    )
                except Exception as submission_exc:
                    assignment["submissions"] = []
                    assignment["is_submitted"] = False
                    assignment["submission_status"] = "unavailable"
                    result.domain_errors[
                        f"assignment_submission:{course_id}:{assignment_id}"
                    ] = str(submission_exc)

            snapshot.assignments = assignments
            result.records_fetched += len(assignments)
            logger.debug(
                "Assignments synced — course=%s count=%d",
                course_id, len(assignments),
            )
        except Exception as exc:
            logger.warning("Assignments sync failed for %s: %s", course_id, exc)
            result.domain_errors[f"assignments:{domain_pfx}"] = str(exc)

        # ── Quizzes ─────────────────────────────────────────────────────────
        try:
            quiz_service  = QuizService(client)
            quiz_records  = quiz_service.get_full_quiz_sync(
                course_id,
                user_id           = result.lms_user_id,
                include_statistics= True,
            )
            snapshot.quizzes = [
                {
                    "lms_quiz_id":       r.lms_quiz_id,
                    "quiz_name":         r.quiz_name,
                    "status":            r.status,
                    "score_obtained":    r.score_obtained,
                    "score_max":         r.score_max,
                    "percentage":        r.percentage,
                    "attempt_count":     r.attempt_count,
                    "submitted_at":      r.submitted_at,
                    "due_at":            r.due_at,
                    "is_late":           r.is_late,
                    "last_synced_at":    r.last_synced_at,
                }
                for r in quiz_records
            ]
            result.records_fetched += len(quiz_records)
            logger.debug(
                "Quizzes synced — course=%s count=%d", course_id, len(quiz_records)
            )
        except Exception as exc:
            logger.warning("Quizzes sync failed for %s: %s", course_id, exc)
            result.domain_errors[f"quizzes:{domain_pfx}"] = str(exc)

        # ── Attendance (optional — gracefully absent) ────────────────────────
        try:
            attendance = self._fetch_attendance(client, course_id, result.lms_user_id)
            if attendance is not None:
                snapshot.attendance = attendance
                result.records_fetched += 1
        except Exception as exc:
            # Attendance is explicitly optional per PRD §FR-8
            logger.debug(
                "Attendance not available for course %s: %s", course_id, exc
            )

    # ------------------------------------------------------------------
    # Attendance (optional domain)
    # ------------------------------------------------------------------

    def _fetch_attendance(
        self,
        client: LumenClient,
        course_id: str,
        user_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to fetch attendance data.

        Brightspace attendance availability is instance-dependent (PRD §FR-8).
        Returns ``None`` if the endpoint is not available or not exposed for
        this course; never raises.
        """
        # Brightspace does not have a single unified attendance endpoint.
        # The most common approach is reading attendance registers via:
        # GET /d2l/api/le/1.55/{orgUnitId}/attendance/registers/
        try:
            registers_endpoint = (
                f"/d2l/api/le/{LUMEN_LE_VERSION}/{course_id}/attendance/registers/"
            )
            registers = client.get_paginated(registers_endpoint, page_size=50, max_pages=5)

            if not registers:
                return None

            # Sum attendance across all registers
            total_sessions   = 0
            attended_sessions = 0

            for register in registers:
                register_id = register.get("RegisterId") or register.get("Id")
                if not register_id:
                    continue
                try:
                    if user_id:
                        users_endpoint = (
                            f"/d2l/api/le/{LUMEN_LE_VERSION}/{course_id}"
                            f"/attendance/registers/{register_id}/users/{user_id}"
                        )
                    else:
                        users_endpoint = (
                            f"/d2l/api/le/{LUMEN_LE_VERSION}/{course_id}"
                            f"/attendance/registers/{register_id}/myattendance"
                        )
                    data = client.request("GET", users_endpoint)
                    for entry in data.get("AttendanceData", []):
                        total_sessions += 1
                        if entry.get("Status") in ("Present", "1", 1):
                            attended_sessions += 1
                except Exception:
                    pass  # register-level failure is non-fatal

            if total_sessions == 0:
                return None

            pct = round((attended_sessions / total_sessions) * 100, 2)
            return {
                "course_id":        course_id,
                "attendance_pct":   pct,
                "attended_sessions": attended_sessions,
                "total_sessions":   total_sessions,
                "risk_flag":        pct < 75,
                "synced_at":        _utcnow(),
            }

        except Exception as exc:
            logger.debug("Attendance endpoint absent for course %s: %s", course_id, exc)
            return None

    def fetch_progress(
        self,
        student_id: str,
        credential: Optional[LumenCredential],
    ) -> Dict[str, Any]:
        """Fetch the latest LMS progress and return a dashboard-ready payload."""
        result = self.run_full_sync(
            student_id=student_id,
            credential=credential,
            trigger=SyncTrigger.MANUAL,
        )
        return result.to_dashboard_payload()

    # ------------------------------------------------------------------
    # OAuth2 helpers (called by the auth callback route, not the sync)
    # ------------------------------------------------------------------

    def build_oauth_url(self, redirect_uri: str, state: str) -> str:
        """
        Build the Brightspace OAuth2 authorisation URL.

        The frontend Connect Lumen button should redirect to this URL.
        The student authenticates in Brightspace, then Brightspace
        redirects back to ``redirect_uri`` with ``code`` and ``state``.

        Args:
            redirect_uri: Your registered callback URL.
            state:        CSRF token generated by the server.

        Returns:
            Full authorisation URL.

        Note
        ----
        This requires your application to be registered in the Brightspace
        tenant by BITS IT.  Without app registration, OAuth2 is not available.
        """
        import urllib.parse
        params = {
            "response_type": "code",
            "client_id":     self.client_id,
            "redirect_uri":  redirect_uri,
            "scope":         (
                "core:*:* "
                "enrollment:*:* "
                "grades:*:* "
                "content:*:* "
                "quizzing:*:* "
                "dropbox:*:* "
                "attendance:*:* "
            ).strip(),
            "state":         state,
        }
        return (
            f"{self.base_url}/core/oauth2/auth?"
            + urllib.parse.urlencode(params)
        )

    def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> LumenCredential:
        """
        Exchange an authorisation code for a LumenCredential.

        Called from the ``GET /api/lumen/connect/callback`` route after the
        student completes Brightspace OAuth2.

        Args:
            code:         The authorisation code from the callback.
            redirect_uri: Must match exactly what was used to generate the URL.

        Returns:
            ``LumenCredential`` ready to be encrypted and stored.

        Raises:
            Exception: If the token exchange fails.
        """
        import requests as req

        token_url = f"{self.base_url}/core/oauth2/token"
        payload = {
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": redirect_uri,
            "client_id":    self.client_id,
            "client_secret": self.client_secret,
        }
        response = req.post(
            token_url,
            data=payload,
            timeout=30,
            headers={"User-Agent": "Academic-OS/1.0 SyncManager/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        credential = LumenCredential.from_oauth_response(data)
        logger.info(
            "OAuth2 code exchanged — lms_user=%s auth_type=oauth2",
            credential.lms_user_id,
        )
        return credential

    def refresh_credential(self, credential: LumenCredential) -> LumenCredential:
        """
        Refresh an expired credential using its refresh_token.

        Returns a new ``LumenCredential`` with updated tokens.
        Raises if no refresh_token is available.
        """
        if not credential.refresh_token:
            raise LumenAuthRequired("Token expired and no refresh token available.")

        import requests as req

        token_url = f"{self.base_url}/core/oauth2/token"
        payload = {
            "grant_type":    "refresh_token",
            "refresh_token": credential.refresh_token,
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
        }
        response = req.post(
            token_url,
            data=payload,
            timeout=30,
            headers={"User-Agent": "Academic-OS/1.0 SyncManager/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        new_cred = LumenCredential.from_oauth_response(data)
        # Keep lms_user_id from original if not returned
        if not new_cred.lms_user_id and credential.lms_user_id:
            new_cred.lms_user_id = credential.lms_user_id
        logger.info("Credential refreshed — lms_user=%s", new_cred.lms_user_id)
        return new_cred
