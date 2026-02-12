# backend/app/models/message.py
"""
Message model for the chat system.

Represents messages exchanged between instructors and students.
Messages are part of a conversation (per-user-pair) and may optionally
reference a booking for context.

Message types:
- 'user': Regular user message (default)
- 'system_booking_created': Auto-generated when lesson booked
- 'system_booking_cancelled': Auto-generated when lesson cancelled
- 'system_booking_rescheduled': Auto-generated when lesson rescheduled
- 'system_booking_completed': Auto-generated when lesson completed
- 'system_conversation_started': Auto-generated for pre-booking inquiries
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON as SAJSON
import ulid

from ..database import Base

# Constants for message types
MESSAGE_TYPE_USER = "user"
MESSAGE_TYPE_SYSTEM_BOOKING_CREATED = "system_booking_created"
MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED = "system_booking_cancelled"
MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED = "system_booking_rescheduled"
MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED = "system_booking_completed"
MESSAGE_TYPE_SYSTEM_CONVERSATION_STARTED = "system_conversation_started"


class Message(Base):
    """
    Message model for conversation-based chat.

    Messages belong to a conversation (per-user-pair) and may optionally
    reference a booking for context. This enables:
    - Unified message history across all bookings
    - Pre-booking messaging (conversation without booking)
    - System messages for booking lifecycle events
    """

    __tablename__ = "messages"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    # booking_id is now nullable (for pre-booking messages or conversation-only context)
    booking_id = Column(String(26), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    # sender_id is nullable for system messages (no human sender)
    sender_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    content = Column(String(1000), nullable=False)

    # Per-user-pair conversation reference (required for all messages)
    conversation_id = Column(
        String(26), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # Message type: 'user', 'system_booking_created', etc.
    message_type = Column(String(50), nullable=False, default=MESSAGE_TYPE_USER)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String(26), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    # Array of { user_id, read_at }
    read_by = Column(SAJSON, nullable=False, default=list)

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_conversation_created", "conversation_id", created_at.desc()),
    )

    # Relationships
    booking = relationship("Booking", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    conversation = relationship("Conversation", back_populates="messages")
    notifications = relationship(
        "MessageNotification", back_populates="message", cascade="all, delete-orphan"
    )
    # Named reaction_list to avoid conflict with MessageResponse.reactions (dict of counts)
    reaction_list = relationship(
        "MessageReaction", backref="message", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_system_message(self) -> bool:
        """Check if this is a system-generated message."""
        return bool(self.message_type != MESSAGE_TYPE_USER)


class MessageReaction(Base):
    """
    Emoji reactions for messages.
    """

    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "user_id",
            "emoji",
            name="uq_message_reactions_message_user_emoji",
        ),
    )

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    message_id = Column(String(26), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emoji = Column(String(16), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class MessageEdit(Base):
    """
    Edit history for messages.
    """

    __tablename__ = "message_edits"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    message_id = Column(String(26), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    original_content = Column(String(1000), nullable=False)
    edited_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class MessageNotification(Base):
    """
    Tracks unread messages for users.

    Each record represents a notification for a specific user
    about a specific message.
    """

    __tablename__ = "message_notifications"
    __table_args__ = (
        Index("ix_message_notifications_user_read", "user_id", "is_read"),
        Index("ix_message_notifications_message", "message_id"),
    )

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    message_id = Column(String(26), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    message = relationship("Message", back_populates="notifications")
    user = relationship("User", foreign_keys=[user_id])
