"""Search pipeline runtime — concurrency, budget, caching, and perf primitives."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Callable, Dict, Tuple

from app.services.search import config as config_module

_PERF_LOG_ENABLED = os.getenv("NL_SEARCH_PERF_LOG") == "1"
_PERF_LOG_SLOW_MS = int(os.getenv("NL_SEARCH_PERF_LOG_SLOW_MS", "0"))

_search_inflight_lock = asyncio.Lock()
_search_inflight_requests = 0

SUBCATEGORY_FILTER_CACHE_TTL_SECONDS = max(
    60,
    int(os.getenv("NL_SEARCH_SUBCATEGORY_FILTER_CACHE_TTL_SECONDS", "180")),
)
SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES = 512
_subcategory_filter_cache: Dict[str, Tuple[float, Any]] = {}
_subcategory_filter_cache_lock = threading.Lock()


def _get_inflight_count_value() -> int:
    return _search_inflight_requests


def _set_inflight_count_value(value: int) -> None:
    global _search_inflight_requests
    _search_inflight_requests = value


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


def _get_adaptive_budget(inflight: int, *, force_high_load: bool = False) -> int:
    return compute_adaptive_budget(
        inflight,
        force_high_load=force_high_load,
        get_config=config_module.get_search_config,
    )


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


async def _increment_search_inflight() -> int:
    return await increment_inflight(
        _search_inflight_lock,
        get_count=_get_inflight_count_value,
        set_count=_set_inflight_count_value,
    )


async def _decrement_search_inflight() -> None:
    await decrement_inflight(
        _search_inflight_lock,
        get_count=_get_inflight_count_value,
        set_count=_set_inflight_count_value,
    )


async def get_search_inflight_count() -> int:
    return await get_inflight_count(_search_inflight_lock, _get_inflight_count_value)


async def set_uncached_search_concurrency_limit(limit: int) -> int:
    return normalize_concurrency_limit(limit)


def _get_cached_subcategory_filter_value(cache_key: str) -> Tuple[bool, Any]:
    return get_cached_subcategory_filter_value(
        cache_key,
        cache=_subcategory_filter_cache,
        lock=_subcategory_filter_cache_lock,
        ttl_seconds=SUBCATEGORY_FILTER_CACHE_TTL_SECONDS,
        monotonic=time.monotonic,
    )


def _set_cached_subcategory_filter_value(cache_key: str, value: Any) -> None:
    set_cached_subcategory_filter_value(
        cache_key,
        value,
        cache=_subcategory_filter_cache,
        lock=_subcategory_filter_cache_lock,
        ttl_seconds=SUBCATEGORY_FILTER_CACHE_TTL_SECONDS,
        max_entries=SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES,
        monotonic=time.monotonic,
    )
