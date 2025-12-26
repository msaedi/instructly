from __future__ import annotations

from datetime import time


def time_to_minutes(t: time, *, is_end_time: bool = False) -> int:
    """
    Convert time to minutes since midnight.

    Args:
        t: Time object.
        is_end_time: If True, treat time(0, 0) as 1440 (end of day).

    Returns:
        Minutes since midnight (0-1440).
    """
    minutes = t.hour * 60 + t.minute
    if is_end_time and minutes == 0:
        return 24 * 60
    return minutes


def minutes_to_time_str(minutes: int) -> str:
    """
    Convert minutes since midnight to HH:MM.

    1440 is rendered as "24:00".
    """
    if not 0 <= minutes <= 24 * 60:
        raise ValueError(f"minutes out of range: {minutes}")
    if minutes == 24 * 60:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
