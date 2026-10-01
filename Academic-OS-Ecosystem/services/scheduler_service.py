"""
Scheduler Service
Manages periodic sync jobs, retry logic, and background task orchestration.

Production considerations:
- Distributed task queue (Redis/Celery pattern)
- Exponential backoff for retries
- Sync job state machine
- Deadlock prevention for concurrent syncs
- Observability and error tracking
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass
import json

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


logger = logging.getLogger(__name__)


class SyncTriggerType(str, Enum):
    """What triggered the sync."""
    LOGIN = "login"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"


class SyncStatus(str, Enum):
    """Sync job lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"  # Some data fetched, some failed
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncErrorCode(str, Enum):
    """Standard sync error classifications."""
    AUTH_INVALID = "auth_invalid"  # Token/session expired
    AUTH_REVOKED = "auth_revoked"  # User disconnected
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    DATABASE_ERROR = "database_error"
    UNKNOWN = "unknown"


@dataclass
class SyncJob:
    """Single sync job record."""
    job_id: str
    student_id: str
    trigger_type: SyncTriggerType
    
    status: SyncStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    # Metrics
    records_fetched: int = 0
    records_saved: int = 0
    records_failed: int = 0
    
    # Error info
    error_code: Optional[SyncErrorCode] = None
    error_message: Optional[str] = None
    
    # Tracking
    correlation_id: str = ""
    attempt_number: int = 1
    max_attempts: int = 3
    retry_after_seconds: int = 60
    
    # Scope
    courses_synced: List[str] = None
    modules_synced: int = 0
    quizzes_synced: int = 0
    assignments_synced: int = 0
    
    def __post_init__(self):
        """Initialize defaults."""
        if self.courses_synced is None:
            self.courses_synced = []
    
    def is_retryable(self) -> bool:
        """Check if job should be retried."""
        if self.status != SyncStatus.FAILED:
            return False
        
        if self.attempt_number >= self.max_attempts:
            return False
        
        # Retryable errors
        retryable_errors = {
            SyncErrorCode.RATE_LIMITED,
            SyncErrorCode.NETWORK_ERROR,
        }
        
        return self.error_code in retryable_errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "job_id": self.job_id,
            "student_id": self.student_id,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "records_fetched": self.records_fetched,
            "records_saved": self.records_saved,
            "records_failed": self.records_failed,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "correlation_id": self.correlation_id,
            "attempt_number": self.attempt_number,
            "courses_synced": self.courses_synced,
            "modules_synced": self.modules_synced,
            "quizzes_synced": self.quizzes_synced,
            "assignments_synced": self.assignments_synced,
        }


@dataclass
class ScheduleConfig:
    """Sync schedule configuration."""
    enabled: bool = True
    sync_interval_minutes: int = 120  # Every 2 hours
    sync_on_login: bool = True
    login_sync_cooldown_minutes: int = 30  # Don't sync again within 30 min of login
    max_concurrent_syncs: int = 10
    max_sync_duration_minutes: int = 15
    retry_backoff_base_seconds: int = 60
    retry_backoff_max_seconds: int = 3600


class SyncJobQueue:
    """In-memory job queue (would use Redis in production)."""
    
    def __init__(self, max_size: int = 1000):
        self.queue = []
        self.max_size = max_size
        self.lock = None  # In production, use distributed lock
    
    def enqueue(self, job: SyncJob) -> bool:
        """Add job to queue."""
        if len(self.queue) >= self.max_size:
            logger.warning(f"Job queue full ({self.max_size}); cannot enqueue {job.job_id}")
            return False
        
        self.queue.append(job)
        logger.info(f"Enqueued sync job {job.job_id} for {job.student_id}")
        return True
    
    def dequeue(self) -> Optional[SyncJob]:
        """Get next job from queue."""
        return self.queue.pop(0) if self.queue else None
    
    def get_job(self, job_id: str) -> Optional[SyncJob]:
        """Retrieve specific job."""
        return next((j for j in self.queue if j.job_id == job_id), None)
    
    def size(self) -> int:
        """Queue length."""
        return len(self.queue)


