"""Video domain utilities shared across service, tasks, and schemas."""

from __future__ import annotations

MAX_GRACE_MINUTES: float = 15


def compute_grace_minutes(duration_minutes: int) -> float:
    """Compute the join-window grace period for a video lesson.

    Returns min(25% of lesson duration, 15 minutes).
    """
    return min(duration_minutes * 0.25, MAX_GRACE_MINUTES)
