from typing import Generator

from sqlalchemy.orm import DeclarativeMeta, Session


class Base(metaclass=DeclarativeMeta): ...


class _SessionFactory:
    def __call__(self) -> Session: ...


SessionLocal: _SessionFactory


def get_db() -> Generator[Session, None, None]: ...


def get_db_pool_status() -> dict[str, int]: ...
