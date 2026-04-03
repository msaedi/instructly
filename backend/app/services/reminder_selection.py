"""Shared reminder candidate selection helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .timezone_service import TimezoneService

if TYPE_CHECKING:
    from app.models.booking import Booking


def resolve_booking_reminder_timezone(booking: "Booking") -> str:
    """Resolve the authoritative timezone used for booking reminders."""
    lesson_tz = getattr(booking, "lesson_timezone", None) or getattr(
        booking, "instructor_tz_at_booking", None
    )
    if isinstance(lesson_tz, str) and lesson_tz:
        return lesson_tz
    return TimezoneService.DEFAULT_TIMEZONE


def reminder_candidate_window(
    now_utc: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return the UTC window that safely covers local-tomorrow reminders."""
    effective_now = now_utc or datetime.now(timezone.utc)
    return effective_now, effective_now + timedelta(hours=50)


def is_local_tomorrow_booking(booking: "Booking", *, now_utc: datetime | None = None) -> bool:
    """Return whether the booking is tomorrow in its authoritative local timezone."""
    effective_now = now_utc or datetime.now(timezone.utc)
    booking_start_utc = getattr(booking, "booking_start_utc", None)
    if not isinstance(booking_start_utc, datetime):
        return False

    reminder_timezone = resolve_booking_reminder_timezone(booking)
    local_now = TimezoneService.utc_to_local(effective_now, reminder_timezone)
    local_start = TimezoneService.utc_to_local(booking_start_utc, reminder_timezone)
    return local_start.date() == local_now.date() + timedelta(days=1)
