"""Video domain utilities shared across service, tasks, and schemas."""

from __future__ import annotations

from datetime import datetime, timedelta

# Minutes before scheduled start that participants can join the video room.
JOIN_WINDOW_EARLY_MINUTES: int = 5


def compute_join_opens_at(booking_start_utc: datetime) -> datetime:
    """Return the earliest allowed join time for a scheduled lesson."""
    return booking_start_utc - timedelta(minutes=JOIN_WINDOW_EARLY_MINUTES)


def compute_join_closes_at(
    booking_start_utc: datetime,
    duration_minutes: int | float,
    booking_end_utc: datetime | None = None,
) -> datetime:
    """Return the last allowed join time for a scheduled lesson."""
    if isinstance(booking_end_utc, datetime):
        return booking_end_utc
    return booking_start_utc + timedelta(minutes=duration_minutes)
