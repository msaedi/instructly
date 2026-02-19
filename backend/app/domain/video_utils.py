"""Video domain utilities shared across service, tasks, and schemas."""

from __future__ import annotations

MAX_GRACE_MINUTES: float = 15


def compute_grace_minutes(duration_minutes: int) -> float:
    """Compute the join-window grace period for a video lesson.

    TESTING-ONLY: revert before production.
    Original formula: min(duration * 0.25, 15).
    Testing formula: max(duration - 5, duration * 0.25) — joinable until 5 min before lesson end.
    """
    return max(
        duration_minutes - 5, duration_minutes * 0.25
    )  # TESTING-ONLY: revert before production
