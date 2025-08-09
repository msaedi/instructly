# backend/app/models/message.py
"""
Message model for the chat system.

Represents messages exchanged between instructors and students
for a specific booking.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base


class Message(Base):
    """
    Message model for booking-related chat.

    Messages are tied to bookings and enable communication
    between the instructor and student.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_deleted = Column(Boolean, nullable=False, default=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    # Array of { user_id, read_at }
    read_by = Column(JSONB, nullable=False, default=list)

    # Relationships
    booking = relationship("Booking", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    notifications = relationship("MessageNotification", back_populates="message", cascade="all, delete-orphan")


class MessageReaction(Base):
    """
    Emoji reactions for messages.
    """

    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emoji = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MessageEdit(Base):
    """
    Edit history for messages.
    """

    __tablename__ = "message_edits"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    original_content = Column(String(1000), nullable=False)
    edited_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MessageNotification(Base):
    """
    Tracks unread messages for users.

    Each record represents a notification for a specific user
    about a specific message.
    """

    __tablename__ = "message_notifications"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", back_populates="notifications")
    user = relationship("User", foreign_keys=[user_id])
