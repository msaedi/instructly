"""Helpers for seeding bitmap availability in tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.utils.bitset as bitset  # type: ignore


def _resolve_windows_to_bits():
    """Return a callable that packs windows into bitmap bytes."""
    for name in ("windows_to_bits", "bits_from_windows", "pack_windows"):
        fn = getattr(bitset, name, None)
        if callable(fn):
            return fn
    raise RuntimeError("Could not locate a windows->bits helper in app.utils.bitset")


_WINDOWS_TO_BITS = _resolve_windows_to_bits()


def next_monday(day: date) -> date:
    """Return the next Monday on/after *day*."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def seed_week_bits(
    session: Session,
    *,
    instructor_id: str,
    week_start: date,
    windows_by_weekday: Dict[int, Iterable[Tuple[str, str]]],
    clear_existing: bool = False,
) -> int:
    """Seed bitmap availability rows for a single instructor week.

    Args:
        session: active SQLAlchemy Session.
        instructor_id: instructor ULID.
        week_start: Monday date for the target week.
        windows_by_weekday: mapping of weekday (0=Mon) to iterable of (start, end) tuples.
        clear_existing: when True, days without windows are overwritten with empty bitsets.

    Returns:
        Number of day rows populated with non-empty windows.
    """

    repo = AvailabilityDayRepository(session)
    items: List[Tuple[date, bytes]] = []
    days_written = 0

    for weekday in range(7):
        day_date = week_start + timedelta(days=weekday)
        windows = list(windows_by_weekday.get(weekday, []))
        if windows:
            items.append((day_date, _WINDOWS_TO_BITS(windows)))
            days_written += 1
        elif clear_existing:
            items.append((day_date, _WINDOWS_TO_BITS([])))

    if items:
        repo.upsert_week(instructor_id, items)
        session.flush()
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise

    return days_written


__all__ = ["next_monday", "seed_week_bits"]
