# backend/app/services/message_service.py
"""
Message Service for chat functionality.

Handles business logic for the messaging system including:
- Message creation and validation
- Access control and permissions
- Notification management
- Email notifications for offline users
"""

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from ..core.enums import PermissionName
from ..core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ..models.message import Message
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.factory import RepositoryFactory
from ..repositories.message_repository import MessageRepository
from .base import BaseService

logger = logging.getLogger(__name__)


@dataclass
class MessageWithContext:
    """Message with notification context for routes to use without DB access."""

    message: Optional[Message]
    conversation_id: Optional[str]
    participant_ids: List[str]  # [student_id, instructor_id]


@dataclass
class MarkReadResult:
    """Result of marking messages as read, with notification context."""

    count: int
    marked_message_ids: List[str]
    conversation_id: Optional[str]
    participant_ids: List[str]


@dataclass
class MessageActionResult:
    """Result of message action (edit/delete/reaction) with notification context."""

    success: bool
    message: Optional[Message]
    conversation_id: Optional[str]
    participant_ids: List[str]
    edited_at: Optional[datetime] = None
    action: Optional[str] = None  # "added" or "removed" for reaction operations


@dataclass
class SSEStreamContext:
    """Context for SSE stream initialization, pre-fetched by service layer."""

    has_permission: bool
    missed_messages: List[Message]


