from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models import AvailabilityDay


class AvailabilityDayRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_week(self, instructor_id: str, week_start: date) -> Dict[date, bytes]:
        res: Dict[date, bytes] = {}
        week_end = week_start + timedelta(days=6)
        rows = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date >= week_start,
                AvailabilityDay.day_date <= week_end,
            )
            .all()
        )
        for row in rows:
            res[row.day_date] = row.bits
        return res

    def upsert_week(self, instructor_id: str, items: List[Tuple[date, bytes]]) -> int:
        """Upsert (date, bits) for a single week; returns row count written."""
        count = 0
        for day_date, bits in items:
            row = (
                self.db.query(AvailabilityDay)
                .filter(
                    AvailabilityDay.instructor_id == instructor_id,
                    AvailabilityDay.day_date == day_date,
                )
                .one_or_none()
            )
            if row:
                row.bits = bits
            else:
                row = AvailabilityDay(instructor_id=instructor_id, day_date=day_date, bits=bits)
                self.db.add(row)
            count += 1
        self.db.flush()
        return count
