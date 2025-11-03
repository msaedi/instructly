from __future__ import annotations

from datetime import date, time, timedelta
from typing import Dict, Iterable, List, Literal, Tuple

from sqlalchemy.orm import Session

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.repositories.availability_repository import AvailabilityRepository
import app.utils.bitset as bitset


def _resolve_windows_to_bits():
    """Return the callable that converts window tuples to bitmap bytes."""
    for name in ("windows_to_bits", "bits_from_windows", "pack_windows"):
        fn = getattr(bitset, name, None)
        if callable(fn):
            return fn
    raise RuntimeError("Could not resolve windows->bits function in app.utils.bitset")


_WINDOWS_TO_BITS = _resolve_windows_to_bits()


def _parse_time(value: str) -> time:
    """Parse HH:MM[:SS] strings into time objects for slot seeding."""
    hours, minutes, *rest = value.split(":")
    seconds = rest[0] if rest else "00"
    return time(int(hours), int(minutes), int(seconds))


def _assert_half_hour_aligned(start: str, end: str) -> None:
    """Raise if the provided window is not aligned to half-hour boundaries."""
    start_time = _parse_time(start)
    end_time = _parse_time(end)
    msg = f"Window {start}-{end} is not half-hour aligned"
    assert start_time.minute in (0, 30), msg
    assert end_time.minute in (0, 30), msg


def _build_windows_by_date(
    week_start: date, windows_by_weekday: Dict[int, Iterable[Tuple[str, str]]]
) -> Dict[date, List[Tuple[str, str]]]:
    """Expand weekday keyed definitions into a concrete date mapping."""
    mapping: Dict[date, List[Tuple[str, str]]] = {}
    for weekday, windows in windows_by_weekday.items():
        if not 0 <= weekday <= 6:
            continue
        day_date = week_start + timedelta(days=weekday)
        mapping[day_date] = list(windows)
    return mapping


def seed_slots_legacy(
    session: Session,
    *,
    instructor_id: str,
    windows_by_date: Dict[date, Iterable[Tuple[str, str]]],
    clear_existing: bool = True,
) -> int:
    """
    Seed legacy availability slots for the provided dates.

    Returns the number of slot rows written.
    """
    repo = AvailabilityRepository(session)
    dates = list(windows_by_date.keys())
    if clear_existing and dates:
        repo.delete_slots_by_dates(instructor_id, dates)

    created = 0
    for day_date, windows in windows_by_date.items():
        for start, end in list(windows):
            _assert_half_hour_aligned(start, end)
            repo.create_slot(
                instructor_id, day_date, _parse_time(start), _parse_time(end)
            )
            created += 1
    return created


def seed_bits_bitmap(
    session: Session,
    *,
    instructor_id: str,
    windows_by_date: Dict[date, Iterable[Tuple[str, str]]],
    clear_existing: bool = True,
) -> int:
    """
    Seed bitmap availability for the provided dates.

    Returns the number of day rows written with non-empty bitmaps.
    """
    repo = AvailabilityDayRepository(session)
    items: List[Tuple[date, bytes]] = []
    days_written = 0

    for day_date, windows in windows_by_date.items():
        win_list = list(windows)
        for start, end in win_list:
            _assert_half_hour_aligned(start, end)
        bits = _WINDOWS_TO_BITS(win_list)
        if clear_existing or win_list:
            items.append((day_date, bits))
        if win_list:
            days_written += 1

    if items:
        repo.upsert_week(instructor_id, items)
    return days_written


def seed_week_bits_for_booking(
    session: Session,
    *,
    instructor_id: str,
    week_start: date,
    windows_by_weekday: Dict[int, Iterable[Tuple[str, str]]],
    mode: Literal["auto", "bitmap", "legacy", "both"] = "auto",
    clear_existing: bool = True,
) -> Dict[str, int]:
    """
    Seed availability so booking flows can pass regardless of guardrails.

    Returns counters for slots and bitmap rows created.
    """
    windows_by_date = _build_windows_by_date(week_start, windows_by_weekday)
    counters = {"days_written": 0, "slots_created": 0}

    effective_mode: Literal["auto", "bitmap", "legacy", "both"] = mode
    if effective_mode == "auto":
        effective_mode = "both"

    if effective_mode in ("both", "legacy"):
        counters["slots_created"] = seed_slots_legacy(
            session,
            instructor_id=instructor_id,
            windows_by_date=windows_by_date,
            clear_existing=clear_existing,
        )
    if effective_mode in ("both", "bitmap"):
        counters["days_written"] = seed_bits_bitmap(
            session,
            instructor_id=instructor_id,
            windows_by_date=windows_by_date,
            clear_existing=clear_existing,
        )

    return counters
