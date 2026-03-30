"""Search pipeline runtime — concurrency, budget, caching primitives."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Tuple


async def increment_inflight(
    lock: asyncio.Lock,
    get_count: Callable[[], int],
    set_count: Callable[[int], None],
) -> int:
    async with lock:
        next_count = get_count() + 1
        set_count(next_count)
        return next_count


async def decrement_inflight(
    lock: asyncio.Lock,
    get_count: Callable[[], int],
    set_count: Callable[[int], None],
) -> None:
    async with lock:
        set_count(max(0, get_count() - 1))


async def get_inflight_count(lock: asyncio.Lock, get_count: Callable[[], int]) -> int:
    async with lock:
        return get_count()


def compute_adaptive_budget(
    inflight: int,
    *,
    force_high_load: bool,
    get_config: Callable[[], Any],
) -> int:
    config = get_config()
    if force_high_load or inflight >= int(config.high_load_threshold):
        return int(config.high_load_budget_ms)
    return int(config.search_budget_ms)


def normalize_concurrency_limit(limit: int) -> int:
    return max(1, int(limit))


def get_cached_subcategory_filter_value(
    cache_key: str,
    *,
    cache: Dict[str, Tuple[float, Any]],
    lock: Any,
    ttl_seconds: int,
    monotonic: Callable[[], float],
) -> Tuple[bool, Any]:
    now = monotonic()
    with lock:
        cached = cache.get(cache_key)
        if cached is None:
            return False, None
        cached_at, value = cached
        if now - cached_at > ttl_seconds:
            cache.pop(cache_key, None)
            return False, None
        return True, value


def set_cached_subcategory_filter_value(
    cache_key: str,
    value: Any,
    *,
    cache: Dict[str, Tuple[float, Any]],
    lock: Any,
    ttl_seconds: int,
    max_entries: int,
    monotonic: Callable[[], float],
) -> None:
    now = monotonic()
    with lock:
        if len(cache) >= max_entries:
            expired_keys = [
                key
                for key, (cached_at, _cached_value) in cache.items()
                if now - cached_at > ttl_seconds
            ]
            for key in expired_keys:
                cache.pop(key, None)
            if len(cache) >= max_entries:
                oldest_entries = sorted(cache.items(), key=lambda item: item[1][0])
                trim_count = max(1, len(oldest_entries) // 2)
                for key, _entry in oldest_entries[:trim_count]:
                    cache.pop(key, None)
        cache[cache_key] = (now, value)
