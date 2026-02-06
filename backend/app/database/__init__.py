"""
Database engine, session factory, and metadata shared across the application.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, Generator, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeMeta, Session, declarative_base

from app.middleware.perf_counters import inc_db_query

from .engines import get_api_engine, get_engine_for_role, get_scheduler_engine, get_worker_engine
from .sessions import (
    APISessionLocal,  # noqa: F401
    SchedulerSessionLocal,  # noqa: F401
    SessionLocal,  # noqa: F401
    WorkerSessionLocal,  # noqa: F401
    get_api_session,  # noqa: F401
    get_db,  # noqa: F401
    get_db_session,  # noqa: F401
    get_scheduler_session,  # noqa: F401
    get_worker_session,  # noqa: F401
    init_session_factories,  # noqa: F401
)

logger = logging.getLogger(__name__)


engine: Engine = get_engine_for_role()

# Register SQLAlchemy engine for OTel instrumentation (if enabled).
from app.monitoring.otel import instrument_database

instrument_database(engine)


@event.listens_for(Engine, "after_cursor_execute", retval=False)
def _perf_after_cursor_execute(
    conn: Engine,
    cursor: Any,
    statement: str,
    params: Any,
    context: Any,
    executemany: bool,
) -> None:
    """Track executed queries for perf instrumentation."""
    inc_db_query(statement)


Base: DeclarativeMeta = declarative_base()


def get_db_with_retry(max_attempts: int = 2) -> Generator[Session, None, None]:
    """Get database session with automatic retry on transient Supabase disconnects.

    This is a more resilient version of get_db() that handles the case where
    Supabase/Supavisor drops SSL connections unexpectedly. It will retry
    once with a fresh session if the initial checkout fails.

    Use this for critical endpoints where you want higher resilience against
    infrastructure hiccups, at the cost of slightly higher latency on retries.

    Args:
        max_attempts: Maximum number of connection attempts (default 2)

    Yields:
        SQLAlchemy Session
    """
    attempt = 1
    last_exception = None

    while attempt <= max_attempts:
        db = None
        try:
            db = SessionLocal()
            # Force a connection checkout to detect stale connections early
            db.connection()
            yield db
            db.commit()
            return  # Success, exit the retry loop
        except OperationalError as exc:
            last_exception = exc
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                try:
                    db.close()
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
            # Check if this is a retryable error
            if attempt < max_attempts and _is_retryable_db_error(exc):
                delay = _retry_delay(attempt)
                logger.warning(
                    "Transient DB failure in get_db, retrying",
                    extra={
                        "event": "get_db_retry",
                        "attempt": attempt,
                        "delay": delay,
                        "error": str(exc),
                    },
                )
                time.sleep(delay)
                attempt += 1
                continue

            # Not retryable or max attempts reached
            raise
        except Exception:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                try:
                    db.close()
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


def _pool_status_from_engine(engine_obj: Engine) -> dict[str, int | float]:
    pool = engine_obj.pool
    size = int(pool.size())
    max_overflow = int(getattr(pool, "_max_overflow", 0) or 0)
    max_capacity = size + max_overflow
    checked_out = int(pool.checkedout())
    checked_in = int(pool.checkedin())
    overflow_in_use = int(pool.overflow())
    utilization_pct = round(100 * checked_out / max_capacity, 1) if max_capacity > 0 else 0.0
    return {
        "size": size,
        "max_overflow": max_overflow,
        "max_capacity": max_capacity,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow_in_use": overflow_in_use,
        "utilization_pct": utilization_pct,
    }


ROLE_POOLS: dict[str, list[str]] = {
    "api": ["api"],
    "worker": ["worker"],
    "scheduler": ["scheduler"],
    "all": ["api", "worker", "scheduler"],
}


def get_db_pool_status(pool_name: str | None = None) -> dict[str, int | float]:
    """Get current database pool statistics."""
    if pool_name:
        normalized = pool_name.strip().lower()
        if normalized == "worker":
            return _pool_status_from_engine(get_worker_engine())
        if normalized == "scheduler":
            return _pool_status_from_engine(get_scheduler_engine())
        return _pool_status_from_engine(get_api_engine())
    return _pool_status_from_engine(get_engine_for_role())


def get_db_pool_statuses() -> dict[str, dict[str, int | float]]:
    """Get pool statistics for all workload pools."""
    return {
        "api": _pool_status_from_engine(get_api_engine()),
        "worker": _pool_status_from_engine(get_worker_engine()),
        "scheduler": _pool_status_from_engine(get_scheduler_engine()),
    }


def get_pool_status_for_role(role: str | None = None) -> dict[str, dict[str, int | float]]:
    """Get pool statistics for the configured service role."""
    from app.core.config import settings

    effective_role = (role or settings.service_role or "").strip().lower()
    if not effective_role:
        effective_role = "api"

    pools_to_report = ROLE_POOLS.get(effective_role, ROLE_POOLS["api"])
    engine_getters = {
        "api": get_api_engine,
        "worker": get_worker_engine,
        "scheduler": get_scheduler_engine,
    }
    return {
        pool_name: _pool_status_from_engine(engine_getters[pool_name]())
        for pool_name in pools_to_report
        if pool_name in engine_getters
    }


T = TypeVar("T")
# Only target the transient disconnect errors Supavisor emits when pgbouncer restarts.
_RETRYABLE_ERROR_SNIPPETS = (
    "server closed the connection",
    "ssl connection has been closed unexpectedly",
)


def _is_retryable_db_error(exc: OperationalError) -> bool:
    message = str(exc).lower()
    return any(snippet in message for snippet in _RETRYABLE_ERROR_SNIPPETS)


def _retry_delay(attempt: int) -> float:
    base = 0.1 * (2 ** (attempt - 1))
    jitter_max_ms = int(0.05 * attempt * 1000)
    jitter = secrets.randbelow(jitter_max_ms + 1) / 1000.0
    return base + jitter


def with_db_retry(op_name: str, func: Callable[[], T], *, max_attempts: int = 3) -> T:
    """
    Execute a DB operation with retries for transient Supabase/pooler disconnects.
    """

    attempt = 1
    while True:
        try:
            return func()
        except OperationalError as exc:
            if attempt >= max_attempts or not _is_retryable_db_error(exc):
                raise

            delay = _retry_delay(attempt)
            logger.warning(
                "Transient DB failure detected, retrying",
                extra={
                    "event": "db_retry",
                    "op": op_name,
                    "attempt": attempt,
                    "delay": delay,
                    "error": str(exc),
                },
            )
            time.sleep(delay)
            attempt += 1


async def with_db_retry_async(
    op_name: str,
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
) -> T:
    """Async variant of with_db_retry for coroutine-based DB interactions."""

    attempt = 1
    while True:
        try:
            return await func()
        except OperationalError as exc:
            if attempt >= max_attempts or not _is_retryable_db_error(exc):
                raise
            delay = _retry_delay(attempt)
            logger.warning(
                "Transient DB failure detected, retrying",
                extra={
                    "event": "db_retry",
                    "op": op_name,
                    "attempt": attempt,
                    "delay": delay,
                    "error": str(exc),
                },
            )
            await asyncio.sleep(delay)
            attempt += 1


__all__ = [
    "Base",
    "APISessionLocal",
    "WorkerSessionLocal",
    "SchedulerSessionLocal",
    "SessionLocal",
    "engine",
    "get_db",
    "get_db_session",
    "get_db_with_retry",
    "get_db_pool_status",
    "get_db_pool_statuses",
    "get_pool_status_for_role",
    "get_api_engine",
    "get_worker_engine",
    "get_scheduler_engine",
    "get_engine_for_role",
    "get_api_session",
    "get_worker_session",
    "get_scheduler_session",
    "init_session_factories",
    "ROLE_POOLS",
    "with_db_retry",
    "with_db_retry_async",
]
