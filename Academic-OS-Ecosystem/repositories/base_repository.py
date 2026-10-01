from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session


class BaseRepository:
    """Small SQLAlchemy Core helper for repository modules."""

    def __init__(self, db: Session):
        self.db = db

    def _execute(self, statement: str, params: Optional[Mapping[str, Any]] = None):
        return self.db.execute(text(statement), dict(params or {}))

    def _execute_many(self, statement: str, rows: Iterable[Mapping[str, Any]]) -> None:
        rows = [dict(row) for row in rows]
        if rows:
            self.db.execute(text(statement), rows)

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        return dict(row._mapping)

    def _fetch_one(self, statement: str, params: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]:
        row = self._execute(statement, params).mappings().first()
        return dict(row) if row else None

    def _fetch_all(self, statement: str, params: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._execute(statement, params).mappings().all()]

    @staticmethod
    def _clean_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (datetime, date)):
                cleaned[key] = value.isoformat()
            elif hasattr(value, "value"):
                cleaned[key] = value.value
            else:
                cleaned[key] = value
        return cleaned

    def _table_columns(self, table: str) -> Set[str]:
        rows = self._execute(f"PRAGMA table_info({table})").mappings().all()
        return {str(row["name"]) for row in rows}

    def _insert_or_update(
        self,
        table: str,
        payload: Mapping[str, Any],
        conflict_columns: Iterable[str],
    ) -> None:
        table_columns = self._table_columns(table)
        data = {
            key: value
            for key, value in self._clean_payload(payload).items()
            if key in table_columns
        }
        columns = list(data.keys())
        conflict = list(conflict_columns)
        missing_conflict_columns = [column for column in conflict if column not in data]
        if missing_conflict_columns:
            missing = ", ".join(missing_conflict_columns)
            raise ValueError(f"Missing required conflict column(s) for {table}: {missing}")

        update_columns = [column for column in columns if column not in conflict]

        placeholders = ", ".join(f":{column}" for column in columns)
        column_names = ", ".join(columns)
        conflict_names = ", ".join(conflict)

        if update_columns:
            updates = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
            updates = f"{updates}, updated_at = CURRENT_TIMESTAMP"
        else:
            updates = "updated_at = CURRENT_TIMESTAMP"

        self._execute(
            f"""
            INSERT INTO {table} ({column_names})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_names}) DO UPDATE SET {updates}
            """,
            data,
        )

    def _delete(self, table: str, where_clause: str, params: Mapping[str, Any]) -> int:
        result = self._execute(f"DELETE FROM {table} WHERE {where_clause}", params)
        return int(result.rowcount or 0)
