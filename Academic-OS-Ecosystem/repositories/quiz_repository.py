from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository


class QuizRepository(BaseRepository):
    """Repository for quizzes and student attempts."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS quizzes (
                quiz_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                quiz_name TEXT,
                instructions TEXT,
                due_at TEXT,
                start_date TEXT,
                end_date TEXT,
                time_limit_minutes INTEGER,
                max_attempts_allowed INTEGER,
                score_max REAL,
                quiz_status TEXT DEFAULT 'active',
                last_synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (quiz_id, course_id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                attempt_id TEXT,
                quiz_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                attempt_number INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                score_obtained REAL,
                score_max REAL,
                percentage REAL,
                started_at TEXT,
                submitted_at TEXT,
                is_late INTEGER DEFAULT 0,
                time_spent_seconds INTEGER,
                last_synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (quiz_id, course_id, student_id, attempt_number)
            )
            """
        )
        self.db.commit()

    def upsert_quiz(self, course_id: str, quiz: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._normalise_quiz_payload(course_id, quiz)
        self._insert_or_update("quizzes", data, ["quiz_id", "course_id"])
        self.db.commit()
        return self.get_quiz(course_id, data["quiz_id"]) or data

    def bulk_upsert_quizzes(self, course_id: str, quizzes: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.upsert_quiz(course_id, quiz) for quiz in quizzes]

    def get_quiz(self, course_id: str, quiz_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            "SELECT * FROM quizzes WHERE course_id = :course_id AND quiz_id = :quiz_id",
            {"course_id": course_id, "quiz_id": quiz_id},
        )

    def list_by_course(self, course_id: str, active_only: bool = False) -> List[Dict[str, Any]]:
        active_clause = "AND quiz_status = 'active'" if active_only else ""
        return self._fetch_all(
            f"""
            SELECT * FROM quizzes
            WHERE course_id = :course_id {active_clause}
            ORDER BY due_at IS NULL, due_at, quiz_name
            """,
            {"course_id": course_id},
        )

    def upsert_attempt(self, course_id: str, quiz_id: str, student_id: str, attempt: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(attempt)
        data["course_id"] = course_id
        data["quiz_id"] = str(data.pop("lms_quiz_id", quiz_id))
        data["student_id"] = str(data.pop("user_id", student_id) or student_id)
        data["attempt_id"] = data.pop("lms_attempt_id", data.get("attempt_id", None))
        data.setdefault("attempt_number", 1)

        if data.get("score_obtained") is not None and data.get("score_max"):
            data.setdefault("percentage", round(float(data["score_obtained"]) / float(data["score_max"]) * 100, 2))

        self._insert_or_update("quiz_attempts", data, ["quiz_id", "course_id", "student_id", "attempt_number"])
        self.db.commit()
        return self.get_attempt(course_id, data["quiz_id"], data["student_id"], int(data["attempt_number"])) or data

    def get_attempt(self, course_id: str, quiz_id: str, student_id: str, attempt_number: int = 1) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            """
            SELECT * FROM quiz_attempts
            WHERE course_id = :course_id
              AND quiz_id = :quiz_id
              AND student_id = :student_id
              AND attempt_number = :attempt_number
            """,
            {
                "course_id": course_id,
                "quiz_id": quiz_id,
                "student_id": student_id,
                "attempt_number": attempt_number,
            },
        )

    def list_student_attempts(self, student_id: str, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        course_clause = "AND a.course_id = :course_id" if course_id else ""
        return self._fetch_all(
            f"""
            SELECT a.*, q.quiz_name, q.due_at
            FROM quiz_attempts a
            LEFT JOIN quizzes q ON q.quiz_id = a.quiz_id AND q.course_id = a.course_id
            WHERE a.student_id = :student_id {course_clause}
            ORDER BY COALESCE(a.submitted_at, q.due_at), q.quiz_name, a.attempt_number
            """,
            {"student_id": student_id, "course_id": course_id},
        )

    def latest_attempts_for_student(self, student_id: str, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        return self._fetch_all(
            f"""
            SELECT *
            FROM quiz_attempts a
            WHERE student_id = :student_id {course_clause}
              AND attempt_number = (
                  SELECT MAX(attempt_number)
                  FROM quiz_attempts b
                  WHERE b.student_id = a.student_id
                    AND b.course_id = a.course_id
                    AND b.quiz_id = a.quiz_id
              )
            ORDER BY submitted_at
            """,
            {"student_id": student_id, "course_id": course_id},
        )

    def average_score(self, student_id: str, course_id: Optional[str] = None) -> Optional[float]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        row = self._fetch_one(
            f"""
            SELECT AVG(percentage) AS average_score
            FROM quiz_attempts
            WHERE student_id = :student_id AND percentage IS NOT NULL {course_clause}
            """,
            {"student_id": student_id, "course_id": course_id},
        )
        return None if not row or row["average_score"] is None else float(row["average_score"])

    def summary(self, student_id: str, course_id: Optional[str] = None) -> Dict[str, Any]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        row = self._fetch_one(
            f"""
            SELECT
                COUNT(*) AS attempts,
                COUNT(DISTINCT quiz_id) AS quizzes_seen,
                SUM(CASE WHEN status IN ('completed', 'submitted', 'late') THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) AS missed,
                SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) AS late,
                AVG(percentage) AS average_score
            FROM quiz_attempts
            WHERE student_id = :student_id {course_clause}
            """,
            {"student_id": student_id, "course_id": course_id},
        )
        return row or {"attempts": 0, "quizzes_seen": 0, "completed": 0, "missed": 0, "late": 0, "average_score": None}

    def _normalise_quiz_payload(self, course_id: str, quiz: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(quiz)
        data["course_id"] = course_id
        data["quiz_id"] = str(data.pop("lms_quiz_id", data.get("quiz_id")))
        if "last_synced_at" not in data and "synced_at" in data:
            data["last_synced_at"] = data.pop("synced_at")
        return data
