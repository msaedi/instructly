"""Session factories for workload-specific database pools."""

from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from .engines import get_api_engine, get_scheduler_engine, get_worker_engine

APISessionLocal = sessionmaker(autocommit=False, autoflush=False)
WorkerSessionLocal = sessionmaker(autocommit=False, autoflush=False)
SchedulerSessionLocal = sessionmaker(autocommit=False, autoflush=False)


def _bind_session_factories() -> None:
    APISessionLocal.configure(bind=get_api_engine())
    WorkerSessionLocal.configure(bind=get_worker_engine())
    SchedulerSessionLocal.configure(bind=get_scheduler_engine())


def _default_role() -> str:
    return os.getenv("DB_POOL_ROLE", "api").strip().lower() or "api"


def _select_default_sessionmaker() -> sessionmaker:
    role = _default_role()
    if role == "worker":
        return WorkerSessionLocal
    if role == "scheduler":
        return SchedulerSessionLocal
    return APISessionLocal


SessionLocal = _select_default_sessionmaker()


def init_session_factories() -> None:
    """Initialize session factories (idempotent)."""
    global SessionLocal
    _bind_session_factories()
    SessionLocal = _select_default_sessionmaker()


@contextmanager
def get_api_session() -> Generator[Session, None, None]:
    session = APISessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_worker_session() -> Generator[Session, None, None]:
    session = WorkerSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_scheduler_session() -> Generator[Session, None, None]:
    session = SchedulerSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency - uses the pool for the current process role."""
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
    """Context manager for short-lived DB operations."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Bind session factories on import so SessionLocal is usable immediately.
init_session_factories()


__all__ = [
    "APISessionLocal",
    "WorkerSessionLocal",
    "SchedulerSessionLocal",
    "SessionLocal",
    "get_api_session",
    "get_worker_session",
    "get_scheduler_session",
    "get_db",
    "get_db_session",
    "init_session_factories",
]
