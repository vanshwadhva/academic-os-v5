import os
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, UniqueConstraint, func
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./placement.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

engine_options = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

class StudentRecord(Base):
    __tablename__ = "student_records"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True, index=True, nullable=False)

    preferred_study_hour = Column(Integer)
    weekly_study_hours = Column(Float)
    consistency_score = Column(Float)
    attendance_pct = Column(Float)
    backlogs_count = Column(Integer)
    aptitude_score = Column(Float)
    avg_quiz_score = Column(Float)
    quiz_score_std = Column(Float)
    assignment_avg = Column(Float)
    trimester_gpa = Column(Float)
    modules_completed_pct = Column(Float)
    communication_score = Column(Float)
    projects_count = Column(Integer)
    internships_count = Column(Integer)
    mock_interviews_attended = Column(Integer)

    predicted_placement_probability = Column(Float, nullable=True)
    actual_placed = Column(Integer, nullable=True)  # fill in once outcome known -> retraining signal

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TrackerProgressRecord(Base):
    """Latest per-trimester tracker snapshot shared with the verified admin dashboard."""
    __tablename__ = "tracker_progress_records"
    __table_args__ = (
        UniqueConstraint("student_id", "trimester_id", name="uq_tracker_student_trimester"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, index=True, nullable=False)
    student_email = Column(String, nullable=False)
    trimester_id = Column(Integer, nullable=False)
    trimester_name = Column(String, nullable=False)
    total_modules = Column(Integer, nullable=False, default=0)
    completed_modules = Column(Integer, nullable=False, default=0)
    completion_pct = Column(Float, nullable=False, default=0)
    courses_json = Column(Text, nullable=False, default="[]")
    prediction_json = Column(Text, nullable=False, default="{}")
    lumen_synced_at = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
