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

        for week_offset in range(weeks):
            current_week = week_start + timedelta(days=7 * week_offset)
            seeded_this_week = 0

            for instructor_id in instructor_ids:
                existing = day_repo.get_week(instructor_id, current_week)
                pending: List[Tuple[date, bytes]] = []

                for day_offset in range(5):  # Monday–Friday
                    day = current_week + timedelta(days=day_offset)
                    current_bits = existing.get(day)
                    if current_bits and any(current_bits):
                        continue
                    pending.append((day, default_bits))

                if not pending:
                    continue

                day_repo.upsert_week(instructor_id, pending)
                seeded_this_week += 1

            if seeded_this_week:
                session.commit()
                seeded_per_week[current_week] += seeded_this_week
                logger.info(
                    "Seeded bitmap availability",
                    extra={
                        "week_start": current_week.isoformat(),
                        "instructors": seeded_this_week,
                        "weeks_ahead": weeks,
                    },
                )
            else:
                session.rollback()

    return {week.isoformat(): count for week, count in seeded_per_week.items()}


__all__ = ["seed_bitmap_availability"]
