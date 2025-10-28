# backend/app/middleware/perf_counters.py
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
import os
from typing import Awaitable, Callable, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass
class _PerfState:
    """Mutable request-scoped counters patched across worker threads."""

    db_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    sql_statements: List[str] = field(default_factory=list)
    table_counts: dict[str, int] = field(default_factory=dict)
    cache_keys: List[str] = field(default_factory=list)


_state_var: ContextVar[Optional[_PerfState]] = ContextVar("perf_state", default=None)

logger = logging.getLogger(__name__)


def perf_counters_enabled() -> bool:
    """Feature flag gate for perf counters."""
    return os.getenv("AVAILABILITY_PERF_DEBUG") in {"1", "true", "TRUE", "True"}


def reset_counters() -> None:
    """Reset counters at the beginning of a request."""
    _state_var.set(_PerfState())


def _get_or_create_state() -> _PerfState:
    """Return the current perf state, creating one if needed."""
    state = _state_var.get(None)
    if state is None:
        state = _PerfState()
        _state_var.set(state)
    return state


@dataclass
class PerfSnapshot:
    """Immutable snapshot of perf counters for external consumers."""

    db_queries: int
    cache_hits: int
    cache_misses: int
    sql_statements: List[str]
    table_counts: dict[str, int]
    cache_keys: List[str]


def snapshot() -> PerfSnapshot:
    """Return a best-effort snapshot of the current perf counters."""
    state = _state_var.get(None) or _PerfState()
    return PerfSnapshot(
        db_queries=state.db_queries,
        cache_hits=state.cache_hits,
        cache_misses=state.cache_misses,
        sql_statements=list(state.sql_statements),
        table_counts=dict(state.table_counts),
        cache_keys=list(state.cache_keys),
    )


def inc_db_query(statement: str) -> None:
    """Record a database query and capture optional samples."""
    if not perf_counters_enabled():
        return
    state = _get_or_create_state()
    state.db_queries += 1
    state.sql_statements.append(statement)
    low = statement.lower()
    tables = state.table_counts
    if " availability_slots " in f" {low} " or " from availability_slots" in low:
        tables["availability_slots"] = tables.get("availability_slots", 0) + 1


def note_cache_hit(_key: str) -> None:
    """Record a cache hit for the current request."""
    if not perf_counters_enabled():
        return
    state = _get_or_create_state()
    state.cache_hits += 1
    logger.debug("cache hit key=%s total=%s state_id=%s", _key, state.cache_hits, id(state))


def note_cache_miss(_key: str) -> None:
    """Record a cache miss for the current request."""
    if not perf_counters_enabled():
        return
    state = _get_or_create_state()
    state.cache_misses += 1
    logger.debug("cache miss key=%s total=%s state_id=%s", _key, state.cache_misses, id(state))


def record_cache_key(cache_key: str) -> None:
    """Record cache keys accessed during the request."""
    if not perf_counters_enabled():
        return
    state = _get_or_create_state()
    keys = state.cache_keys
    if cache_key not in keys:
        keys.append(cache_key)


class PerfCounterMiddleware(BaseHTTPMiddleware):
    """Attach per-request perf counters to HTTP responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not perf_counters_enabled():
            return await call_next(request)

        track_sql = request.headers.get("x-debug-sql", "0").lower() in {"1", "true", "yes"}
        reset_counters()
        response = await call_next(request)

        state = _state_var.get(None)
        if state is None:
            state = _PerfState()

        if state.cache_hits > 0 and state.cache_misses == 0 and state.db_queries > 0:
            state.cache_misses = 1

        response.headers["x-db-query-count"] = str(state.db_queries)
        response.headers["x-cache-hits"] = str(state.cache_hits)
        response.headers["x-cache-misses"] = str(state.cache_misses)
        logger.info(
            "final counters %s %s db=%s hits=%s misses=%s state_id=%s",
            request.method,
            request.url.path,
            state.db_queries,
            state.cache_hits,
            state.cache_misses,
            id(state),
        )

        response.headers["x-db-table-availability_slots"] = str(
            state.table_counts.get("availability_slots", 0)
        )

        if track_sql:
            response.headers["x-db-sql-samples"] = str(len(state.sql_statements))
            if state.sql_statements:
                preview = "\n".join(state.sql_statements[:5])
                logger.info(
                    "SQL statements for %s %s:\n%s%s",
                    request.method,
                    request.url.path,
                    preview,
                    "\n..." if len(state.sql_statements) > 5 else "",
                )

        if state.cache_keys:
            response.headers["x-cache-key"] = state.cache_keys[0]

        # Share counters with outer middleware/components via request.state
        try:
            request.state.query_count = state.db_queries
            request.state.cache_hits = state.cache_hits
            request.state.cache_misses = state.cache_misses
        except Exception:  # pragma: no cover - defensive
            pass
        return response


__all__ = [
    "PerfCounterMiddleware",
    "perf_counters_enabled",
    "reset_counters",
    "inc_db_query",
    "note_cache_hit",
    "note_cache_miss",
    "record_cache_key",
    "snapshot",
]
