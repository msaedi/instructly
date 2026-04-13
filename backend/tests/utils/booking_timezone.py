from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

import pytz

DEFAULT_TIMEZONE = "America/New_York"


def _safe_local_to_utc(
    booking_date: date,
    local_time: time,
    tz_str: str,
    *,
    is_dst_for_ambiguous: Optional[bool] = None,
) -> datetime:
    """Convert a local wall-clock time to UTC for test fixtures."""
    tz = pytz.timezone(tz_str)
    naive_dt = datetime.combine(booking_date, local_time)  # tz-pattern-ok: intentionally naive for pytz.localize()
    try:
        local_dt = tz.localize(naive_dt, is_dst=None)
    except pytz.exceptions.AmbiguousTimeError as exc:
        # Default behavior: raise on both nonexistent AND ambiguous times.
        # Tests that need to construct ambiguous times (e.g. fall-back
        # day 1:30 AM) must pass is_dst_for_ambiguous explicitly to opt in.
        # This prevents tests from accidentally coercing impossible times
        # into silently-wrong UTC datetimes.
        if is_dst_for_ambiguous is None:
            raise ValueError(
                "Ambiguous local time "
                f"{naive_dt.isoformat()} in timezone {tz_str}; pass "
                "is_dst_for_ambiguous=True or False explicitly."
            ) from exc
        local_dt = tz.localize(naive_dt, is_dst=is_dst_for_ambiguous)
    except pytz.exceptions.NonExistentTimeError:
        raise ValueError(
            "Nonexistent local time "
            f"{naive_dt.isoformat()} in timezone {tz_str} due to daylight saving "
            "time transition."
        )
    return local_dt.astimezone(timezone.utc)


def booking_timezone_fields(
    booking_date: date,
    start_time: time,
    end_time: time,
    instructor_timezone: Optional[str] = None,
    student_timezone: Optional[str] = None,
    is_dst_for_ambiguous: Optional[bool] = None,
) -> dict[str, Any]:
    if start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)
    if end_time.tzinfo is not None:
        end_time = end_time.replace(tzinfo=None)
    lesson_tz = instructor_timezone or DEFAULT_TIMEZONE
    student_tz = student_timezone or lesson_tz
    # When end_time < start_time the booking crosses midnight;
    # use the next day for the end UTC calculation.
    end_date = booking_date + timedelta(days=1) if end_time < start_time else booking_date
    return {
        "booking_start_utc": _safe_local_to_utc(
            booking_date,
            start_time,
            lesson_tz,
            is_dst_for_ambiguous=is_dst_for_ambiguous,
        ),
        "booking_end_utc": _safe_local_to_utc(
            end_date,
            end_time,
            lesson_tz,
            is_dst_for_ambiguous=is_dst_for_ambiguous,
        ),
        "lesson_timezone": lesson_tz,
        "instructor_tz_at_booking": lesson_tz,
        "student_tz_at_booking": student_tz,
    }
