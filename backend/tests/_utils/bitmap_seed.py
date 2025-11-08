"""Helpers for seeding bitmap availability in tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Tuple

from backend.tests._utils import bitmap_avail as BA
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


def next_monday(day: date | None = None) -> date:
    """Return the next Monday on/after *day* (or today if None)."""
    today = day or date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7  # If today is Monday, get next Monday
    return today + timedelta(days=days_until_monday)


def seed_full_week(
    db: Session,
    instructor_id: str,
    start: str = "09:00:00",
    end: str = "18:00:00",
    weeks: int = 1,
) -> None:
    """
    Seed continuous availability windows for the next `weeks` weeks, Mon..Sun,
    so any booking tests have time slots to work with.
    Also includes tomorrow if it's not already covered.
    """
    from datetime import date, timedelta

    mon = next_monday()
    tomorrow = date.today() + timedelta(days=1)

    # Build windows dict starting from tomorrow if needed, then the weeks
    windows: Dict[str, List[Tuple[str, str]]] = {}

    # Always include tomorrow if it's not already in the weeks
    if tomorrow < mon:
        windows[str(tomorrow)] = [(start, end)]

    # Add the weeks
    for w in range(weeks):
        week_start = mon + timedelta(days=7 * w)
        for i in range(7):
            d = week_start + timedelta(days=i)
            windows[str(d)] = [(start, end)]

    # Seed all windows
    if windows:
        # Use the earliest date as the week_start for seed_week
        earliest_date = min(date.fromisoformat(d) for d in windows.keys())
        # Find the Monday of that week
        week_start_for_seed = earliest_date - timedelta(days=earliest_date.weekday())
        BA.seed_week(db, instructor_id, week_start_for_seed, windows)


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


def clear_week_bits(
    db: Session,
    instructor_id: str,
    week_start: date,
    weeks: int = 1,
) -> None:
    """Clear bitmap availability for the specified week range."""
    from datetime import timedelta

    from app.models.availability_day import AvailabilityDay

    # Calculate date range
    start_date = week_start
    end_date = week_start + timedelta(days=7 * weeks - 1)

    # Delete AvailabilityDay rows for the date range
    db.query(AvailabilityDay).filter(
        AvailabilityDay.instructor_id == instructor_id,
        AvailabilityDay.day_date >= start_date,
        AvailabilityDay.day_date <= end_date,
    ).delete()
    db.commit()


__all__ = ["next_monday", "seed_week_bits", "seed_full_week", "clear_week_bits"]
