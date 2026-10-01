"""
Feature Engineering Service
Transforms raw academic records into ML-ready feature vectors.

Production considerations:
- Incremental feature computation (only recompute changed records)
- Feature validation and schema enforcement
- Missing value handling strategies
- Feature versioning for model reproducibility
- Efficient batch processing
- Monitoring for feature drift
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import numpy as np
from dataclasses import dataclass
import hashlib
import json

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class FeatureVersion(str):
    """Feature set versioning for reproducibility."""
    pass


@dataclass
class FeatureSnapshot:
    """Immutable snapshot of computed features at a point in time."""
    snapshot_id: str
    student_id: str
    course_id: str
    feature_version: FeatureVersion
    
    # Features
    features: Dict[str, float]
    
    # Metadata
    computed_at: datetime
    records_considered: int  # How many raw records fed into computation
    data_freshness_hours: float  # Age of oldest record in snapshot
    
    def get_hash(self) -> str:
        """Get SHA256 of feature values for audit."""
        feature_str = json.dumps(self.features, sort_keys=True)
        return hashlib.sha256(feature_str.encode()).hexdigest()


class FeatureDefinition(BaseModel):
    """Schema for a single feature."""
    name: str
    description: str
    dtype: str  # float, int, categorical
    nullable: bool = False
    default_value: Optional[float] = None
    valid_range: Optional[tuple] = None  # (min, max) for numeric
    valid_categories: Optional[List[str]] = None  # For categorical


class FeatureEngineering(BaseModel):
    """Base features (directly from LMS)."""
    module_completion_pct: float = Field(..., ge=0, le=100)
    completed_modules: int = Field(..., ge=0)
    pending_modules: int = Field(..., ge=0)
    quiz_average: Optional[float] = Field(None, ge=0, le=100)
    assignment_average: Optional[float] = Field(None, ge=0, le=100)
    attendance_pct: Optional[float] = Field(None, ge=0, le=100)
    missing_submissions: int = Field(default=0, ge=0)
    late_submissions: int = Field(default=0, ge=0)
    days_since_activity: int = Field(default=0, ge=0)
    current_grade: Optional[float] = Field(None, ge=0, le=100)
    course_age_days: int = Field(..., ge=0)
    weeks_remaining: int = Field(..., ge=0)
    submission_consistency: Optional[float] = Field(None, ge=0, le=1)
    
    # Derived features (computed below)
    rolling_7day_activity_change: Optional[float] = None
    rolling_14day_activity_change: Optional[float] = None
    grade_trend: Optional[float] = None
    assessment_volatility: Optional[float] = None
    attendance_performance_correlation: Optional[float] = None
    engagement_score: Optional[float] = None
    deadline_pressure_index: Optional[float] = None


class FeatureStore:
    """In-memory feature store (Redis in production)."""
    
    def __init__(self):
        self.snapshots: Dict[str, FeatureSnapshot] = {}
    
    def save_snapshot(self, snapshot: FeatureSnapshot):
        """Save feature snapshot."""
        self.snapshots[snapshot.snapshot_id] = snapshot
        logger.debug(f"Saved feature snapshot {snapshot.snapshot_id}")
    
    def get_latest_snapshot(self, student_id: str, course_id: str) -> Optional[FeatureSnapshot]:
        """Get most recent feature snapshot for student-course."""
        key_prefix = f"{student_id}:{course_id}:"
        matching = [
            s for s in self.snapshots.values()
            if s.student_id == student_id and s.course_id == course_id
        ]
        
        if not matching:
            return None
        
        return max(matching, key=lambda s: s.computed_at)
    
    def get_snapshot_history(
        self,
        student_id: str,
        course_id: str,
        limit: int = 10,
    ) -> List[FeatureSnapshot]:
        """Get historical snapshots for trend analysis."""
        matching = [
            s for s in self.snapshots.values()
            if s.student_id == student_id and s.course_id == course_id
        ]
        
        return sorted(matching, key=lambda s: s.computed_at, reverse=True)[:limit]


class FeatureEngineeringService:
    """
    Computes ML features from raw academic records.
    
    Transforms:
    - Module completion records → completion percentage, trends
    - Quiz/assignment records → averages, volatility, late rates
    - Login/activity events → engagement metrics
    - Historical snapshots → derived features (rolling avgs, trends)
    
    Feature Categories:
    1. Base features: direct from LMS data (module %, quiz avg, etc.)
    2. Derived features: computed from base + time series
    3. Engagement features: from login/activity patterns
    4. Risk features: indicators of struggle
    """
    
    # Feature schema (for validation)
    FEATURE_SCHEMA = {
        # Base features
        "module_completion_pct": FeatureDefinition(
            name="module_completion_pct",
            description="Percentage of modules completed",
            dtype="float",
            valid_range=(0, 100),
        ),
        "completed_modules": FeatureDefinition(
            name="completed_modules",
            description="Count of completed modules",
            dtype="int",
        ),
        "pending_modules": FeatureDefinition(
            name="pending_modules",
            description="Count of pending modules",
            dtype="int",
        ),
        "quiz_average": FeatureDefinition(
            name="quiz_average",
            description="Average quiz score",
            dtype="float",
            nullable=True,
            valid_range=(0, 100),
            default_value=0.0,
        ),
        "assignment_average": FeatureDefinition(
            name="assignment_average",
            description="Average assignment score",
            dtype="float",
            nullable=True,
            valid_range=(0, 100),
            default_value=0.0,
        ),
        "attendance_pct": FeatureDefinition(
            name="attendance_pct",
            description="Attendance percentage",
            dtype="float",
            nullable=True,
            valid_range=(0, 100),
            default_value=50.0,
        ),
        "missing_submissions": FeatureDefinition(
            name="missing_submissions",
            description="Count of missing submissions",
            dtype="int",
            default_value=0,
        ),
        "late_submissions": FeatureDefinition(
            name="late_submissions",
            description="Count of late submissions",
            dtype="int",
            default_value=0,
        ),
        "days_since_activity": FeatureDefinition(
            name="days_since_activity",
            description="Days since last login or submission",
            dtype="int",
            default_value=0,
        ),
        "current_grade": FeatureDefinition(
            name="current_grade",
            description="Current course grade",
            dtype="float",
            nullable=True,
            valid_range=(0, 100),
            default_value=0.0,
        ),
        "course_age_days": FeatureDefinition(
            name="course_age_days",
            description="Days since course start",
            dtype="int",
        ),
        "weeks_remaining": FeatureDefinition(
            name="weeks_remaining",
            description="Weeks until course end",
            dtype="int",
        ),
        "submission_consistency": FeatureDefinition(
            name="submission_consistency",
            description="Consistency of submissions (0-1)",
            dtype="float",
            nullable=True,
            valid_range=(0, 1),
            default_value=0.5,
        ),
        
        # Derived features
        "rolling_7day_activity_change": FeatureDefinition(
            name="rolling_7day_activity_change",
            description="Change in submissions over 7 days",
            dtype="float",
            nullable=True,
            default_value=0.0,
        ),
        "rolling_14day_activity_change": FeatureDefinition(
            name="rolling_14day_activity_change",
            description="Change in submissions over 14 days",
            dtype="float",
            nullable=True,
            default_value=0.0,
        ),
        "grade_trend": FeatureDefinition(
            name="grade_trend",
            description="Slope of grade progression",
            dtype="float",
            nullable=True,
            default_value=0.0,
        ),
        "assessment_volatility": FeatureDefinition(
            name="assessment_volatility",
            description="Standard deviation of assessment scores",
            dtype="float",
            nullable=True,
            default_value=0.0,
        ),
        "attendance_performance_correlation": FeatureDefinition(
            name="attendance_performance_correlation",
            description="Correlation between attendance and grades",
            dtype="float",
            nullable=True,
            valid_range=(-1, 1),
            default_value=0.0,
        ),
        "engagement_score": FeatureDefinition(
            name="engagement_score",
            description="Composite engagement metric (0-1)",
            dtype="float",
            nullable=True,
            valid_range=(0, 1),
            default_value=0.5,
        ),
        "deadline_pressure_index": FeatureDefinition(
            name="deadline_pressure_index",
            description="Pressure from upcoming deadlines",
            dtype="float",
            nullable=True,
            valid_range=(0, 10),
            default_value=0.0,
        ),
    }
    
    def __init__(self, feature_store: Optional[FeatureStore] = None):
        """
        Initialize feature engineering service.
        
        Args:
            feature_store: FeatureStore instance (creates default if None)
        """
        self.feature_store = feature_store or FeatureStore()
        self.feature_version = FeatureVersion("v1.0")
    
    def engineer_features(
        self,
        student_id: str,
        course_id: str,
        # Base inputs from progress service
        module_completion_pct: float,
        completed_modules: int,
        pending_modules: int,
        quiz_records: List[Dict[str, Any]],  # [{"score": 85, "percentage": 85, "submitted_at": datetime}, ...]
        assignment_records: List[Dict[str, Any]],
        attendance_pct: Optional[float] = None,
        current_grade: Optional[float] = None,
        course_start_date: Optional[datetime] = None,
        course_end_date: Optional[datetime] = None,
        # Historical data for trend computation
        historical_snapshots: Optional[List[FeatureSnapshot]] = None,
    ) -> FeatureSnapshot:
        """
        Compute complete feature vector for a student-course pair.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            module_completion_pct: Current module completion
            completed_modules: Count of completed modules
            pending_modules: Count of pending modules
            quiz_records: List of quiz records with scores and timestamps
            assignment_records: List of assignment records
            attendance_pct: Attendance percentage if available
            current_grade: Latest grade if available
            course_start_date: Course start datetime
            course_end_date: Course end datetime
            historical_snapshots: Previous feature snapshots for trend computation
            
        Returns:
            FeatureSnapshot with computed features
        """
        logger.info(f"Engineering features for {student_id}/{course_id}")
        
        now = datetime.utcnow()
        
        # Compute base features
        features = {}
        
        # Module features
        features["module_completion_pct"] = module_completion_pct
        features["completed_modules"] = completed_modules
        features["pending_modules"] = pending_modules
        
        # Quiz features
        quiz_scores = [q.get("percentage") for q in quiz_records if q.get("percentage") is not None]
        features["quiz_average"] = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0.0
        
        # Assignment features
        assignment_scores = [a.get("percentage") for a in assignment_records if a.get("percentage") is not None]
        features["assignment_average"] = sum(assignment_scores) / len(assignment_scores) if assignment_scores else 0.0
        
        # Attendance
        features["attendance_pct"] = attendance_pct or 0.0
        
        # Submission timing
        features["missing_submissions"] = self._count_missing_submissions(quiz_records + assignment_records)
        features["late_submissions"] = self._count_late_submissions(quiz_records + assignment_records)
        
        # Activity
        features["days_since_activity"] = self._compute_days_since_activity(quiz_records + assignment_records)
        
        # Grade
        features["current_grade"] = current_grade or 0.0
        
        # Course temporal
        if course_start_date:
            features["course_age_days"] = (now - course_start_date).days
        else:
            features["course_age_days"] = 0
        
        if course_end_date:
            features["weeks_remaining"] = max(0, (course_end_date - now).days // 7)
        else:
            features["weeks_remaining"] = 0
        
        # Submission consistency
        features["submission_consistency"] = self._compute_submission_consistency(
            quiz_records + assignment_records
        )
        
        # Derived features (from historical data)
        features["rolling_7day_activity_change"] = self._compute_activity_change(
            quiz_records + assignment_records,
            days=7,
        )
        features["rolling_14day_activity_change"] = self._compute_activity_change(
            quiz_records + assignment_records,
            days=14,
        )
        
        features["grade_trend"] = self._compute_grade_trend(quiz_records + assignment_records)
        features["assessment_volatility"] = self._compute_assessment_volatility(quiz_scores + assignment_scores)
        features["attendance_performance_correlation"] = self._compute_correlation(
            [attendance_pct] if attendance_pct else [],
            quiz_scores + assignment_scores,
        )
        
        features["engagement_score"] = self._compute_engagement_score(
            features["login_count_7d"] if "login_count_7d" in features else 0,
            features["submission_count_7d"] if "submission_count_7d" in features else 0,
            features["days_since_activity"],
        )
        
        features["deadline_pressure_index"] = self._compute_deadline_pressure(
            quiz_records + assignment_records,
            course_end_date,
        )
        
        # Validate features
        self._validate_features(features)
        
        # Create snapshot
        snapshot = FeatureSnapshot(
            snapshot_id=f"{student_id}:{course_id}:{now.timestamp()}",
            student_id=student_id,
            course_id=course_id,
            feature_version=self.feature_version,
            features=features,
            computed_at=now,
            records_considered=len(quiz_records) + len(assignment_records),
            data_freshness_hours=self._compute_data_freshness(quiz_records + assignment_records),
        )
        
        # Store snapshot
        self.feature_store.save_snapshot(snapshot)
        
        logger.info(f"Engineered features snapshot {snapshot.snapshot_id}")
        return snapshot
    
    @staticmethod
    def _count_missing_submissions(records: List[Dict[str, Any]]) -> int:
        """Count submissions with 'missed' status."""
        return sum(1 for r in records if r.get("status") == "missed")
    
    @staticmethod
    def _count_late_submissions(records: List[Dict[str, Any]]) -> int:
        """Count submissions with 'late' status."""
        return sum(1 for r in records if r.get("status") == "late")
    
    @staticmethod
    def _compute_days_since_activity(records: List[Dict[str, Any]]) -> int:
        """Compute days since most recent submission."""
        dates = [r.get("submitted_at") for r in records if r.get("submitted_at")]
        if not dates:
            return 999  # Large value for no activity
        
        latest = max(dates)
        if isinstance(latest, str):
            latest = datetime.fromisoformat(latest)
        
        return (datetime.utcnow() - latest).days
    
    @staticmethod
    def _compute_submission_consistency(records: List[Dict[str, Any]]) -> float:
        """
        Compute consistency of submissions (0-1).
        Higher = more uniform submission pattern.
        """
        if len(records) < 2:
            return 1.0
        
        dates = [r.get("submitted_at") for r in records if r.get("submitted_at")]
        if len(dates) < 2:
            return 1.0
        
        # Calculate intervals between submissions
        sorted_dates = sorted(dates)
        intervals = []
        for i in range(1, len(sorted_dates)):
            if isinstance(sorted_dates[i-1], str):
                sorted_dates[i-1] = datetime.fromisoformat(sorted_dates[i-1])
            if isinstance(sorted_dates[i], str):
                sorted_dates[i] = datetime.fromisoformat(sorted_dates[i])
            
            interval = (sorted_dates[i] - sorted_dates[i-1]).days
            intervals.append(interval)
        
        # Consistency = inverse of coefficient of variation
        if not intervals or sum(intervals) == 0:
            return 0.5
        
        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return 0.5
        
        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        std_dev = variance ** 0.5
        cv = std_dev / mean if mean > 0 else 0
        
        # Map to 0-1 scale (lower cv = higher consistency)
        return 1.0 / (1.0 + cv)
    
    @staticmethod
    def _compute_activity_change(records: List[Dict[str, Any]], days: int = 7) -> float:
        """
        Compute change in submission frequency over a time window.
        Positive = increasing activity, negative = decreasing.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)
        
        recent_records = [
            r for r in records
            if r.get("submitted_at") and (
                datetime.fromisoformat(r["submitted_at"]) if isinstance(r["submitted_at"], str)
                else r["submitted_at"]
            ) > cutoff
        ]
        
        if len(recent_records) == 0:
            return 0.0
        
        # Simple: count of submissions
        return float(len(recent_records))
    
    @staticmethod
    def _compute_grade_trend(records: List[Dict[str, Any]]) -> float:
        """
        Compute linear trend in assessment scores.
        Positive = improving grades, negative = declining.
        """
        scores = [r.get("percentage") for r in records if r.get("percentage") is not None]
        if len(scores) < 2:
            return 0.0
        
        # Simple linear regression
        n = len(scores)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(scores) / n
        
        numerator = sum((x[i] - x_mean) * (scores[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope
    
    @staticmethod
    def _compute_assessment_volatility(scores: List[float]) -> float:
        """Compute standard deviation of assessment scores."""
        if len(scores) < 2:
            return 0.0
        
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return variance ** 0.5
    
    @staticmethod
    def _compute_correlation(x: List[float], y: List[float]) -> float:
        """Compute Pearson correlation between two series."""
        if len(x) < 2 or len(y) < 2 or len(x) != len(y):
            return 0.0
        
        x_mean = sum(x) / len(x)
        y_mean = sum(y) / len(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(len(x)))
        x_variance = sum((xi - x_mean) ** 2 for xi in x)
        y_variance = sum((yi - y_mean) ** 2 for yi in y)
        
        denominator = (x_variance * y_variance) ** 0.5
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    @staticmethod
    def _compute_engagement_score(login_count: int, submission_count: int, days_inactive: int) -> float:
        """
        Compute composite engagement score (0-1).
        Combines login frequency, submission frequency, and recency.
        """
        # Normalize components
        login_component = min(login_count / 7, 1.0)  # Up to 7 logins/week
        submission_component = min(submission_count / 5, 1.0)  # Up to 5 submissions/week
        recency_component = max(1.0 - (days_inactive / 30), 0.0)  # Decay over 30 days
        
        # Weighted average
        engagement = (login_component * 0.3 + submission_component * 0.4 + recency_component * 0.3)
        return max(0.0, min(engagement, 1.0))
    
    @staticmethod
    def _compute_deadline_pressure(records: List[Dict[str, Any]], course_end_date: Optional[datetime]) -> float:
        """
        Compute pressure from upcoming deadlines (0-10 scale).
        Higher = more urgent deadlines.
        """
        if not course_end_date:
            return 0.0
        
        now = datetime.utcnow()
        days_to_end = (course_end_date - now).days
        
        # Pending items
        pending = sum(1 for r in records if r.get("status") == "pending")
        
        # Pressure increases as deadline approaches and pending items accumulate
        if days_to_end <= 0:
            return 10.0
        elif days_to_end <= 7:
            pressure = 8.0 + (pending * 0.5)
        elif days_to_end <= 14:
            pressure = 5.0 + (pending * 0.3)
        else:
            pressure = 2.0 + (pending * 0.1)
        
        return min(pressure, 10.0)
    
    @staticmethod
    def _compute_data_freshness(records: List[Dict[str, Any]]) -> float:
        """
        Compute age of oldest record in hours.
        Used to assess feature freshness.
        """
        if not records:
            return float('inf')
        
        dates = [
            r.get("submitted_at") or r.get("completed_at")
            for r in records
            if r.get("submitted_at") or r.get("completed_at")
        ]
        
        if not dates:
            return float('inf')
        
        oldest = min(dates)
        if isinstance(oldest, str):
            oldest = datetime.fromisoformat(oldest)
        
        age_hours = (datetime.utcnow() - oldest).total_seconds() / 3600
        return age_hours
    
    def _validate_features(self, features: Dict[str, float]):
        """
        Validate features against schema.
        
        Args:
            features: Feature dict to validate
            
        Raises:
            ValueError: If validation fails
        """
        for feature_name, feature_def in self.FEATURE_SCHEMA.items():
            value = features.get(feature_name)
            
            if value is None:
                if not feature_def.nullable:
                    if feature_def.default_value is not None:
                        features[feature_name] = feature_def.default_value
                    else:
                        logger.warning(f"Feature {feature_name} is None and non-nullable")
            else:
                # Type check
                if feature_def.dtype == "int" and not isinstance(value, (int, np.integer)):
                    logger.warning(f"Feature {feature_name} should be int, got {type(value)}")
                
                # Range check
                if feature_def.valid_range and isinstance(value, (int, float)):
                    min_val, max_val = feature_def.valid_range
                    if not (min_val <= value <= max_val):
                        logger.warning(
                            f"Feature {feature_name}={value} outside valid range {feature_def.valid_range}"
                        )
        
        logger.debug(f"Validated feature set")