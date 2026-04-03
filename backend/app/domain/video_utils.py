"""Video domain utilities shared across service, tasks, and schemas."""

from __future__ import annotations

from datetime import datetime, timedelta

MAX_GRACE_MINUTES: float = 15
# Minutes before scheduled start that participants can join the video room.
JOIN_WINDOW_EARLY_MINUTES: int = 5


def compute_join_opens_at(booking_start_utc: datetime) -> datetime:
    """Return the earliest allowed join time for a scheduled lesson."""
    return booking_start_utc - timedelta(minutes=JOIN_WINDOW_EARLY_MINUTES)


def compute_join_closes_at(
    booking_start_utc: datetime,
    duration_minutes: int,
    booking_end_utc: datetime | None = None,
) -> datetime:
    """Return the last allowed join time for a scheduled lesson."""
    if isinstance(booking_end_utc, datetime):
        return booking_end_utc
    return booking_start_utc + timedelta(minutes=duration_minutes)


def compute_grace_minutes(duration_minutes: int) -> float:
    """Compute the no-show grace period for a video lesson.

    Returns min(25% of lesson duration, 15 minutes).
    """
    return min(duration_minutes * 0.25, MAX_GRACE_MINUTES)
