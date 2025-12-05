"""Repository for conversation state management (user state and aggregates)."""

from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy.orm import Session
from ulid import ULID

from app.models.booking import Booking
from app.models.conversation import Conversation
from app.models.conversation_state import ConversationState
from app.models.conversation_user_state import ConversationUserState
from app.repositories.base_repository import BaseRepository


class ConversationStateRepository(BaseRepository[ConversationUserState]):
    """Repository for managing conversation archive/trash states (per-user)."""

    def __init__(self, db: Session):
        super().__init__(db, ConversationUserState)

    def get_state(
        self,
        user_id: str,
        *,
        conversation_id: Optional[str] = None,
        booking_id: Optional[str] = None,
    ) -> Optional[ConversationUserState]:
        """Get conversation state for a user. Returns None if no custom state (defaults to active)."""
        query = self.db.query(ConversationUserState).filter(
            ConversationUserState.user_id == user_id
        )
        if conversation_id:
            query = query.filter(ConversationUserState.conversation_id == conversation_id)
        elif booking_id:
            query = query.filter(ConversationUserState.booking_id == booking_id)
        else:
            return None

        result = query.first()
        return cast(Optional[ConversationUserState], result)

    def set_state(
        self,
        user_id: str,
        state: str,
        *,
        conversation_id: Optional[str] = None,
        booking_id: Optional[str] = None,
    ) -> ConversationUserState:
        """Set conversation state. Creates record if doesn't exist, updates if exists."""
        if not conversation_id and booking_id:
            conversation_id = self._get_conversation_id_from_booking(booking_id)
        if not conversation_id:
            raise ValueError("conversation_id is required to set state")

        existing = self.get_state(user_id, conversation_id=conversation_id, booking_id=booking_id)

        if existing:
            existing.state = state
            existing.state_changed_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing
        else:
            new_state = ConversationUserState(
                id=str(ULID()),
                user_id=user_id,
                conversation_id=conversation_id,
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

    def get_conversation_ids_by_state(self, user_id: str, state: str) -> list[str]:
        """Get list of conversation IDs in a specific state for a user."""
        results = (
            self.db.query(ConversationUserState.conversation_id)
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.state == state,
            )
            .all()
        )
        return [r[0] for r in results if r[0]]

    def get_booking_ids_by_state(self, user_id: str, state: str) -> list[str]:
        """Legacy: Get list of booking IDs in a specific state for a user."""
        results = (
            self.db.query(ConversationUserState.booking_id)
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.state == state,
            )
            .all()
        )
        return [r[0] for r in results if r[0]]

    def restore_to_active(
        self,
        user_id: str,
        *,
        conversation_id: Optional[str] = None,
        booking_id: Optional[str] = None,
    ) -> Optional[ConversationUserState]:
        """Restore a conversation to active state. Used for auto-restore on new message."""
        if not conversation_id and booking_id:
            conversation_id = self._get_conversation_id_from_booking(booking_id)
        existing = self.get_state(user_id, conversation_id=conversation_id, booking_id=booking_id)
        if existing and existing.state != "active":
            existing.state = "active"
            existing.state_changed_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing
        return existing

    def _get_conversation_id_from_booking(self, booking_id: str) -> Optional[str]:
        """Resolve conversation_id from a booking."""
        booking = self.db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None
        conversation = (
            self.db.query(Conversation)
            .filter(
                Conversation.student_id == booking.student_id,
                Conversation.instructor_id == booking.instructor_id,
            )
            .first()
        )
        return conversation.id if conversation else None


class ConversationSummaryRepository(BaseRepository[ConversationState]):
    """Repository for conversation summary (denormalized state)."""

    def __init__(self, db: Session):
        super().__init__(db, ConversationState)

    def get_by_booking_id(self, booking_id: str) -> Optional[ConversationState]:
        """Fetch conversation summary by booking id."""
        result = (
            self.db.query(ConversationState)
            .filter(ConversationState.booking_id == booking_id)
            .first()
        )
        return cast(Optional[ConversationState], result)

    def update_after_message_delete(self, booking_id: str, latest_message: Optional[Any]) -> None:
        """
        Update denormalized conversation state after a message delete.

        Args:
            booking_id: Booking/conversation id
            latest_message: Latest remaining message or None if none remain
        """
        conv_state = self.get_by_booking_id(booking_id)
        if not conv_state:
            return

        if latest_message:
            conv_state.last_message_id = latest_message.id
            conv_state.last_message_preview = (latest_message.content or "")[:100]
            conv_state.last_message_at = latest_message.created_at
            conv_state.last_message_sender_id = latest_message.sender_id
        else:
            conv_state.last_message_id = None
            conv_state.last_message_preview = None
            conv_state.last_message_at = None
            conv_state.last_message_sender_id = None

        conv_state.updated_at = datetime.now(timezone.utc)
        self.db.flush()
