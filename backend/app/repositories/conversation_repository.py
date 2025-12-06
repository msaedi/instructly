# backend/app/repositories/conversation_repository.py
"""
Conversation Repository for per-user-pair messaging.

Provides data access methods for conversations between students and instructors.
Follows the repository pattern with clean separation from business logic.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, cast

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Query, Session, joinedload

from ..models.conversation import Conversation
from ..models.message import Message
from ..models.user import User
from .base_repository import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """
    Repository for Conversation entity operations.

    Handles all database operations for conversations including:
    - Finding or creating conversations for user pairs
    - Listing conversations for a user
    - Updating conversation metadata (last_message_at)
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        super().__init__(db, Conversation)

    def find_by_pair(self, student_id: str, instructor_id: str) -> Optional[Conversation]:
        """
        Find a conversation between a specific student and instructor.

        Uses a simple OR clause to match regardless of column order,
        since we enforce pair uniqueness via LEAST/GREATEST in the DB.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID

        Returns:
            The conversation if found, None otherwise
        """
        result = (
            self.db.query(Conversation)
            .filter(
                or_(
                    and_(
                        Conversation.student_id == student_id,
                        Conversation.instructor_id == instructor_id,
                    ),
                    and_(
                        Conversation.student_id == instructor_id,
                        Conversation.instructor_id == student_id,
                    ),
                )
            )
            .first()
        )
        return cast(Optional[Conversation], result)

    def get_or_create(self, student_id: str, instructor_id: str) -> tuple[Conversation, bool]:
        """
        Get an existing conversation or create a new one.

        Provides idempotent conversation creation - safe to call
        multiple times for the same pair.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID

        Returns:
            Tuple of (conversation, created) where created is True if new
        """
        existing = self.find_by_pair(student_id, instructor_id)
        if existing:
            return existing, False

        # Create new conversation using inherited create() method
        conversation = self.create(
            student_id=student_id,
            instructor_id=instructor_id,
        )

        return conversation, True

    def find_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        include_messages: bool = False,
        state_filter: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> Sequence[Conversation]:
        """
        Find all conversations where a user is a participant.

        Supports both offset-based and cursor-based pagination.
        Cursor is an ISO timestamp for last_message_at.

        Args:
            user_id: The user ID to find conversations for
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip (for offset pagination)
            include_messages: Whether to eager-load messages
            state_filter: Optional filter by state (active/archived/trashed)
            cursor: ISO timestamp for cursor-based pagination

        Returns:
            List of conversations ordered by last_message_at desc
        """
        query: Query = self.db.query(Conversation).filter(
            or_(
                Conversation.student_id == user_id,
                Conversation.instructor_id == user_id,
            )
        )

        if include_messages:
            query = query.options(joinedload(Conversation.messages))

        # Apply cursor-based pagination if cursor provided
        if cursor:
            from datetime import datetime

            try:
                cursor_time = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                # Get items older than the cursor
                query = query.filter(
                    func.coalesce(Conversation.last_message_at, Conversation.created_at)
                    < cursor_time
                )
            except (ValueError, TypeError):
                # Invalid cursor, ignore it
                pass

        # Order by most recent activity first
        # Use coalesce to handle NULL last_message_at
        query = query.order_by(
            func.coalesce(Conversation.last_message_at, Conversation.created_at).desc()
        )

        # Use offset only if cursor not provided
        if not cursor and offset > 0:
            query = query.offset(offset)

        return cast(Sequence[Conversation], query.limit(limit).all())

    def count_for_user(self, user_id: str) -> int:
        """
        Count conversations where a user is a participant.

        Args:
            user_id: The user ID

        Returns:
            Number of conversations
        """
        return (
            self.db.query(func.count(Conversation.id))
            .filter(
                or_(
                    Conversation.student_id == user_id,
                    Conversation.instructor_id == user_id,
                )
            )
            .scalar()
            or 0
        )

    def update_last_message_at(
        self, conversation_id: str, timestamp: Optional[datetime] = None
    ) -> Optional[Conversation]:
        """
        Update the last_message_at timestamp for a conversation.

        Args:
            conversation_id: The conversation ID
            timestamp: The timestamp to set (defaults to now)

        Returns:
            The updated conversation if found
        """
        conversation = self.get_by_id(conversation_id, load_relationships=False)
        if conversation:
            conversation.last_message_at = timestamp or datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)
            self.db.flush()
        return conversation

    def find_by_user_pair_ids(self, user_id_1: str, user_id_2: str) -> Optional[Conversation]:
        """
        Find a conversation between any two users.

        This is a more flexible version of find_by_pair that doesn't
        require knowing which user is the student vs instructor.

        Args:
            user_id_1: First user ID
            user_id_2: Second user ID

        Returns:
            The conversation if found, None otherwise
        """
        result = (
            self.db.query(Conversation)
            .filter(
                or_(
                    and_(
                        Conversation.student_id == user_id_1,
                        Conversation.instructor_id == user_id_2,
                    ),
                    and_(
                        Conversation.student_id == user_id_2,
                        Conversation.instructor_id == user_id_1,
                    ),
                )
            )
            .first()
        )
        return cast(Optional[Conversation], result)

    def find_by_booking_participants(
        self, student_id: str, instructor_id: str
    ) -> Optional[Conversation]:
        """
        Find conversation for booking participants.

        This is an alias for find_by_pair that makes the intent clearer
        when called from booking-related code.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID

        Returns:
            The conversation if found, None otherwise
        """
        return self.find_by_pair(student_id, instructor_id)

    def get_with_participant_info(self, conversation_id: str) -> Optional[Conversation]:
        """
        Get a conversation with eagerly loaded participant info.

        Args:
            conversation_id: The conversation ID

        Returns:
            Conversation with loaded student and instructor relationships
        """
        result = (
            self.db.query(Conversation)
            .options(
                joinedload(Conversation.student),
                joinedload(Conversation.instructor),
            )
            .filter(Conversation.id == conversation_id)
            .first()
        )
        return cast(Optional[Conversation], result)

    def get_unread_count(self, conversation_id: str, user_id: str) -> int:
        """
        Count unread messages in a conversation for a specific user.

        A message is unread if it was sent by the other participant and the user_id
        is not present in the message.read_by array.
        """
        dialect_name = self.db.bind.dialect.name if self.db.bind else "postgresql"
        if dialect_name == "postgresql":
            stmt = text(
                """
                SELECT COUNT(*) FROM messages
                WHERE conversation_id = :conversation_id
                  AND sender_id != :user_id
                  AND is_deleted = false
                  AND NOT (read_by @> :read_entry)
                """
            )
            result = self.db.execute(
                stmt,
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "read_entry": f'[{{"user_id": "{user_id}"}}]',
                },
            ).scalar()
            return int(result or 0)

        result = (
            self.db.query(func.count(Message.id))
            .filter(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.is_deleted == False,  # noqa: E712
                ~Message.read_by.contains([{"user_id": user_id}]),
            )
            .scalar()
        )
        return int(result or 0)

    def get_participant_first_names(self, user_ids: List[str]) -> Dict[str, Optional[str]]:
        """
        Get first names for a list of user IDs.

        Used for personalizing system messages with participant names.

        Args:
            user_ids: List of user IDs to look up

        Returns:
            Dict mapping user_id to first_name (None if not found)
        """
        if not user_ids:
            return {}

        try:
            rows = self.db.query(User.id, User.first_name).filter(User.id.in_(user_ids)).all()
            return {uid: first_name for uid, first_name in rows}
        except Exception:
            return {uid: None for uid in user_ids}
