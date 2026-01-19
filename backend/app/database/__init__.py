"""
Database engine, session factory, and metadata shared across the application.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, Generator, TypeVar

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeMeta, Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.middleware.perf_counters import inc_db_query

# Import production config if in production
if settings.environment == "production":
    from app.core.config_production import DATABASE_POOL_CONFIG
else:
    DATABASE_POOL_CONFIG = None

logger = logging.getLogger(__name__)

# Engine tuning for Supabase/Supavisor:
# - All traffic goes through the pooled (pgbouncer) endpoint on port 6543.
# - pool_pre_ping + pool_recycle keep stale pooled connections from hanging around
#   after Supavisor restarts a pod.
# - keepalives ensure idle sockets stay registered with Supabase's load balancer.
# - statement_timeout caps runaway queries so the API layer recovers quickly.
_DEFAULT_CONNECT_ARGS: dict[str, Any] = {
    "sslmode": "require",
    "keepalives": 1,
    # Aggressive keepalive to detect dead connections faster
    "keepalives_idle": 15,
    "keepalives_interval": 5,
    "keepalives_count": 3,
    # Statement timeout: 15s (was 30s) - fail fast on slow queries
    "options": "-c statement_timeout=15000",
    # Connection timeout: 5s (was 10s) - fail fast when pool is exhausted
    "connect_timeout": 5,
    "application_name": "instainstru_render",
}

_DEFAULT_POOL_KWARGS: dict[str, Any] = {
    # AGGRESSIVE pool sizing for Supabase transaction pooler (port 6543):
    # - Supabase Pro tier: ~60 connections on transaction pooler
    # - With 2 uvicorn workers: (pool_size + max_overflow) × 2 must be < 60
    # - CONSERVATIVE config: 3 + 5 = 8 per worker × 2 = 16 total (73% headroom)
    # - Extra headroom needed for SSE manual sessions and Celery workers
    "pool_size": 3,
    "max_overflow": 5,
    # Fail FAST when pool exhausted - return 503 instead of blocking for seconds
    # Under load, waiting for connections causes cascade failures
    "pool_timeout": 2,
    # Supavisor Transaction Mode (port 6543) times out idle connections at ~60s.
    # Recycle at 30s to stay well ahead of Supabase's timeout and avoid stale connections.
    "pool_recycle": 30,
    "pool_pre_ping": True,
    # LIFO: Reuse most recently used connection (more likely to be healthy)
    "pool_use_lifo": True,
    "future": True,
}


def _should_require_ssl(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""
    normalized = hostname.lower()
    return "supabase" in normalized or normalized.endswith(".supabase.net")


def _build_engine_kwargs(db_url: str) -> dict[str, Any]:
    """Merge runtime + production overrides for the SQLAlchemy engine."""

    kwargs = dict(_DEFAULT_POOL_KWARGS)
    connect_args = dict(_DEFAULT_CONNECT_ARGS)

    if DATABASE_POOL_CONFIG:
        # Production mode: use explicit config from config_production.py
        config = dict(DATABASE_POOL_CONFIG)
        supplied_connect_args = config.pop("connect_args", {})
        kwargs.update(config)
        connect_args.update(supplied_connect_args or {})
    elif not _should_require_ssl(db_url):
        # Local development (non-Supabase): use larger pool since local PostgreSQL
        # has no connection limits. The instructor dashboard makes 10+ parallel
        # requests which exhaust the conservative Supabase-friendly pool (3+5=8).
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20

    if not _should_require_ssl(db_url):
        connect_args.pop("sslmode", None)

    kwargs["connect_args"] = connect_args
    return kwargs


db_url = settings.get_database_url()
# DatabaseConfig resolves to the Supabase pooled endpoint (Supavisor/pgbouncer on 6543),
# so every connection here is multiplexed through Supabase's pooler.
engine: Engine = create_engine(db_url, poolclass=QueuePool, **_build_engine_kwargs(db_url))


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


# Log pool events for monitoring
@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection: Any, connection_record: Any) -> None:
    connection_record.info["connect_time"] = datetime.now(timezone.utc)
    logger.debug("Database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection: Any, connection_record: Any, connection_proxy: Any) -> None:
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection: Any, connection_record: Any) -> None:
    logger.debug("Connection returned to pool")


@event.listens_for(engine, "invalidate")
def receive_invalidate(dbapi_connection: Any, connection_record: Any, exception: Any) -> None:
    """Handle pool connection invalidation (SSL drops, Supabase disconnects).

    When Supabase/Supavisor drops a connection, SQLAlchemy invalidates it.
    This handler logs the event and ensures metrics are tracked for observability.
    """
    logger.warning(
        "Connection invalidated",
        extra={
            "event": "db_connection_invalidated",
            "exception": str(exception) if exception else "unknown",
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
        },
    )


@event.listens_for(engine, "soft_invalidate")
def receive_soft_invalidate(dbapi_connection: Any, connection_record: Any, exception: Any) -> None:
    """Handle soft invalidation (connection recycled due to age)."""
    logger.debug("Connection soft invalidated (recycled)")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

Base: DeclarativeMeta = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Get database session with proper cleanup."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for short-lived DB operations.

    Prefer this over storing SQLAlchemy sessions on long-lived service objects.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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


def get_db_pool_status() -> dict[str, int]:
    """Get current database pool statistics."""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "total": pool.size() + pool.overflow(),
        "overflow": pool.overflow(),
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
    "SessionLocal",
    "engine",
    "get_db",
    "get_db_with_retry",
    "get_db_pool_status",
    "with_db_retry",
    "with_db_retry_async",
]