class MessageService(BaseService):
    """
    Service for managing chat messages in conversations.

    Handles message creation, retrieval, and notifications
    with proper access control and validation.
    """

    def __init__(self, db: Session):
        """Initialize message service."""
        super().__init__(db)
        self.repository: MessageRepository = RepositoryFactory.create_message_repository(db)
        self.conversation_repository = RepositoryFactory.create_conversation_repository(db)
        self.logger = logging.getLogger(__name__)

    @BaseService.measure_operation("get_stream_context")
    def get_stream_context(
        self,
        user_id: str,
        last_event_id: Optional[str] = None,
        has_permission: Optional[bool] = None,
    ) -> SSEStreamContext:
        """
        Get context for SSE stream initialization.

        Handles permission check and missed message fetch in the service layer,
        so routes don't need to open their own DB sessions.

        Args:
            user_id: ID of the user requesting the stream
            last_event_id: Optional Last-Event-ID header from reconnection
            has_permission: Optional pre-computed permission check (from cached user).
                           If provided, skips the DB query for permission check.

        Returns:
            SSEStreamContext with permission status and missed messages
        """
        # Use pre-computed permission if available (from cached user), else query DB
        if has_permission is None:
            # Import here to avoid circular dependency
            from .permission_service import PermissionService

            permission_service = PermissionService(self.db)
            has_permission = permission_service.user_has_permission(
                user_id, PermissionName.VIEW_MESSAGES
            )

        missed_messages: List[Message] = []

        if has_permission and last_event_id:
            # Fetch user's conversations
            conversations = self.conversation_repository.find_for_user(user_id, 1000, 0)
            conversation_ids = [c.id for c in conversations]

            if conversation_ids:
                # Fetch messages after the last seen event
                missed_messages = self.repository.get_messages_after_id_for_conversations(
                    conversation_ids, last_event_id, 100
                )

        return SSEStreamContext(
            has_permission=has_permission,
            missed_messages=missed_messages,
        )

    @BaseService.measure_operation("get_message_by_id")
    def get_message_by_id(self, message_id: str, user_id: str) -> Optional[Message]:
        """
        Get a message by ID if the user has access.

        Args:
            message_id: ID of the message
            user_id: ID of the requesting user

        Returns:
            The message if found and user has access, None otherwise
        """
        message = self.repository.get_by_id(message_id)
        if not message:
            return None
        if not self._user_has_message_access(message, user_id):
            return None
        return message

    @BaseService.measure_operation("get_unread_count")
    def get_unread_count(self, user_id: str) -> int:
        """
        Get total unread message count for a user.

        Args:
            user_id: ID of the user

        Returns:
            Total number of unread messages
        """
        count = self.repository.get_unread_count_for_user(user_id)
        return int(count or 0)

    @BaseService.measure_operation("mark_messages_as_read")
    def mark_messages_as_read(self, message_ids: List[str], user_id: str) -> int:
        """
        Mark messages as read for a user.

        Args:
            message_ids: List of message IDs to mark as read
            user_id: ID of the user

        Returns:
            Number of messages marked as read
        """
        if not message_ids:
            return 0

        with self.transaction():
            count = self.repository.mark_messages_as_read(message_ids, user_id)
            self.logger.info(f"Marked {count} messages as read for user {user_id}")
            return int(count or 0)

    @BaseService.measure_operation("mark_conversation_messages_as_read")
    def mark_conversation_messages_as_read(self, conversation_id: str, user_id: str) -> int:
        """
        Mark all messages in a conversation as read for a user.

        Args:
            conversation_id: ID of the conversation
            user_id: ID of the user

        Returns:
            Number of messages marked as read
        """
        unread_messages = self.repository.get_unread_messages_by_conversation(
            conversation_id, user_id
        )
        message_ids = [msg.id for msg in unread_messages]
        if not message_ids:
            return 0
        count = self.mark_messages_as_read(message_ids, user_id)
        return count

    @BaseService.measure_operation("delete_message")
    def delete_message(self, message_id: str, user_id: str) -> bool:
        """
        Soft delete a message (only by sender).

        Args:
            message_id: ID of the message to delete
            user_id: ID of the user requesting deletion

        Returns:
            True if deleted, False if not found

        Raises:
            ForbiddenError: If user is not the sender
        """
        message = self.repository.get_by_id(message_id)
        if not message:
            return False

        if message.sender_id != user_id:
            raise ForbiddenException("You can only delete your own messages")

        # Reuse edit window for delete operations
        try:
            from datetime import datetime, timedelta, timezone

            from ..core.config import settings

            window_minutes = getattr(settings, "message_edit_window_minutes", 5)
            if (datetime.now(timezone.utc) - message.created_at) > timedelta(
                minutes=window_minutes
            ):
                raise ValidationException("Delete window has expired")
        except Exception:
            pass

        with self.transaction():
            deleted = self.repository.soft_delete_message(message_id, user_id)
            return bool(deleted)

    # Phase 2: reactions
    @BaseService.measure_operation("add_reaction")
    def add_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        # [MSG-DEBUG] Log reaction add entry
        self.logger.info(
            "[MSG-DEBUG] MessageService.add_reaction: Starting",
            extra={"message_id": message_id, "user_id": user_id, "emoji": emoji},
        )

        # Access: user must be participant of the booking of this message
        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")
        if not self._user_has_message_access(message, user_id):
            raise ForbiddenException("You don't have access to this conversation")
        with self.transaction():
            # Toggle behavior: if exists, remove; else add (through repository)
            exists = bool(self.repository.has_user_reaction(message_id, user_id, emoji))
            action = "added"
            if exists:
                self.repository.remove_reaction(message_id, user_id, emoji)
                action = "removed"
                ok = True
            else:
                ok = bool(self.repository.add_reaction(message_id, user_id, emoji))

            self.logger.info(
                "[MSG-DEBUG] MessageService.add_reaction: Reaction processed",
                extra={
                    "message_id": message_id,
                    "user_id": user_id,
                    "emoji": emoji,
                    "action": action,
                    "ok": ok,
                },
            )

            # Note: Real-time notification is now handled via Redis Pub/Sub in the route
            return ok

    @BaseService.measure_operation("remove_reaction")
    def remove_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        # [MSG-DEBUG] Log reaction remove entry
        self.logger.info(
            "[MSG-DEBUG] MessageService.remove_reaction: Starting",
            extra={"message_id": message_id, "user_id": user_id, "emoji": emoji},
        )

        message = self.repository.get_by_id(message_id)
        if not message:
            return False
        if not self._user_has_message_access(message, user_id):
            raise ForbiddenException("You don't have access to this conversation")
        with self.transaction():
            ok = bool(self.repository.remove_reaction(message_id, user_id, emoji))

            self.logger.info(
                "[MSG-DEBUG] MessageService.remove_reaction: Reaction removed",
                extra={
                    "message_id": message_id,
                    "user_id": user_id,
                    "emoji": emoji,
                    "ok": ok,
                },
            )

            # Note: Real-time notification is now handled via Redis Pub/Sub in the route
            return ok

    @BaseService.measure_operation("edit_message")
    def edit_message(self, message_id: str, user_id: str, new_content: str) -> bool:
        # validate
        if not new_content or not new_content.strip():
            raise ValidationException("Message content cannot be empty")
        message = self.repository.get_by_id(message_id)
        if not message:
            return False
        if message.sender_id != user_id:
            raise ForbiddenException("You can only edit your own messages")
        # no-op if content unchanged
        if message.content == new_content.strip():
            return True
        # within 5 minutes
        try:
            from datetime import datetime, timedelta, timezone

            from ..core.config import settings

            window_minutes = getattr(settings, "message_edit_window_minutes", 5)
            if (datetime.now(timezone.utc) - message.created_at) > timedelta(
                minutes=window_minutes
            ):
                raise ValidationException("Edit window has expired")
        except Exception:
            pass
        with self.transaction():
            # Save history and apply edit through repository
            # Repository returns edited_at timestamp (truthy) or None (falsy)
            edited_at = self.repository.apply_message_edit(message_id, new_content.strip())
            return edited_at is not None

    def _user_has_message_access(self, message: Message, user_id: str) -> bool:
        """
        Check if the user participates in the conversation or booking for a message.
        """
        if message.conversation_id:
            conv_repo = ConversationRepository(self.db)
            conversation = conv_repo.get_by_id(str(message.conversation_id))
            if conversation and user_id in (conversation.student_id, conversation.instructor_id):
                return True
        return False

    def _get_conversation_participants(self, conversation_id: str) -> List[str]:
        """Get participant IDs for a conversation (internal helper)."""
        conversation = self.conversation_repository.get_by_id(conversation_id)
        if conversation:
            return [conversation.student_id, conversation.instructor_id]
        return []

    # =========================================================================
    # NEW METHODS: Return notification context for route-level pub/sub
    # These methods return all data needed so routes don't need DB access
    # =========================================================================

    @BaseService.measure_operation("get_message_with_context")
    def get_message_with_context(self, message_id: str, user_id: str) -> MessageWithContext:
        """
        Get a message with notification context (no DB access needed in route).

        Returns MessageWithContext with:
        - message: The message (if found and user has access)
        - conversation_id: For notification routing
        - participant_ids: Pre-fetched for direct publish functions
        """
        message = self.repository.get_by_id(message_id)
        if not message:
            return MessageWithContext(message=None, conversation_id=None, participant_ids=[])

        if not self._user_has_message_access(message, user_id):
            return MessageWithContext(message=None, conversation_id=None, participant_ids=[])

        # Pre-fetch participants for notifications
        participants = []
        if message.conversation_id:
            participants = self._get_conversation_participants(str(message.conversation_id))

        return MessageWithContext(
            message=message,
            conversation_id=str(message.conversation_id) if message.conversation_id else None,
            participant_ids=participants,
        )

    @BaseService.measure_operation("mark_messages_read_with_context")
    def mark_messages_read_with_context(
        self,
        conversation_id: Optional[str],
        message_ids: Optional[List[str]],
        user_id: str,
    ) -> MarkReadResult:
        """
        Mark messages as read and return notification context.

        Routes call this single method instead of accessing repository directly.
        Returns MarkReadResult with all data needed for notifications.
        """
        marked_message_ids: List[str] = []
        actual_conversation_id: Optional[str] = None
        participant_ids: List[str] = []
        count = 0

        if conversation_id:
            actual_conversation_id = conversation_id
            unread_messages = self.repository.get_unread_messages_by_conversation(
                conversation_id, user_id
            )
            marked_message_ids = [msg.id for msg in unread_messages]

            if marked_message_ids:
                with self.transaction():
                    count = self.repository.mark_messages_as_read(marked_message_ids, user_id)
                    self.logger.info(f"Marked {count} messages as read for user {user_id}")

            # Pre-fetch participants
            participant_ids = self._get_conversation_participants(conversation_id)

        elif message_ids:
            marked_message_ids = message_ids
            with self.transaction():
                count = self.repository.mark_messages_as_read(message_ids, user_id)
                self.logger.info(f"Marked {count} messages as read for user {user_id}")

            # Get conversation_id from first message for notification
            if marked_message_ids:
                first_msg = self.repository.get_by_id(marked_message_ids[0])
                if first_msg and first_msg.conversation_id:
                    actual_conversation_id = str(first_msg.conversation_id)
                    participant_ids = self._get_conversation_participants(actual_conversation_id)

        return MarkReadResult(
            count=int(count or 0),
            marked_message_ids=marked_message_ids,
            conversation_id=actual_conversation_id,
            participant_ids=participant_ids,
        )

    @BaseService.measure_operation("edit_message_with_context")
    def edit_message_with_context(
        self, message_id: str, user_id: str, new_content: str
    ) -> MessageActionResult:
        """
        Edit a message and return notification context.

        Returns MessageActionResult with all data needed for notifications.
        """
        from datetime import datetime, timedelta, timezone

        from ..core.config import settings

        if not new_content or not new_content.strip():
            raise ValidationException("Message content cannot be empty")

        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")

        if message.sender_id != user_id:
            raise ForbiddenException("You can only edit your own messages")

        # Check edit window
        window_minutes = getattr(settings, "message_edit_window_minutes", 5)
        if (datetime.now(timezone.utc) - message.created_at) > timedelta(minutes=window_minutes):
            raise ValidationException("Edit window has expired")

        # No-op if content unchanged
        if message.content == new_content.strip():
            participants = (
                self._get_conversation_participants(str(message.conversation_id))
                if message.conversation_id
                else []
            )
            return MessageActionResult(
                success=True,
                message=message,
                conversation_id=str(message.conversation_id) if message.conversation_id else None,
                participant_ids=participants,
                edited_at=message.edited_at,
            )

        with self.transaction():
            # Repository returns the edited_at timestamp directly (no db.refresh needed)
            edited_at = self.repository.apply_message_edit(message_id, new_content.strip())

        participants = (
            self._get_conversation_participants(str(message.conversation_id))
            if message.conversation_id
            else []
        )

        return MessageActionResult(
            success=True,
            message=message,
            conversation_id=str(message.conversation_id) if message.conversation_id else None,
            participant_ids=participants,
            edited_at=edited_at,
        )

    @BaseService.measure_operation("delete_message_with_context")
    def delete_message_with_context(self, message_id: str, user_id: str) -> MessageActionResult:
        """
        Soft delete a message and return notification context.

        Returns MessageActionResult with all data needed for notifications.
        """
        from datetime import datetime, timedelta, timezone

        from ..core.config import settings

        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")

        if message.sender_id != user_id:
            raise ForbiddenException("You can only delete your own messages")

        # Check delete window (reuses edit window)
        window_minutes = getattr(settings, "message_edit_window_minutes", 5)
        if (datetime.now(timezone.utc) - message.created_at) > timedelta(minutes=window_minutes):
            raise ValidationException("Delete window has expired")

        # Pre-fetch context BEFORE delete
        conversation_id = str(message.conversation_id) if message.conversation_id else None
        participants = (
            self._get_conversation_participants(conversation_id) if conversation_id else []
        )

        with self.transaction():
            deleted = self.repository.soft_delete_message(message_id, user_id)

        return MessageActionResult(
            success=bool(deleted),
            message=message,
            conversation_id=conversation_id,
            participant_ids=participants,
        )

    @BaseService.measure_operation("add_reaction_with_context")
    def add_reaction_with_context(
        self, message_id: str, user_id: str, emoji: str
    ) -> MessageActionResult:
        """
        Add a reaction and return notification context.

        Returns MessageActionResult with all data needed for notifications.
        """
        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")

        if not self._user_has_message_access(message, user_id):
            raise ForbiddenException("You don't have access to this conversation")

        with self.transaction():
            exists = bool(self.repository.has_user_reaction(message_id, user_id, emoji))
            if exists:
                self.repository.remove_reaction(message_id, user_id, emoji)
                action = "removed"
            else:
                self.repository.add_reaction(message_id, user_id, emoji)
                action = "added"

        conversation_id = str(message.conversation_id) if message.conversation_id else None
        participants = (
            self._get_conversation_participants(conversation_id) if conversation_id else []
        )

        return MessageActionResult(
            success=True,
            message=message,
            conversation_id=conversation_id,
            participant_ids=participants,
            action=action,
        )

    @BaseService.measure_operation("remove_reaction_with_context")
    def remove_reaction_with_context(
        self, message_id: str, user_id: str, emoji: str
    ) -> MessageActionResult:
        """
        Remove a reaction and return notification context.

        Returns MessageActionResult with all data needed for notifications.
        """
        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")

        if not self._user_has_message_access(message, user_id):
            raise ForbiddenException("You don't have access to this conversation")

        with self.transaction():
            self.repository.remove_reaction(message_id, user_id, emoji)

        conversation_id = str(message.conversation_id) if message.conversation_id else None
        participants = (
            self._get_conversation_participants(conversation_id) if conversation_id else []
        )

        return MessageActionResult(
            success=True,
            message=message,
            conversation_id=conversation_id,
            participant_ids=participants,
        )
