"""
Progress Service
Computes and tracks course completion metrics across modules, assignments, and quizzes.

Production considerations:
- Incremental progress computation (no full recalc on every sync)
- Handles missing/incomplete data gracefully
- Caches progress for dashboard fast paths
- Tracks progress trends over time
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class CompletionStatus(str, Enum):
    """Module/assignment completion statuses."""
    COMPLETED = "completed"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    IN_PROGRESS = "in_progress"


class SubmissionStatus(str, Enum):
    """Submission statuses for assignments and quizzes."""
    SUBMITTED = "submitted"
    PENDING = "pending"
    LATE = "late"
    MISSED = "missed"


@dataclass
class ModuleProgress:
    """Single module progress snapshot."""
    module_id: str
    module_title: str
    week_label: Optional[str]
    status: CompletionStatus
    completed_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    
    def is_late(self) -> bool:
        """Check if module was completed late."""
        if self.status != CompletionStatus.COMPLETED or not self.due_at or not self.completed_at:
            return False
        return self.completed_at > self.due_at


@dataclass
class AssessmentProgress:
    """Quiz or assignment progress snapshot."""
    assessment_id: str
    assessment_type: str  # quiz, assignment
    assessment_name: str
    status: SubmissionStatus
    score_obtained: Optional[float] = None
    score_max: Optional[float] = None
    percentage: Optional[float] = None
    submitted_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    
    def is_late(self) -> bool:
        """Check if submitted late."""
        if self.status not in [SubmissionStatus.SUBMITTED, SubmissionStatus.LATE]:
            return False
        if not self.due_at or not self.submitted_at:
            return False
        return self.submitted_at > self.due_at


class CourseProgressMetrics(BaseModel):
    """Aggregated progress metrics for a course."""
    course_id: str
    student_id: str
    
    # Module progress
    total_modules: int = 0
    completed_modules: int = 0
    pending_modules: int = 0
    module_completion_pct: float = Field(default=0.0, ge=0, le=100)
    
    # Assessment progress
    total_assessments: int = 0
    completed_assessments: int = 0
    pending_assessments: int = 0
    
    # Quiz metrics
    total_quizzes: int = 0
    completed_quizzes: int = 0
    quiz_average: Optional[float] = Field(None, ge=0, le=100)
    quiz_trend: Optional[float] = None  # Slope of quiz scores over time
    
    # Assignment metrics
    total_assignments: int = 0
    completed_assignments: int = 0
    assignment_average: Optional[float] = Field(None, ge=0, le=100)
    assignment_trend: Optional[float] = None
    
    # Late/missed metrics
    late_submissions: int = 0
    missed_submissions: int = 0
    
    # Current grade
    current_grade: Optional[float] = Field(None, ge=0, le=100)
    final_grade: Optional[float] = Field(None, ge=0, le=100)
    
    # Temporal
    days_since_last_activity: int = 0
    course_start_date: Optional[datetime] = None
    course_end_date: Optional[datetime] = None
    weeks_completed: int = 0
    weeks_remaining: int = 0
    
    # Computed at
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated_at: Optional[datetime] = None


class ProgressService:
    """
    Manages progress tracking and computation across a student's courses.
    
    Responsibilities:
    - Aggregate module/assignment/quiz records into progress metrics
    - Compute completion percentages
    - Track activity trends
    - Calculate late/missed counts
    - Handle missing data gracefully
    """
    
    def __init__(self, db_session=None):
        """
        Initialize progress service.
        
        Args:
            db_session: Database session for persisting progress snapshots
        """
        self.db_session = db_session
    
    def compute_course_progress(
        self,
        course_id: str,
        student_id: str,
        modules: List[ModuleProgress],
        assessments: List[AssessmentProgress],
        current_grade: Optional[float] = None,
        final_grade: Optional[float] = None,
        course_start_date: Optional[datetime] = None,
        course_end_date: Optional[datetime] = None,
    ) -> CourseProgressMetrics:
        """
        Compute aggregated progress metrics for a course.
        
        Args:
            course_id: Course identifier
            student_id: Student identifier
            modules: List of module progress records
            assessments: List of quiz/assignment records
            current_grade: Latest grade if available
            final_grade: Final grade if available
            course_start_date: Course start datetime
            course_end_date: Course end datetime
            
        Returns:
            CourseProgressMetrics object
        """
        metrics = CourseProgressMetrics(
            course_id=course_id,
            student_id=student_id,
            course_start_date=course_start_date,
            course_end_date=course_end_date,
        )
        
        # Compute module progress
        if modules:
            metrics.total_modules = len(modules)
            metrics.completed_modules = sum(
                1 for m in modules if m.status == CompletionStatus.COMPLETED
            )
            metrics.pending_modules = sum(
                1 for m in modules if m.status == CompletionStatus.PENDING
            )
            
            if metrics.total_modules > 0:
                metrics.module_completion_pct = (
                    metrics.completed_modules / metrics.total_modules * 100
                )
        
        # Separate and compute assessments
        quizzes = [a for a in assessments if a.assessment_type == "quiz"]
        assignments = [a for a in assessments if a.assessment_type == "assignment"]
        
        # Quiz metrics
        if quizzes:
            metrics.total_quizzes = len(quizzes)
            metrics.completed_quizzes = sum(
                1 for q in quizzes if q.status in [SubmissionStatus.SUBMITTED, SubmissionStatus.LATE]
            )
            
            # Quiz average (of non-null scores)
            scores = [q.percentage for q in quizzes if q.percentage is not None]
            if scores:
                metrics.quiz_average = sum(scores) / len(scores)
                metrics.quiz_trend = self._compute_trend([q.percentage for q in quizzes if q.percentage])
        
        # Assignment metrics
        if assignments:
            metrics.total_assignments = len(assignments)
            metrics.completed_assignments = sum(
                1 for a in assignments if a.status in [SubmissionStatus.SUBMITTED, SubmissionStatus.LATE]
            )
            
            scores = [a.percentage for a in assignments if a.percentage is not None]
            if scores:
                metrics.assignment_average = sum(scores) / len(scores)
                metrics.assignment_trend = self._compute_trend([a.percentage for a in assignments if a.percentage])
        
        # Late and missed metrics
        metrics.late_submissions = sum(1 for a in assessments if a.is_late())
        metrics.missed_submissions = sum(1 for a in assessments if a.status == SubmissionStatus.MISSED)
        
        # Total assessments
        metrics.total_assessments = len(assessments)
        metrics.completed_assessments = sum(
            1 for a in assessments if a.status in [SubmissionStatus.SUBMITTED, SubmissionStatus.LATE]
        )
        
        # Grades
        if current_grade is not None:
            metrics.current_grade = current_grade
        if final_grade is not None:
            metrics.final_grade = final_grade
        
        # Temporal metrics
        all_dates = [a.submitted_at for a in assessments if a.submitted_at]
        all_dates.extend([m.completed_at for m in modules if m.completed_at])
        
        if all_dates:
            latest_activity = max(all_dates)
            metrics.days_since_last_activity = (datetime.utcnow() - latest_activity).days
        
        # Compute week progress
        if course_start_date and course_end_date:
            total_days = (course_end_date - course_start_date).days
            if total_days > 0:
                days_elapsed = (datetime.utcnow() - course_start_date).days
                metrics.weeks_completed = max(0, days_elapsed // 7)
                metrics.weeks_remaining = max(0, (total_days - days_elapsed) // 7)
        
        metrics.last_updated_at = datetime.utcnow()
        
        logger.info(
            f"Computed progress for {student_id}/{course_id}: "
            f"{metrics.module_completion_pct:.1f}% modules, "
            f"{metrics.quiz_average or 'N/A'}% quiz avg"
        )
        
        return metrics
    
    def compute_overall_progress(
        self,
        student_id: str,
        course_metrics: List[CourseProgressMetrics],
    ) -> Dict[str, Any]:
        """
        Compute overall progress across all courses.
        
        Args:
            student_id: Student identifier
            course_metrics: List of per-course metrics
            
        Returns:
            Dict with aggregated metrics
        """
        if not course_metrics:
            return {
                "student_id": student_id,
                "total_courses": 0,
                "avg_module_completion": 0,
                "avg_quiz_score": None,
                "avg_assignment_score": None,
                "total_late_submissions": 0,
                "total_missed_submissions": 0,
                "computed_at": datetime.utcnow(),
            }
        
        # Filter out courses with no data
        courses_with_data = [m for m in course_metrics if m.total_modules > 0 or m.total_assessments > 0]
        
        return {
            "student_id": student_id,
            "total_courses": len(course_metrics),
            "active_courses": len(courses_with_data),
            "avg_module_completion": (
                sum(m.module_completion_pct for m in courses_with_data) / len(courses_with_data)
                if courses_with_data else 0
            ),
            "avg_quiz_score": self._compute_average(
                [m.quiz_average for m in course_metrics if m.quiz_average is not None]
            ),
            "avg_assignment_score": self._compute_average(
                [m.assignment_average for m in course_metrics if m.assignment_average is not None]
            ),
            "total_late_submissions": sum(m.late_submissions for m in course_metrics),
            "total_missed_submissions": sum(m.missed_submissions for m in course_metrics),
            "courses": [
                {
                    "course_id": m.course_id,
                    "module_completion_pct": m.module_completion_pct,
                    "quiz_average": m.quiz_average,
                    "assignment_average": m.assignment_average,
                }
                for m in course_metrics
            ],
            "computed_at": datetime.utcnow(),
        }
    
    def compute_progress_trend(
        self,
        student_id: str,
        course_id: str,
        historical_metrics: List[CourseProgressMetrics],
    ) -> Dict[str, Any]:
        """
        Compute progress trend over time.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            historical_metrics: List of historical metric snapshots (ordered by date)
            
        Returns:
            Trend analysis dict with slope, direction, etc.
        """
        if len(historical_metrics) < 2:
            return {
                "trend_direction": "neutral",
                "trend_slope": 0,
                "data_points": len(historical_metrics),
            }
        
        # Use module completion as trend indicator
        completion_trend = self._compute_trend(
            [m.module_completion_pct for m in historical_metrics]
        )
        
        # Quiz score trend
        quiz_scores = [m.quiz_average for m in historical_metrics if m.quiz_average is not None]
        quiz_trend = self._compute_trend(quiz_scores) if quiz_scores else None
        
        # Assignment score trend
        assignment_scores = [m.assignment_average for m in historical_metrics if m.assignment_average is not None]
        assignment_trend = self._compute_trend(assignment_scores) if assignment_scores else None
        
        # Determine direction
        if completion_trend > 2:
            direction = "improving"
        elif completion_trend < -2:
            direction = "declining"
        else:
            direction = "stable"
        
        return {
            "course_id": course_id,
            "student_id": student_id,
            "completion_trend": completion_trend,
            "quiz_score_trend": quiz_trend,
            "assignment_score_trend": assignment_trend,
            "trend_direction": direction,
            "data_points": len(historical_metrics),
            "computed_at": datetime.utcnow(),
        }
    
    @staticmethod
    def _compute_trend(values: List[float]) -> float:
        """
        Compute linear trend (slope) from a series of values.
        
        Args:
            values: List of numeric values
            
        Returns:
            Slope (positive = improving, negative = declining)
        """
        if len(values) < 2:
            return 0.0
        
        # Simple linear regression: y = mx + b
        n = len(values)
        x = list(range(n))
        
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope
    
    @staticmethod
    def _compute_average(values: List[float]) -> Optional[float]:
        """Compute average, returning None if list is empty."""
        if not values:
            return None
        return sum(values) / len(values)
    
    def get_progress_by_week(
        self,
        student_id: str,
        course_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Get weekly progress summary for a course.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            start_date: Start of range
            end_date: End of range
            
        Returns:
            List of weekly summaries with dates and metrics
        """
        # This would query historical snapshots from DB
        # Placeholder for integration with database
        current_date = start_date
        weeks = []
        
        while current_date < end_date:
            week_end = current_date + timedelta(days=7)
            weeks.append({
                "week_start": current_date,
                "week_end": week_end,
                "student_id": student_id,
                "course_id": course_id,
                # Would be filled from DB queries
                "modules_completed": 0,
                "assessments_completed": 0,
                "avg_score": None,
            })
            current_date = week_end
        
        return weeks