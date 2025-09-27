from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

class DeclarativeBase:
    """Minimal placeholder for SQLAlchemy's DeclarativeBase."""


class Base(DeclarativeBase): ...


class _SessionFactory:
    def __call__(self) -> Session: ...


SessionLocal: _SessionFactory


def get_db() -> Iterator[Session]: ...


def get_db_pool_status() -> dict[str, int]: ...
