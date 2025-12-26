"""
Centralized timezone handling for InstaInstru.

Rules:
- In-person lessons: Instructor's timezone (lesson happens at their location)
- Online lessons: Instructor's timezone (they set availability in their time)
- All storage: UTC
- All comparisons: UTC
- API responses: UTC with timezone context
"""

from datetime import date, datetime, time, timezone
from typing import Optional, Tuple

import pytz


class TimezoneService:
    """Handles all timezone conversions consistently."""

    DEFAULT_TIMEZONE = "America/New_York"

    @staticmethod
    def get_timezone(tz_str: Optional[str]) -> pytz.BaseTzInfo:
        """Get timezone object, with fallback to default."""
        try:
            return pytz.timezone(tz_str or TimezoneService.DEFAULT_TIMEZONE)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone(TimezoneService.DEFAULT_TIMEZONE)

    @staticmethod
    def local_to_utc(booking_date: date, start_time: time, timezone_str: str) -> datetime:
        """
        Convert local date/time to UTC.

        Uses the timezone rules valid on the booking_date (not today).
        This correctly handles DST transitions.

        Raises:
            ValueError: If the time doesn't exist (DST spring-forward gap)
        """
        tz = TimezoneService.get_timezone(timezone_str)
        naive_dt = datetime.combine(
            booking_date, start_time
        )  # utc-naive-ok: Intentionally naive for pytz.localize()

        try:
            # is_dst=None raises exception for ambiguous/nonexistent times
            local_dt = tz.localize(naive_dt, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            # Fall back (time exists twice) - use first occurrence
            local_dt = tz.localize(naive_dt, is_dst=True)
        except pytz.exceptions.NonExistentTimeError:
            raise ValueError(
                f"The time {start_time.strftime('%I:%M %p')} does not exist on "
                f"{booking_date} in {timezone_str} due to Daylight Saving Time. "
                f"Please select a different time."
            )

        return local_dt.astimezone(timezone.utc)

    @staticmethod
    def utc_to_local(utc_dt: datetime, timezone_str: str) -> datetime:
        """Convert UTC datetime to local timezone."""
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)

        tz = TimezoneService.get_timezone(timezone_str)
        return utc_dt.astimezone(tz)

    @staticmethod
    def get_lesson_timezone(instructor_timezone: Optional[str], is_online: bool = False) -> str:
        """
        Determine authoritative timezone for a lesson.

        Both in-person and online use instructor's timezone.
        (In-person: instructor's location. Online: instructor sets availability.)
        """
        _ = is_online
        return instructor_timezone or TimezoneService.DEFAULT_TIMEZONE

    @staticmethod
    def validate_time_exists(
        booking_date: date, start_time: time, timezone_str: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a time exists in a timezone on a given date.

        Returns:
            (is_valid, error_message)
        """
        tz = TimezoneService.get_timezone(timezone_str)
        naive_dt = datetime.combine(
            booking_date, start_time
        )  # utc-naive-ok: Intentionally naive for pytz.localize()

        try:
            tz.localize(naive_dt, is_dst=None)
            return (True, None)
        except pytz.exceptions.AmbiguousTimeError:
            # Time exists twice (fall back) - acceptable
            return (True, None)
        except pytz.exceptions.NonExistentTimeError:
            return (
                False,
                f"The time {start_time.strftime('%I:%M %p')} does not exist on "
                f"{booking_date} due to Daylight Saving Time. Please select a different time.",
            )

    @staticmethod
    def hours_until(booking_start_utc: datetime) -> float:
        """Calculate hours from now (UTC) until a booking start time (UTC)."""
        now_utc = datetime.now(timezone.utc)
        delta = booking_start_utc - now_utc
        return delta.total_seconds() / 3600

    @staticmethod
    def is_past(booking_start_utc: datetime) -> bool:
        """Check if a booking time is in the past."""
        return TimezoneService.hours_until(booking_start_utc) < 0

    @staticmethod
    def format_for_display(
        utc_dt: datetime, timezone_str: str, include_tz_abbrev: bool = True
    ) -> str:
        """
        Format a UTC datetime for display in a specific timezone.

        Returns: e.g., "Dec 25, 2025 at 2:00 PM EST"
        """
        local_dt = TimezoneService.utc_to_local(utc_dt, timezone_str)

        if include_tz_abbrev:
            return local_dt.strftime("%b %d, %Y at %I:%M %p %Z")
        return local_dt.strftime("%b %d, %Y at %I:%M %p")
