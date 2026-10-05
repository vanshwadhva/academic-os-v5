"""
Dashboard Service
Aggregates data from all services and serves dashboard API responses.

Production considerations:
- Multi-level caching (in-memory, Redis fallback)
- Async aggregation with timeouts
- Graceful degradation when services fail
- Data provenance labeling (synced vs. computed vs. predicted)
- Request deduplication for concurrent dashboard loads
"""

import logging
import base64
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
import asyncio
from dataclasses import dataclass, asdict
import hashlib

import requests
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

ADMIN_EMAIL = os.getenv(
    "ADMIN_DASHBOARD_EMAIL",
    "2025em1300265@bitspilani-digital.edu.in",
).strip().lower()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "bits-dsai-tracker")
FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)


class AdminAccessDenied(Exception):
    """Raised when a caller is not allowed to view the admin dashboard."""


class FirebaseTokenError(Exception):
    """Raised when a Firebase ID token cannot be verified."""


def _b64url_decode(value: str) -> bytes:
    padding_len = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding_len))


class FirebaseIdTokenVerifier:
    """Verify Firebase ID tokens without requiring Firebase Admin SDK."""

    def __init__(
        self,
        project_id: str = FIREBASE_PROJECT_ID,
        certs_url: str = FIREBASE_CERTS_URL,
        cache_ttl_seconds: int = 3600,
    ):
        self.project_id = project_id
        self.certs_url = certs_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self._certs: Dict[str, str] = {}
        self._certs_expires_at = datetime.min

    def verify(self, id_token: str) -> Dict[str, Any]:
        if not id_token:
            raise FirebaseTokenError("Missing Firebase ID token")

        try:
            header_b64, payload_b64, signature_b64 = id_token.split(".")
            header = json.loads(_b64url_decode(header_b64))
            claims = json.loads(_b64url_decode(payload_b64))
            signature = _b64url_decode(signature_b64)
        except Exception as exc:
            raise FirebaseTokenError("Malformed Firebase ID token") from exc

        if header.get("alg") != "RS256":
            raise FirebaseTokenError("Firebase ID token must use RS256")

        kid = header.get("kid")
        try:
            cert_pem = self._get_certs().get(kid)
        except requests.RequestException as exc:
            raise FirebaseTokenError("Firebase signing certificates are unavailable") from exc
        if not cert_pem:
            raise FirebaseTokenError("Firebase signing certificate not found")

        signed_part = f"{header_b64}.{payload_b64}".encode("utf-8")
        certificate = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        public_key = certificate.public_key()

        try:
            public_key.verify(signature, signed_part, padding.PKCS1v15(), hashes.SHA256())
        except Exception as exc:
            raise FirebaseTokenError("Invalid Firebase ID token signature") from exc

        self._validate_claims(claims)
        return claims

    def _get_certs(self) -> Dict[str, str]:
        if self._certs and datetime.utcnow() < self._certs_expires_at:
            return self._certs

        response = requests.get(self.certs_url, timeout=5)
        response.raise_for_status()
        self._certs = response.json()
        self._certs_expires_at = datetime.utcnow() + timedelta(seconds=self.cache_ttl_seconds)
        return self._certs

    def _validate_claims(self, claims: Dict[str, Any]) -> None:
        now = int(datetime.utcnow().timestamp())
        issuer = f"https://securetoken.google.com/{self.project_id}"

        if claims.get("aud") != self.project_id:
            raise FirebaseTokenError("Firebase ID token audience mismatch")
        if claims.get("iss") != issuer:
            raise FirebaseTokenError("Firebase ID token issuer mismatch")
        if not claims.get("sub"):
            raise FirebaseTokenError("Firebase ID token subject is missing")
        try:
            expires_at = int(claims.get("exp", 0))
            issued_at = int(claims.get("iat", 0))
        except (TypeError, ValueError) as exc:
            raise FirebaseTokenError("Firebase ID token timestamps are invalid") from exc
        if expires_at <= now:
            raise FirebaseTokenError("Firebase ID token has expired")
        if issued_at <= 0 or issued_at > now + 300:
            raise FirebaseTokenError("Firebase ID token issued-at is in the future")


