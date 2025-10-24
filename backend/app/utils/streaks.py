"""
Utilities for computing weekly lesson streaks in a user's local timezone.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List


def compute_week_streak_local(
    completions_local: Iterable[datetime],
    now_local: datetime,
    grace_days: int = 1,
) -> int:
    """
    Return the count of consecutive weekly completions up to the week of now_local.

    Args:
        completions_local: Iterable of timezone-aware datetimes in the user's timezone.
        now_local: The completion datetime (also tz-aware) triggering the calculation.
        grace_days: Additional days allowed beyond 7 between weekly completions.

    Returns:
        Length of the consecutive weekly streak including the week of now_local.
    """
    completions: List[datetime] = [dt for dt in completions_local if isinstance(dt, datetime)]
    if not completions:
        return 0

    # Bucket completions by ISO week start (Monday 00:00 in local tz),
    # keeping the latest completion per week.
    buckets: dict[datetime, datetime] = {}
    for dt in completions:
        week_start = (dt - timedelta(days=dt.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        current = buckets.get(week_start)
        if current is None or dt > current:
            buckets[week_start] = dt

    if not buckets:
        return 0

    # Ensure current week is represented (especially if now_local is not in the original list).
    current_week_start = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if current_week_start not in buckets:
        buckets[current_week_start] = now_local

    week_starts = sorted(buckets.keys(), reverse=True)
    if not week_starts:
        return 0

    streak = 1
    previous_dt = buckets[week_starts[0]]
    max_gap = timedelta(days=7 + max(grace_days, 0))

    for week_start in week_starts[1:]:
        current_dt = buckets[week_start]
        if previous_dt - current_dt <= max_gap:
            streak += 1
            previous_dt = current_dt
        else:
            break

    return streak


__all__ = ["compute_week_streak_local"]
