from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.models import AvailabilityDay


class AvailabilityDayRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_week_rows(self, instructor_id: str, week_start: date) -> List[AvailabilityDay]:
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
        return cast(List[AvailabilityDay], rows)

    def get_day_bits(self, instructor_id: str, day: date) -> Optional[bytes]:
        row = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == day,
            )
            .one_or_none()
        )
        return row.bits if row else None

    def get_week(self, instructor_id: str, week_start: date) -> Dict[date, bytes]:
        res: Dict[date, bytes] = {}
        rows = self.get_week_rows(instructor_id, week_start)
        for row in rows:
            res[row.day_date] = row.bits
        return res

    def get_days_in_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> List[AvailabilityDay]:
        rows = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date >= start_date,
                AvailabilityDay.day_date <= end_date,
            )
            .all()
        )
        return cast(List[AvailabilityDay], rows)

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

    def delete_days_for_instructor(
        self,
        instructor_id: str,
        *,
        exclude_dates: Optional[Iterable[date]] = None,
    ) -> int:
        """Delete AvailabilityDay rows for an instructor, optionally excluding specific dates."""
        query = self.db.query(AvailabilityDay).filter(
            AvailabilityDay.instructor_id == instructor_id
        )
        if exclude_dates:
            query = query.filter(~AvailabilityDay.day_date.in_(list(exclude_dates)))
        deleted = query.delete(synchronize_session=False)
        self.db.flush()
        return int(deleted or 0)
