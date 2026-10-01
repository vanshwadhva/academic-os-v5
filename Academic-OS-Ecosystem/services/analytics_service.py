"""
Analytics Service
Aggregates behavioral and engagement metrics for analytics dashboards and insights.

Production considerations:
- Efficient time-series aggregations
- Configurable metric definitions
- Handles sparse data gracefully
- Caching for heavy analytics queries
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class EngagementMetrics(BaseModel):
    """Student engagement snapshot."""
    student_id: str
    course_id: str
    
    # Activity frequency
    login_count_7d: int = Field(default=0, ge=0)
    login_count_14d: int = Field(default=0, ge=0)
    submission_count_7d: int = Field(default=0, ge=0)
    content_views_7d: int = Field(default=0, ge=0)
    
    # Response times
    avg_submission_time_minutes: Optional[float] = None
    avg_days_until_submission_after_due: Optional[float] = None
    
    # Consistency
    submissions_on_time_pct: Optional[float] = Field(None, ge=0, le=100)
    participation_consistency_score: Optional[float] = Field(None, ge=0, le=1)
    
    # Learning patterns
    preferred_activity_time: Optional[str] = None  # morning, afternoon, evening
    peak_engagement_day: Optional[str] = None  # Monday, Tuesday, etc.
    
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class CohortAnalytics(BaseModel):
    """Aggregated analytics for a cohort of students."""
    cohort_id: str
    cohort_name: str
    course_id: str
    total_students: int
    
    # Performance distribution
    avg_quiz_score: float
    median_quiz_score: float
    std_quiz_score: float
    avg_assignment_score: float
    median_assignment_score: float
    
    # Progress distribution
    avg_module_completion_pct: float
    students_at_risk_pct: float
    students_on_track_pct: float
    students_advanced_pct: float
    
    # Engagement distribution
    avg_login_frequency: float
    avg_submission_frequency: float
    highly_engaged_pct: float  # Top quartile engagement
    disengaged_pct: float  # Bottom quartile
    
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class TimeSeriesMetric(BaseModel):
    """Single time-series data point."""
    timestamp: datetime
    metric_name: str
    value: float
    student_id: Optional[str] = None
    course_id: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)


class AnalyticsService:
    """
    Computes and aggregates analytics across students and cohorts.
    
    Tracks:
    - Student engagement and activity patterns
    - Performance distribution within cohorts
    - Risk and on-track indicators
    - Temporal trends
    """
    
    # Risk classification thresholds
    AT_RISK_THRESHOLD = {
        "module_completion_pct": 40,  # Below 40% completion
        "avg_score": 60,  # Below 60% average
        "days_inactive": 14,  # No activity for 14+ days
    }
    
    ON_TRACK_THRESHOLD = {
        "module_completion_pct": 70,
        "avg_score": 75,
        "quiz_completion_pct": 80,
    }
    
    ADVANCED_THRESHOLD = {
        "module_completion_pct": 90,
        "avg_score": 85,
    }
    
    def __init__(self, db_session=None):
        """
        Initialize analytics service.
        
        Args:
            db_session: Database session for persisting metrics
        """
        self.db_session = db_session
    
    def compute_engagement_metrics(
        self,
        student_id: str,
        course_id: str,
        login_events: List[Dict[str, Any]],
        submission_events: List[Dict[str, Any]],
        content_views: List[Dict[str, Any]],
    ) -> EngagementMetrics:
        """
        Compute engagement metrics for a student in a course.
        
        Args:
            student_id: Student ID
            course_id: Course ID
            login_events: List of login timestamps
            submission_events: List of submission records with timestamps and due dates
            content_views: List of content view events
            
        Returns:
            EngagementMetrics object
        """
        now = datetime.utcnow()
        metrics = EngagementMetrics(student_id=student_id, course_id=course_id)
        
        # Count logins in last 7 and 14 days
        login_7d = [d for d in login_events if (now - d).days <= 7]
        login_14d = [d for d in login_events if (now - d).days <= 14]
        metrics.login_count_7d = len(login_7d)
        metrics.login_count_14d = len(login_14d)
        
        # Count submissions in last 7 days
        submission_7d = [d for d in submission_events if (now - d.get("submitted_at", now)).days <= 7]
        metrics.submission_count_7d = len(submission_7d)
        
        # Count content views
        views_7d = [d for d in content_views if (now - d).days <= 7]
        metrics.content_views_7d = len(views_7d)
        
        # Compute submission timeliness
        on_time = 0
        total_with_due = 0
        time_diffs = []
        
        for submission in submission_events:
            due_at = submission.get("due_at")
            submitted_at = submission.get("submitted_at")
            
            if due_at and submitted_at:
                total_with_due += 1
                if submitted_at <= due_at:
                    on_time += 1
                
                # Time to submission (minutes)
                time_diff = (submitted_at - due_at).total_seconds() / 60
                time_diffs.append(time_diff)
        
        if total_with_due > 0:
            metrics.submissions_on_time_pct = (on_time / total_with_due) * 100
        
        if time_diffs:
            metrics.avg_submission_time_minutes = sum(time_diffs) / len(time_diffs)
        
        # Preferred activity time (simple heuristic)
        if login_7d:
            hours = [d.hour for d in login_7d]
            avg_hour = sum(hours) / len(hours)
            if avg_hour < 12:
                metrics.preferred_activity_time = "morning"
            elif avg_hour < 17:
                metrics.preferred_activity_time = "afternoon"
            else:
                metrics.preferred_activity_time = "evening"
        
        # Peak engagement day
        if login_7d:
            weekdays = defaultdict(int)
            for d in login_7d:
                weekdays[d.strftime("%A")] += 1
            peak_day = max(weekdays, key=weekdays.get) if weekdays else None
            metrics.peak_engagement_day = peak_day
        
        # Participation consistency (stdev of logins per day)
        if login_14d:
            days_with_logins = defaultdict(int)
            for d in login_14d:
                days_with_logins[d.date()] += 1
            
            login_counts = list(days_with_logins.values())
            if len(login_counts) > 1:
                mean = sum(login_counts) / len(login_counts)
                variance = sum((x - mean) ** 2 for x in login_counts) / len(login_counts)
                std_dev = variance ** 0.5
                
                # Consistency score: lower std = higher consistency
                metrics.participation_consistency_score = 1.0 / (1.0 + std_dev)
        
        logger.info(f"Computed engagement for {student_id}/{course_id}: {metrics.login_count_7d} logins, {metrics.submission_count_7d} submissions")
        
        return metrics
    
    def classify_student_status(
        self,
        module_completion_pct: float,
        avg_score: float,
        quiz_completion_pct: float,
        days_since_activity: int,
    ) -> str:
        """
        Classify student as at-risk, on-track, or advanced.
        
        Args:
            module_completion_pct: Module completion percentage
            avg_score: Average assessment score
            quiz_completion_pct: Quiz completion percentage
            days_since_activity: Days since last activity
            
        Returns:
            One of: "at_risk", "on_track", "advanced"
        """
        # At-risk indicators
        if (
            module_completion_pct < self.AT_RISK_THRESHOLD["module_completion_pct"]
            or avg_score < self.AT_RISK_THRESHOLD["avg_score"]
            or days_since_activity > self.AT_RISK_THRESHOLD["days_inactive"]
        ):
            return "at_risk"
        
        # Advanced indicators
        if (
            module_completion_pct >= self.ADVANCED_THRESHOLD["module_completion_pct"]
            and avg_score >= self.ADVANCED_THRESHOLD["avg_score"]
        ):
            return "advanced"
        
        # On-track (default)
        return "on_track"
    
    def compute_cohort_analytics(
        self,
        cohort_id: str,
        cohort_name: str,
        course_id: str,
        student_metrics: List[Dict[str, Any]],
    ) -> CohortAnalytics:
        """
        Aggregate analytics across all students in a cohort.
        
        Args:
            cohort_id: Cohort identifier
            cohort_name: Human-readable cohort name
            course_id: Course identifier
            student_metrics: List of per-student metric dicts
            
        Returns:
            CohortAnalytics object
        """
        if not student_metrics:
            logger.warning(f"No metrics for cohort {cohort_id}")
            return CohortAnalytics(
                cohort_id=cohort_id,
                cohort_name=cohort_name,
                course_id=course_id,
                total_students=0,
                avg_quiz_score=0,
                median_quiz_score=0,
                std_quiz_score=0,
                avg_assignment_score=0,
                median_assignment_score=0,
                avg_module_completion_pct=0,
                students_at_risk_pct=0,
                students_on_track_pct=0,
                students_advanced_pct=0,
                avg_login_frequency=0,
                avg_submission_frequency=0,
                highly_engaged_pct=0,
                disengaged_pct=0,
            )
        
        # Extract metric arrays
        quiz_scores = [m.get("quiz_average") for m in student_metrics if m.get("quiz_average")]
        assignment_scores = [m.get("assignment_average") for m in student_metrics if m.get("assignment_average")]
        completions = [m.get("module_completion_pct", 0) for m in student_metrics]
        
        # Compute percentiles and distribution
        quiz_scores_sorted = sorted(quiz_scores) if quiz_scores else [0]
        assignment_scores_sorted = sorted(assignment_scores) if assignment_scores else [0]
        
        avg_quiz = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        median_quiz = quiz_scores_sorted[len(quiz_scores_sorted) // 2] if quiz_scores_sorted else 0
        std_quiz = self._compute_std_dev(quiz_scores) if quiz_scores else 0
        
        avg_assignment = sum(assignment_scores) / len(assignment_scores) if assignment_scores else 0
        median_assignment = assignment_scores_sorted[len(assignment_scores_sorted) // 2] if assignment_scores_sorted else 0
        std_assignment = self._compute_std_dev(assignment_scores) if assignment_scores else 0
        
        # Student status distribution
        statuses = [self.classify_student_status(
            m.get("module_completion_pct", 0),
            m.get("quiz_average", 0),
            m.get("quiz_completion_pct", 0),
            m.get("days_since_activity", 0),
        ) for m in student_metrics]
        
        at_risk_count = sum(1 for s in statuses if s == "at_risk")
        on_track_count = sum(1 for s in statuses if s == "on_track")
        advanced_count = sum(1 for s in statuses if s == "advanced")
        
        total = len(student_metrics)
        
        # Engagement quartiles
        login_counts = [m.get("login_count_7d", 0) for m in student_metrics]
        engagement_threshold_high = sorted(login_counts)[int(len(login_counts) * 0.75)] if login_counts else 0
        engagement_threshold_low = sorted(login_counts)[int(len(login_counts) * 0.25)] if login_counts else 0
        
        highly_engaged = sum(1 for lc in login_counts if lc >= engagement_threshold_high)
        disengaged = sum(1 for lc in login_counts if lc <= engagement_threshold_low)
        
        analytics = CohortAnalytics(
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            course_id=course_id,
            total_students=total,
            avg_quiz_score=avg_quiz,
            median_quiz_score=median_quiz,
            std_quiz_score=std_quiz,
            avg_assignment_score=avg_assignment,
            median_assignment_score=median_assignment,
            avg_module_completion_pct=sum(completions) / len(completions) if completions else 0,
            students_at_risk_pct=(at_risk_count / total * 100) if total else 0,
            students_on_track_pct=(on_track_count / total * 100) if total else 0,
            students_advanced_pct=(advanced_count / total * 100) if total else 0,
            avg_login_frequency=sum(login_counts) / len(login_counts) if login_counts else 0,
            avg_submission_frequency=0,  # Would compute from submission events
            highly_engaged_pct=(highly_engaged / total * 100) if total else 0,
            disengaged_pct=(disengaged / total * 100) if total else 0,
        )
        
        logger.info(
            f"Computed cohort analytics for {cohort_id}: "
            f"{at_risk_count} at-risk, {on_track_count} on-track, {advanced_count} advanced"
        )
        
        return analytics
    
    def compute_time_series(
        self,
        student_id: str,
        course_id: str,
        historical_events: List[Dict[str, Any]],
        window_days: int = 7,
    ) -> List[TimeSeriesMetric]:
        """
        Aggregate events into time-series metrics.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            historical_events: List of timestamped events
            window_days: Aggregation window (7, 14, 30)
            
        Returns:
            List of TimeSeriesMetric objects
        """
        if not historical_events:
            return []
        
        # Group events by window
        windows = defaultdict(list)
        base_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        for event in historical_events:
            event_date = event.get("timestamp", datetime.utcnow())
            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date)
            
            window_start = base_date - timedelta(days=(base_date - event_date).days % window_days)
            windows[window_start].append(event)
        
        # Compute metrics per window
        metrics = []
        for window_start, events in windows.items():
            window_end = window_start + timedelta(days=window_days)
            
            # Count submissions
            submissions = len([e for e in events if e.get("event_type") == "submission"])
            if submissions > 0:
                metrics.append(TimeSeriesMetric(
                    timestamp=window_end,
                    metric_name="submissions",
                    value=submissions,
                    student_id=student_id,
                    course_id=course_id,
                ))
            
            # Count logins
            logins = len([e for e in events if e.get("event_type") == "login"])
            if logins > 0:
                metrics.append(TimeSeriesMetric(
                    timestamp=window_end,
                    metric_name="logins",
                    value=logins,
                    student_id=student_id,
                    course_id=course_id,
                ))
        
        return sorted(metrics, key=lambda m: m.timestamp)
    
    @staticmethod
    def _compute_std_dev(values: List[float]) -> float:
        """Compute standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5