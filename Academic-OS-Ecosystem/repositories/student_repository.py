from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy.orm import Session

from backend.db import StudentRecord
from backend.schemas import StudentFeatures


class StudentRepository:
    """Repository for placement feature records stored in student_records."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, record_id: int) -> Optional[StudentRecord]:
        return self.db.query(StudentRecord).filter(StudentRecord.id == record_id).first()

    def get_by_student_id(self, student_id: str) -> Optional[StudentRecord]:
        return self.db.query(StudentRecord).filter(StudentRecord.student_id == student_id).first()

    def list(self, skip: int = 0, limit: int = 100) -> List[StudentRecord]:
        return (
            self.db.query(StudentRecord)
            .order_by(StudentRecord.student_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create(self, payload: StudentFeatures | Mapping[str, Any]) -> StudentRecord:
        data = self._payload_to_dict(payload)
        record = StudentRecord(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update(self, student_id: str, payload: Mapping[str, Any]) -> Optional[StudentRecord]:
        record = self.get_by_student_id(student_id)
        if not record:
            return None

        for key, value in self._payload_to_dict(payload, exclude_unset=True).items():
            if hasattr(record, key):
                setattr(record, key, value)

        self.db.commit()
        self.db.refresh(record)
        return record

    def upsert(self, payload: StudentFeatures | Mapping[str, Any]) -> StudentRecord:
        data = self._payload_to_dict(payload)
        student_id = data["student_id"]
        record = self.get_by_student_id(student_id)

        if record:
            for key, value in data.items():
                if hasattr(record, key):
                    setattr(record, key, value)
        else:
            record = StudentRecord(**data)
            self.db.add(record)

        self.db.commit()
        self.db.refresh(record)
        return record

    def bulk_upsert(self, payloads: Iterable[StudentFeatures | Mapping[str, Any]]) -> List[StudentRecord]:
        records = [self.upsert(payload) for payload in payloads]
        return records

    def set_prediction(self, student_id: str, probability: float) -> Optional[StudentRecord]:
        return self.update(student_id, {"predicted_placement_probability": probability})

    def record_outcome(self, student_id: str, placed: int | bool) -> Optional[StudentRecord]:
        return self.update(student_id, {"actual_placed": int(placed)})

    def delete(self, student_id: str) -> bool:
        record = self.get_by_student_id(student_id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def list_at_risk(self, threshold: float = 0.33, limit: int = 100) -> List[StudentRecord]:
        return (
            self.db.query(StudentRecord)
            .filter(StudentRecord.predicted_placement_probability.isnot(None))
            .filter(StudentRecord.predicted_placement_probability < threshold)
            .order_by(StudentRecord.predicted_placement_probability.asc())
            .limit(limit)
            .all()
        )

    def count(self) -> int:
        return int(self.db.query(StudentRecord).count())

    @staticmethod
    def _payload_to_dict(payload: StudentFeatures | Mapping[str, Any], exclude_unset: bool = False) -> Dict[str, Any]:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(exclude_unset=exclude_unset)
        if hasattr(payload, "dict"):
            return payload.dict(exclude_unset=exclude_unset)
        return dict(payload)
