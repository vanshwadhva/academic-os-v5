from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository


class AssignmentRepository(BaseRepository):
    """Repository for assignments and per-student submissions."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                assignment_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                name TEXT,
                description TEXT,
                due_date TEXT,
                is_hidden INTEGER DEFAULT 0,
                is_dropbox INTEGER DEFAULT 1,
                grade_item_id TEXT,
                max_points REAL,
                allow_submissions INTEGER DEFAULT 1,
                allow_late_submissions INTEGER DEFAULT 0,
                synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (assignment_id, course_id)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS assignment_submissions (
                submission_id TEXT,
                assignment_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                submission_date TEXT,
                feedback_date TEXT,
                is_submitted INTEGER DEFAULT 0,
                is_late INTEGER DEFAULT 0,
                attempt_count INTEGER DEFAULT 0,
                score_obtained REAL,
                score_max REAL,
                percentage REAL,
                status TEXT,
                synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (assignment_id, course_id, student_id)
            )
            """
        )
        self.db.commit()

    def upsert_assignment(self, course_id: str, assignment: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(assignment)
        data["course_id"] = course_id
        data["assignment_id"] = str(data["assignment_id"])
        self._insert_or_update("assignments", data, ["assignment_id", "course_id"])
        self.db.commit()
        return self.get_assignment(course_id, data["assignment_id"]) or data

    def bulk_upsert_assignments(self, course_id: str, assignments: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.upsert_assignment(course_id, assignment) for assignment in assignments]

    def get_assignment(self, course_id: str, assignment_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            "SELECT * FROM assignments WHERE course_id = :course_id AND assignment_id = :assignment_id",
            {"course_id": course_id, "assignment_id": assignment_id},
        )

    def list_by_course(self, course_id: str, include_hidden: bool = False) -> List[Dict[str, Any]]:
        hidden_clause = "" if include_hidden else "AND COALESCE(is_hidden, 0) = 0"
        return self._fetch_all(
            f"""
            SELECT * FROM assignments
            WHERE course_id = :course_id {hidden_clause}
            ORDER BY due_date IS NULL, due_date, name
            """,
            {"course_id": course_id},
        )

    def upsert_submission(self, course_id: str, assignment_id: str, student_id: str, submission: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(submission)
        data["course_id"] = course_id
        data["assignment_id"] = assignment_id
        data["student_id"] = student_id

        if data.get("score_obtained") is not None and data.get("score_max"):
            data.setdefault("percentage", round(float(data["score_obtained"]) / float(data["score_max"]) * 100, 2))
        if not data.get("status"):
            data["status"] = "late" if data.get("is_late") else ("submitted" if data.get("is_submitted") else "pending")

        self._insert_or_update("assignment_submissions", data, ["assignment_id", "course_id", "student_id"])
        self.db.commit()
        return self.get_submission(course_id, assignment_id, student_id) or data

    def get_submission(self, course_id: str, assignment_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            """
            SELECT * FROM assignment_submissions
            WHERE course_id = :course_id AND assignment_id = :assignment_id AND student_id = :student_id
            """,
            {"course_id": course_id, "assignment_id": assignment_id, "student_id": student_id},
        )

    def list_student_submissions(self, student_id: str, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        course_clause = "AND s.course_id = :course_id" if course_id else ""
        params = {"student_id": student_id, "course_id": course_id}
        return self._fetch_all(
            f"""
            SELECT s.*, a.name, a.due_date, a.max_points
            FROM assignment_submissions s
            LEFT JOIN assignments a ON a.assignment_id = s.assignment_id AND a.course_id = s.course_id
            WHERE s.student_id = :student_id {course_clause}
            ORDER BY COALESCE(a.due_date, s.submission_date), a.name
            """,
            params,
        )

    def average_score(self, student_id: str, course_id: Optional[str] = None) -> Optional[float]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        row = self._fetch_one(
            f"""
            SELECT AVG(percentage) AS average_score
            FROM assignment_submissions
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
                COUNT(*) AS total,
                SUM(CASE WHEN status IN ('submitted', 'late') OR is_submitted = 1 THEN 1 ELSE 0 END) AS submitted,
                SUM(CASE WHEN status = 'late' OR is_late = 1 THEN 1 ELSE 0 END) AS late,
                SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) AS missed,
                AVG(percentage) AS average_score
            FROM assignment_submissions
            WHERE student_id = :student_id {course_clause}
            """,
            {"student_id": student_id, "course_id": course_id},
        )
        return row or {"total": 0, "submitted": 0, "late": 0, "missed": 0, "average_score": None}
