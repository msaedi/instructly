"""
Helpers for working with SQLAlchemy sessions in a dialect-agnostic way.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


def resolve_session_bind(session: Session) -> Optional[Connection | Engine]:
    """Return the engine/connection bound to a session without direct .bind access."""
    try:
        bind = session.get_bind()
        if bind is not None:
            return bind
    except Exception:
        bind = None

    try:
        insp = inspect(session)
    except Exception:
        return None

    return getattr(insp, "bind", None)


def get_dialect_name(session: Session, default: str = "sqlite") -> str:
    """
    Return SQLAlchemy dialect name without touching Session.bind directly.

    Falls back to ``default`` when the bound engine cannot be resolved.
    """
    bind = resolve_session_bind(session)
    if bind is None:
        return default
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", None)
    return name or default
