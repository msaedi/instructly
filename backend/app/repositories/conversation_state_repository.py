"""Repository for conversation user state management."""

from datetime import datetime, timezone
from typing import Optional, cast

from sqlalchemy.orm import Session
from ulid import ULID

from app.models.conversation_user_state import ConversationUserState
from app.repositories.base_repository import BaseRepository


class ConversationStateRepository(BaseRepository[ConversationUserState]):
    """Repository for managing conversation archive/trash states."""

    def __init__(self, db: Session):
        super().__init__(db, ConversationUserState)

    def get_state(self, user_id: str, booking_id: str) -> Optional[ConversationUserState]:
        """Get conversation state for a user. Returns None if no custom state (defaults to active)."""
        result = (
            self.db.query(ConversationUserState)
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.booking_id == booking_id,
            )
            .first()
        )
        return cast(Optional[ConversationUserState], result)

    def set_state(self, user_id: str, booking_id: str, state: str) -> ConversationUserState:
        """Set conversation state. Creates record if doesn't exist, updates if exists."""
        existing = self.get_state(user_id, booking_id)

        if existing:
            existing.state = state
            existing.state_changed_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing
        else:
            new_state = ConversationUserState(
                id=str(ULID()),
                user_id=user_id,
                booking_id=booking_id,
                state=state,
                state_changed_at=datetime.now(timezone.utc),
            )
            self.db.add(new_state)
            self.db.flush()
            return new_state

    def get_states_for_user(
        self, user_id: str, state: Optional[str] = None
    ) -> list[ConversationUserState]:
        """Get all conversation states for a user, optionally filtered by state."""
        query = self.db.query(ConversationUserState).filter(
            ConversationUserState.user_id == user_id
        )
        if state:
            query = query.filter(ConversationUserState.state == state)
        result = query.all()
        return cast(list[ConversationUserState], result)

    def get_booking_ids_by_state(self, user_id: str, state: str) -> list[str]:
        """Get list of booking IDs in a specific state for a user."""
        results = (
            self.db.query(ConversationUserState.booking_id)
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.state == state,
            )
            .all()
        )
        return [r[0] for r in results]

    def restore_to_active(self, user_id: str, booking_id: str) -> Optional[ConversationUserState]:
        """Restore a conversation to active state. Used for auto-restore on new message."""
        existing = self.get_state(user_id, booking_id)
        if existing and existing.state != "active":
            existing.state = "active"
            existing.state_changed_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing
        return existing
