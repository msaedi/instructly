"""Notification policy helpers (quiet hours + daily caps)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any, Optional, Tuple

QUIET_HOURS_START = 22  # 10 PM local
QUIET_HOURS_END = 8  # 8 AM local
DAILY_CAP = 2


def _resolve_timezone(user: Any) -> Optional[tzinfo]:
    from app.core.timezone_utils import get_user_timezone

    return get_user_timezone(user)


def _build_local_day_key(user_id: str, local_dt: Optional[datetime]) -> str:
    if not local_dt:
        return ""
    return f"notif:{user_id}:{local_dt.strftime('%Y%m%d')}"


def _read_counter(cache_service: Any, key: str) -> int:
    if not cache_service or not key:
        return 0
    cached = cache_service.get(key)
    if isinstance(cached, (int, float)):
        return int(cached)
    if isinstance(cached, str) and cached.isdigit():
        return int(cached)
    return 0


def can_send_now(user: Any, now_utc: datetime, cache_service: Any) -> Tuple[bool, str, str]:
    """Return (allowed, reason, local_day_key)."""

    try:
        user_tz = _resolve_timezone(user)
    except Exception:
        user_tz = None

    if not user_tz:
        return False, "no_timezone", ""

    local_dt = now_utc.astimezone(user_tz)
    key = _build_local_day_key(getattr(user, "id", "unknown"), local_dt)
    hour = local_dt.hour
    if QUIET_HOURS_START <= hour or hour < QUIET_HOURS_END:
        return False, "quiet_hours", key

    count = _read_counter(cache_service, key)
    if count >= DAILY_CAP:
        return False, "daily_cap", key

    return True, "ok", key


def record_send(local_day_key: str, cache_service: Any, ttl_hours: int = 36) -> None:
    """Increment the per-user local-day counter."""

    if not cache_service or not local_day_key:
        return

    count = _read_counter(cache_service, local_day_key) + 1
    ttl_seconds = int(ttl_hours * 3600)
    cache_service.set(local_day_key, count, ttl=ttl_seconds)
