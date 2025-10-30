# backend/app/models/event_outbox.py
"""
Event outbox persistence models.

Implements the storage required for the notification outbox pattern with
idempotent delivery tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import JSON
import ulid

from app.database import Base


def _now_utc() -> datetime:
    """Return timezone-aware UTC timestamp for default factories."""
    return datetime.now(timezone.utc)


class EventOutboxStatus(str, Enum):
    """Lifecycle states for an outbox event."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class EventOutbox(Base):
    """Transactional outbox entry pending delivery."""

    __tablename__ = "event_outbox"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    event_type = Column(String(100), nullable=False, index=True)
    aggregate_id = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    payload = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    status = Column(String(20), nullable=False, default=EventOutboxStatus.PENDING.value, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_event_outbox_idempotency_key"),)

    def mark_pending(self, next_attempt_at: datetime, attempt_count: int) -> None:
        """Update row state for another delivery attempt."""
        self.status = EventOutboxStatus.PENDING.value
        self.attempt_count = attempt_count
        self.next_attempt_at = next_attempt_at
        self.updated_at = _now_utc()

    def mark_sent(self, attempt_count: int) -> None:
        """Mark the event as successfully delivered."""
        self.status = EventOutboxStatus.SENT.value
        self.attempt_count = attempt_count
        self.next_attempt_at = _now_utc()
        self.updated_at = _now_utc()

    def mark_failed(self, attempt_count: int, error: str | None = None) -> None:
        """Mark the event as permanently failed."""
        self.status = EventOutboxStatus.FAILED.value
        self.attempt_count = attempt_count
        if error:
            self.last_error = error[:1000]
        self.updated_at = _now_utc()


class NotificationDelivery(Base):
    """Record of dispatched notifications to enforce idempotency downstream."""

    __tablename__ = "notification_delivery"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    event_type = Column(String(100), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    payload = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    attempt_count = Column(Integer, nullable=False, default=1)
    delivered_at = Column(DateTime(timezone=True), nullable=False, default=_now_utc)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_delivery_idempotency"),
    )

    def touch(self, payload: Dict[str, Any] | None = None) -> None:
        """Update delivery metadata if a duplicate send is attempted."""
        self.attempt_count += 1
        self.delivered_at = _now_utc()
        if payload is not None:
            self.payload = payload
        self.updated_at = _now_utc()
