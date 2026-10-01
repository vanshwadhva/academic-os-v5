from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository


class ProgressRepository(BaseRepository):
    """Repository for computed progress snapshots."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS progress_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                total_modules INTEGER DEFAULT 0,
                completed_modules INTEGER DEFAULT 0,
                pending_modules INTEGER DEFAULT 0,
                module_completion_pct REAL DEFAULT 0,
                total_assessments INTEGER DEFAULT 0,
                completed_assessments INTEGER DEFAULT 0,
                pending_assessments INTEGER DEFAULT 0,
                total_quizzes INTEGER DEFAULT 0,
                completed_quizzes INTEGER DEFAULT 0,
                quiz_average REAL,
                quiz_trend REAL,
                total_assignments INTEGER DEFAULT 0,
                completed_assignments INTEGER DEFAULT 0,
                assignment_average REAL,
                assignment_trend REAL,
                late_submissions INTEGER DEFAULT 0,
                missed_submissions INTEGER DEFAULT 0,
                current_grade REAL,
                final_grade REAL,
                days_since_last_activity INTEGER DEFAULT 0,
                course_start_date TEXT,
                course_end_date TEXT,
                weeks_completed INTEGER DEFAULT 0,
                weeks_remaining INTEGER DEFAULT 0,
                payload_json TEXT,
                computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._execute(
            "CREATE INDEX IF NOT EXISTS idx_progress_student_course ON progress_snapshots(student_id, course_id, computed_at)"
        )
        self.db.commit()

    def save_snapshot(self, metrics: Mapping[str, Any] | Any) -> Dict[str, Any]:
        data = self._serialise_metrics(metrics)
        data["payload_json"] = json.dumps(data, sort_keys=True, default=str)
        table_columns = self._table_columns("progress_snapshots")
        data = {key: value for key, value in data.items() if key in table_columns}

        columns = list(data.keys())
        placeholders = ", ".join(f":{column}" for column in columns)
        self._execute(
            f"INSERT INTO progress_snapshots ({', '.join(columns)}) VALUES ({placeholders})",
            data,
        )
        self.db.commit()
        return self.latest(data["student_id"], data["course_id"]) or data

    def bulk_save(self, metrics_rows: Iterable[Mapping[str, Any] | Any]) -> List[Dict[str, Any]]:
        return [self.save_snapshot(metrics) for metrics in metrics_rows]

    def latest(self, student_id: str, course_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        return self._fetch_one(
            f"""
            SELECT * FROM progress_snapshots
            WHERE student_id = :student_id {course_clause}
            ORDER BY datetime(COALESCE(computed_at, created_at)) DESC, id DESC
            LIMIT 1
            """,
            {"student_id": student_id, "course_id": course_id},
        )

    def history(self, student_id: str, course_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        course_clause = "AND course_id = :course_id" if course_id else ""
        return self._fetch_all(
            f"""
            SELECT * FROM progress_snapshots
            WHERE student_id = :student_id {course_clause}
            ORDER BY datetime(COALESCE(computed_at, created_at)) DESC, id DESC
            LIMIT :limit
            """,
            {"student_id": student_id, "course_id": course_id, "limit": limit},
        )

    def latest_by_course(self, student_id: str) -> List[Dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT p.*
            FROM progress_snapshots p
            JOIN (
                SELECT course_id, MAX(id) AS latest_id
                FROM progress_snapshots
                WHERE student_id = :student_id
                GROUP BY course_id
            ) latest ON latest.latest_id = p.id
            ORDER BY p.course_id
            """,
            {"student_id": student_id},
        )

    def overall_summary(self, student_id: str) -> Dict[str, Any]:
        rows = self.latest_by_course(student_id)
        if not rows:
            return {
                "student_id": student_id,
                "total_courses": 0,
                "avg_module_completion": 0,
                "avg_quiz_score": None,
                "avg_assignment_score": None,
                "total_late_submissions": 0,
                "total_missed_submissions": 0,
            }

        quiz_scores = [row["quiz_average"] for row in rows if row.get("quiz_average") is not None]
        assignment_scores = [row["assignment_average"] for row in rows if row.get("assignment_average") is not None]
        return {
            "student_id": student_id,
            "total_courses": len(rows),
            "active_courses": sum(1 for row in rows if (row.get("total_modules") or row.get("total_assessments"))),
            "avg_module_completion": sum(float(row.get("module_completion_pct") or 0) for row in rows) / len(rows),
            "avg_quiz_score": sum(quiz_scores) / len(quiz_scores) if quiz_scores else None,
            "avg_assignment_score": sum(assignment_scores) / len(assignment_scores) if assignment_scores else None,
            "total_late_submissions": sum(int(row.get("late_submissions") or 0) for row in rows),
            "total_missed_submissions": sum(int(row.get("missed_submissions") or 0) for row in rows),
            "courses": rows,
        }

    def delete_history(self, student_id: str, course_id: Optional[str] = None) -> int:
        if course_id:
            deleted = self._delete(
                "progress_snapshots",
                "student_id = :student_id AND course_id = :course_id",
                {"student_id": student_id, "course_id": course_id},
            )
        else:
            deleted = self._delete("progress_snapshots", "student_id = :student_id", {"student_id": student_id})
        self.db.commit()
        return deleted

    def _serialise_metrics(self, metrics: Mapping[str, Any] | Any) -> Dict[str, Any]:
        if hasattr(metrics, "model_dump"):
            raw = metrics.model_dump()
        elif hasattr(metrics, "dict"):
            raw = metrics.dict()
        else:
            raw = dict(metrics)
        return self._clean_payload(raw)
