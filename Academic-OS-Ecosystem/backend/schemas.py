from typing import Optional, List
from pydantic import BaseModel, Field


class StudentFeatures(BaseModel):
    student_id: str
    preferred_study_hour: int = Field(ge=0, le=23)
    weekly_study_hours: float = Field(ge=0, le=80)
    consistency_score: float = Field(ge=0, le=1)
    attendance_pct: float = Field(ge=0, le=100)
    backlogs_count: int = Field(ge=0)
    aptitude_score: float = Field(ge=0, le=100)
    avg_quiz_score: float = Field(ge=0, le=100)
    quiz_score_std: float = Field(ge=0)
    assignment_avg: float = Field(ge=0, le=100)
    trimester_gpa: float = Field(ge=0, le=10)
    modules_completed_pct: float = Field(ge=0, le=100)
    communication_score: float = Field(ge=0, le=100)
    projects_count: int = Field(ge=0)
    internships_count: int = Field(ge=0)
    mock_interviews_attended: int = Field(ge=0)


class TopFactor(BaseModel):
    feature: str
    global_importance: float
    student_value: Optional[float] = None


class PredictionResponse(BaseModel):
    student_id: str
    placement_probability: float
    risk_band: str  # Low / Medium / High likelihood band, named to avoid false certainty
    top_factors: List[TopFactor]
    disclaimer: str = (
        "Model trained on synthetic data with hand-specified correlations. "
        "This is a systems-design exercise, not a validated real-world predictor."
    )


class StoredStudentResponse(StudentFeatures):
    id: int
    predicted_placement_probability: Optional[float]
    actual_placed: Optional[int]

    class Config:
        from_attributes = True


class TrackerModuleSnapshot(BaseModel):
    title: str
    completed: bool = False


class TrackerWeekSnapshot(BaseModel):
    week_label: str
    topic: Optional[str] = None
    case_study: Optional[str] = None
    modules: List[TrackerModuleSnapshot] = Field(default_factory=list)


class TrackerLumenActivitySnapshot(BaseModel):
    kind: str
    title: str
    status: str
    completed: bool = False
    item_id: Optional[str] = None
    score_pct: Optional[float] = None
    updated_at: Optional[str] = None


class TrackerLumenProgressSnapshot(BaseModel):
    completion_pct: float = 0
    lecture_status_available: bool = True
    lectures_viewed: int = 0
    lectures_total: int = 0
    quizzes_completed: int = 0
    quizzes_total: int = 0
    assignments_submitted: int = 0
    assignments_total: int = 0
    activities: List[TrackerLumenActivitySnapshot] = Field(default_factory=list)
    last_synced_at: Optional[str] = None


class TrackerCourseSnapshot(BaseModel):
    course_id: str
    course_name: str
    weeks: List[TrackerWeekSnapshot] = Field(default_factory=list)
    lumen_progress: Optional[TrackerLumenProgressSnapshot] = None


class TrackerProgressUpload(BaseModel):
    trimester_id: int = Field(ge=1, le=6)
    trimester_name: str
    courses: List[TrackerCourseSnapshot] = Field(default_factory=list)
    lumen_synced_at: Optional[str] = None


class TrackerProgressBatchUpload(BaseModel):
    snapshots: List[TrackerProgressUpload] = Field(default_factory=list)
