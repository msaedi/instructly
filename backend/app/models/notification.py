"""
Notification models for InstaInstru.

Includes preference toggles, in-app notifications, and web push subscriptions.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON
import ulid

from ..database import Base

NOTIFICATION_CATEGORIES = (
    "lesson_updates",
    "messages",
    "reviews",
    "learning_tips",
    "system_updates",
    "promotional",
)
NOTIFICATION_CHANNELS = ("email", "push", "sms")
LOCKED_NOTIFICATION_PREFERENCES = {("messages", "push")}


class NotificationPreference(Base):
    """Per-user notification channel preferences by category."""

    __tablename__ = "notification_preferences"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(50), nullable=False)
    channel = Column(String(20), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    locked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "category",
            "channel",
            name="uq_notification_preferences_user_category_channel",
        ),
        CheckConstraint(
            "category IN ('lesson_updates', 'messages', 'reviews', 'learning_tips', 'system_updates', 'promotional')",
            name="ck_notification_preferences_category",
        ),
        CheckConstraint(
            "channel IN ('email', 'push', 'sms')",
            name="ck_notification_preferences_channel",
        ),
    )


class Notification(Base):
    """In-app notification inbox entries."""

    __tablename__ = "notifications"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)
    type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "category IN ('lesson_updates', 'messages', 'reviews', 'learning_tips', 'system_updates', 'promotional')",
            name="ck_notifications_category",
        ),
        Index("ix_notifications_user_read_at", "user_id", "read_at"),
        Index("ix_notifications_user_category", "user_id", "category"),
        Index(
            "ix_notifications_user_created_at",
            "user_id",
            created_at.desc(),
        ),
    )


class PushSubscription(Base):
    """Web push subscription details for a user."""

    __tablename__ = "push_subscriptions"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = Column(Text, nullable=False)
    p256dh_key = Column(String(255), nullable=False)
    auth_key = Column(String(255), nullable=False)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
    )


__all__ = [
    "NotificationPreference",
    "Notification",
    "PushSubscription",
    "NOTIFICATION_CATEGORIES",
    "NOTIFICATION_CHANNELS",
    "LOCKED_NOTIFICATION_PREFERENCES",
]
