from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository


class CourseRepository(BaseRepository):
    """Repository for LMS course metadata and student enrollments."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                course_code TEXT,
                course_name TEXT,
                course_type TEXT,
                description TEXT,
                department TEXT,
                semester TEXT,
                instructor TEXT,
                term_id TEXT,
                section TEXT,
                credits REAL,
                is_active INTEGER DEFAULT 1,
                start_date TEXT,
                end_date TEXT,
                synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS course_enrollments (
                student_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                role TEXT DEFAULT 'student',
                is_active INTEGER DEFAULT 1,
                enrolled_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (student_id, course_id),
                FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE
            )
            """
        )
        self.db.commit()

    def upsert(self, course: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(course)
        data["course_id"] = str(data["course_id"])
        self._insert_or_update("courses", data, ["course_id"])
        self.db.commit()
        return self.get(data["course_id"]) or data

    def bulk_upsert(self, courses: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        saved = [self.upsert(course) for course in courses]
        return saved

    def get(self, course_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM courses WHERE course_id = :course_id", {"course_id": course_id})

    def list(self, active_only: bool = False, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        where = "WHERE is_active = 1" if active_only else ""
        return self._fetch_all(
            f"SELECT * FROM courses {where} ORDER BY course_name, course_id LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset},
        )

    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        pattern = f"%{query}%"
        return self._fetch_all(
            """
            SELECT * FROM courses
            WHERE course_name LIKE :pattern OR course_code LIKE :pattern OR course_id LIKE :pattern
            ORDER BY course_name
            LIMIT :limit
            """,
            {"pattern": pattern, "limit": limit},
        )

    def enroll_student(self, student_id: str, course_id: str, role: str = "student", is_active: bool = True) -> None:
        self._insert_or_update(
            "course_enrollments",
            {
                "student_id": student_id,
                "course_id": course_id,
                "role": role,
                "is_active": int(is_active),
            },
            ["student_id", "course_id"],
        )
        self.db.commit()

    def get_student_courses(self, student_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        active_clause = "AND e.is_active = 1 AND c.is_active = 1" if active_only else ""
        return self._fetch_all(
            f"""
            SELECT c.*, e.role, e.enrolled_at, e.is_active AS enrollment_active
            FROM course_enrollments e
            JOIN courses c ON c.course_id = e.course_id
            WHERE e.student_id = :student_id {active_clause}
            ORDER BY c.course_name, c.course_id
            """,
            {"student_id": student_id},
        )

    def list_course_students(self, course_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        active_clause = "AND is_active = 1" if active_only else ""
        return self._fetch_all(
            f"""
            SELECT * FROM course_enrollments
            WHERE course_id = :course_id {active_clause}
            ORDER BY student_id
            """,
            {"course_id": course_id},
        )

    def delete(self, course_id: str) -> bool:
        deleted = self._delete("courses", "course_id = :course_id", {"course_id": course_id})
        self.db.commit()
        return deleted > 0
