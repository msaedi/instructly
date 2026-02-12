"""Conversation user state model for archive/trash functionality."""

from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base


class ConversationUserState(Base):
    """User-specific conversation states (active, archived, trashed)."""

    __tablename__ = "conversation_user_state"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(
        String(26), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    state = Column(String(20), nullable=False, default="active")  # active, archived, trashed
    state_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="conversation_states")
    conversation = relationship("Conversation")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "conversation_id", name="uq_conversation_user_state_user_conversation"
        ),
        Index("ix_conversation_user_state_user_state", "user_id", "state"),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = str(ulid.ULID())
        super().__init__(**kwargs)
