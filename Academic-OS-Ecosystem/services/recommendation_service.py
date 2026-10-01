"""
Recommendation Service
Generates actionable recommendations based on predictions, progress, and engagement analytics.

Production considerations:
- Rules-based recommendations with fallback
- Personalization based on student profile
- Ranking by impact and urgency
- A/B testing framework for recommendation efficacy
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class RecommendationPriority(str, Enum):
    """Recommendation priority levels."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # This week
    MEDIUM = "medium"  # This month
    LOW = "low"  # Nice to have


class RecommendationType(str, Enum):
    """Categories of recommendations."""
    STUDY_STRATEGY = "study_strategy"
    TIME_MANAGEMENT = "time_management"
    CONTENT_REVIEW = "content_review"
    SUBMISSION_REMINDER = "submission_reminder"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    ENGAGEMENT_BOOST = "engagement_boost"


class Recommendation(BaseModel):
    """Single actionable recommendation."""
    recommendation_id: str
    student_id: str
    course_id: str
    
    recommendation_type: RecommendationType
    title: str
    description: str
    action_items: List[str] = Field(default_factory=list)
    
    priority: RecommendationPriority
    urgency_days: int = Field(..., ge=1, description="Days until action becomes critical")
    
    # Reasoning
    trigger_metric: str  # e.g., "low_quiz_average", "high_days_inactive"
    trigger_value: float
    threshold_value: float
    
    # Personalization
    confidence_score: float = Field(..., ge=0, le=1)
    student_segment: Optional[str] = None  # e.g., "low_engagement", "high_performer"
    
    # Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    dismissed_at: Optional[datetime] = None


class StudyPlanRecommendation(Recommendation):
    """Recommendation with a structured study plan."""
    suggested_study_hours_per_day: float = Field(..., ge=0.5, le=8)
    focus_areas: List[str] = Field(default_factory=list)
    preferred_study_times: List[str] = Field(default_factory=list)  # e.g., ["7am-9am", "7pm-9pm"]