class SchedulerService:
    """
    Manages sync job scheduling, queuing, and lifecycle.
    
    Responsibilities:
    - Create and track sync jobs
    - Manage job queue
    - Schedule periodic syncs
    - Handle retries with backoff
    - Collect sync metrics
    """
    
    def __init__(
        self,
        schedule_config: Optional[ScheduleConfig] = None,
        sync_callback: Optional[Callable] = None,
    ):
        """
        Initialize scheduler.
        
        Args:
            schedule_config: Sync scheduling parameters
            sync_callback: Async function that performs actual sync
                          (receives SyncJob as argument)
        """
        self.config = schedule_config or ScheduleConfig()
        self.sync_callback = sync_callback
        self.job_queue = SyncJobQueue()
        
        # In-memory tracking of running syncs (would use distributed cache in production)
        self.running_syncs: Dict[str, SyncJob] = {}
        self.completed_syncs: Dict[str, SyncJob] = {}
        self.student_last_login_sync: Dict[str, datetime] = {}
        
        logger.info(f"Scheduler initialized with interval {self.config.sync_interval_minutes}m")
    
    def create_sync_job(
        self,
        student_id: str,
        trigger_type: SyncTriggerType,
    ) -> SyncJob:
        """
        Create and queue a new sync job.
        
        Args:
            student_id: Student to sync
            trigger_type: What triggered this sync
            
        Returns:
            SyncJob object
        """
        job = SyncJob(
            job_id=str(uuid.uuid4()),
            student_id=student_id,
            trigger_type=trigger_type,
            status=SyncStatus.QUEUED,
            correlation_id=self._generate_correlation_id(),
        )
        
        # Check cooldown for login-triggered syncs
        if trigger_type == SyncTriggerType.LOGIN:
            last_sync = self.student_last_login_sync.get(student_id)
            if last_sync and (datetime.utcnow() - last_sync).seconds < self.config.login_sync_cooldown_minutes * 60:
                logger.info(f"Login sync for {student_id} within cooldown; skipping")
                job.status = SyncStatus.CANCELLED
                return job
        
        # Enqueue
        if self.job_queue.enqueue(job):
            logger.info(f"Created sync job {job.job_id} for {student_id} (trigger: {trigger_type.value})")
        else:
            job.status = SyncStatus.FAILED
            job.error_code = SyncErrorCode.UNKNOWN
            job.error_message = "Job queue full"
        
        return job
    
    def get_next_job(self) -> Optional[SyncJob]:
        """
        Get next job ready to run.
        
        Returns:
            Next SyncJob or None if queue empty or limit reached
        """
        if len(self.running_syncs) >= self.config.max_concurrent_syncs:
            logger.debug(f"Max concurrent syncs reached ({len(self.running_syncs)})")
            return None
        
        job = self.job_queue.dequeue()
        if job:
            job.status = SyncStatus.RUNNING
            job.started_at = datetime.utcnow()
            self.running_syncs[job.job_id] = job
            logger.info(f"Started sync job {job.job_id}")
        
        return job
    
    def mark_job_success(self, job_id: str, records_fetched: int, records_saved: int):
        """
        Mark sync job as successfully completed.
        
        Args:
            job_id: Job identifier
            records_fetched: Number of records retrieved from LMS
            records_saved: Number of records persisted
        """
        job = self.running_syncs.pop(job_id, None)
        if not job:
            logger.warning(f"Sync job {job_id} not found in running syncs")
            return
        
        job.status = SyncStatus.SUCCESS
        job.ended_at = datetime.utcnow()
        job.records_fetched = records_fetched
        job.records_saved = records_saved
        
        self.completed_syncs[job_id] = job
        
        # Update login sync cooldown
        if job.trigger_type == SyncTriggerType.LOGIN:
            self.student_last_login_sync[job.student_id] = datetime.utcnow()
        
        logger.info(
            f"Sync job {job_id} completed: "
            f"{records_fetched} fetched, {records_saved} saved"
        )
    
    def mark_job_partial(
        self,
        job_id: str,
        records_fetched: int,
        records_saved: int,
        records_failed: int,
        error_code: SyncErrorCode,
        error_message: str,
    ):
        """
        Mark sync job as partially successful (some data fetched, some failed).
        
        Args:
            job_id: Job identifier
            records_fetched: Records retrieved
            records_saved: Records persisted
            records_failed: Records that failed to process
            error_code: Error classification
            error_message: Human-readable error
        """
        job = self.running_syncs.get(job_id)
        if not job:
            logger.warning(f"Sync job {job_id} not found")
            return
        
        job.status = SyncStatus.PARTIAL
        job.ended_at = datetime.utcnow()
        job.records_fetched = records_fetched
        job.records_saved = records_saved
        job.records_failed = records_failed
        job.error_code = error_code
        job.error_message = error_message
        
        logger.warning(
            f"Sync job {job_id} partial: {error_message} "
            f"({records_fetched} fetched, {records_saved} saved, {records_failed} failed)"
        )
    
    def mark_job_failed(
        self,
        job_id: str,
        error_code: SyncErrorCode,
        error_message: str,
    ):
        """
        Mark sync job as failed.
        
        Args:
            job_id: Job identifier
            error_code: Error classification
            error_message: Human-readable error
        """
        job = self.running_syncs.pop(job_id, None)
        if not job:
            logger.warning(f"Sync job {job_id} not found")
            return
        
        job.status = SyncStatus.FAILED
        job.ended_at = datetime.utcnow()
        job.error_code = error_code
        job.error_message = error_message
        job.attempt_number += 1
        
        # Schedule retry if retryable
        if job.is_retryable():
            retry_delay_seconds = min(
                self.config.retry_backoff_base_seconds * (2 ** (job.attempt_number - 1)),
                self.config.retry_backoff_max_seconds,
            )
            job.retry_after_seconds = retry_delay_seconds
            job.status = SyncStatus.QUEUED  # Re-queue for retry
            
            self.job_queue.enqueue(job)
            logger.info(
                f"Sync job {job_id} queued for retry in {retry_delay_seconds}s "
                f"(attempt {job.attempt_number}/{job.max_attempts})"
            )
        else:
            self.completed_syncs[job_id] = job
            logger.error(
                f"Sync job {job_id} failed permanently: {error_message} "
                f"({job.attempt_number} attempts)"
            )
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a sync job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Dict with job details or None
        """
        # Check running syncs first
        job = self.running_syncs.get(job_id) or self.completed_syncs.get(job_id)
        if job:
            return job.to_dict()
        
        # Check queue
        job = self.job_queue.get_job(job_id)
        if job:
            return job.to_dict()
        
        return None
    
    def get_student_sync_history(
        self,
        student_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get recent sync jobs for a student.
        
        Args:
            student_id: Student identifier
            limit: Number of most recent jobs to return
            
        Returns:
            List of job dicts, sorted by date descending
        """
        student_syncs = [
            j for j in self.completed_syncs.values()
            if j.student_id == student_id
        ]
        
        # Sort by end time descending
        student_syncs = sorted(
            student_syncs,
            key=lambda j: j.ended_at or datetime.min,
            reverse=True,
        )
        
        return [j.to_dict() for j in student_syncs[:limit]]
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get overall scheduler health and queue status.
        
        Returns:
            Dict with queue metrics
        """
        return {
            "queue_size": self.job_queue.size(),
            "running_syncs": len(self.running_syncs),
            "max_concurrent": self.config.max_concurrent_syncs,
            "scheduled_interval_minutes": self.config.sync_interval_minutes,
            "enabled": self.config.enabled,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @staticmethod
    def _generate_correlation_id() -> str:
        """Generate correlation ID for tracing."""
        return f"sync_{uuid.uuid4().hex[:12]}"
    
    def get_sync_metrics(self) -> Dict[str, Any]:
        """
        Aggregate sync metrics across all completed jobs.
        
        Returns:
            Dict with success rate, avg duration, error breakdown
        """
        completed = list(self.completed_syncs.values())
        
        if not completed:
            return {
                "total_syncs": 0,
                "successful_syncs": 0,
                "partial_syncs": 0,
                "failed_syncs": 0,
                "success_rate": 0,
            }
        
        successful = sum(1 for j in completed if j.status == SyncStatus.SUCCESS)
        partial = sum(1 for j in completed if j.status == SyncStatus.PARTIAL)
        failed = sum(1 for j in completed if j.status == SyncStatus.FAILED)
        
        # Average duration
        durations = []
        for job in completed:
            if job.started_at and job.ended_at:
                duration = (job.ended_at - job.started_at).total_seconds()
                durations.append(duration)
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Error breakdown
        error_counts = {}
        for job in completed:
            if job.error_code:
                error_counts[job.error_code.value] = error_counts.get(job.error_code.value, 0) + 1
        
        return {
            "total_syncs": len(completed),
            "successful_syncs": successful,
            "partial_syncs": partial,
            "failed_syncs": failed,
            "success_rate": (successful / len(completed) * 100) if completed else 0,
            "avg_sync_duration_seconds": avg_duration,
            "error_breakdown": error_counts,
        }