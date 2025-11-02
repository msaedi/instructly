from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from sqlalchemy.orm import Session

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.utils.bitset import bits_from_windows

WindowSeq = Sequence[tuple[str, str]]


def seed_bits_for_range(
    session: Session,
    instructor_id: str,
    start_date: date,
    *,
    weeks: int = 1,
    windows: WindowSeq | None = None,
) -> None:
    """
    Seed bitmap availability for an instructor across a contiguous range of weeks.

    Args:
        session: Active database session.
        instructor_id: Instructor identifier.
        start_date: Monday date representing the first week to seed.
        weeks: Number of consecutive weeks (default 1).
        windows: Iterable of time window tuples (start_time, end_time) for each day.
                 Defaults to a full-day 09:00-18:00 window.
    """

    repo = AvailabilityDayRepository(session)
    daily_windows: WindowSeq = windows if windows is not None else [("09:00:00", "18:00:00")]

    encoded_windows = bits_from_windows(list(daily_windows))

    for week_index in range(max(weeks, 0)):
        monday = start_date + timedelta(days=week_index * 7)
        items: list[tuple[date, bytes]] = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            items.append((day, encoded_windows))
        repo.upsert_week(instructor_id, items)
    session.flush()


__all__ = ["seed_bits_for_range"]
