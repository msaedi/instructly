from __future__ import annotations

from datetime import date, time
from typing import Any, Optional

from app.services.timezone_service import TimezoneService

DEFAULT_TIMEZONE = "America/New_York"


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
    return {
        "booking_start_utc": TimezoneService.local_to_utc(booking_date, start_time, lesson_tz),
        "booking_end_utc": TimezoneService.local_to_utc(booking_date, end_time, lesson_tz),
        "lesson_timezone": lesson_tz,
        "instructor_tz_at_booking": lesson_tz,
        "student_tz_at_booking": student_tz,
    }
