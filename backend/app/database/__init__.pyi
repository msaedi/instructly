from collections.abc import Generator
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
    checked_in: int
    checked_out: int
    total: int
    overflow: int
    error: str


class Base(DeclarativeBase):
    def __init__(self, **kwargs: Any) -> None: ...


def get_db() -> Generator[Session, None, None]: ...


def get_db_pool_status() -> _PoolStatus: ...

def with_db_retry(
    op_name: str,
    func: Callable[[], T],
    *,
    max_attempts: int = ...,
) -> T: ...


async def with_db_retry_async(
    op_name: str,
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = ...,
) -> T: ...


engine: Engine
SessionLocal: sessionmaker[Session]

__all__ = [
    "Base",
    "get_db",
    "get_db_pool_status",
    "engine",
    "SessionLocal",
    "with_db_retry",
    "with_db_retry_async",
]
