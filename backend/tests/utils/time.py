from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Tuple

SAFE_EPS_MINUTES = 5


def now_trimmed(base: datetime | None = None) -> datetime:
    dt = base or datetime.now()
    return dt.replace(second=0, microsecond=0)


def start_within_24h(base: datetime | None = None, hours: int = 2, minutes: int = SAFE_EPS_MINUTES) -> datetime:
    n = now_trimmed(base)
    start = n + timedelta(hours=hours, minutes=minutes)
    # avoid midnight-wrap for typical +1h durations
    if (start + timedelta(hours=1)).date() != start.date():
        start = datetime.combine((n + timedelta(days=1)).date(), time(10, 0))
    return start


def start_beyond_24h(base: datetime | None = None, hours: int = 26, minutes: int = SAFE_EPS_MINUTES) -> datetime:
    n = now_trimmed(base)
    start = n + timedelta(hours=hours, minutes=minutes)
    # +26h rarely wraps; keep as-is
    return start


def start_just_under_24h(base: datetime | None = None, minutes: int = 1) -> datetime:
    n = now_trimmed(base)
    candidate = n + timedelta(hours=24) - timedelta(minutes=minutes)
    # If end would wrap past midnight, move earlier to keep end same-day
    if (candidate + timedelta(hours=1)).date() != candidate.date():
        candidate = n + timedelta(hours=22)
    return candidate


def start_just_over_24h(base: datetime | None = None, minutes: int = 1) -> datetime:
    n = now_trimmed(base)
    candidate = n + timedelta(hours=24, minutes=minutes)
    # If end would wrap past midnight, move further out (still >24h)
    if (candidate + timedelta(hours=1)).date() != candidate.date():
        candidate = n + timedelta(hours=26)
    return candidate


def booking_fields_from_start(start: datetime, duration_minutes: int = 60) -> Tuple[date, time, time]:
    end = start + timedelta(minutes=duration_minutes)
    return start.date(), start.time(), end.time()
