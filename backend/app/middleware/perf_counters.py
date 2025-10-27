# backend/app/middleware/perf_counters.py
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import os
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass
class _PerfState:
    db_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


# Context variable tracks the mutable state for the current request.
_perf_state: ContextVar[_PerfState] = ContextVar("perf_state", default=_PerfState())


def perf_counters_enabled() -> bool:
    """Feature flag gate for perf counters."""
    return os.getenv("AVAILABILITY_PERF_DEBUG") in {"1", "true", "TRUE", "True"}


def reset_perf_counters() -> None:
    """Reset counters at the beginning of a request."""
    _perf_state.set(_PerfState())


def increment_db_queries() -> None:
    """Increment the DB query counter when instrumentation is enabled."""
    if not perf_counters_enabled():
        return
    state = _perf_state.get()
    state.db_queries += 1


def record_cache_hit() -> None:
    """Record a cache hit for the current request."""
    if not perf_counters_enabled():
        return
    state = _perf_state.get()
    state.cache_hits += 1


def record_cache_miss() -> None:
    """Record a cache miss for the current request."""
    if not perf_counters_enabled():
        return
    state = _perf_state.get()
    state.cache_misses += 1


def _current_counts() -> tuple[int, int, int]:
    """Return the current counter snapshot."""
    state = _perf_state.get()
    return (state.db_queries, state.cache_hits, state.cache_misses)


class PerfCounterMiddleware(BaseHTTPMiddleware):
    """Attach per-request perf counters to HTTP responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not perf_counters_enabled():
            return await call_next(request)

        reset_perf_counters()
        response = await call_next(request)

        db_count, cache_hits, cache_misses = _current_counts()
        response.headers["x-db-query-count"] = str(db_count)
        response.headers["x-cache-hits"] = str(cache_hits)
        response.headers["x-cache-misses"] = str(cache_misses)
        return response


__all__ = [
    "PerfCounterMiddleware",
    "perf_counters_enabled",
    "increment_db_queries",
    "record_cache_hit",
    "record_cache_miss",
    "reset_perf_counters",
]
