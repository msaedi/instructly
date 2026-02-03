"""Webhook event ledger model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
import ulid

from app.database import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class WebhookEvent(Base):
    """Persistence model for inbound webhook events."""

    __tablename__ = "webhook_events"

    __table_args__ = (
        sa.Index("ix_webhook_events_source", "source"),
        sa.Index("ix_webhook_events_event_type", "event_type"),
        sa.Index("ix_webhook_events_status", "status"),
        sa.Index("ix_webhook_events_received_at", "received_at"),
        sa.Index("ix_webhook_events_event_id", "event_id"),
        sa.Index("ix_webhook_events_related_entity", "related_entity_type", "related_entity_id"),
        sa.UniqueConstraint("source", "event_id", name="uq_webhook_events_source_event_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replay_of: Mapped[str | None] = mapped_column(String(26), nullable=True)
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )
