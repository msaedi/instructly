"""Database engine factories for workload-specific pools."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.pool import QueuePool

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_CONNECT_ARGS: dict[str, Any] = {
    "sslmode": "require",
    "keepalives": 1,
    "keepalives_idle": 15,
    "keepalives_interval": 5,
    "keepalives_count": 3,
    "connect_timeout": 5,
    "application_name": "instainstru_render",
}


def _should_require_ssl(url: str) -> bool:
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""
    normalized = hostname.lower()
    return "supabase" in normalized or normalized.endswith(".supabase.net")


def _pool_recycle_seconds() -> int:
    # Supavisor Transaction Mode times out idle connections at ~60s.
    return 45 if settings.environment == "production" else 30


def _build_connect_args(
    *,
    db_url: str,
    statement_timeout_ms: int,
    connect_timeout: int,
) -> dict[str, Any]:
    args = dict(_BASE_CONNECT_ARGS)
    args["connect_timeout"] = connect_timeout
    args["options"] = f"-c statement_timeout={statement_timeout_ms}"
    if not _should_require_ssl(db_url):
        args.pop("sslmode", None)
    return args


def _add_pool_events(engine: Engine, pool_name: str) -> None:
    @event.listens_for(engine, "connect")  # type: ignore[untyped-decorator]
    def _on_connect(_dbapi_connection: Any, _connection_record: Any) -> None:
        logger.info("[%s] Database connection established", pool_name)

    @event.listens_for(engine, "checkout")  # type: ignore[untyped-decorator]
    def _on_checkout(
        dbapi_connection: Any, _connection_record: Any, _connection_proxy: Any
    ) -> None:
        logger.debug("[%s] Connection checked out from pool", pool_name)
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        except Exception as exc:
            raise DisconnectionError("Connection ping failed") from exc

    @event.listens_for(engine, "checkin")  # type: ignore[untyped-decorator]
    def _on_checkin(_dbapi_connection: Any, _connection_record: Any) -> None:
        logger.debug("[%s] Connection returned to pool", pool_name)

    @event.listens_for(engine, "invalidate")  # type: ignore[untyped-decorator]
    def _on_invalidate(_dbapi_connection: Any, _connection_record: Any, exception: Any) -> None:
        logger.warning(
            "[%s] Connection invalidated",
            pool_name,
            extra={
                "event": "db_connection_invalidated",
                "exception": str(exception) if exception else "unknown",
                "pool_size": engine.pool.size(),
                "checked_out": engine.pool.checkedout(),
            },
        )

    @event.listens_for(engine, "soft_invalidate")  # type: ignore[untyped-decorator]
    def _on_soft_invalidate(
        _dbapi_connection: Any, _connection_record: Any, _exception: Any
    ) -> None:
        logger.debug("[%s] Connection soft invalidated (recycled)", pool_name)


def _create_engine(
    *,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    statement_timeout_ms: int,
    connect_timeout: int,
    pool_name: str,
) -> Engine:
    db_url = settings.get_database_url()
    engine = create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=_pool_recycle_seconds(),
        pool_pre_ping=True,
        pool_use_lifo=True,
        future=True,
        connect_args=_build_connect_args(
            db_url=db_url,
            statement_timeout_ms=statement_timeout_ms,
            connect_timeout=connect_timeout,
        ),
    )
    _add_pool_events(engine, pool_name)
    return engine


_api_engine: Engine | None = None
_worker_engine: Engine | None = None
_scheduler_engine: Engine | None = None


def create_api_engine() -> Engine:
    return _create_engine(
        pool_size=settings.db_api_pool_size,
        max_overflow=settings.db_api_max_overflow,
        pool_timeout=settings.db_api_pool_timeout,
        statement_timeout_ms=30000,
        connect_timeout=5,
        pool_name="API",
    )


def create_worker_engine() -> Engine:
    return _create_engine(
        pool_size=settings.db_worker_pool_size,
        max_overflow=settings.db_worker_max_overflow,
        pool_timeout=settings.db_worker_pool_timeout,
        statement_timeout_ms=120000,
        connect_timeout=10,
        pool_name="Worker",
    )


def create_scheduler_engine() -> Engine:
    raw_env = os.getenv("DB_SCHEDULER_POOL_SIZE", "NOT_SET")
    logger.info(
        "Scheduler pool config: DB_SCHEDULER_POOL_SIZE env=%s, "
        "settings.db_scheduler_pool_size=%s, settings.db_scheduler_max_overflow=%s, "
        "settings.db_scheduler_pool_timeout=%s",
        raw_env,
        settings.db_scheduler_pool_size,
        settings.db_scheduler_max_overflow,
        settings.db_scheduler_pool_timeout,
    )
    return _create_engine(
        pool_size=settings.db_scheduler_pool_size,
        max_overflow=settings.db_scheduler_max_overflow,
        pool_timeout=settings.db_scheduler_pool_timeout,
        statement_timeout_ms=15000,
        connect_timeout=5,
        pool_name="Scheduler",
    )


def get_api_engine() -> Engine:
    global _api_engine
    if _api_engine is None:
        _api_engine = create_api_engine()
    return _api_engine


def get_worker_engine() -> Engine:
    global _worker_engine
    if _worker_engine is None:
        _worker_engine = create_worker_engine()
    return _worker_engine


def get_scheduler_engine() -> Engine:
    global _scheduler_engine
    if _scheduler_engine is None:
        _scheduler_engine = create_scheduler_engine()
    return _scheduler_engine


def get_engine_for_role(role: str | None = None) -> Engine:
    role_value = (role or os.getenv("DB_POOL_ROLE") or "api").strip().lower()
    if role_value == "worker":
        return get_worker_engine()
    if role_value == "scheduler":
        return get_scheduler_engine()
    return get_api_engine()


__all__ = [
    "create_api_engine",
    "create_worker_engine",
    "create_scheduler_engine",
    "get_api_engine",
    "get_worker_engine",
    "get_scheduler_engine",
    "get_engine_for_role",
]
