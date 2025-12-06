# backend/app/services/message_service.py
"""
Message Service for chat functionality.

Handles business logic for the messaging system including:
- Message creation and validation
- Access control and permissions
- Notification management
- Email notifications for offline users
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from ..core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ..models.message import Message
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.factory import RepositoryFactory
from ..repositories.message_repository import MessageRepository
from .base import BaseService

logger = logging.getLogger(__name__)


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
            ok = bool(self.repository.apply_message_edit(message_id, new_content.strip()))
            return ok

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
