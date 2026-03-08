from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

import pytz

DEFAULT_TIMEZONE = "America/New_York"


def _safe_local_to_utc(booking_date: date, local_time: time, tz_str: str) -> datetime:
    """Convert local time to UTC, skipping over DST gaps for test data."""
    tz = pytz.timezone(tz_str)
    naive_dt = datetime.combine(booking_date, local_time)  # tz-pattern-ok: intentionally naive for pytz.localize()
    try:
        local_dt = tz.localize(naive_dt, is_dst=None)
    except pytz.exceptions.AmbiguousTimeError:
        local_dt = tz.localize(naive_dt, is_dst=True)
    except pytz.exceptions.NonExistentTimeError:
        # DST gap — push forward to the next valid time (e.g. 2:00 AM → 3:00 AM)
        local_dt = tz.localize(naive_dt, is_dst=False)
    return local_dt.astimezone(timezone.utc)


def booking_timezone_fields(
    booking_date: date,
    start_time: time,
    end_time: time,
    instructor_timezone: Optional[str] = None,
    student_timezone: Optional[str] = None,
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
        "booking_start_utc": _safe_local_to_utc(booking_date, start_time, lesson_tz),
        "booking_end_utc": _safe_local_to_utc(end_date, end_time, lesson_tz),
        "lesson_timezone": lesson_tz,
        "instructor_tz_at_booking": lesson_tz,
        "student_tz_at_booking": student_tz,
    }