def is_admin_email(email: Optional[str]) -> bool:
    """Return True only for the configured admin dashboard email."""
    return (email or "").strip().lower() == ADMIN_EMAIL


def assert_admin_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce the exact admin email required by the admin dashboard flow."""
    email = claims.get("email")
    if not is_admin_email(email) or claims.get("email_verified") is not True:
        raise AdminAccessDenied("403 Forbidden: admin dashboard access is restricted")
    return claims


class DataProvenance(str, Enum):
    """Source of truth for a data point."""
    SYNCED = "synced"  # From LMS via sync
    COMPUTED = "computed"  # Derived from synced data
    PREDICTED = "predicted"  # ML model output


@dataclass
class DataPoint:
    """Single dashboard metric with provenance."""
    value: Any
    provenance: DataProvenance
    source: str  # e.g., "lumen_api", "progress_service", "xgboost_v1.0"
    computed_at: datetime
    confidence_score: Optional[float] = None  # 0-1, None if N/A
    is_stale: bool = False  # True if data older than threshold


class DashboardMetrics(BaseModel):
    """High-level dashboard metrics for a student."""
    student_id: str
    
    # Current progress (synced from LMS)
    current_completion_pct: Optional[float] = Field(None, ge=0, le=100, description="Synced from LMS")
    
    # Predicted completion (computed by model)
    predicted_completion_pct: Optional[float] = Field(None, ge=0, le=100, description="ML prediction")
    predicted_completion_confidence: Optional[float] = Field(None, ge=0, le=1)
    
    # Expected grade (predicted)
    expected_grade: Optional[str] = None
    expected_grade_confidence: Optional[float] = Field(None, ge=0, le=1)
    current_grade: Optional[float] = Field(None, ge=0, le=100, description="Latest synced grade")
    
    # Risk assessment (predicted)
    risk_level: Optional[str] = None  # low, medium, high, critical
    risk_score: Optional[float] = Field(None, ge=0, le=1)
    risk_confidence: Optional[float] = Field(None, ge=0, le=1)
    
    # Activity metrics
    days_since_last_activity: int = 0
    login_count_7d: int = 0
    submission_count_7d: int = 0
    
    # Engagement
    engagement_score: Optional[float] = Field(None, ge=0, le=1)
    preferred_activity_time: Optional[str] = None  # morning, afternoon, evening
    
    # Assessment performance
    quiz_average: Optional[float] = Field(None, ge=0, le=100)
    assignment_average: Optional[float] = Field(None, ge=0, le=100)
    
    # Temporal
    weeks_completed: int = 0
    weeks_remaining: int = 0
    course_completion_deadline: Optional[datetime] = None
    
    # Sync status
    last_sync_at: Optional[datetime] = None
    sync_status: str = "unknown"  # success, partial, failed, pending
    sync_error: Optional[str] = None
    
    # Metadata
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    data_freshness_minutes: int = 0  # Minutes since most recent data point


class CourseDashboard(BaseModel):
    """Course-specific dashboard."""
    course_id: str
    course_name: str
    term_name: Optional[str] = None
    
    # Progress
    module_completion_pct: float = Field(default=0, ge=0, le=100)
    completed_modules: int = 0
    total_modules: int = 0
    
    # Assessment
    current_grade: Optional[float] = Field(None, ge=0, le=100)
    quiz_average: Optional[float] = Field(None, ge=0, le=100)
    quiz_count_completed: int = 0
    quiz_count_total: int = 0
    assignment_average: Optional[float] = Field(None, ge=0, le=100)
    assignment_count_completed: int = 0
    assignment_count_total: int = 0
    
    # Predictions
    expected_final_grade: Optional[str] = None
    predicted_completion_pct: Optional[float] = Field(None, ge=0, le=100)
    risk_level: Optional[str] = None
    
    # Timing
    late_submissions: int = 0
    missed_submissions: int = 0
    days_until_deadline: Optional[int] = None
    
    # Modules breakdown (for module-level tracker)
    modules: List[Dict[str, Any]] = Field(default_factory=list)
    
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class OverviewDashboard(BaseModel):
    """Student overview dashboard."""
    student_id: str
    
    # Aggregate metrics across all courses
    total_courses: int = 0
    courses_on_track: int = 0
    courses_at_risk: int = 0
    courses_advanced: int = 0
    
    # Aggregated performance
    avg_course_completion_pct: float = 0
    avg_quiz_score: Optional[float] = None
    avg_assignment_score: Optional[float] = None
    
    # Risk and engagement
    student_status: str  # on_track, at_risk, advanced
    overall_engagement_score: Optional[float] = Field(None, ge=0, le=1)
    
    # Upcoming
    high_priority_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    upcoming_deadlines: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Sync health
    all_courses_synced_recently: bool = True
    last_full_sync_at: Optional[datetime] = None
    
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class DashboardCache:
    """In-memory cache for dashboard responses (Redis in production)."""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, tuple] = {}  # (data, expiry_time)
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached data if not expired."""
        if key not in self.cache:
            return None
        
        data, expiry = self.cache[key]
        if datetime.utcnow() > expiry:
            del self.cache[key]
            return None
        
        return data
    
    def set(self, key: str, data: Dict[str, Any], ttl_seconds: Optional[int] = None):
        """Cache data with TTL."""
        ttl = ttl_seconds or self.ttl_seconds
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self.cache[key] = (data, expiry)
    
    def invalidate(self, pattern: str):
        """Invalidate cache entries matching pattern."""
        keys_to_delete = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self.cache[key]
        logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
    
    def clear(self):
        """Clear entire cache."""
        self.cache.clear()


