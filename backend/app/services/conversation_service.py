# backend/app/services/conversation_service.py
"""
Conversation Service for per-user-pair messaging.

Handles business logic for the conversation system including:
- Listing conversations for a user
- Getting conversation details
- Sending messages with auto-tagging
- Managing conversation metadata
"""

import logging
from typing import List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from ..models.booking import Booking
from ..models.conversation import Conversation
from ..models.message import MESSAGE_TYPE_USER, Message
from ..repositories.booking_repository import BookingRepository
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.conversation_state_repository import ConversationStateRepository
from ..repositories.factory import RepositoryFactory
from ..repositories.message_repository import MessageRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class ConversationService(BaseService):
    """
    Service for managing per-user-pair conversations.

    Handles conversation creation, message sending, and
    related business logic with proper access control.
    """

    def __init__(
        self,
        db: Session,
        conversation_repository: Optional[ConversationRepository] = None,
        message_repository: Optional[MessageRepository] = None,
        booking_repository: Optional[BookingRepository] = None,
    ):
        """
        Initialize conversation service.

        Args:
            db: Database session
            conversation_repository: Optional repository for conversations
            message_repository: Optional repository for messages
            booking_repository: Optional repository for bookings
        """
        super().__init__(db)
        self.conversation_repository = (
            conversation_repository or RepositoryFactory.create_conversation_repository(db)
        )
        self.message_repository = message_repository or RepositoryFactory.create_message_repository(
            db
        )
        self.booking_repository = booking_repository or RepositoryFactory.create_booking_repository(
            db
        )
        self.conversation_state_repository = ConversationStateRepository(db)
        self.logger = logging.getLogger(__name__)

    @BaseService.measure_operation("get_or_create_conversation")
    def get_or_create_conversation(
        self,
        student_id: str,
        instructor_id: str,
    ) -> Tuple[Conversation, bool]:
        """
        Get existing conversation or create new one.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID

        Returns:
            Tuple of (conversation, created) where created is True if new
        """
        return self.conversation_repository.get_or_create(
            student_id=student_id,
            instructor_id=instructor_id,
        )

    @BaseService.measure_operation("get_conversation_for_booking")
    def get_conversation_for_booking(
        self,
        booking_id: str,
        user_id: str,
    ) -> Tuple[Optional[Conversation], bool]:
        """
        Get or create conversation for a booking's student-instructor pair.

        This is used by the Chat component which operates by booking_id
        but needs the conversation_id for SSE subscription.

        Args:
            booking_id: The booking's ID
            user_id: The requesting user's ID (must be participant)

        Returns:
            Tuple of (conversation, created) or (None, False) if booking not found
            or user is not a participant
        """
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            self.logger.warning(f"Booking not found: {booking_id}")
            return None, False

        # Verify user is a participant
        if user_id not in (booking.student_id, booking.instructor_id):
            self.logger.warning(f"User {user_id} is not a participant in booking {booking_id}")
            return None, False

        return self.conversation_repository.get_or_create(
            student_id=booking.student_id,
            instructor_id=booking.instructor_id,
        )

    @BaseService.measure_operation("list_conversations_for_user")
    def list_conversations_for_user(
        self,
        user_id: str,
        state_filter: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Conversation], Optional[str]]:
        """
        List conversations for a user with pagination.

        Args:
            user_id: The user's ID
            state_filter: Optional filter by state (active/archived/trashed)
            limit: Maximum number of conversations to return
            cursor: Pagination cursor (ISO timestamp)

        Returns:
            Tuple of (conversations, next_cursor) where next_cursor is
            None if no more pages
        """
        # Fetch one extra to determine if there's more
        conversations_seq = self.conversation_repository.find_for_user(
            user_id=user_id,
            state_filter=state_filter,
            limit=limit + 1,
            cursor=cursor,
        )
        # Convert Sequence to list for manipulation
        conversations = list(conversations_seq)

        # Apply per-user state filtering using conversation_user_state records.
        # "active" is the default when no state row exists, so treat it the same
        # as the unfiltered view: exclude archived/trashed, include everything else.
        archived_ids = set(
            self.conversation_state_repository.get_conversation_ids_by_state(user_id, "archived")
        )
        trashed_ids = set(
            self.conversation_state_repository.get_conversation_ids_by_state(user_id, "trashed")
        )

        if state_filter in (None, "active"):
            excluded = archived_ids | trashed_ids
            conversations = [c for c in conversations if c.id not in excluded]
        elif state_filter == "archived":
            conversations = [c for c in conversations if c.id in archived_ids]
        elif state_filter == "trashed":
            conversations = [c for c in conversations if c.id in trashed_ids]

        next_cursor = None
        if len(conversations) > limit:
            conversations = conversations[:limit]
            # Use last_message_at of last item as cursor
            last_conv = conversations[-1]
            if last_conv.last_message_at:
                next_cursor = last_conv.last_message_at.isoformat()

        return conversations, next_cursor

    @BaseService.measure_operation("get_conversation_user_state")
    def get_conversation_user_state(self, conversation_id: str, user_id: str) -> str:
        """Return per-user state for the conversation."""
        state_record = self.conversation_state_repository.get_state(
            user_id, conversation_id=conversation_id
        )
        state_value = state_record.state if state_record else "active"
        return cast(str, state_value)

    @BaseService.measure_operation("set_conversation_user_state")
    def set_conversation_user_state(self, conversation_id: str, user_id: str, state: str) -> None:
        """Update per-user state for a conversation."""
        if state not in ("active", "archived", "trashed"):
            raise ValueError(f"Invalid state: {state}")
        self.conversation_state_repository.set_state(
            user_id,
            state,
            conversation_id=conversation_id,
        )

    @BaseService.measure_operation("get_unread_count")
    def get_unread_count(self, conversation_id: str, user_id: str) -> int:
        """Count unread messages for a user in a conversation."""
        return self.conversation_repository.get_unread_count(conversation_id, user_id)

    @BaseService.measure_operation("get_conversation_by_id")
    def get_conversation_by_id(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[Conversation]:
        """
        Get conversation by ID, verifying user is a participant.

        Args:
            conversation_id: The conversation ID
            user_id: The user's ID (for access control)

        Returns:
            Conversation if found and user is participant, None otherwise
        """
        conversation = self.conversation_repository.get_by_id(conversation_id)
        if not conversation:
            return None
        if not conversation.is_participant(user_id):
            return None
        return conversation

    @BaseService.measure_operation("get_messages")
    def get_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before_cursor: Optional[str] = None,
        booking_id_filter: Optional[str] = None,
    ) -> Tuple[List[Message], bool, Optional[str]]:
        """
        Get messages for a conversation with pagination.

        Messages are returned in chronological order (oldest first).
        Pagination works backwards from most recent.

        Args:
            conversation_id: The conversation ID
            user_id: The user's ID (for access control)
            limit: Maximum messages to return
            before_cursor: Message ID to paginate before (gets older messages)
            booking_id_filter: Optional filter by booking ID

        Returns:
            Tuple of (messages, has_more, next_cursor) where messages are
            in chronological order
        """
        # Verify user is participant
        conversation = self.get_conversation_by_id(conversation_id, user_id)
        if not conversation:
            return [], False, None

        # Repository returns newest first
        messages = self.message_repository.find_by_conversation(
            conversation_id=conversation_id,
            limit=limit + 1,
            before_cursor=before_cursor,
            booking_id_filter=booking_id_filter,
        )

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        next_cursor = None
        if has_more and messages:
            # Cursor is the ID of the oldest message in this batch
            # Since messages are returned newest-first, oldest is last in list
            next_cursor = messages[-1].id

        # Reverse to return in chronological order (oldest first)
        messages.reverse()

        return messages, has_more, next_cursor

    @BaseService.measure_operation("send_message")
    def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        explicit_booking_id: Optional[str] = None,
    ) -> Optional[Message]:
        """
        Send a message in a conversation.

        Auto-tags booking_id if exactly one upcoming booking exists.

        Args:
            conversation_id: The conversation ID
            sender_id: The sender's user ID
            content: Message content
            explicit_booking_id: Optional explicit booking to attach

        Returns:
            Created message, or None if user is not a participant
        """
        # Verify user is participant
        conversation = self.get_conversation_by_id(conversation_id, sender_id)
        if not conversation:
            return None

        # Determine booking_id to attach
        booking_id = self._determine_booking_id(
            conversation=conversation,
            explicit_booking_id=explicit_booking_id,
        )

        # Create message using repository's method
        message = self.message_repository.create_conversation_message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=MESSAGE_TYPE_USER,
            booking_id=booking_id,
        )

        # Update conversation's last_message_at
        self.conversation_repository.update_last_message_at(conversation_id, message.created_at)

        # Auto-restore archived/trashed state for the other participant
        recipient_id = (
            conversation.instructor_id
            if sender_id == conversation.student_id
            else conversation.student_id
        )
        self.conversation_state_repository.restore_to_active(
            user_id=recipient_id,
            conversation_id=conversation_id,
        )

        self.logger.info(
            f"Message sent in conversation {conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "message_id": message.id,
                "booking_id": booking_id,
            },
        )

        return message

    def _determine_booking_id(
        self,
        conversation: Conversation,
        explicit_booking_id: Optional[str],
    ) -> Optional[str]:
        """
        Determine which booking_id to attach to a user message.

        Rules:
        1. If user explicitly provides booking_id, validate and use it
        2. If exactly ONE upcoming booking exists for this pair, auto-tag
        3. If ZERO or MULTIPLE upcoming bookings, leave as NULL

        Rationale: False confidence is worse than no tag.

        Args:
            conversation: The conversation
            explicit_booking_id: User-provided booking ID (optional)

        Returns:
            Booking ID to attach, or None
        """
        if explicit_booking_id:
            # Validate the booking belongs to this conversation's pair
            booking = self.booking_repository.get_by_id(explicit_booking_id)
            if booking and self._booking_matches_conversation(booking, conversation):
                return explicit_booking_id
            # Invalid booking_id provided, ignore it
            return None

        # Find upcoming bookings for this pair
        upcoming_bookings = self.booking_repository.find_upcoming_for_pair(
            student_id=conversation.student_id,
            instructor_id=conversation.instructor_id,
        )

        if len(upcoming_bookings) == 1:
            return cast(str, upcoming_bookings[0].id)

        # Zero or multiple bookings: don't guess
        return None

    def _booking_matches_conversation(self, booking: Booking, conversation: Conversation) -> bool:
        """Check if a booking belongs to this conversation's student-instructor pair."""
        return cast(
            bool,
            booking.student_id == conversation.student_id
            and booking.instructor_id == conversation.instructor_id,
        )

    @BaseService.measure_operation("get_upcoming_bookings_for_conversation")
    def get_upcoming_bookings_for_conversation(
        self,
        conversation: Conversation,
    ) -> List[Booking]:
        """
        Get all upcoming bookings for a conversation's pair.

        Args:
            conversation: The conversation

        Returns:
            List of upcoming bookings ordered by date/time
        """
        return self.booking_repository.find_upcoming_for_pair(
            student_id=conversation.student_id,
            instructor_id=conversation.instructor_id,
        )

    @BaseService.measure_operation("get_next_booking_for_conversation")
    def get_next_booking_for_conversation(
        self,
        conversation: Conversation,
    ) -> Optional[Booking]:
        """
        Get the next upcoming booking for a conversation's pair.

        Args:
            conversation: The conversation

        Returns:
            Next booking or None if no upcoming bookings
        """
        bookings = self.get_upcoming_bookings_for_conversation(conversation)
        return bookings[0] if bookings else None
