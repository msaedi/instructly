"""Shared bitmap availability helpers for repository pattern tests."""

from __future__ import annotations

from datetime import date, time
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.models.availability_day import AvailabilityDay
from app.utils.bitset import bits_from_windows, windows_from_bits
from app.utils.time_helpers import string_to_time
from app.utils.time_utils import time_to_minutes


def _time_str(value: time | str) -> str:
    return value if isinstance(value, str) else value.strftime("%H:%M:%S")


def _minutes(value: time | str, *, is_end_time: bool = False) -> int:
    if isinstance(value, str):
        if value.startswith("24:"):
            is_end_time = True
        return time_to_minutes(string_to_time(value), is_end_time=is_end_time)
    return time_to_minutes(value, is_end_time=is_end_time)


def seed_day(
    db: Session,
    instructor_id: str,
    day_date: date,
    windows: Sequence[tuple[time | str, time | str]],
) -> AvailabilityDay:
    """Create or replace bitmap windows for a single day."""
    normalized = [(_time_str(start), _time_str(end)) for start, end in windows]
    row = (
        db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id, AvailabilityDay.day_date == day_date)
        .one_or_none()
    )
    bits = bits_from_windows(normalized)
    if row:
        row.bits = bits
    else:
        row = AvailabilityDay(instructor_id=instructor_id, day_date=day_date, bits=bits)
        db.add(row)
    db.flush()
    return row


def fetch_days(
    db: Session,
    instructor_id: str,
    start_date: date,
    end_date: date,
) -> list[AvailabilityDay]:
    """Return ordered AvailabilityDay rows for the window."""
    return (
        db.query(AvailabilityDay)
        .filter(
            AvailabilityDay.instructor_id == instructor_id,
            AvailabilityDay.day_date >= start_date,
            AvailabilityDay.day_date <= end_date,
        )
        .order_by(AvailabilityDay.day_date)
        .all()
    )


def flatten_windows(rows: Iterable[AvailabilityDay]) -> list[dict[str, object]]:
    """Flatten AvailabilityDay rows into comparable dicts."""
    flat: list[dict[str, object]] = []
    for row in rows:
        for start, end in windows_from_bits(row.bits or b""):
            flat.append({"date": row.day_date, "start_time": start, "end_time": end})
    return sorted(flat, key=lambda item: (item["date"], item["start_time"], item["end_time"]))


def window_exists(
    db: Session, instructor_id: str, day_date: date, start: time | str, end: time | str
) -> bool:
    """Return True if the given window exists on the day."""
    row = (
        db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id, AvailabilityDay.day_date == day_date)
        .one_or_none()
    )
    if not row:
        return False
    target = (_time_str(start), _time_str(end))
    return target in set(windows_from_bits(row.bits or b""))


def delete_day(db: Session, instructor_id: str, day_date: date) -> int:
    """Delete the AvailabilityDay row for the target date."""
    deleted = (
        db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id, AvailabilityDay.day_date == day_date)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted


def overlaps(window: tuple[str, str], start: time, end: time) -> bool:
    """Return True if the stored window overlaps the candidate time range."""
    win_start, win_end = window
    start_min = _minutes(start, is_end_time=False)
    end_min = _minutes(end, is_end_time=True)
    win_start_min = _minutes(win_start, is_end_time=False)
    win_end_min = _minutes(win_end, is_end_time=True)
    return max(start_min, win_start_min) < min(end_min, win_end_min)


def window_counts(rows: Iterable[AvailabilityDay]) -> dict[str, int]:
    """Return ISO date → window count for populated days."""
    counts: dict[str, int] = {}
    for row in rows:
        windows = windows_from_bits(row.bits or b"")
        if windows:
            counts[row.day_date.isoformat()] = len(windows)
    return counts


def flatten_range(
    db: Session,
    instructor_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    """Flatten windows across a date range."""
    return flatten_windows(fetch_days(db, instructor_id, start_date, end_date))


def count_windows_total(
    db: Session,
    instructor_id: str,
    start_date: date,
    end_date: date,
) -> int:
    """Return total number of windows across a date range."""
    return len(flatten_range(db, instructor_id, start_date, end_date))


def get_day_windows(db: Session, instructor_id: str, day_date: date) -> list[tuple[str, str]]:
    """Return windows for a single day."""
    row = (
        db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id, AvailabilityDay.day_date == day_date)
        .one_or_none()
    )
    if not row:
        return []
    return windows_from_bits(row.bits or b"")
