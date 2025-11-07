# backend/tests/_utils/bitmap_avail.py
"""
Test utilities for creating bitmap-based availability in tests.

These helpers replace direct AvailabilitySlot model usage with bitmap storage.
"""

from datetime import date
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.availability_day import AvailabilityDay
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.utils.bitset import bits_from_windows, windows_from_bits


def seed_day(
    db: Session,
    instructor_id: str,
    target_date: date,
    windows: List[Tuple[str, str]],
) -> None:
    """
    Create or update availability for a single day using bitmap storage.

    Args:
        db: Database session
        instructor_id: Instructor identifier
        target_date: Date to set availability for
        windows: List of (start_time, end_time) tuples as strings (e.g., "09:00", "10:00")
    """
    repo = AvailabilityDayRepository(db)
    bits = bits_from_windows(windows)
    repo.upsert_week(instructor_id, [(target_date, bits)])
    db.flush()


def seed_week(
    db: Session,
    instructor_id: str,
    monday: date,
    week_map: Dict[str, List[Tuple[str, str]]],
) -> None:
    """
    Create or update availability for a week using bitmap storage.

    Args:
        db: Database session
        instructor_id: Instructor identifier
        monday: Monday of the target week
        week_map: Dict mapping date strings (ISO format) to lists of (start_time, end_time) tuples
                  Example: {"2025-01-06": [("09:00", "10:00"), ("14:00", "15:00")]}
    """
    repo = AvailabilityDayRepository(db)
    items: List[Tuple[date, bytes]] = []

    for date_str, windows in week_map.items():
        target_date = date.fromisoformat(date_str)
        bits = bits_from_windows(windows)
        items.append((target_date, bits))

    if items:
        repo.upsert_week(instructor_id, items)
        db.flush()


def get_day_windows(
    db: Session,
    instructor_id: str,
    target_date: date,
) -> List[Tuple[str, str]]:
    """
    Get availability windows for a day from bitmap storage.

    Args:
        db: Database session
        instructor_id: Instructor identifier
        target_date: Date to query

    Returns:
        List of (start_time, end_time) tuples as strings
    """
    repo = AvailabilityDayRepository(db)
    bits = repo.get_day_bits(instructor_id, target_date)
    if bits is None:
        return []
    return windows_from_bits(bits)


def get_week_windows(
    db: Session,
    instructor_id: str,
    monday: date,
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Get availability windows for a week from bitmap storage.

    Args:
        db: Database session
        instructor_id: Instructor identifier
        monday: Monday of the target week

    Returns:
        Dict mapping date strings (ISO format) to lists of (start_time, end_time) tuples
    """
    repo = AvailabilityDayRepository(db)
    week_bits = repo.get_week(instructor_id, monday)

    result: Dict[str, List[Tuple[str, str]]] = {}
    for day_date, bits in week_bits.items():
        windows = windows_from_bits(bits)
        if windows:
            result[day_date.isoformat()] = windows

    return result


def flatten_range(
    db: Session,
    instructor_id: str,
    start_date: date,
    end_date: date,
) -> List[Dict[str, str]]:
    """Return a flattened list of windows across a date range."""
    rows = (
        db.query(AvailabilityDay)
        .filter(
            AvailabilityDay.instructor_id == instructor_id,
            AvailabilityDay.day_date >= start_date,
            AvailabilityDay.day_date <= end_date,
        )
        .order_by(AvailabilityDay.day_date)
        .all()
    )
    flat: List[Dict[str, str]] = []
    for row in rows:
        for start_time, end_time in windows_from_bits(row.bits or b""):
            flat.append({"date": row.day_date.isoformat(), "start_time": start_time, "end_time": end_time})
    return flat


def window_exists(
    db: Session,
    instructor_id: str,
    target_date: date,
    start_time: str,
    end_time: str,
) -> bool:
    """Return True if the exact window exists on the day."""
    return (start_time, end_time) in get_day_windows(db, instructor_id, target_date)
