from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Any, Awaitable, Callable, TypedDict, TypeVar

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

T = TypeVar("T")

class DeclarativeBase:
    """Lightweight stand-in for SQLAlchemy's DeclarativeBase."""

    metadata: Any

    def __init__(self, **kwargs: Any) -> None: ...


class _PoolStatus(TypedDict, total=False):
    size: int
    max_overflow: int
    max_capacity: int
    checked_in: int
    checked_out: int
    overflow_in_use: int
    utilization_pct: float
    error: str


class Base(DeclarativeBase):
    def __init__(self, **kwargs: Any) -> None: ...


def get_db() -> Generator[Session, None, None]: ...

def get_db_session() -> AbstractContextManager[Session]: ...


def get_db_pool_status(pool_name: str | None = ...) -> _PoolStatus: ...

def get_db_pool_statuses() -> dict[str, _PoolStatus]: ...

def get_pool_status_for_role(role: str | None = ...) -> dict[str, _PoolStatus]: ...

def get_db_with_retry(max_attempts: int = ...) -> Generator[Session, None, None]: ...

def get_api_engine() -> Engine: ...

def get_worker_engine() -> Engine: ...

def get_scheduler_engine() -> Engine: ...

def get_engine_for_role(role: str | None = ...) -> Engine: ...

def get_api_session() -> AbstractContextManager[Session]: ...

def get_worker_session() -> AbstractContextManager[Session]: ...

def get_scheduler_session() -> AbstractContextManager[Session]: ...

def init_session_factories() -> None: ...

def with_db_retry(
    op_name: str,
    func: Callable[[], T],
    *,
    max_attempts: int = ...,
    on_retry: Callable[[], None] | None = ...,
) -> T: ...


async def with_db_retry_async(
    op_name: str,
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = ...,
    on_retry: Callable[[], None] | None = ...,
) -> T: ...


engine: Engine
SessionLocal: sessionmaker[Session]
APISessionLocal: sessionmaker[Session]
WorkerSessionLocal: sessionmaker[Session]
SchedulerSessionLocal: sessionmaker[Session]
ROLE_POOLS: dict[str, list[str]]

__all__ = [
    "Base",
    "APISessionLocal",
    "WorkerSessionLocal",
    "SchedulerSessionLocal",
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
    "engine",
    "SessionLocal",
    "with_db_retry",
    "with_db_retry_async",
]
