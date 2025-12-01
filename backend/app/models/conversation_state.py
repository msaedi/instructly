# backend/app/models/conversation_state.py
"""
ConversationState model for efficient inbox queries.

Pre-computed conversation metadata including unread counts and last message info.
Eliminates N+1 queries for inbox state by denormalizing key conversation data.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class ConversationState(Base):
    """
    Pre-computed conversation state for O(1) inbox queries.

    Stores denormalized data about each conversation (booking):
    - Unread counts for both instructor and student
    - Last message metadata for preview
    - Auto-updated via database trigger on message insert
    """

    __tablename__ = "conversation_state"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instructor_unread_count = Column(Integer, default=0, nullable=False)
    student_unread_count = Column(Integer, default=0, nullable=False)
    last_message_id = Column(
        String(26), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    last_message_preview = Column(String(100), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    last_message_sender_id = Column(String(26), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    booking = relationship("Booking", back_populates="conversation_state")
    instructor = relationship("User", foreign_keys=[instructor_id])
    student = relationship("User", foreign_keys=[student_id])
    last_message = relationship("Message", foreign_keys=[last_message_id])
