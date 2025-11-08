"""
Database engine, session factory, and metadata shared across the application.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
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

# Create engine with connection pooling
if DATABASE_POOL_CONFIG:
    # Use production-optimized settings
    engine: Engine = create_engine(
        settings.get_database_url(), poolclass=QueuePool, **DATABASE_POOL_CONFIG
    )
else:
    # Use default development settings
    engine = create_engine(
        settings.get_database_url(),
        poolclass=QueuePool,
        pool_size=20,  # Number of persistent connections
        max_overflow=10,  # Maximum overflow connections
        pool_timeout=30,  # Timeout for getting connection
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True,  # Test connections before using
        echo_pool=False,  # Set to True for pool debugging
        connect_args={"connect_timeout": 10, "application_name": "instainstru_backend"},
    )


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


__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "get_db_pool_status",
]
