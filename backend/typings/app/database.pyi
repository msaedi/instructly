from typing import Any, Generator, TypeVar

from sqlalchemy.orm import Session


Base: Any


class _SessionLocal:
    def __call__(self) -> Session: ...


SessionLocal: _SessionLocal


def get_db() -> Generator[Session, None, None]: ...


def get_db_pool_status() -> dict[str, Any]: ...
