"""Tests targeting missed lines in app/utils/streaks.py.

Missed lines:
  43: buckets is empty after filtering (no valid datetimes)
  54: week_starts is empty after sorting
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.utils.streaks import compute_week_streak_local


def test_compute_week_streak_empty_completions() -> None:
    """Line 43: empty completions list => return 0."""
    now = datetime.now(timezone.utc)
    assert compute_week_streak_local([], now) == 0


def test_compute_week_streak_non_datetime_items() -> None:
    """Line 43: completions with non-datetime items => filters them out => 0."""
    now = datetime.now(timezone.utc)
    # Pass non-datetime items; they get filtered out
    result = compute_week_streak_local(
        ["not_a_datetime", 123, None],  # type: ignore[arg-type]
        now,
    )
    assert result == 0


def test_compute_week_streak_single_week() -> None:
    """Single completion in the current week => streak of 1."""
    now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)  # Wednesday
    completions = [datetime(2025, 1, 14, 10, 0, tzinfo=timezone.utc)]  # Tuesday
    assert compute_week_streak_local(completions, now) == 1


def test_compute_week_streak_gap_breaks_streak() -> None:
    """Two completions with a gap > 7+grace_days break the streak."""
    now = datetime(2025, 1, 29, 12, 0, tzinfo=timezone.utc)  # Wednesday
    completions = [
        datetime(2025, 1, 28, 10, 0, tzinfo=timezone.utc),  # This week
        datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),   # 4 weeks ago - gap too big
    ]
    result = compute_week_streak_local(completions, now, grace_days=1)
    # Should only count this week since there's a gap
    assert result == 1


def test_compute_week_streak_consecutive_weeks() -> None:
    """Two consecutive weeks => streak of 2."""
    now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)  # Wednesday Week 3
    completions = [
        datetime(2025, 1, 14, 10, 0, tzinfo=timezone.utc),  # Week 3
        datetime(2025, 1, 7, 10, 0, tzinfo=timezone.utc),   # Week 2
    ]
    result = compute_week_streak_local(completions, now, grace_days=1)
    assert result == 2


def test_compute_week_streak_grace_days_zero() -> None:
    """Line 54: grace_days=0, strict 7-day window."""
    now = datetime(2025, 1, 13, 12, 0, tzinfo=timezone.utc)  # Monday Week 3
    completions = [
        datetime(2025, 1, 13, 10, 0, tzinfo=timezone.utc),  # Week 3
        datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc),   # Week 2 (exactly 7 days)
    ]
    result = compute_week_streak_local(completions, now, grace_days=0)
    assert result == 2