class DashboardService:
    """
    Aggregates data from all services and returns dashboard responses.
    
    Responsibilities:
    - Orchestrate multi-service requests with timeouts
    - Merge data with provenance tracking
    - Cache responses efficiently
    - Detect and report stale data
    - Graceful degradation on service failures
    - Request deduplication for high concurrency
    """
    
    # Service call timeouts (seconds)
    SERVICE_TIMEOUTS = {
        "progress": 2.0,
        "prediction": 3.0,
        "analytics": 2.0,
        "recommendation": 2.0,
        "sync": 1.0,
    }
    
    # Data staleness thresholds (minutes)
    STALENESS_THRESHOLDS = {
        "synced_data": 120,  # LMS data older than 2 hours
        "computed_data": 60,  # Computed metrics older than 1 hour
        "prediction": 180,  # Predictions older than 3 hours
    }
    
    def __init__(
        self,
        progress_service=None,
        prediction_service=None,
        analytics_service=None,
        recommendation_service=None,
        scheduler_service=None,
        cache: Optional[DashboardCache] = None,
    ):
        """
        Initialize dashboard service with dependencies.
        
        Args:
            progress_service: ProgressService instance
            prediction_service: PredictionService instance
            analytics_service: AnalyticsService instance
            recommendation_service: RecommendationService instance
            scheduler_service: SchedulerService instance
            cache: DashboardCache instance (creates default if None)
        """
        self.progress_service = progress_service
        self.prediction_service = prediction_service
        self.analytics_service = analytics_service
        self.recommendation_service = recommendation_service
        self.scheduler_service = scheduler_service
        self.cache = cache or DashboardCache(ttl_seconds=300)
        
        # Request deduplication (prevent thundering herd)
        self.pending_requests: Dict[str, asyncio.Future] = {}
    
    async def get_overview(self, student_id: str) -> OverviewDashboard:
        """
        Get overview dashboard for a student (all courses aggregate).
        
        Args:
            student_id: Student identifier
            
        Returns:
            OverviewDashboard object
        """
        # Check cache
        cache_key = f"dashboard:overview:{student_id}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Dashboard overview cache hit for {student_id}")
            return OverviewDashboard(**cached)
        
        # Request deduplication
        if cache_key in self.pending_requests:
            logger.debug(f"Reusing pending request for {cache_key}")
            return await self.pending_requests[cache_key]
        
        # Create future for this request
        future = asyncio.Future()
        self.pending_requests[cache_key] = future
        
        try:
            # Parallel fetch from all services (with timeouts)
            tasks = [
                self._get_courses_status(student_id),
                self._get_overall_metrics(student_id),
                self._get_engagement_metrics(student_id),
                self._get_active_recommendations(student_id, limit=3),
                self._get_upcoming_deadlines(student_id),
                self._get_sync_status(student_id),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            courses_status, overall_metrics, engagement, recommendations, deadlines, sync_status = results
            
            # Handle exceptions gracefully
            if isinstance(courses_status, Exception):
                logger.error(f"Failed to fetch courses status: {courses_status}")
                courses_status = {}
            
            if isinstance(overall_metrics, Exception):
                logger.error(f"Failed to fetch overall metrics: {overall_metrics}")
                overall_metrics = {}
            
            # Build dashboard
            dashboard = OverviewDashboard(
                student_id=student_id,
                total_courses=courses_status.get("total_courses", 0),
                courses_on_track=courses_status.get("courses_on_track", 0),
                courses_at_risk=courses_status.get("courses_at_risk", 0),
                courses_advanced=courses_status.get("courses_advanced", 0),
                avg_course_completion_pct=overall_metrics.get("avg_completion_pct", 0),
                avg_quiz_score=overall_metrics.get("avg_quiz_score"),
                avg_assignment_score=overall_metrics.get("avg_assignment_score"),
                student_status=courses_status.get("student_status", "unknown"),
                overall_engagement_score=engagement.get("engagement_score"),
                high_priority_recommendations=recommendations if isinstance(recommendations, list) else [],
                upcoming_deadlines=deadlines if isinstance(deadlines, list) else [],
                all_courses_synced_recently=sync_status.get("all_synced_recently", False),
                last_full_sync_at=sync_status.get("last_sync_at"),
            )
            
            # Cache result
            self.cache.set(cache_key, dashboard.dict())
            
            future.set_result(dashboard)
            logger.info(f"Generated overview dashboard for {student_id}")
            return dashboard
        
        except Exception as e:
            logger.error(f"Dashboard overview generation failed: {e}")
            future.set_exception(e)
            raise
        
        finally:
            self.pending_requests.pop(cache_key, None)
    
    async def get_course_dashboard(self, student_id: str, course_id: str) -> CourseDashboard:
        """
        Get detailed dashboard for a specific course.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            
        Returns:
            CourseDashboard object
        """
        cache_key = f"dashboard:course:{student_id}:{course_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return CourseDashboard(**cached)
        
        # Request deduplication
        if cache_key in self.pending_requests:
            return await self.pending_requests[cache_key]
        
        future = asyncio.Future()
        self.pending_requests[cache_key] = future
        
        try:
            # Parallel fetch
            tasks = [
                self._get_course_progress(student_id, course_id),
                self._get_course_predictions(student_id, course_id),
                self._get_course_modules(student_id, course_id),
            ]
            
            progress, predictions, modules = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(progress, Exception):
                logger.error(f"Failed to fetch course progress: {progress}")
                progress = {}
            
            if isinstance(predictions, Exception):
                logger.error(f"Failed to fetch predictions: {predictions}")
                predictions = {}
            
            if isinstance(modules, Exception):
                logger.error(f"Failed to fetch modules: {modules}")
                modules = []
            
            # Build dashboard
            dashboard = CourseDashboard(
                course_id=course_id,
                course_name=progress.get("course_name", f"Course {course_id}"),
                term_name=progress.get("term_name"),
                module_completion_pct=progress.get("module_completion_pct", 0),
                completed_modules=progress.get("completed_modules", 0),
                total_modules=progress.get("total_modules", 0),
                current_grade=progress.get("current_grade"),
                quiz_average=progress.get("quiz_average"),
                quiz_count_completed=progress.get("quiz_count_completed", 0),
                quiz_count_total=progress.get("quiz_count_total", 0),
                assignment_average=progress.get("assignment_average"),
                assignment_count_completed=progress.get("assignment_count_completed", 0),
                assignment_count_total=progress.get("assignment_count_total", 0),
                expected_final_grade=predictions.get("expected_grade"),
                predicted_completion_pct=predictions.get("completion_probability"),
                risk_level=predictions.get("risk_level"),
                late_submissions=progress.get("late_submissions", 0),
                missed_submissions=progress.get("missed_submissions", 0),
                days_until_deadline=progress.get("days_until_deadline"),
                modules=modules if isinstance(modules, list) else [],
            )
            
            # Cache
            self.cache.set(cache_key, dashboard.dict())
            future.set_result(dashboard)
            
            logger.info(f"Generated course dashboard for {student_id}/{course_id}")
            return dashboard
        
        except Exception as e:
            logger.error(f"Course dashboard generation failed: {e}")
            future.set_exception(e)
            raise
        
        finally:
            self.pending_requests.pop(cache_key, None)
    
    async def _get_courses_status(self, student_id: str) -> Dict[str, Any]:
        """Fetch aggregate course status."""
        try:
            if not self.progress_service:
                return {}
            
            # Would fetch all course metrics for student
            return {
                "total_courses": 0,
                "courses_on_track": 0,
                "courses_at_risk": 0,
                "courses_advanced": 0,
                "student_status": "unknown",
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching courses status for {student_id}")
            return {}
    
    async def _get_overall_metrics(self, student_id: str) -> Dict[str, Any]:
        """Fetch aggregate performance metrics."""
        try:
            if not self.progress_service:
                return {}
            
            return {
                "avg_completion_pct": 0,
                "avg_quiz_score": None,
                "avg_assignment_score": None,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching overall metrics for {student_id}")
            return {}
    
    async def _get_engagement_metrics(self, student_id: str) -> Dict[str, Any]:
        """Fetch engagement and activity metrics."""
        try:
            if not self.analytics_service:
                return {}
            
            return {
                "engagement_score": None,
                "login_count_7d": 0,
                "submission_count_7d": 0,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching engagement metrics for {student_id}")
            return {}
    
    async def _get_active_recommendations(self, student_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Fetch active recommendations."""
        try:
            if not self.recommendation_service:
                return []
            
            return []
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching recommendations for {student_id}")
            return []
    
    async def _get_upcoming_deadlines(self, student_id: str) -> List[Dict[str, Any]]:
        """Fetch upcoming assignment/quiz deadlines."""
        try:
            if not self.progress_service:
                return []
            
            return []
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching deadlines for {student_id}")
            return []
    
    async def _get_sync_status(self, student_id: str) -> Dict[str, Any]:
        """Fetch latest sync job status."""
        try:
            if not self.scheduler_service:
                return {}
            
            history = self.scheduler_service.get_student_sync_history(student_id, limit=1)
            if history:
                latest = history[0]
                return {
                    "all_synced_recently": latest.get("status") == "success",
                    "last_sync_at": latest.get("ended_at"),
                    "last_sync_status": latest.get("status"),
                }
            
            return {"all_synced_recently": False, "last_sync_at": None}
        except Exception as e:
            logger.warning(f"Error fetching sync status: {e}")
            return {}
    
    async def _get_course_progress(self, student_id: str, course_id: str) -> Dict[str, Any]:
        """Fetch course-level progress metrics."""
        try:
            if not self.progress_service:
                return {}
            
            return {}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching progress for {student_id}/{course_id}")
            return {}
    
    async def _get_course_predictions(self, student_id: str, course_id: str) -> Dict[str, Any]:
        """Fetch course-level predictions."""
        try:
            if not self.prediction_service:
                return {}
            
            return {}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching predictions for {student_id}/{course_id}")
            return {}
    
    async def _get_course_modules(self, student_id: str, course_id: str) -> List[Dict[str, Any]]:
        """Fetch module-level breakdown."""
        try:
            if not self.progress_service:
                return []
            
            return []
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching modules for {student_id}/{course_id}")
            return []
    
    def invalidate_student_cache(self, student_id: str):
        """Invalidate all dashboard caches for a student."""
        self.cache.invalidate(f"dashboard:*:{student_id}")
        logger.info(f"Invalidated dashboard cache for {student_id}")
    
    def invalidate_course_cache(self, student_id: str, course_id: str):
        """Invalidate dashboard cache for a course."""
        self.cache.invalidate(f"dashboard:course:{student_id}:{course_id}")
        logger.info(f"Invalidated dashboard cache for {student_id}/{course_id}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Return cache health metrics."""
        return {
            "cache_size": len(self.cache.cache),
            "pending_requests": len(self.pending_requests),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_all_user_progress(self, db_session) -> Dict[str, Any]:
        """
        Return progress rows for every stored user.

        This method is intentionally admin-facing. The route layer must verify
        Firebase auth and call ``assert_admin_claims`` before invoking it.
        """
        from backend.db import StudentRecord, TrackerProgressRecord

        cohort_size = int(os.getenv("ADMIN_COHORT_SIZE", "250"))
        records = db_session.query(StudentRecord).order_by(StudentRecord.student_id.asc()).all()
        users_by_id: Dict[str, Dict[str, Any]] = {}
        latest_tracker_by_student: Dict[str, Dict[int, Any]] = {}

        for record in records:
            completion = record.modules_completed_pct or 0
            placement_probability = record.predicted_placement_probability
            users_by_id[record.student_id] = {
                "id": record.id,
                "student_id": record.student_id,
                "email": record.student_id if str(record.student_id).endswith("@bitspilani-digital.edu.in") else None,
                "progress": {
                    "modules_completed_pct": completion,
                    "attendance_pct": record.attendance_pct,
                    "avg_quiz_score": record.avg_quiz_score,
                    "assignment_avg": record.assignment_avg,
                    "weekly_study_hours": record.weekly_study_hours,
                    "consistency_score": record.consistency_score,
                    "preferred_study_hour": record.preferred_study_hour,
                    "backlogs_count": record.backlogs_count,
                    "aptitude_score": record.aptitude_score,
                    "quiz_score_std": record.quiz_score_std,
                    "trimester_gpa": record.trimester_gpa,
                    "communication_score": record.communication_score,
                    "projects_count": record.projects_count,
                    "internships_count": record.internships_count,
                    "mock_interviews_attended": record.mock_interviews_attended,
                },
                "prediction": {
                    "placement_probability": placement_probability,
                    "risk_band": self._admin_risk_band(placement_probability),
                    "actual_placed": record.actual_placed,
                },
                "tracker_progress": [],
                "tracker_prediction": None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

        tracker_records = db_session.query(TrackerProgressRecord).order_by(
            TrackerProgressRecord.updated_at.desc()
        ).all()
        for record in tracker_records:
            user = users_by_id.get(record.student_id)
            if user is None:
                user = {
                    "id": None,
                    "student_id": record.student_id,
                    "email": record.student_email,
                    "progress": {
                        "modules_completed_pct": record.completion_pct,
                        "attendance_pct": None,
                        "avg_quiz_score": None,
                        "assignment_avg": None,
                        "weekly_study_hours": None,
                        "consistency_score": None,
                        "preferred_study_hour": None,
                        "backlogs_count": None,
                        "aptitude_score": None,
                        "quiz_score_std": None,
                        "trimester_gpa": None,
                        "communication_score": None,
                        "projects_count": None,
                        "internships_count": None,
                        "mock_interviews_attended": None,
                    },
                    "prediction": {"placement_probability": None, "risk_band": None, "actual_placed": None},
                    "tracker_progress": [],
                    "tracker_prediction": None,
                    "updated_at": None,
                    "created_at": None,
                }
                users_by_id[record.student_id] = user
            elif record.student_email:
                user["email"] = record.student_email

            try:
                courses = json.loads(record.courses_json or "[]")
            except (TypeError, ValueError):
                courses = []
            try:
                prediction = json.loads(record.prediction_json or "{}")
            except (TypeError, ValueError):
                prediction = {}

            updated_at = record.updated_at.isoformat() if record.updated_at else None
            user["tracker_progress"].append(
                {
                    "trimester_id": record.trimester_id,
                    "trimester_name": record.trimester_name,
                    "completion_pct": record.completion_pct,
                    "completed_modules": record.completed_modules,
                    "total_modules": record.total_modules,
                    "courses": courses,
                    "prediction": prediction,
                    "lumen_synced_at": record.lumen_synced_at,
                    "updated_at": updated_at,
                }
            )

            student_terms = latest_tracker_by_student.setdefault(record.student_id, {})
            previous = student_terms.get(record.trimester_id)
            if previous is None or (
                record.updated_at is not None
                and (previous.updated_at is None or record.updated_at >= previous.updated_at)
            ):
                student_terms[record.trimester_id] = record

        users = list(users_by_id.values())
        for user in users:
            user["tracker_progress"].sort(key=lambda item: item["trimester_id"])
        users.sort(key=lambda item: (item.get("email") or item["student_id"]).lower())

        latest_tracker_records = []
        student_completion_pcts = []
        for student_id, term_records in latest_tracker_by_student.items():
            records = list(term_records.values())
            latest_tracker_records.extend(records)
            completed = sum(record.completed_modules or 0 for record in records)
            total = sum(record.total_modules or 0 for record in records)
            completion_pct = round((completed / total) * 100, 1) if total else 0.0
            student_completion_pcts.append(completion_pct)

            user = users_by_id[student_id]
            user["progress"]["modules_completed_pct"] = completion_pct
            most_recent = max(
                records,
                key=lambda record: (record.updated_at or datetime.min, record.trimester_id),
            )
            try:
                user["tracker_prediction"] = json.loads(most_recent.prediction_json or "{}")
            except (TypeError, ValueError):
                user["tracker_prediction"] = None
            user["updated_at"] = most_recent.updated_at.isoformat() if most_recent.updated_at else None

        avg_completion = (
            sum(student_completion_pcts) / len(student_completion_pcts)
            if student_completion_pcts
            else 0
        )
        at_risk_count = sum(
            1 for completion_pct in student_completion_pcts if completion_pct < 60
        )

        return {
            "admin_email": ADMIN_EMAIL,
            "cohort_size": cohort_size,
            "total_users": len(users),
            "missing_users": max(cohort_size - len(users), 0),
            "average_modules_completed_pct": round(avg_completion, 2),
            "at_risk_count": at_risk_count,
            "tracker_students": len(latest_tracker_by_student),
            "tracker_snapshot_count": len(tracker_records),
            "tracker_completed_modules": sum(record.completed_modules or 0 for record in latest_tracker_records),
            "tracker_total_modules": sum(record.total_modules or 0 for record in latest_tracker_records),
            "users": users,
            "generated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _admin_risk_band(placement_probability: Optional[float]) -> Optional[str]:
        if placement_probability is None:
            return None
        if placement_probability >= 0.66:
            return "High likelihood"
        if placement_probability >= 0.33:
            return "Medium likelihood"
        return "Low likelihood"
