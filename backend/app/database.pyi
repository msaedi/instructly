from collections.abc import Generator
from typing import Any, TypedDict

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

class DeclarativeBase:
    """Lightweight stand-in for SQLAlchemy's DeclarativeBase."""

    metadata: Any

    def __init__(self, **kwargs: Any) -> None: ...


class _PoolStatus(TypedDict):
    size: int
    checked_in: int
    checked_out: int
    total: int
    overflow: int

class Base(DeclarativeBase):
    def __init__(self, **kwargs: Any) -> None: ...


def get_db() -> Generator[Session, None, None]:
    ...


def get_db_pool_status() -> _PoolStatus:
    ...


engine: Engine
SessionLocal: sessionmaker[Session]

__all__ = [
    "Base",
    "get_db",
    "get_db_pool_status",
    "engine",
    "SessionLocal",
]
