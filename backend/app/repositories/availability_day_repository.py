from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

from sqlalchemy.orm import Session

from app.core.constants import BITS_PER_TAG, BYTES_PER_DAY, SLOTS_PER_DAY, TAG_BYTES_PER_DAY
from app.models import AvailabilityDay
from app.utils.bitset import new_empty_tags

DayBitmapItem = Tuple[date, bytes]
DayBitmapWithTagsItem = Tuple[date, bytes, bytes]
MultiInstructorBitmapItem = Tuple[str, date, bytes]
MultiInstructorBitmapWithTagsItem = Tuple[str, date, bytes, bytes]


def normalize_format_tags(bits: bytes, format_tags: bytes) -> bytes:
    """Clear tags for any slot whose availability bit is off."""
    if len(bits) != BYTES_PER_DAY:
        raise ValueError(f"bits length must be {BYTES_PER_DAY}")
    if len(format_tags) != TAG_BYTES_PER_DAY:
        raise ValueError(f"format_tags length must be {TAG_BYTES_PER_DAY}")

    normalized = bytearray(format_tags)
    for slot in range(SLOTS_PER_DAY):
        if bits[slot // 8] & (1 << (slot % 8)):
            continue

        bit_offset = slot * BITS_PER_TAG
        byte_idx = bit_offset // 8
        bit_pos = bit_offset % 8
        normalized[byte_idx] &= ~(0b11 << bit_pos)

    return bytes(normalized)


class AvailabilityDayRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _normalize_format_tags(bits: bytes, format_tags: bytes) -> bytes:
        return normalize_format_tags(bits, format_tags)

    def _resolve_format_tags(
        self,
        *,
        bits: bytes,
        provided_format_tags: Optional[bytes],
        existing_format_tags: Optional[bytes] = None,
    ) -> bytes:
        candidate = provided_format_tags
        if candidate is None:
            candidate = existing_format_tags or new_empty_tags()
        return self._normalize_format_tags(bits, candidate)

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

    def get_day_bitmaps(self, instructor_id: str, day: date) -> Optional[Tuple[bytes, bytes]]:
        row = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == day,
            )
            .one_or_none()
        )
        if row is None:
            return None
        format_tags = row.format_tags or new_empty_tags()
        return row.bits, format_tags

    def get_week(self, instructor_id: str, week_start: date) -> Dict[date, bytes]:
        res: Dict[date, bytes] = {}
        rows = self.get_week_rows(instructor_id, week_start)
        for row in rows:
            res[row.day_date] = row.bits
        return res

    def get_week_bitmaps(
        self, instructor_id: str, week_start: date
    ) -> Dict[date, Tuple[bytes, bytes]]:
        res: Dict[date, Tuple[bytes, bytes]] = {}
        rows = self.get_week_rows(instructor_id, week_start)
        for row in rows:
            res[row.day_date] = (row.bits, row.format_tags or new_empty_tags())
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

    def upsert_week(
        self,
        instructor_id: str,
        items: Sequence[DayBitmapItem | DayBitmapWithTagsItem],
    ) -> int:
        """Upsert (date, bits[, format_tags]) for a single week; returns row count written."""
        count = 0
        for item in items:
            day_date, bits = item[0], item[1]
            provided_format_tags = item[2] if len(item) == 3 else None
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
                row.format_tags = self._resolve_format_tags(
                    bits=bits,
                    provided_format_tags=provided_format_tags,
                    existing_format_tags=row.format_tags,
                )
            else:
                row = AvailabilityDay(
                    instructor_id=instructor_id,
                    day_date=day_date,
                    bits=bits,
                    format_tags=self._resolve_format_tags(
                        bits=bits,
                        provided_format_tags=provided_format_tags,
                    ),
                )
                self.db.add(row)
            count += 1
        self.db.flush()
        return count

    def bulk_upsert_all(
        self,
        items: Sequence[MultiInstructorBitmapItem | MultiInstructorBitmapWithTagsItem],
    ) -> int:
        """Bulk upsert (instructor_id, date, bits[, format_tags]) for multiple instructors at once.

        Optimized for seeding: pre-loads all existing rows in one query,
        then batches inserts/updates for a single flush.

        Args:
            items: List of (instructor_id, day_date, bits[, format_tags]) tuples

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
        for item in items:
            instructor_id, day_date, bits = item[0], item[1], item[2]
            provided_format_tags = item[3] if len(item) == 4 else None
            key = (instructor_id, day_date)
            row = existing_lookup.get(key)
            if row:
                row.bits = bits
                row.format_tags = self._resolve_format_tags(
                    bits=bits,
                    provided_format_tags=provided_format_tags,
                    existing_format_tags=row.format_tags,
                )
            else:
                row = AvailabilityDay(
                    instructor_id=instructor_id,
                    day_date=day_date,
                    bits=bits,
                    format_tags=self._resolve_format_tags(
                        bits=bits,
                        provided_format_tags=provided_format_tags,
                    ),
                )
                self.db.add(row)
                existing_lookup[key] = row  # Track for future iterations
            count += 1

        self.db.flush()
        return count

    def bulk_upsert_native(
        self,
        items: Sequence[MultiInstructorBitmapItem | MultiInstructorBitmapWithTagsItem],
        batch_size: int = 5000,
    ) -> int:
        """Bulk upsert using native PostgreSQL INSERT ... ON CONFLICT.

        Much faster than ORM-based upsert for remote databases.
        Chunks into batches to avoid PostgreSQL parameter/packet limits.

        Args:
            items: List of (instructor_id, day_date, bits[, format_tags]) tuples
            batch_size: Max rows per batch (default 5000)

        Returns:
            Number of rows affected
        """
        if not items:
            return 0

        from sqlalchemy import text

        instructor_ids = list({item[0] for item in items})
        dates = [item[1] for item in items]
        min_date = min(dates)
        max_date = max(dates)
        existing_rows = (
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id.in_(instructor_ids),
                AvailabilityDay.day_date >= min_date,
                AvailabilityDay.day_date <= max_date,
            )
            .all()
        )
        existing_lookup: Dict[Tuple[str, date], AvailabilityDay] = {
            (row.instructor_id, row.day_date): row for row in existing_rows
        }

        total = 0
        # Process in chunks to avoid parameter limits
        for chunk_start in range(0, len(items), batch_size):
            chunk = items[chunk_start : chunk_start + batch_size]

            # Build VALUES clause with parameters for this chunk
            values_clauses: list[str] = []
            params: Dict[str, Any] = {}
            for i, item in enumerate(chunk):
                instructor_id, day_date, bits = item[0], item[1], item[2]
                provided_format_tags = item[3] if len(item) == 4 else None
                key = (instructor_id, day_date)
                existing_row = existing_lookup.get(key)
                format_tags = self._resolve_format_tags(
                    bits=bits,
                    provided_format_tags=provided_format_tags,
                    existing_format_tags=existing_row.format_tags if existing_row else None,
                )
                values_clauses.append(
                    f"(:instructor_id_{i}, :day_date_{i}, :bits_{i}, :format_tags_{i})"
                )
                params[f"instructor_id_{i}"] = instructor_id
                params[f"day_date_{i}"] = day_date
                params[f"bits_{i}"] = bits
                params[f"format_tags_{i}"] = format_tags
                existing_lookup[key] = AvailabilityDay(
                    instructor_id=instructor_id,
                    day_date=day_date,
                    bits=bits,
                    format_tags=format_tags,
                )

            # PostgreSQL native UPSERT (parameterized - values_clauses are placeholders only)
            sql = f"""
                INSERT INTO availability_days (instructor_id, day_date, bits, format_tags)
                VALUES {', '.join(values_clauses)}
                ON CONFLICT (instructor_id, day_date)
                DO UPDATE SET
                    bits = EXCLUDED.bits,
                    format_tags = EXCLUDED.format_tags
            """  # nosec B608 - SQL injection safe: values_clauses contains parameterized placeholders

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
