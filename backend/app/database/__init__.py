"""
Database engine, session factory, and metadata shared across the application.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import random
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
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
    "options": "-c statement_timeout=30000",
    "connect_timeout": 10,
    "application_name": "instainstru_backend",
}

_DEFAULT_POOL_KWARGS: dict[str, Any] = {
    # Conservative pool sizing to stay under Supabase pooler limits:
    # - Supabase Pro tier: ~60 connections on transaction pooler (port 6543)
    # - With 2 uvicorn workers: (pool_size + max_overflow) × 2 must be < 60
    # - Safe config: 5 + 10 = 15 per worker × 2 = 30 total (50% headroom)
    "pool_size": 5,
    "max_overflow": 10,
    # Fail-fast when pool exhausted (better than blocking for 10s during load)
    "pool_timeout": 5,
    # Supavisor Transaction Mode (port 6543) times out idle connections at ~60s.
    # Set pool_recycle to 55s to ensure connections are refreshed before timeout.
    "pool_recycle": 55,
    "pool_pre_ping": True,
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
        config = dict(DATABASE_POOL_CONFIG)
        supplied_connect_args = config.pop("connect_args", {})
        kwargs.update(config)
        connect_args.update(supplied_connect_args or {})

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
    connection_record.info["connect_time"] = datetime.now()
    logger.debug("Database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection: Any, connection_record: Any, connection_proxy: Any) -> None:
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection: Any, connection_record: Any) -> None:
    logger.debug("Connection returned to pool")


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
    return base + random.uniform(0, 0.05 * attempt)


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
    "get_db_pool_status",
    "with_db_retry",
    "with_db_retry_async",
]
