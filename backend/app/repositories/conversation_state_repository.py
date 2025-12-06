"""Repository for conversation state management (user state and aggregates)."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, cast

from sqlalchemy.orm import Session
from ulid import ULID

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
    ) -> Optional[ConversationUserState]:
        """Get conversation state for a user. Returns None if no custom state (defaults to active)."""
        query = self.db.query(ConversationUserState).filter(
            ConversationUserState.user_id == user_id
        )
        if conversation_id:
            query = query.filter(ConversationUserState.conversation_id == conversation_id)
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
    ) -> ConversationUserState:
        """Set conversation state. Creates record if doesn't exist, updates if exists."""
        if not conversation_id:
            raise ValueError("conversation_id is required to set state")

        existing = self.get_state(user_id, conversation_id=conversation_id)

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
        return []

    def restore_to_active(
        self,
        user_id: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> Optional[ConversationUserState]:
        """Restore a conversation to active state. Used for auto-restore on new message."""
        existing = self.get_state(user_id, conversation_id=conversation_id)
        if existing and existing.state != "active":
            existing.state = "active"
            existing.state_changed_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing
        return existing

    def batch_get_states(self, user_id: str, conversation_ids: List[str]) -> Dict[str, str]:
        """
        Get states for multiple conversations in a single query.

        Args:
            user_id: The user ID
            conversation_ids: List of conversation IDs to fetch states for

        Returns:
            Dict mapping conversation_id to state. Missing entries default to "active".
        """
        if not conversation_ids:
            return {}

        results = (
            self.db.query(
                ConversationUserState.conversation_id,
                ConversationUserState.state,
            )
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.conversation_id.in_(conversation_ids),
            )
            .all()
        )

        # Build dict with found states
        states = {conv_id: state for conv_id, state in results}

        # Default to "active" for missing entries
        return {conv_id: states.get(conv_id, "active") for conv_id in conversation_ids}

    def get_excluded_conversation_ids(self, user_id: str) -> tuple[set[str], set[str]]:
        """
        Get archived and trashed conversation IDs for a user in a single query.

        Combines what was previously two separate queries into one.

        Args:
            user_id: The user ID

        Returns:
            Tuple of (archived_ids, trashed_ids) sets
        """
        results = (
            self.db.query(
                ConversationUserState.conversation_id,
                ConversationUserState.state,
            )
            .filter(
                ConversationUserState.user_id == user_id,
                ConversationUserState.state.in_(["archived", "trashed"]),
            )
            .all()
        )

        archived_ids: set[str] = set()
        trashed_ids: set[str] = set()

        for conv_id, state in results:
            if conv_id:
                if state == "archived":
                    archived_ids.add(conv_id)
                elif state == "trashed":
                    trashed_ids.add(conv_id)

        return archived_ids, trashed_ids
