from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository


class AttendanceRepository(BaseRepository):
    """Repository for attendance sessions and per-student attendance marks."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_records (
                attendance_id TEXT,
                course_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                session_date TEXT NOT NULL,
                status TEXT NOT NULL,
                minutes_present INTEGER,
                minutes_scheduled INTEGER,
                source TEXT,
                synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (course_id, student_id, session_date)
            )
            """
        )
        self.db.commit()

    def upsert(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        data = self._clean_payload(record)
        data["course_id"] = str(data["course_id"])
        data["student_id"] = str(data["student_id"])
        self._insert_or_update("attendance_records", data, ["course_id", "student_id", "session_date"])
        self.db.commit()
        return self.get(data["course_id"], data["student_id"], data["session_date"]) or data

    def bulk_upsert(self, records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.upsert(record) for record in records]

    def get(self, course_id: str, student_id: str, session_date: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            """
            SELECT * FROM attendance_records
            WHERE course_id = :course_id AND student_id = :student_id AND session_date = :session_date
            """,
            {"course_id": course_id, "student_id": student_id, "session_date": session_date},
        )

    def list_for_student(
        self,
        student_id: str,
        course_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses = ["student_id = :student_id"]
        params: Dict[str, Any] = {"student_id": student_id, "course_id": course_id, "start_date": start_date, "end_date": end_date}
        if course_id:
            clauses.append("course_id = :course_id")
        if start_date:
            clauses.append("session_date >= :start_date")
        if end_date:
            clauses.append("session_date <= :end_date")

        return self._fetch_all(
            f"""
            SELECT * FROM attendance_records
            WHERE {' AND '.join(clauses)}
            ORDER BY session_date
            """,
            params,
        )

    def attendance_percentage(self, student_id: str, course_id: Optional[str] = None) -> Optional[float]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        row = self._fetch_one(
            f"""
            SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN status IN ('present', 'late', 'excused') THEN 1 ELSE 0 END) AS attended_sessions
            FROM attendance_records
            WHERE student_id = :student_id {course_clause}
            """,
            {"student_id": student_id, "course_id": course_id},
        )
        if not row or not row["total_sessions"]:
            return None
        return round(float(row["attended_sessions"] or 0) / float(row["total_sessions"]) * 100, 2)

    def summary(self, student_id: str, course_id: Optional[str] = None) -> Dict[str, Any]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        row = self._fetch_one(
            f"""
            SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) AS late,
                SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) AS absent,
                SUM(CASE WHEN status = 'excused' THEN 1 ELSE 0 END) AS excused
            FROM attendance_records
            WHERE student_id = :student_id {course_clause}
            """,
            {"student_id": student_id, "course_id": course_id},
        )
        if not row:
            return {"total_sessions": 0, "present": 0, "late": 0, "absent": 0, "excused": 0, "attendance_pct": None}
        row["attendance_pct"] = self.attendance_percentage(student_id, course_id)
        return row

    def delete_for_course(self, course_id: str) -> int:
        deleted = self._delete("attendance_records", "course_id = :course_id", {"course_id": course_id})
        self.db.commit()
        return deleted
