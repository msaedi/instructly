# backend/app/middleware/perf_counters.py
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import logging
import os
from typing import Awaitable, Callable, List, Optional

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
_sql_statements: ContextVar[Optional[List[str]]] = ContextVar("perf_sql_statements", default=None)
_table_counts: ContextVar[Optional[dict[str, int]]] = ContextVar(
    "perf_sql_table_counts", default=None
)
_table_samples: ContextVar[Optional[dict[str, List[str]]]] = ContextVar(
    "perf_sql_table_samples", default=None
)

logger = logging.getLogger(__name__)


def perf_counters_enabled() -> bool:
    """Feature flag gate for perf counters."""
    return os.getenv("AVAILABILITY_PERF_DEBUG") in {"1", "true", "TRUE", "True"}


def reset_perf_counters(track_sql: bool = False) -> None:
    """Reset counters at the beginning of a request."""
    _perf_state.set(_PerfState())
    _sql_statements.set([] if track_sql else None)
    _table_counts.set({} if track_sql else None)
    _table_samples.set({} if track_sql else None)


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


def record_sql_statement(statement: str) -> None:
    """Record SQL text when request-level debug is active."""
    if not perf_counters_enabled():
        return
    statements = _sql_statements.get()
    if statements is None:
        return
    statements.append(statement)


def record_table_hit(table_name: str, statement: str | None = None) -> None:
    """Record that a statement touched a table."""
    if not perf_counters_enabled():
        return
    counts = _table_counts.get()
    if counts is None:
        return
    counts[table_name] = counts.get(table_name, 0) + 1
    samples = _table_samples.get()
    if samples is None or statement is None:
        return
    entries = samples.setdefault(table_name, [])
    if statement not in entries:
        entries.append(statement)


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

        track_sql = request.headers.get("x-debug-sql", "0").lower() in {"1", "true", "yes"}
        reset_perf_counters(track_sql=track_sql)
        response = await call_next(request)

        db_count, cache_hits, cache_misses = _current_counts()
        response.headers["x-db-query-count"] = str(db_count)
        response.headers["x-cache-hits"] = str(cache_hits)
        response.headers["x-cache-misses"] = str(cache_misses)

        statements = _sql_statements.get()
        if statements is not None:
            response.headers["x-db-sql-samples"] = str(len(statements))
            if statements:
                preview = "\n".join(statements[:5])
                logger.info(
                    "SQL statements for %s %s:\n%s%s",
                    request.method,
                    request.url.path,
                    preview,
                    "\n..." if len(statements) > 5 else "",
                )
            table_counts = _table_counts.get() or {}
            table_samples = _table_samples.get() or {}
            availability_hits = table_counts.get("availability_slots")
            if availability_hits is not None:
                response.headers["x-db-table-availability_slots"] = str(availability_hits)
                samples = table_samples.get("availability_slots", [])
                response.headers["x-db-table-availability_slots-samples"] = str(len(samples))
                if samples:
                    response.headers["x-db-table-availability_slots-sql"] = " || ".join(samples[:3])
                    logger.info(
                        "availability_slots statements for %s %s:\n%s",
                        request.method,
                        request.url.path,
                        "\n".join(samples),
                    )
        return response


__all__ = [
    "PerfCounterMiddleware",
    "perf_counters_enabled",
    "increment_db_queries",
    "record_cache_hit",
    "record_cache_miss",
    "record_sql_statement",
    "record_table_hit",
    "reset_perf_counters",
]