class RecommendationService:
    """
    Generates personalized recommendations for students.
    
    Strategies:
    - Rules-based triggers from metrics
    - Peer comparison insights
    - Deadline pressure modeling
    - Personalization by learning profile
    """
    
    # Thresholds for triggering recommendations
    TRIGGERS = {
        "low_quiz_average": 65.0,  # Average < 65%
        "low_assignment_average": 70.0,
        "high_days_inactive": 7,  # No activity for 7+ days
        "low_module_completion": 40.0,  # < 40% of modules done
        "high_late_submissions": 3,  # 3+ late submissions
        "low_attendance": 80.0,  # Attendance < 80%
        "high_risk_prediction": 0.7,  # Risk score > 0.7
        "low_completion_prediction": 0.4,  # Predicted completion < 40%
        "low_expected_grade": 2.0,  # Expected grade < B (using numeric scale)
    }
    
    # Study hours recommendation by risk level
    STUDY_HOURS_BY_RISK = {
        "at_risk": 4.0,
        "on_track": 2.5,
        "advanced": 1.5,
    }
    
    def __init__(self, db_session=None):
        """Initialize recommendation service."""
        self.db_session = db_session
    
    def generate_recommendations(
        self,
        student_id: str,
        course_id: str,
        progress_metrics: Dict[str, Any],
        engagement_metrics: Dict[str, Any],
        predictions: Dict[str, Any],
        student_status: str,  # "at_risk", "on_track", "advanced"
    ) -> List[Recommendation]:
        """
        Generate all applicable recommendations for a student-course pair.
        
        Args:
            student_id: Student identifier
            course_id: Course identifier
            progress_metrics: CourseProgressMetrics dict
            engagement_metrics: EngagementMetrics dict
            predictions: Prediction outputs (expected_grade, completion, risk)
            student_status: Classification of student status
            
        Returns:
            List of Recommendation objects, sorted by priority
        """
        recommendations = []
        
        # Check each trigger condition
        
        # 1. Low quiz average
        quiz_avg = progress_metrics.get("quiz_average")
        if quiz_avg and quiz_avg < self.TRIGGERS["low_quiz_average"]:
            recommendations.append(self._create_quiz_improvement_recommendation(
                student_id, course_id, quiz_avg, student_status
            ))
        
        # 2. High days inactive
        days_inactive = progress_metrics.get("days_since_last_activity", 0)
        if days_inactive > self.TRIGGERS["high_days_inactive"]:
            recommendations.append(self._create_engagement_recommendation(
                student_id, course_id, days_inactive
            ))
        
        # 3. Low module completion
        completion_pct = progress_metrics.get("module_completion_pct", 0)
        if completion_pct < self.TRIGGERS["low_module_completion"]:
            recommendations.append(self._create_catch_up_recommendation(
                student_id, course_id, completion_pct
            ))
        
        # 4. High late submissions
        late_submissions = progress_metrics.get("late_submissions", 0)
        if late_submissions > self.TRIGGERS["high_late_submissions"]:
            recommendations.append(self._create_time_management_recommendation(
                student_id, course_id, late_submissions
            ))
        
        # 5. High risk prediction
        risk_pred = predictions.get("risk", {})
        risk_value = risk_pred.get("raw_score", 0)
        if risk_value > self.TRIGGERS["high_risk_prediction"]:
            recommendations.append(self._create_intervention_recommendation(
                student_id, course_id, risk_value, predictions
            ))
        
        # 6. Low completion prediction
        completion_pred = predictions.get("completion", {})
        completion_value = completion_pred.get("raw_score", 1.0)
        if completion_value < self.TRIGGERS["low_completion_prediction"]:
            recommendations.append(self._create_completion_focus_recommendation(
                student_id, course_id, completion_value
            ))
        
        # 7. Low expected grade (advanced only if already doing well)
        grade_pred = predictions.get("expected_grade", {})
        grade_confidence = grade_pred.get("confidence_score", 0)
        if student_status != "advanced" and grade_confidence > 0.6:
            recommendations.append(self._create_grade_improvement_recommendation(
                student_id, course_id, grade_pred, student_status
            ))
        
        # 8. Low engagement (logins)
        login_7d = engagement_metrics.get("login_count_7d", 0)
        if login_7d < 2 and student_status == "at_risk":
            recommendations.append(self._create_engagement_reminder(
                student_id, course_id, login_7d
            ))
        
        # Sort by priority and deadline
        recommendations = sorted(
            recommendations,
            key=lambda r: (
                self._priority_order(r.priority),
                r.urgency_days,
            )
        )
        
        logger.info(f"Generated {len(recommendations)} recommendations for {student_id}/{course_id}")
        
        return recommendations
    
    def _create_quiz_improvement_recommendation(
        self,
        student_id: str,
        course_id: str,
        quiz_avg: float,
        student_status: str,
    ) -> Recommendation:
        """Recommend quiz-focused study strategy."""
        return Recommendation(
            recommendation_id=f"quiz_improve_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.STUDY_STRATEGY,
            title="Strengthen Quiz Performance",
            description=f"Your current quiz average is {quiz_avg:.1f}%. Focused review of quiz-heavy topics can improve your grade by 5-10%.",
            action_items=[
                "Review quiz feedback and identify weak topic areas",
                "Practice with past quiz questions",
                "Schedule 30 min daily practice sessions starting this week",
            ],
            priority=RecommendationPriority.HIGH if student_status == "at_risk" else RecommendationPriority.MEDIUM,
            urgency_days=7,
            trigger_metric="quiz_average",
            trigger_value=quiz_avg,
            threshold_value=self.TRIGGERS["low_quiz_average"],
            confidence_score=0.85,
            student_segment=student_status,
        )
    
    def _create_engagement_recommendation(
        self,
        student_id: str,
        course_id: str,
        days_inactive: int,
    ) -> Recommendation:
        """Recommend re-engagement."""
        return Recommendation(
            recommendation_id=f"engage_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.ENGAGEMENT_BOOST,
            title="Get Back on Track",
            description=f"You haven't logged in for {days_inactive} days. Getting back engaged now will help you catch up on coursework.",
            action_items=[
                "Log in and review recent announcements",
                "Check due dates for upcoming assignments",
                "Schedule regular study sessions",
            ],
            priority=RecommendationPriority.CRITICAL if days_inactive > 14 else RecommendationPriority.HIGH,
            urgency_days=3,
            trigger_metric="days_since_activity",
            trigger_value=days_inactive,
            threshold_value=self.TRIGGERS["high_days_inactive"],
            confidence_score=0.9,
        )
    
    def _create_catch_up_recommendation(
        self,
        student_id: str,
        course_id: str,
        completion_pct: float,
    ) -> Recommendation:
        """Recommend catching up on modules."""
        return Recommendation(
            recommendation_id=f"catchup_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.CONTENT_REVIEW,
            title="Complete Pending Modules",
            description=f"You've completed {completion_pct:.0f}% of course modules. Prioritize completing pending modules to stay on schedule.",
            action_items=[
                "List all incomplete modules",
                "Estimate time needed for each",
                "Create a completion schedule",
                "Aim to complete 1-2 modules per week",
            ],
            priority=RecommendationPriority.CRITICAL if completion_pct < 20 else RecommendationPriority.HIGH,
            urgency_days=7,
            trigger_metric="module_completion_pct",
            trigger_value=completion_pct,
            threshold_value=self.TRIGGERS["low_module_completion"],
            confidence_score=0.95,
        )
    
    def _create_time_management_recommendation(
        self,
        student_id: str,
        course_id: str,
        late_submissions: int,
    ) -> Recommendation:
        """Recommend time management improvements."""
        return Recommendation(
            recommendation_id=f"timemgt_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.TIME_MANAGEMENT,
            title="Improve Time Management",
            description=f"You have {late_submissions} late submissions. Better planning can reduce stress and penalties.",
            action_items=[
                "Create a calendar of all due dates",
                "Set reminders 3 days before each deadline",
                "Start assignments earlier (aim for 2-3 days ahead)",
                "Break large assignments into smaller milestones",
            ],
            priority=RecommendationPriority.HIGH,
            urgency_days=5,
            trigger_metric="late_submissions",
            trigger_value=late_submissions,
            threshold_value=self.TRIGGERS["high_late_submissions"],
            confidence_score=0.88,
        )
    
    def _create_intervention_recommendation(
        self,
        student_id: str,
        course_id: str,
        risk_score: float,
        predictions: Dict[str, Any],
    ) -> Recommendation:
        """Create urgent intervention recommendation."""
        grade_pred = predictions.get("expected_grade", {})
        expected_grade = grade_pred.get("prediction_value", "TBD")
        
        return Recommendation(
            recommendation_id=f"intervention_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.PERFORMANCE_IMPROVEMENT,
            title="Course at Risk",
            description=f"Based on current performance, your expected grade is {expected_grade}. Immediate action can improve your outcome.",
            action_items=[
                "Meet with instructor during office hours",
                "Request tutoring if available",
                "Focus on highest-point remaining assignments",
                "Consider dropping other commitments to prioritize this course",
            ],
            priority=RecommendationPriority.CRITICAL,
            urgency_days=1,
            trigger_metric="risk_score",
            trigger_value=risk_score,
            threshold_value=self.TRIGGERS["high_risk_prediction"],
            confidence_score=0.8,
            student_segment="at_risk",
        )
    
    def _create_completion_focus_recommendation(
        self,
        student_id: str,
        course_id: str,
        completion_prob: float,
    ) -> Recommendation:
        """Recommend focusing on course completion."""
        return Recommendation(
            recommendation_id=f"completion_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.SUBMISSION_REMINDER,
            title="Focus on Course Completion",
            description=f"Your predicted completion probability is {completion_prob:.0%}. Prioritize required coursework to ensure completion.",
            action_items=[
                "List all required submissions remaining",
                "Prioritize mandatory vs. optional work",
                "Submit at least one piece of work this week",
            ],
            priority=RecommendationPriority.HIGH,
            urgency_days=5,
            trigger_metric="completion_probability",
            trigger_value=completion_prob,
            threshold_value=self.TRIGGERS["low_completion_prediction"],
            confidence_score=0.75,
        )
    
    def _create_grade_improvement_recommendation(
        self,
        student_id: str,
        course_id: str,
        grade_pred: Dict[str, Any],
        student_status: str,
    ) -> Recommendation:
        """Recommend grade improvement strategies."""
        expected_grade = grade_pred.get("prediction_value", "TBD")
        
        return Recommendation(
            recommendation_id=f"grade_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.PERFORMANCE_IMPROVEMENT,
            title=f"Improve Grade from {expected_grade}",
            description=f"With targeted effort, you could raise your expected grade. Focus on high-value remaining work.",
            action_items=[
                "Calculate points needed for target grade",
                "Identify assignments worth most points",
                "Dedicate extra effort to remaining high-value work",
            ],
            priority=RecommendationPriority.MEDIUM,
            urgency_days=10,
            trigger_metric="expected_grade",
            trigger_value=2.0,  # Numeric representation of letter grade
            threshold_value=self.TRIGGERS["low_expected_grade"],
            confidence_score=0.7,
            student_segment=student_status,
        )
    
    def _create_engagement_reminder(
        self,
        student_id: str,
        course_id: str,
        login_count: int,
    ) -> Recommendation:
        """Create engagement reminder for disengaged at-risk students."""
        return Recommendation(
            recommendation_id=f"engage_reminder_{student_id}_{course_id}_{int(datetime.utcnow().timestamp())}",
            student_id=student_id,
            course_id=course_id,
            recommendation_type=RecommendationType.ENGAGEMENT_BOOST,
            title="Course Needs Your Attention",
            description="Low engagement combined with low performance suggests you may need to reprioritize this course.",
            action_items=[
                "Log in to the course today",
                "Review the syllabus and schedule",
                "Check what you've missed this week",
                "Set a recurring weekly check-in time",
            ],
            priority=RecommendationPriority.CRITICAL,
            urgency_days=1,
            trigger_metric="login_count_7d",
            trigger_value=login_count,
            threshold_value=2,
            confidence_score=0.85,
        )
    
    @staticmethod
    def _priority_order(priority: RecommendationPriority) -> int:
        """Convert priority to sort order."""
        return {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }.get(priority, 4)
    
    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        """
        Mark a recommendation as dismissed by student.
        
        Args:
            recommendation_id: ID of recommendation to dismiss
            
        Returns:
            True if successful
        """
        logger.info(f"Recommendation {recommendation_id} dismissed by student")
        # Would update DB here
        return True
    
    def get_active_recommendations(
        self,
        student_id: str,
        course_id: Optional[str] = None,
    ) -> List[Recommendation]:
        """
        Retrieve active recommendations for a student.
        
        Args:
            student_id: Student identifier
            course_id: Optional course filter
            
        Returns:
            List of active recommendations
        """
        # Would query from DB
        return []