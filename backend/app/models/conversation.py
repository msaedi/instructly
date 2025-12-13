# backend/app/models/conversation.py
"""
Conversation model for per-user-pair messaging architecture.

This model represents a conversation between a student and instructor.
Each student-instructor pair has exactly one conversation, regardless
of how many bookings they have together.

Design decisions:
- One conversation per student-instructor pair (not per booking)
- Messages reference conversations, not bookings
- Bookings can be linked to messages for context, but conversation is primary
- Pre-booking messaging is supported (conversation exists without booking)
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class Conversation(Base):
    """
    Conversation model for per-user-pair messaging.

    Each conversation represents a single communication channel between
    a student and an instructor. All messages between them (across all
    bookings or before any booking) are part of this single conversation.

    Attributes:
        id: ULID primary key
        student_id: Foreign key to the student (User)
        instructor_id: Foreign key to the instructor (User)
        created_at: When the conversation was created
        updated_at: When the conversation was last updated
        last_message_at: When the most recent message was sent
    """

    __tablename__ = "conversations"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    student_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    student = relationship(
        "User",
        foreign_keys=[student_id],
        backref="conversations_as_student",
    )
    instructor = relationship(
        "User",
        foreign_keys=[instructor_id],
        backref="conversations_as_instructor",
    )
    messages = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )

    # Table-level indexes (in addition to those created in migration)
    __table_args__ = (
        Index("idx_conversations_student", "student_id"),
        Index("idx_conversations_instructor", "instructor_id"),
        Index("idx_conversations_last_message", "last_message_at"),
        {
            "comment": "One conversation per student-instructor pair",
        },
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, student={self.student_id}, instructor={self.instructor_id})>"

    def get_other_user_id(self, current_user_id: str) -> str:
        """
        Get the ID of the other participant in the conversation.

        Args:
            current_user_id: The ID of the current user

        Returns:
            The ID of the other participant
        """
        if current_user_id == self.student_id:
            return str(self.instructor_id)
        return str(self.student_id)

    def is_participant(self, user_id: str) -> bool:
        """
        Check if a user is a participant in this conversation.

        Args:
            user_id: The ID to check

        Returns:
            True if the user is the student or instructor
        """
        return user_id in (self.student_id, self.instructor_id)
