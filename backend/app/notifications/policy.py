"""Notification policy helpers (quiet hours + daily caps)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from app.core.timezone_utils import get_user_timezone

QUIET_HOURS_START = 22  # 10 PM local
QUIET_HOURS_END = 8  # 8 AM local
DAILY_CAP = 2


def _build_local_day_key(user_id: str, local_dt: Optional[datetime]) -> str:
    date_part = local_dt.strftime("%Y%m%d") if local_dt else "unknown"
    return f"notif:{user_id}:{date_part}"


def can_send_now(user, now_utc: datetime, cache_service) -> Tuple[bool, str, str]:
    """Return (allowed, reason, local_day_key)."""

    try:
        user_tz = get_user_timezone(user)
    except Exception:
        user_tz = None

    if not user_tz:
        key = _build_local_day_key(getattr(user, "id", "unknown"), None)
        return False, "no_timezone", key

    local_dt = now_utc.astimezone(user_tz)
    key = _build_local_day_key(getattr(user, "id", "unknown"), local_dt)
    hour = local_dt.hour
    if QUIET_HOURS_START <= hour or hour < QUIET_HOURS_END:
        return False, "quiet_hours", key

    current_count = 0
    if cache_service:
        cached = cache_service.get(key)
        if isinstance(cached, (int, float)):
            current_count = int(cached)
        elif isinstance(cached, str) and cached.isdigit():
            current_count = int(cached)

    if current_count >= DAILY_CAP:
        return False, "daily_cap", key

    return True, "ok", key


def record_send(local_day_key: str, cache_service, ttl_hours: int = 36) -> None:
    """Increment the per-user local-day counter."""

    if not cache_service or not local_day_key:
        return

    cached = cache_service.get(local_day_key)
    if isinstance(cached, (int, float)):
        count = int(cached) + 1
    elif isinstance(cached, str) and cached.isdigit():
        count = int(cached) + 1
    else:
        count = 1

    ttl_seconds = int(ttl_hours * 3600)
    cache_service.set(local_day_key, count, ttl=ttl_seconds)
