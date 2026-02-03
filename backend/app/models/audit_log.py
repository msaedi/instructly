# backend/app/models/audit_log.py
"""
Audit logging model to capture administrative actions for key entities.

Provides a simple helper for building rows from change events while applying
lightweight actor extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import JSON
import ulid

from app.database import Base


def _now_utc() -> datetime:
    """Return timezone-aware UTC timestamp for defaults."""
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Persistence model for audit trail entries."""

    __tablename__ = "audit_log"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(64), nullable=False)
    action = Column(String(30), nullable=False)
    actor_id = Column(String(64), nullable=True)
    actor_role = Column(String(30), nullable=True)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )
    before = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    after = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    @classmethod
    def from_change(
        cls,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: Any | None,
        before: Mapping[str, Any] | MutableMapping[str, Any] | None,
        after: Mapping[str, Any] | MutableMapping[str, Any] | None,
    ) -> "AuditLog":
        """Factory helper to build an AuditLog instance from change metadata."""
        actor_id: str | None = None
        actor_role: str | None = None

        if actor is not None:
            if isinstance(actor, Mapping):
                actor_id = _extract_value(actor, ("id", "actor_id", "user_id"))
                role_value = _extract_value(actor, ("role", "actor_role", "role_name"))
                actor_role = str(role_value) if role_value is not None else None
            else:
                actor_id = _first_attr(actor, ("id", "actor_id", "user_id"))
                role_value = _first_attr(actor, ("role", "actor_role", "role_name"))
                if role_value is None:
                    roles_candidate = _first_attr(actor, ("roles", "role_names"))
                    if isinstance(roles_candidate, (list, tuple)) and roles_candidate:
                        role_value = roles_candidate[0]
                actor_role = str(role_value) if role_value is not None else None

        payload_before = dict(before) if isinstance(before, MutableMapping) else before
        payload_after = dict(after) if isinstance(after, MutableMapping) else after

        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            before=payload_before,
            after=payload_after,
        )


class AuditLogEntry(Base):
    """Governance audit log entry with enriched actor/context fields."""

    __tablename__ = "audit_logs"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )

    # Who
    actor_type = Column(String(20), nullable=False)
    actor_id = Column(String(64), nullable=True)
    actor_email = Column(String(255), nullable=True)
    actor_ip = Column(String(45), nullable=True)
    actor_user_agent = Column(String(500), nullable=True)

    # What
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(26), nullable=True)

    # Details
    description = Column(Text, nullable=True)
    changes = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    metadata_json = Column(
        "metadata",
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Outcome
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)

    # Context
    request_id = Column(String(36), nullable=True)
    trace_id = Column(String(32), nullable=True)
    session_id = Column(String(64), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )


def _first_attr(obj: Any, names: tuple[str, ...]) -> Any | None:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return None


def _extract_value(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None
