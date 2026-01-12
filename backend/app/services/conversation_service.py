# backend/app/services/conversation_service.py
"""
Conversation Service for per-user-pair messaging.

Handles business logic for the conversation system including:
- Listing conversations for a user
- Getting conversation details
- Sending messages with auto-tagging
- Managing conversation metadata
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

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
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


# =============================================================================
# Dataclasses for returning context from service methods
# =============================================================================


@dataclass
class CreateConversationResult:
    """Result of creating/getting a conversation."""

    conversation_id: str
    created: bool
    success: bool = True
    error: Optional[str] = None


@dataclass
class TypingContext:
    """Context needed for publishing typing status."""

    conversation_id: str
    participant_ids: List[str]


@dataclass
class MessageWithPublishContext:
    """Message with context needed for publishing."""

    message: Optional[Message]
    conversation_id: str
    participant_ids: List[str]


@dataclass
class MessageData:
    """Message data with booking details for response building."""

    id: str
    content: str
    sender_id: Optional[str]
    message_type: str
    booking_id: Optional[str]
    booking_details: Optional[Dict[str, Any]]
    created_at: datetime
    edited_at: Optional[datetime]
    is_deleted: bool
    delivered_at: Optional[datetime]
    read_by: List[Dict[str, Any]]
    reactions: List[Dict[str, str]]


@dataclass
class MessagesWithDetailsResult:
    """Result of getting messages with booking details."""

    messages: List[MessageData]
    has_more: bool
    next_cursor: Optional[str]
    conversation_found: bool = True


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
        notification_service: Optional[NotificationService] = None,
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
        self.notification_service = notification_service
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

        Uses database-level filtering for better performance at scale.
        State filtering is done via JOIN/LEFT JOIN instead of post-fetch Python filtering.

        Args:
            user_id: The user's ID
            state_filter: Optional filter by state (active/archived/trashed)
            limit: Maximum number of conversations to return
            cursor: Pagination cursor (ISO timestamp)

        Returns:
            Tuple of (conversations, next_cursor) where next_cursor is
            None if no more pages
        """
        # Use database-level filtering for efficiency
        # Fetch one extra to determine if there's more
        if state_filter in (None, "active"):
            # Active = exclude archived and trashed at database level
            conversations_seq = self.conversation_repository.find_for_user_excluding_states(
                user_id=user_id,
                excluded_states=["archived", "trashed"],
                limit=limit + 1,
                cursor=cursor,
            )
        elif state_filter == "archived":
            # Only archived conversations
            conversations_seq = self.conversation_repository.find_for_user_with_state(
                user_id=user_id,
                state="archived",
                limit=limit + 1,
                cursor=cursor,
            )
        elif state_filter == "trashed":
            # Only trashed conversations
            conversations_seq = self.conversation_repository.find_for_user_with_state(
                user_id=user_id,
                state="trashed",
                limit=limit + 1,
                cursor=cursor,
            )
        else:
            # Unknown filter, return empty
            return [], None

        conversations = list(conversations_seq)

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

    # =========================================================================
    # Batch methods for reducing N+1 queries in conversation list
    # =========================================================================

    @BaseService.measure_operation("batch_get_upcoming_bookings")
    def batch_get_upcoming_bookings(
        self,
        conversations: List[Conversation],
        user_id: str,
    ) -> Dict[str, List[Booking]]:
        """
        Get upcoming bookings for multiple conversations in a single query.

        Args:
            conversations: List of conversations
            user_id: The requesting user's ID (for timezone)

        Returns:
            Dict mapping conversation_id to list of upcoming bookings
        """
        if not conversations:
            return {}

        # Build list of (student_id, instructor_id) pairs
        pairs = [(c.student_id, c.instructor_id) for c in conversations]

        # Get all bookings in one query
        bookings_by_pair = self.booking_repository.batch_find_upcoming_for_pairs(
            pairs=pairs,
            user_id=user_id,
        )

        # Map back to conversation IDs
        result: Dict[str, List[Booking]] = {}
        for conv in conversations:
            pair_key = (conv.student_id, conv.instructor_id)
            result[conv.id] = bookings_by_pair.get(pair_key, [])

        return result

    @BaseService.measure_operation("batch_get_states")
    def batch_get_states(
        self,
        conversation_ids: List[str],
        user_id: str,
    ) -> Dict[str, str]:
        """
        Get states for multiple conversations in a single query.

        Args:
            conversation_ids: List of conversation IDs
            user_id: The user's ID

        Returns:
            Dict mapping conversation_id to state
        """
        return self.conversation_state_repository.batch_get_states(user_id, conversation_ids)

    @BaseService.measure_operation("batch_get_unread_counts")
    def batch_get_unread_counts(
        self,
        conversation_ids: List[str],
        user_id: str,
    ) -> Dict[str, int]:
        """
        Get unread counts for multiple conversations in a single query.

        Args:
            conversation_ids: List of conversation IDs
            user_id: The user's ID

        Returns:
            Dict mapping conversation_id to unread count
        """
        return self.conversation_repository.batch_get_unread_counts(conversation_ids, user_id)

    # =========================================================================
    # Methods with context for route layer (no direct DB access needed in routes)
    # =========================================================================

    def _get_conversation_participants(self, conversation: Conversation) -> List[str]:
        """Get participant IDs from a conversation."""
        return [conversation.student_id, conversation.instructor_id]

    @BaseService.measure_operation("validate_instructor")
    def validate_instructor(self, instructor_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a user exists and is an instructor.

        Args:
            instructor_id: The user ID to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        user_repo = RepositoryFactory.create_user_repository(self.db)
        instructor = user_repo.get_by_id(instructor_id)
        if not instructor:
            return False, "Instructor not found"
        if not instructor.is_instructor:
            return False, "Target user is not an instructor"
        return True, None

    @BaseService.measure_operation("create_conversation_with_message")
    def create_conversation_with_message(
        self,
        student_id: str,
        instructor_id: str,
        initial_message: Optional[str] = None,
    ) -> CreateConversationResult:
        """
        Validate instructor, create/get conversation, and optionally send initial message.

        All operations are wrapped in a transaction and committed.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID
            initial_message: Optional initial message content

        Returns:
            CreateConversationResult with conversation_id and created flag
        """
        # Validate instructor
        is_valid, error = self.validate_instructor(instructor_id)
        if not is_valid:
            return CreateConversationResult(
                conversation_id="",
                created=False,
                success=False,
                error=error,
            )

        with self.transaction():
            conversation, created = self.conversation_repository.get_or_create(
                student_id=student_id,
                instructor_id=instructor_id,
            )

            # If initial message provided and conversation was created, send it
            if initial_message and created:
                self.message_repository.create_conversation_message(
                    conversation_id=conversation.id,
                    sender_id=student_id,
                    content=initial_message,
                    message_type=MESSAGE_TYPE_USER,
                )
                self.conversation_repository.update_last_message_at(
                    conversation.id, datetime.now(timezone.utc)
                )

        return CreateConversationResult(
            conversation_id=conversation.id,
            created=created,
            success=True,
        )

    @BaseService.measure_operation("get_typing_context")
    def get_typing_context(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[TypingContext]:
        """
        Get context needed for publishing typing status.

        Args:
            conversation_id: The conversation ID
            user_id: The user's ID (for access control)

        Returns:
            TypingContext if user is a participant, None otherwise
        """
        conversation = self.get_conversation_by_id(conversation_id, user_id)
        if not conversation:
            return None

        return TypingContext(
            conversation_id=conversation_id,
            participant_ids=self._get_conversation_participants(conversation),
        )

    @BaseService.measure_operation("get_messages_with_details")
    def get_messages_with_details(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before_cursor: Optional[str] = None,
        booking_id_filter: Optional[str] = None,
    ) -> MessagesWithDetailsResult:
        """
        Get messages with booking details pre-fetched.

        Args:
            conversation_id: The conversation ID
            user_id: The user's ID (for access control and is_from_me)
            limit: Maximum messages to return
            before_cursor: Message ID to paginate before
            booking_id_filter: Optional filter by booking ID

        Returns:
            MessagesWithDetailsResult with all data needed for response
        """
        # Verify user is participant
        conversation = self.get_conversation_by_id(conversation_id, user_id)
        if not conversation:
            return MessagesWithDetailsResult(
                messages=[],
                has_more=False,
                next_cursor=None,
                conversation_found=False,
            )

        # Get messages
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
            next_cursor = messages[-1].id

        # Reverse to return in chronological order
        messages.reverse()

        # Collect booking IDs to batch-fetch
        booking_ids = [m.booking_id for m in messages if m.booking_id and m.message_type != "user"]
        bookings_by_id: Dict[str, Booking] = {}
        if booking_ids:
            for booking_id in set(booking_ids):
                booking = self.booking_repository.get_by_id(booking_id)
                if booking:
                    bookings_by_id[booking_id] = booking

        # Build message data with booking details
        message_data_list: List[MessageData] = []
        for msg in messages:
            booking_details = None
            if msg.booking_id and msg.booking_id in bookings_by_id:
                booking = bookings_by_id[msg.booking_id]
                # Get service name
                service_name = "Lesson"
                if booking.instructor_service and booking.instructor_service.name:
                    service_name = booking.instructor_service.name

                # Format start_time
                start_time_str = str(booking.start_time)
                if hasattr(booking.start_time, "strftime"):
                    start_time_str = booking.start_time.strftime("%H:%M")
                elif isinstance(booking.start_time, str):
                    start_time_str = booking.start_time[:5]

                booking_details = {
                    "id": booking.id,
                    "date": booking.booking_date.isoformat(),
                    "start_time": start_time_str,
                    "service_name": service_name,
                }

            # Keep full read_by objects
            read_by_entries = [
                {"user_id": r["user_id"], "read_at": r.get("read_at", "")}
                for r in (msg.read_by or [])
                if isinstance(r, dict) and "user_id" in r
            ]

            # Transform reactions
            reactions = [
                {"user_id": r.user_id, "emoji": r.emoji} for r in (msg.reaction_list or [])
            ]

            message_data_list.append(
                MessageData(
                    id=msg.id,
                    content="This message was deleted" if msg.is_deleted else msg.content,
                    sender_id=msg.sender_id,
                    message_type=msg.message_type or "user",
                    booking_id=msg.booking_id,
                    booking_details=booking_details,
                    created_at=msg.created_at,
                    edited_at=msg.edited_at,
                    is_deleted=bool(msg.is_deleted),
                    delivered_at=msg.delivered_at,
                    read_by=read_by_entries,
                    reactions=reactions,
                )
            )

        return MessagesWithDetailsResult(
            messages=message_data_list,
            has_more=has_more,
            next_cursor=next_cursor,
            conversation_found=True,
        )

    @BaseService.measure_operation("send_message_with_context")
    def send_message_with_context(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        explicit_booking_id: Optional[str] = None,
    ) -> MessageWithPublishContext:
        """
        Send a message and return context needed for publishing.

        All operations are wrapped in a transaction and committed.

        Args:
            conversation_id: The conversation ID
            sender_id: The sender's user ID
            content: Message content
            explicit_booking_id: Optional explicit booking to attach

        Returns:
            MessageWithPublishContext with message and participant IDs
        """
        # Verify user is participant
        conversation = self.get_conversation_by_id(conversation_id, sender_id)
        if not conversation:
            return MessageWithPublishContext(
                message=None,
                conversation_id=conversation_id,
                participant_ids=[],
            )

        participant_ids = self._get_conversation_participants(conversation)

        with self.transaction():
            # Determine booking_id to attach
            booking_id = self._determine_booking_id(
                conversation=conversation,
                explicit_booking_id=explicit_booking_id,
            )

            # Create message
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

        self._send_message_notifications(
            conversation=conversation,
            message=message,
            sender_id=sender_id,
            content=content,
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

        return MessageWithPublishContext(
            message=message,
            conversation_id=conversation_id,
            participant_ids=participant_ids,
        )

    def _send_message_notifications(
        self,
        conversation: Conversation,
        message: Message,
        sender_id: str,
        content: str,
    ) -> None:
        if self.notification_service is None:
            self.notification_service = NotificationService(self.db)

        recipient_id = (
            conversation.instructor_id
            if sender_id == conversation.student_id
            else conversation.student_id
        )

        booking_id = getattr(message, "booking_id", None)
        if not booking_id:
            self.logger.info(
                "Skipping message notification: no booking context",
                extra={"message_id": message.id, "conversation_id": conversation.id},
            )
            return

        booking = self.booking_repository.get_by_id(str(booking_id))
        if not booking:
            self.logger.warning(
                "Skipping message notification: booking not found",
                extra={"message_id": message.id, "booking_id": booking_id},
            )
            return

        try:
            self.notification_service.send_message_notification(
                recipient_id=recipient_id,
                booking=booking,
                sender_id=sender_id,
                message_content=content,
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to send message notification",
                extra={
                    "message_id": message.id,
                    "recipient_id": recipient_id,
                    "error": str(exc),
                },
            )
