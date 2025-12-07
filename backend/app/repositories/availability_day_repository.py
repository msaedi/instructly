from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

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

    def bulk_upsert_all(
        self,
        items: List[Tuple[str, date, bytes]],
    ) -> int:
        """Bulk upsert (instructor_id, date, bits) for multiple instructors at once.

        Optimized for seeding: pre-loads all existing rows in one query,
        then batches inserts/updates for a single flush.

        Args:
            items: List of (instructor_id, day_date, bits) tuples

        Returns:
            Number of rows written
        """
        if not items:
            return 0

        # Extract unique instructor IDs and date range
        instructor_ids = list({item[0] for item in items})
        dates = [item[1] for item in items]
        min_date = min(dates)
        max_date = max(dates)

        # Pre-load all existing rows in one query
        existing_rows = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id.in_(instructor_ids),
                AvailabilityDay.day_date >= min_date,
                AvailabilityDay.day_date <= max_date,
            )
            .all()
        )

        # Build lookup: (instructor_id, day_date) -> row
        existing_lookup: Dict[Tuple[str, date], AvailabilityDay] = {
            (row.instructor_id, row.day_date): row for row in existing_rows
        }

        # Upsert all items
        count = 0
        for instructor_id, day_date, bits in items:
            key = (instructor_id, day_date)
            row = existing_lookup.get(key)
            if row:
                row.bits = bits
            else:
                row = AvailabilityDay(instructor_id=instructor_id, day_date=day_date, bits=bits)
                self.db.add(row)
                existing_lookup[key] = row  # Track for future iterations
            count += 1

        self.db.flush()
        return count

    def bulk_upsert_native(
        self,
        items: List[Tuple[str, date, bytes]],
        batch_size: int = 5000,
    ) -> int:
        """Bulk upsert using native PostgreSQL INSERT ... ON CONFLICT.

        Much faster than ORM-based upsert for remote databases.
        Chunks into batches to avoid PostgreSQL parameter/packet limits.

        Args:
            items: List of (instructor_id, day_date, bits) tuples
            batch_size: Max rows per batch (default 5000)

        Returns:
            Number of rows affected
        """
        if not items:
            return 0

        from sqlalchemy import text

        total = 0
        # Process in chunks to avoid parameter limits
        for chunk_start in range(0, len(items), batch_size):
            chunk = items[chunk_start : chunk_start + batch_size]

            # Build VALUES clause with parameters for this chunk
            values_clauses: list[str] = []
            params: Dict[str, Any] = {}
            for i, (instructor_id, day_date, bits) in enumerate(chunk):
                values_clauses.append(f"(:instructor_id_{i}, :day_date_{i}, :bits_{i})")
                params[f"instructor_id_{i}"] = instructor_id
                params[f"day_date_{i}"] = day_date
                params[f"bits_{i}"] = bits

            # PostgreSQL native UPSERT
            sql = f"""
                INSERT INTO availability_days (instructor_id, day_date, bits)
                VALUES {', '.join(values_clauses)}
                ON CONFLICT (instructor_id, day_date)
                DO UPDATE SET bits = EXCLUDED.bits
            """

            self.db.execute(text(sql), params)
            total += len(chunk)

        self.db.flush()
        return total

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
