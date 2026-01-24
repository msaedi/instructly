"""
Instructor lifecycle event tracking for funnel analytics.

Events are immutable (append-only) and track state transitions
through the instructor onboarding journey.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON
import ulid

from ..database import Base

EVENT_TYPES = (
    "registered",
    "profile_submitted",
    "services_configured",
    "bgc_initiated",
    "bgc_completed",
    "identity_verified",
    "went_live",
    "paused",
    "reactivated",
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InstructorLifecycleEvent(Base):
    """Append-only lifecycle events for instructor onboarding."""

    __tablename__ = "instructor_lifecycle_events"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(32), nullable=False)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )
    metadata_json = Column(
        "metadata",
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        server_default=func.now(),
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('registered','profile_submitted','services_configured','bgc_initiated',"
            "'bgc_completed','identity_verified','went_live','paused','reactivated')",
            name="ck_instructor_lifecycle_event_type",
        ),
        Index("idx_lifecycle_events_user_id", "user_id"),
        Index("idx_lifecycle_events_type_occurred", "event_type", "occurred_at"),
        Index("idx_lifecycle_events_occurred", "occurred_at"),
    )


__all__ = ["InstructorLifecycleEvent", "EVENT_TYPES"]
