#!/usr/bin/env python3
"""
Seed default bitmap availability for instructors.

Intended for dev/stg environments to ensure the bitmap editor opens with
reasonable defaults. Uses repository APIs exclusively.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import logging
from typing import Dict, List, Tuple

from app.database import SessionLocal
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.repositories.factory import RepositoryFactory
from app.utils.bitset import bits_from_windows

logger = logging.getLogger(__name__)

DEFAULT_WINDOWS: List[Tuple[str, str]] = [
    ("09:00:00", "12:00:00"),
    ("13:00:00", "17:00:00"),
]


def _current_monday(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def seed_bitmap_availability(weeks_ahead: int = 3) -> Dict[str, int]:
    """
    Seed default availability bits for instructors.

    Args:
        weeks_ahead: Number of future weeks (inclusive of current week) to seed.

    Returns:
        Mapping of ISO week_start -> instructors written count.

    Optimized version: uses bulk_upsert_all for single database round-trip.
    """

    weeks = max(1, weeks_ahead)
    week_start = _current_monday()
    default_bits = bits_from_windows(DEFAULT_WINDOWS)
    seeded_per_week: Dict[date, int] = defaultdict(int)

    with SessionLocal() as session:
        day_repo = AvailabilityDayRepository(session)
        user_repo = RepositoryFactory.create_user_repository(session)
        instructor_ids = user_repo.list_instructor_ids()

        if not instructor_ids:
            logger.info("Bitmap availability seed: no instructors found.")
            return {}

        # Pre-load all existing bitmap data in one query
        last_week_end = week_start + timedelta(days=7 * weeks - 1)

        from app.models.availability_day import AvailabilityDay

        all_bitmap_rows = (
            session.query(
                AvailabilityDay.instructor_id,
                AvailabilityDay.day_date,
                AvailabilityDay.bits
            )
            .filter(
                AvailabilityDay.instructor_id.in_(instructor_ids),
                AvailabilityDay.day_date >= week_start,
                AvailabilityDay.day_date <= last_week_end,
            )
            .all()
        )

        # Build lookup: {instructor_id: {date: bits}}
        existing_by_instructor: Dict[str, Dict[date, bytes]] = {}
        for instructor_id, day_date, bits in all_bitmap_rows:
            if instructor_id not in existing_by_instructor:
                existing_by_instructor[instructor_id] = {}
            if bits is not None:
                existing_by_instructor[instructor_id][day_date] = bits

        # Collect ALL items for bulk upsert
        all_items: List[Tuple[str, date, bytes]] = []
        instructors_touched_per_week: Dict[date, set] = defaultdict(set)

        for week_offset in range(weeks):
            current_week = week_start + timedelta(days=7 * week_offset)

            for instructor_id in instructor_ids:
                existing = existing_by_instructor.get(instructor_id, {})
                instructor_has_pending = False

                for day_offset in range(5):  # Monday–Friday
                    day = current_week + timedelta(days=day_offset)
                    current_bits = existing.get(day)
                    if current_bits and any(current_bits):
                        continue
                    all_items.append((instructor_id, day, default_bits))
                    instructor_has_pending = True

                if instructor_has_pending:
                    instructors_touched_per_week[current_week].add(instructor_id)

        # Single native PostgreSQL UPSERT for all data (1 statement)
        if all_items:
            day_repo.bulk_upsert_native(all_items)
            session.commit()

            # Build return value with per-week counts
            for week_date, instructors in instructors_touched_per_week.items():
                seeded_per_week[week_date] = len(instructors)
                logger.info(
                    "Seeded bitmap availability",
                    extra={
                        "week_start": week_date.isoformat(),
                        "instructors": len(instructors),
                        "weeks_ahead": weeks,
                    },
                )

    return {week.isoformat(): count for week, count in seeded_per_week.items()}


__all__ = ["seed_bitmap_availability"]
