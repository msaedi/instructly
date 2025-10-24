from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.utils.streaks import compute_week_streak_local


def _make(dt_str: str, tz: str = "UTC") -> datetime:
    return datetime.fromisoformat(dt_str).replace(tzinfo=ZoneInfo(tz))


def test_week_streak_simple_consecutive_weeks():
    tz = ZoneInfo("UTC")
    base = datetime(2024, 1, 1, 10, 0, tzinfo=tz)
    completions = [
        base,
        base + timedelta(days=7),
        base + timedelta(days=14),
    ]
    streak = compute_week_streak_local(completions, completions[-1])
    assert streak == 3


def test_week_streak_with_grace_day_allowed():
    tz = ZoneInfo("UTC")
    base = datetime(2024, 1, 1, 10, 0, tzinfo=tz)
    completions = [
        base,
        base + timedelta(days=8),
        base + timedelta(days=16),
    ]
    streak = compute_week_streak_local(completions, completions[-1], grace_days=1)
    assert streak == 3


def test_week_streak_breaks_beyond_grace():
    tz = ZoneInfo("UTC")
    base = datetime(2024, 1, 1, 10, 0, tzinfo=tz)
    completions = [
        base,
        base + timedelta(days=9),
        base + timedelta(days=18),
    ]
    streak = compute_week_streak_local(completions, completions[-1], grace_days=1)
    assert streak == 1


def test_week_streak_handles_dst_transitions():
    tz = ZoneInfo("America/New_York")
    # Dates chosen around spring DST transition (second Sunday in March)
    completion1 = datetime(2024, 3, 3, 10, 0, tzinfo=tz)   # week before DST
    completion2 = datetime(2024, 3, 10, 10, 0, tzinfo=tz)  # DST day
    completion3 = datetime(2024, 3, 17, 10, 0, tzinfo=tz)  # week after DST

    completions = [completion1, completion2, completion3]
    streak = compute_week_streak_local(completions, completion3, grace_days=1)
    assert streak == 3
