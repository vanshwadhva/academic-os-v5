"""
Lumen Quizzes Module — Fetch, parse, and normalize quiz data.

Retrieves quiz objects, attempt records, individual question scores,
and computed statistics from the Brightspace Quizzing APIs.

Brightspace API references used:
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/                (quiz list)
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/{quizId}        (quiz detail)
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/{quizId}/attempts/myattempts
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/{quizId}/attempts/{attemptId}
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/{quizId}/statistics/
  - /d2l/api/le/{ver}/{orgUnitId}/quizzes/{quizId}/questions/

Data flows into the `quiz_marks` table as defined in the PRD data model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .lumen_client import LumenClient
from .lumen_exceptions import LumenAPIError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LE_VERSION = "1.55"
_DEFAULT_PAGE_SIZE = 100
_MAX_PAGES = 50  # safety cap — prevents runaway pagination


# ---------------------------------------------------------------------------
# Brightspace quiz status vocabulary → internal vocabulary
# ---------------------------------------------------------------------------

_ATTEMPT_STATUS_MAP: Dict[str, str] = {
    "Completed": "completed",
    "InProgress": "in_progress",
    "NotStarted": "pending",
    "Abandoned": "missed",
    "TimedOut": "missed",
    "Pending": "pending",
}

_QUIZ_STATUS_MAP: Dict[str, str] = {
    "Active": "active",
    "Inactive": "inactive",
    "Deleted": "deleted",
}

# ---------------------------------------------------------------------------
# Lightweight domain dataclasses
# Keeps calling code type-safe and makes serialisation trivial via asdict().
# ---------------------------------------------------------------------------


@dataclass
class QuizRecord:
    """Normalised representation of a single quiz (maps to PRD quiz_marks row)."""

    # Identifiers
    lms_quiz_id: str
    course_id: str

    # Descriptive
    quiz_name: str
    instructions: Optional[str]

    # Timing
    due_at: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    time_limit_minutes: Optional[int]

    # Attempt policy
    max_attempts_allowed: Optional[int]
    attempt_count: int = 0

    # Latest-attempt scores (populated after attempt fetch)
    score_obtained: Optional[float] = None
    score_max: Optional[float] = None
    percentage: Optional[float] = None

    # Status
    status: str = "pending"          # completed | pending | missed | in_progress
    quiz_status: str = "active"      # active | inactive | deleted

    # Submission tracking
    submitted_at: Optional[str] = None
    is_late: bool = False

    # Meta
    last_synced_at: str = field(default_factory=lambda: _utcnow_iso())


@dataclass
class QuizAttemptRecord:
    """Normalised representation of a single quiz attempt."""

    lms_attempt_id: str
    lms_quiz_id: str
    course_id: str
    user_id: Optional[str]

    attempt_number: int
    status: str                       # completed | in_progress | pending | missed

    score_obtained: Optional[float]
    score_max: Optional[float]
    percentage: Optional[float]

    started_at: Optional[str]
    submitted_at: Optional[str]
    is_late: bool = False

    time_spent_seconds: Optional[int] = None

    last_synced_at: str = field(default_factory=lambda: _utcnow_iso())


@dataclass
class QuizStatistics:
    """Class-level statistics for a quiz (useful for relative performance features)."""

    lms_quiz_id: str
    course_id: str

    class_mean: Optional[float]
    class_median: Optional[float]
    class_std_dev: Optional[float]
    class_min: Optional[float]
    class_max: Optional[float]
    attempt_count: Optional[int]
    completion_rate: Optional[float]

    last_synced_at: str = field(default_factory=lambda: _utcnow_iso())


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(raw: Optional[str]) -> Optional[str]:
    """
    Normalise a Brightspace datetime string to a timezone-aware ISO-8601 string.

    Brightspace typically returns strings like '2024-03-15T14:30:00.000Z'.
    Returns the original string (un-parsed) if it cannot be converted so
    that no data is silently dropped.
    """
    if not raw:
        return None
    try:
        # Handles trailing 'Z' and offset suffixes
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, AttributeError):
        logger.warning("Could not parse datetime string: %r — returning as-is", raw)
        return raw


def _safe_percentage(obtained: Optional[float], maximum: Optional[float]) -> Optional[float]:
    """Calculate percentage, guarding against None and zero-division."""
    if obtained is None or maximum is None or maximum == 0:
        return None
    return round((obtained / maximum) * 100, 2)


def _map_attempt_status(raw_status: Optional[str]) -> str:
    """Map Brightspace attempt status to internal vocabulary."""
    if not raw_status:
        return "pending"
    return _ATTEMPT_STATUS_MAP.get(raw_status, raw_status.lower())


def _map_quiz_status(raw_status: Optional[str]) -> str:
    """Map Brightspace quiz status to internal vocabulary."""
    if not raw_status:
        return "active"
    return _QUIZ_STATUS_MAP.get(raw_status, raw_status.lower())


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------


class LumenQuizzes:
    """
    Retrieve and normalise quiz data from the Lumen/Brightspace API.

    Responsibilities
    ----------------
    * Fetch all quizzes for a course offering.
    * Fetch the current student's attempt history per quiz.
    * Derive best-attempt scores and overall quiz summary metrics.
    * Fetch class-level statistics for relative scoring (ML features).
    * Surface a flat, ML-ready list of ``QuizRecord`` objects that map
      directly to the ``quiz_marks`` table defined in the PRD.

    Design principles
    -----------------
    * All public methods are safe to call independently — no hidden state
      dependency between calls.
    * Failures on optional endpoints (statistics, questions) are caught and
      logged; they never abort a full sync.
    * Due-date comparison uses timezone-aware datetimes throughout.
    * No data is silently dropped; parsing errors produce warnings and fall
      back to the raw value or None.

    Usage
    -----
    ::

        client = LumenClient(base_url=..., client_id=..., client_secret=...)
        quizzes = LumenQuizzes(client)

        # Full quiz sync for one course
        records = quizzes.get_full_quiz_sync(course_id="12345")

        # Serialise for DB upsert
        rows = [asdict(r) for r in records]
    """

    def __init__(self, client: LumenClient) -> None:
        """
        Initialise with an authenticated ``LumenClient``.

        Args:
            client: Authenticated, ready-to-use ``LumenClient`` instance.
        """
        self.client = client
        self._ver = _LE_VERSION
        logger.info("LumenQuizzes service initialised (LE API v%s)", self._ver)

    # ------------------------------------------------------------------
    # Public API — primary entry points
    # ------------------------------------------------------------------

    def get_full_quiz_sync(
        self,
        course_id: str,
        user_id: Optional[str] = None,
        include_statistics: bool = True,
    ) -> List[QuizRecord]:
        """
        Execute a complete quiz sync for a course.

        Fetches every quiz, resolves attempt records, merges best-attempt
        scores, and optionally annotates with class statistics.  This is
        the method the ``SyncManager`` should call.

        Args:
            course_id:           Brightspace org-unit ID of the course.
            user_id:             Optional Brightspace user ID.  Defaults to
                                 the token holder (self-service mode).
            include_statistics:  If True, fetch class-level stats and attach
                                 them to each record's ``score_max`` context.
                                 Statistics failures are non-fatal.

        Returns:
            List of ``QuizRecord`` objects, one per quiz in the course.

        Raises:
            LumenAPIError: If the primary quiz list cannot be fetched.
        """
        logger.info(
            "Starting full quiz sync — course_id=%s user_id=%s",
            course_id,
            user_id or "<self>",
        )

        quizzes = self.get_course_quizzes(course_id)
        records: List[QuizRecord] = []

        for quiz_raw in quizzes:
            quiz_id = quiz_raw.get("lms_quiz_id")
            if not quiz_id:
                logger.warning("Skipping quiz with no ID in course %s", course_id)
                continue

            # Build base record from quiz metadata
            record = self._build_quiz_record(quiz_raw, course_id)

            # Enrich with attempt data
            try:
                attempts = self.get_quiz_attempts(course_id, quiz_id, user_id=user_id)
                record = self._enrich_record_with_attempts(record, attempts)
            except LumenAPIError as exc:
                logger.warning(
                    "Could not fetch attempts for quiz %s: %s — continuing with base record",
                    quiz_id, exc,
                )

            # Optionally fetch class statistics (non-fatal)
            if include_statistics:
                try:
                    stats = self.get_quiz_statistics(course_id, quiz_id)
                    record = self._annotate_with_stats(record, stats)
                except LumenAPIError as exc:
                    logger.debug(
                        "Statistics unavailable for quiz %s: %s", quiz_id, exc
                    )

            records.append(record)

        logger.info(
            "Quiz sync complete — course_id=%s quizzes=%d", course_id, len(records)
        )
        return records

    def get_course_quizzes(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all quizzes in a course offering.

        Args:
            course_id: Brightspace org-unit ID.

        Returns:
            List of normalised quiz metadata dicts (not yet attempt-enriched).

        Raises:
            LumenAPIError: If the API call fails.
        """
        endpoint = f"/d2l/api/le/{self._ver}/{course_id}/quizzes/"

        try:
            raw_quizzes = self.client.get_paginated(
                endpoint,
                page_size=_DEFAULT_PAGE_SIZE,
                max_pages=_MAX_PAGES,
            )
        except Exception as exc:
            logger.error("Failed to fetch quiz list for course %s: %s", course_id, exc)
            raise LumenAPIError(f"Failed to fetch quiz list for course {course_id}: {exc}") from exc

        normalised = [self._normalise_quiz_metadata(q, course_id) for q in raw_quizzes]
        logger.info("Fetched %d quizzes for course %s", len(normalised), course_id)
        return normalised

    def get_quiz_details(self, course_id: str, quiz_id: str) -> Dict[str, Any]:
        """
        Fetch full detail for a single quiz.

        Args:
            course_id: Brightspace org-unit ID.
            quiz_id:   Brightspace quiz ID.

        Returns:
            Normalised quiz detail dict.

        Raises:
            LumenAPIError: If the API call fails.
        """
        endpoint = f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}"

        try:
            raw = self.client.request("GET", endpoint)
        except Exception as exc:
            logger.error("Failed to fetch quiz detail %s: %s", quiz_id, exc)
            raise LumenAPIError(f"Failed to fetch quiz detail {quiz_id}: {exc}") from exc

        normalised = self._normalise_quiz_metadata(raw, course_id)
        logger.debug("Fetched details for quiz %s in course %s", quiz_id, course_id)
        return normalised

    def get_quiz_attempts(
        self,
        course_id: str,
        quiz_id: str,
        user_id: Optional[str] = None,
    ) -> List[QuizAttemptRecord]:
        """
        Fetch all attempt records for a quiz.

        Uses the ``myattempts`` endpoint when ``user_id`` is None (student
        self-service) or the admin user-scoped endpoint when provided.

        Args:
            course_id: Brightspace org-unit ID.
            quiz_id:   Brightspace quiz ID.
            user_id:   Optional specific Brightspace user ID.

        Returns:
            List of ``QuizAttemptRecord`` objects sorted by attempt number.

        Raises:
            LumenAPIError: If the API call fails.
        """
        if user_id:
            endpoint = (
                f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}"
                f"/attempts/users/{user_id}/"
            )
        else:
            endpoint = (
                f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}"
                f"/attempts/myattempts/"
            )

        try:
            raw_attempts = self.client.get_paginated(
                endpoint,
                page_size=_DEFAULT_PAGE_SIZE,
                max_pages=_MAX_PAGES,
            )
        except Exception as exc:
            logger.error(
                "Failed to fetch attempts for quiz %s in course %s: %s",
                quiz_id, course_id, exc,
            )
            raise LumenAPIError(
                f"Failed to fetch attempts for quiz {quiz_id}: {exc}"
            ) from exc

        records = [
            self._normalise_attempt(a, quiz_id, course_id)
            for a in raw_attempts
        ]
        # Sort by attempt number ascending so callers can easily take latest/best
        records.sort(key=lambda r: r.attempt_number)

        logger.debug(
            "Fetched %d attempts for quiz %s in course %s",
            len(records), quiz_id, course_id,
        )
        return records

    def get_attempt_details(
        self,
        course_id: str,
        quiz_id: str,
        attempt_id: str,
    ) -> QuizAttemptRecord:
        """
        Fetch full detail for a single attempt, including per-question scores.

        Args:
            course_id:  Brightspace org-unit ID.
            quiz_id:    Brightspace quiz ID.
            attempt_id: Brightspace attempt ID.

        Returns:
            ``QuizAttemptRecord`` with detailed scoring.

        Raises:
            LumenAPIError: If the API call fails.
        """
        endpoint = (
            f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}"
            f"/attempts/{attempt_id}"
        )

        try:
            raw = self.client.request("GET", endpoint)
        except Exception as exc:
            logger.error("Failed to fetch attempt detail %s: %s", attempt_id, exc)
            raise LumenAPIError(f"Failed to fetch attempt {attempt_id}: {exc}") from exc

        record = self._normalise_attempt(raw, quiz_id, course_id)
        logger.debug("Fetched detail for attempt %s", attempt_id)
        return record

    def get_quiz_statistics(
        self,
        course_id: str,
        quiz_id: str,
    ) -> QuizStatistics:
        """
        Fetch class-level statistics for a quiz.

        These are used as ML features (e.g. relative-to-class performance).
        Availability depends on Brightspace instance configuration; a
        ``LumenAPIError`` is raised and the caller should treat it as
        optional.

        Args:
            course_id: Brightspace org-unit ID.
            quiz_id:   Brightspace quiz ID.

        Returns:
            ``QuizStatistics`` dataclass.

        Raises:
            LumenAPIError: If statistics are unavailable or the call fails.
        """
        endpoint = (
            f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}/statistics/"
        )

        try:
            raw = self.client.request("GET", endpoint)
        except Exception as exc:
            logger.debug(
                "Statistics endpoint unavailable for quiz %s: %s", quiz_id, exc
            )
            raise LumenAPIError(
                f"Statistics unavailable for quiz {quiz_id}: {exc}"
            ) from exc

        return QuizStatistics(
            lms_quiz_id=str(quiz_id),
            course_id=str(course_id),
            class_mean=raw.get("AverageScore"),
            class_median=raw.get("Median"),
            class_std_dev=raw.get("StandardDeviation"),
            class_min=raw.get("MinScore"),
            class_max=raw.get("MaxScore"),
            attempt_count=raw.get("AttemptCount"),
            completion_rate=raw.get("CompletionRate"),
        )

    def get_quiz_questions(
        self,
        course_id: str,
        quiz_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch question metadata for a quiz.

        Useful for fine-grained topic-level analysis.  Availability depends
        on quiz configuration and Brightspace permissions.

        Args:
            course_id: Brightspace org-unit ID.
            quiz_id:   Brightspace quiz ID.

        Returns:
            List of question metadata dicts.

        Raises:
            LumenAPIError: If the call fails.
        """
        endpoint = (
            f"/d2l/api/le/{self._ver}/{course_id}/quizzes/{quiz_id}/questions/"
        )

        try:
            raw_questions = self.client.get_paginated(
                endpoint,
                page_size=_DEFAULT_PAGE_SIZE,
                max_pages=_MAX_PAGES,
            )
        except Exception as exc:
            logger.error("Failed to fetch questions for quiz %s: %s", quiz_id, exc)
            raise LumenAPIError(
                f"Failed to fetch questions for quiz {quiz_id}: {exc}"
            ) from exc

        normalised = [self._normalise_question(q) for q in raw_questions]
        logger.debug("Fetched %d questions for quiz %s", len(normalised), quiz_id)
        return normalised

    def get_course_quiz_summary(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a high-level summary of quiz performance for a course.

        Useful for dashboard overview cards and for constructing ML
        feature vectors (avg score, attempt rate, missed count, etc.).

        Args:
            course_id: Brightspace org-unit ID.
            user_id:   Optional specific user ID.

        Returns:
            Summary dictionary with aggregate metrics.

        Raises:
            LumenAPIError: If quiz list cannot be fetched.
        """
        records = self.get_full_quiz_sync(
            course_id,
            user_id=user_id,
            include_statistics=False,
        )

        total = len(records)
        completed = [r for r in records if r.status == "completed"]
        pending = [r for r in records if r.status == "pending"]
        missed = [r for r in records if r.status == "missed"]
        late = [r for r in records if r.is_late]

        percentages = [
            r.percentage for r in completed if r.percentage is not None
        ]
        average_pct = (
            round(sum(percentages) / len(percentages), 2) if percentages else None
        )
        best_pct = max(percentages) if percentages else None
        worst_pct = min(percentages) if percentages else None

        return {
            "course_id": course_id,
            "total_quizzes": total,
            "completed_count": len(completed),
            "pending_count": len(pending),
            "missed_count": len(missed),
            "late_count": len(late),
            "average_percentage": average_pct,
            "best_percentage": best_pct,
            "worst_percentage": worst_pct,
            "attempt_rate": (
                round(len(completed) / total, 4) if total > 0 else None
            ),
            "synced_at": _utcnow_iso(),
        }

    # ------------------------------------------------------------------
    # Internal normalisation methods
    # ------------------------------------------------------------------

    def _normalise_quiz_metadata(
        self,
        raw: Dict[str, Any],
        course_id: str,
    ) -> Dict[str, Any]:
        """
        Convert a raw Brightspace quiz object into a flat internal dict.

        Brightspace quiz objects follow the ``QuizReadData`` schema:
        ``{ QuizId, Name, IsActive, DueDate, StartDate, EndDate,
            AttemptsAllowed, TimeLimit, Instructions, ... }``

        Args:
            raw:       Raw quiz dict from Brightspace API.
            course_id: Parent course org-unit ID.

        Returns:
            Flat dict aligned to the ``QuizRecord`` field names.
        """
        time_limit_raw = raw.get("TimeLimit") or {}
        time_limit_mins: Optional[int] = None
        if isinstance(time_limit_raw, dict):
            time_limit_mins = time_limit_raw.get("Minutes") or time_limit_raw.get("Value")
        elif isinstance(time_limit_raw, (int, float)):
            time_limit_mins = int(time_limit_raw)

        instructions_raw = raw.get("Instructions") or {}
        instructions_text: Optional[str] = None
        if isinstance(instructions_raw, dict):
            instructions_text = instructions_raw.get("Text") or instructions_raw.get("Html")
        elif isinstance(instructions_raw, str):
            instructions_text = instructions_raw

        return {
            "lms_quiz_id": str(raw.get("QuizId", "")),
            "course_id": str(course_id),
            "quiz_name": raw.get("Name", ""),
            "instructions": instructions_text,
            "due_at": _parse_iso(raw.get("DueDate")),
            "start_date": _parse_iso(raw.get("StartDate")),
            "end_date": _parse_iso(raw.get("EndDate")),
            "time_limit_minutes": time_limit_mins,
            "max_attempts_allowed": raw.get("AttemptsAllowed"),
            "quiz_status": _map_quiz_status(
                "Active" if raw.get("IsActive") else "Inactive"
            ),
            "synced_at": _utcnow_iso(),
        }

    def _build_quiz_record(
        self,
        normalised_meta: Dict[str, Any],
        course_id: str,
    ) -> QuizRecord:
        """
        Construct a ``QuizRecord`` from normalised metadata (no attempt data yet).

        Args:
            normalised_meta: Output of ``_normalise_quiz_metadata``.
            course_id:       Parent course ID.

        Returns:
            Unpopulated ``QuizRecord`` (scores/status filled in later).
        """
        return QuizRecord(
            lms_quiz_id=normalised_meta["lms_quiz_id"],
            course_id=course_id,
            quiz_name=normalised_meta.get("quiz_name", ""),
            instructions=normalised_meta.get("instructions"),
            due_at=normalised_meta.get("due_at"),
            start_date=normalised_meta.get("start_date"),
            end_date=normalised_meta.get("end_date"),
            time_limit_minutes=normalised_meta.get("time_limit_minutes"),
            max_attempts_allowed=normalised_meta.get("max_attempts_allowed"),
            quiz_status=normalised_meta.get("quiz_status", "active"),
        )

    def _normalise_attempt(
        self,
        raw: Dict[str, Any],
        quiz_id: str,
        course_id: str,
    ) -> QuizAttemptRecord:
        """
        Normalise a raw Brightspace attempt object.

        Brightspace attempt objects follow ``QuizAttemptData`` / ``AttemptData``:
        ``{ AttemptId, UserId, AttemptNumber, CompletionStatusId, Score,
            TimeStarted, TimeCompleted, IsLate, TimeLimitEnforced, ... }``

        Scores can be nested under a ``Score`` key as
        ``{ Score, OutOf }`` or appear at top level as
        ``{ ScoreActual, ScoreMax }``.

        Args:
            raw:       Raw attempt dict from Brightspace API.
            quiz_id:   Parent quiz ID.
            course_id: Parent course ID.

        Returns:
            Normalised ``QuizAttemptRecord``.
        """
        # Score extraction — handle nested and flat variants
        score_block = raw.get("Score") or {}
        if isinstance(score_block, dict):
            score_obtained = score_block.get("Score") or score_block.get("Actual")
            score_max = score_block.get("OutOf") or score_block.get("Max")
        else:
            score_obtained = raw.get("ScoreActual") or raw.get("Score")
            score_max = raw.get("ScoreMax") or raw.get("OutOf")

        # Also try top-level keys used by some LE versions
        if score_obtained is None:
            score_obtained = raw.get("ScoreActual")
        if score_max is None:
            score_max = raw.get("ScoreMax")

        percentage = _safe_percentage(score_obtained, score_max)

        # Time-spent calculation
        started_raw = raw.get("TimeStarted") or raw.get("StartedDate")
        completed_raw = raw.get("TimeCompleted") or raw.get("CompletedDate")
        time_spent_secs: Optional[int] = None
        if started_raw and completed_raw:
            try:
                t_start = datetime.fromisoformat(
                    started_raw.replace("Z", "+00:00")
                )
                t_end = datetime.fromisoformat(
                    completed_raw.replace("Z", "+00:00")
                )
                time_spent_secs = max(0, int((t_end - t_start).total_seconds()))
            except Exception:
                pass

        return QuizAttemptRecord(
            lms_attempt_id=str(raw.get("AttemptId", "")),
            lms_quiz_id=str(quiz_id),
            course_id=str(course_id),
            user_id=str(raw["UserId"]) if raw.get("UserId") else None,
            attempt_number=int(raw.get("AttemptNumber", 1)),
            status=_map_attempt_status(raw.get("CompletionStatusId") or raw.get("Status")),
            score_obtained=float(score_obtained) if score_obtained is not None else None,
            score_max=float(score_max) if score_max is not None else None,
            percentage=percentage,
            started_at=_parse_iso(started_raw),
            submitted_at=_parse_iso(completed_raw),
            is_late=bool(raw.get("IsLate", False)),
            time_spent_seconds=time_spent_secs,
        )

    def _enrich_record_with_attempts(
        self,
        record: QuizRecord,
        attempts: List[QuizAttemptRecord],
    ) -> QuizRecord:
        """
        Merge attempt data into a ``QuizRecord``.

        Strategy: use the **best** score across all completed attempts (not
        just the latest), which is the most common Brightspace grading
        policy and the most useful signal for predictions.  The latest
        attempt's submission timestamp is used for the ``submitted_at``
        field.

        Args:
            record:   Base ``QuizRecord`` with metadata only.
            attempts: All attempts for this quiz, sorted ascending.

        Returns:
            Enriched ``QuizRecord``.
        """
        record.attempt_count = len(attempts)

        if not attempts:
            record.status = self._derive_status_from_dates(record)
            return record

        completed_attempts = [
            a for a in attempts if a.status == "completed"
        ]
        in_progress_attempts = [
            a for a in attempts if a.status == "in_progress"
        ]

        if completed_attempts:
            # Pick attempt with highest percentage; fall back to score_obtained
            best = max(
                completed_attempts,
                key=lambda a: (
                    a.percentage if a.percentage is not None else -1
                ),
            )
            # Latest submission time across completed attempts
            latest = max(
                completed_attempts,
                key=lambda a: a.submitted_at or "",
            )
            record.score_obtained = best.score_obtained
            record.score_max = best.score_max
            record.percentage = best.percentage
            record.submitted_at = latest.submitted_at
            record.is_late = any(a.is_late for a in completed_attempts)
            record.status = "completed"

        elif in_progress_attempts:
            record.status = "in_progress"

        else:
            # All attempts are pending / missed states
            record.status = _map_attempt_status(attempts[-1].status)

        return record

    def _derive_status_from_dates(self, record: QuizRecord) -> str:
        """
        Infer quiz status from due/end dates when no attempts exist.

        Args:
            record: ``QuizRecord`` with date fields populated.

        Returns:
            Status string: 'missed' | 'pending'.
        """
        due_raw = record.due_at or record.end_date
        if not due_raw:
            return "pending"

        try:
            due_dt = datetime.fromisoformat(due_raw)
            now = datetime.now(tz=due_dt.tzinfo or timezone.utc)
            return "missed" if now > due_dt else "pending"
        except Exception:
            return "pending"

    def _annotate_with_stats(
        self,
        record: QuizRecord,
        stats: QuizStatistics,
    ) -> QuizRecord:
        """
        Attach class statistics to a ``QuizRecord``.

        Currently stored in the record for downstream feature engineering.
        The ``score_max`` is cross-validated against the class max score
        and corrected when absent.

        Args:
            record: Enriched ``QuizRecord``.
            stats:  ``QuizStatistics`` for the same quiz.

        Returns:
            Annotated ``QuizRecord``.
        """
        # If score_max was not resolvable from attempts, use class max
        if record.score_max is None and stats.class_max is not None:
            record.score_max = stats.class_max
            # Recompute percentage with the updated max
            record.percentage = _safe_percentage(record.score_obtained, record.score_max)

        return record

    @staticmethod
    def _normalise_question(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise a raw Brightspace question object.

        Args:
            raw: Raw question dict from Brightspace API.

        Returns:
            Flat normalised question dict.
        """
        return {
            "question_id": raw.get("QuestionId"),
            "question_text": (raw.get("QuestionText") or {}).get("Text", ""),
            "question_type": raw.get("QuestionTypeId"),
            "points": raw.get("Points"),
            "difficulty": raw.get("Difficulty"),
            "synced_at": _utcnow_iso(),
        }


# ---------------------------------------------------------------------------
# Module-level alias — matches the import in integrations/__init__.py
# ---------------------------------------------------------------------------

QuizService = LumenQuizzes
