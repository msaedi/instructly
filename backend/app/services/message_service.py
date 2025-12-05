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
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from ..core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ..models.booking import Booking, BookingStatus
from ..models.message import Message
from ..repositories.conversation_state_repository import (
    ConversationStateRepository,
    ConversationSummaryRepository,
)
from ..repositories.factory import RepositoryFactory
from ..repositories.message_repository import MessageRepository
from .base import BaseService
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


class MessageService(BaseService):
    """
    Service for managing chat messages in bookings.

    Handles message creation, retrieval, and notifications
    with proper access control and validation.
    """

    def __init__(self, db: Session, notification_service: Optional[NotificationService] = None):
        """
        Initialize message service.

        Args:
            db: Database session
            notification_service: Optional notification service for emails
        """
        super().__init__(db)
        self.repository: MessageRepository = RepositoryFactory.create_message_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.conversation_state_repository = ConversationStateRepository(db)
        self.conversation_summary_repository = ConversationSummaryRepository(db)
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

    @BaseService.measure_operation("send_message")
    def send_message(self, booking_id: str, sender_id: str, content: str) -> Message:
        """
        Send a message in a booking chat.

        Args:
            booking_id: ID of the booking
            sender_id: ID of the sender
            content: Message content

        Returns:
            Created message

        Raises:
            ValidationError: If content is invalid
            ForbiddenError: If user doesn't have access to the booking
            NotFoundException: If booking not found
        """
        # [MSG-DEBUG] Log service method entry
        self.logger.info(
            "[MSG-DEBUG] MessageService.send_message: Starting",
            extra={
                "booking_id": booking_id,
                "sender_id": sender_id,
                "content_length": len(content) if content else 0,
            },
        )

        # Validate content
        if not content or not content.strip():
            raise ValidationException("Message content cannot be empty")

        content = content.strip()
        if len(content) > 1000:
            raise ValidationException("Message content cannot exceed 1000 characters")

        # Verify user has access to this booking
        if not self._user_has_booking_access(booking_id, sender_id):
            raise ForbiddenException("You don't have access to this booking")

        # Verify booking is in a valid state for messaging
        booking = self._get_booking(booking_id)
        if booking.status not in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]:
            raise ValidationException(f"Cannot send messages for {booking.status.lower()} bookings")

        self.logger.info(
            "[MSG-DEBUG] MessageService.send_message: Validation passed, creating message",
            extra={
                "booking_id": booking_id,
                "booking_status": booking.status.value
                if hasattr(booking.status, "value")
                else str(booking.status),
                "student_id": booking.student_id,
                "instructor_id": booking.instructor_id,
            },
        )

        # Create the message
        # Note: Database trigger `message_insert_notify` automatically broadcasts to
        # SSE subscribers when a message is inserted (see migration 006)
        with self.transaction():
            message = self.repository.create_message(
                booking_id=booking_id, sender_id=sender_id, content=content
            )

            self.logger.info(
                "[MSG-DEBUG] MessageService.send_message: Message created, DB trigger should fire",
                extra={
                    "booking_id": booking_id,
                    "message_id": message.id,
                    "sender_id": sender_id,
                },
            )

            # AUTO-RESTORE: If recipient has archived/trashed this conversation, restore it
            recipient_id = self._get_recipient_id(booking_id, sender_id)
            if recipient_id:
                self.conversation_state_repository.restore_to_active(
                    recipient_id, booking_id=booking_id
                )

            # Send email notification if recipient is offline
            self._send_offline_notification(booking, sender_id, content)

            self.logger.info(
                "[MSG-DEBUG] MessageService.send_message: Success",
                extra={
                    "booking_id": booking_id,
                    "message_id": message.id,
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                },
            )
            return message

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
        if not self._user_has_booking_access(message.booking_id, user_id):
            return None
        return message

    @BaseService.measure_operation("get_message_history")
    def get_message_history(
        self, booking_id: str, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Message]:
        """
        Get message history for a booking.

        Args:
            booking_id: ID of the booking
            user_id: ID of the requesting user
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            List of messages ordered by creation time

        Raises:
            ForbiddenError: If user doesn't have access to the booking
        """
        # Verify user has access
        if not self._user_has_booking_access(booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")

        messages = self.repository.get_messages_for_booking(
            booking_id=booking_id, limit=limit, offset=offset
        )

        # Reverse to get chronological order (oldest first)
        messages = list(reversed(messages))

        # Ensure read_by is hydrated from notifications for current user view consistency
        try:
            # Assemble read_by from repository
            ids = [m.id for m in messages]
            read_rows = self.repository.get_read_receipts_for_message_ids(ids)
            message_id_to_reads: dict[str, list[dict[str, str | None]]] = {}
            for mid, uid, read_at in read_rows:
                message_id_to_reads.setdefault(mid, []).append(
                    {
                        "user_id": uid,
                        "read_at": read_at.isoformat() if read_at else None,
                    }
                )
            for m in messages:
                original_read_by = getattr(m, "read_by", None)
                if not original_read_by:
                    setattr(m, "read_by", message_id_to_reads.get(m.id, []))

            # Reactions summary and my reactions via repository
            reaction_rows = self.repository.get_reaction_counts_for_message_ids(ids)
            my_reaction_rows = self.repository.get_user_reactions_for_message_ids(ids, user_id)
            message_id_to_reactions: dict[str, dict[str, int]] = {}
            for mid, emoji, cnt in reaction_rows:
                d = message_id_to_reactions.setdefault(mid, {})
                d[emoji] = int(cnt)
            message_id_to_my: dict[str, list[str]] = {}
            for mid, emoji in my_reaction_rows:
                lst = message_id_to_my.setdefault(mid, [])
                lst.append(emoji)
            for m in messages:
                setattr(m, "reactions", message_id_to_reactions.get(m.id, {}))
                setattr(m, "my_reactions", message_id_to_my.get(m.id, []))
        except Exception:
            pass

        return messages

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

    @BaseService.measure_operation("send_typing_indicator")
    def send_typing_indicator(self, booking_id: str, user_id: str, user_name: str) -> Optional[str]:
        """Validate typing indicator request and return the recipient user ID."""
        # Verify access
        if not self._user_has_booking_access(booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")

        # Get booking to determine the other participant
        booking = self._get_booking(booking_id)

        # Determine recipient (the other participant, not the sender)
        recipient_id = (
            booking.student_id if user_id == booking.instructor_id else booking.instructor_id
        )

        return cast(Optional[str], recipient_id)

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

    @BaseService.measure_operation("mark_booking_messages_as_read")
    def mark_booking_messages_as_read(self, booking_id: str, user_id: str) -> int:
        """
        Mark all messages in a booking as read for a user.

        Args:
            booking_id: ID of the booking
            user_id: ID of the user

        Returns:
            Number of messages marked as read

        Raises:
            ForbiddenError: If user doesn't have access to the booking
        """
        # Verify user has access
        if not self._user_has_booking_access(booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")

        # Get unread messages for this booking
        unread_messages = self.repository.get_unread_messages(booking_id, user_id)
        message_ids = [msg.id for msg in unread_messages]

        if message_ids:
            count = self.mark_messages_as_read(message_ids, user_id)

            # Also update conversation_state to reset unread count
            self._reset_conversation_unread_count(booking_id, user_id)

            return count
        return 0

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

            # Refresh conversation_state if this was the last message
            if deleted and deleted.booking_id:
                self._refresh_conversation_state_after_delete(
                    booking_id=str(deleted.booking_id), deleted_message_id=message_id
                )

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
        if not self._user_has_booking_access(message.booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")
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
                    "booking_id": message.booking_id,
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
        if not self._user_has_booking_access(message.booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")
        with self.transaction():
            ok = bool(self.repository.remove_reaction(message_id, user_id, emoji))

            self.logger.info(
                "[MSG-DEBUG] MessageService.remove_reaction: Reaction removed",
                extra={
                    "message_id": message_id,
                    "user_id": user_id,
                    "emoji": emoji,
                    "ok": ok,
                    "booking_id": message.booking_id,
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

    def _user_has_booking_access(self, booking_id: str, user_id: str) -> bool:
        """
        Check if user has access to a booking's messages.

        Args:
            booking_id: ID of the booking
            user_id: ID of the user

        Returns:
            True if user is student or instructor of the booking
        """
        participants = self.repository.get_booking_participants(booking_id)
        if not participants:
            return False

        student_id, instructor_id = participants
        return user_id in [student_id, instructor_id]

    def _get_booking(self, booking_id: str) -> Booking:
        """
        Get a booking by ID.

        Args:
            booking_id: ID of the booking

        Returns:
            Booking object

        Raises:
            NotFoundException: If booking not found
        """
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found")
        return booking

    def _send_offline_notification(self, booking: Booking, sender_id: str, content: str) -> None:
        """
        Send email notification for offline recipient.

        Args:
            booking: Booking object
            sender_id: ID of the sender
            content: Message content
        """
        # Skip if notification service not available
        if not self.notification_service:
            return

        try:
            # Determine recipient
            recipient_id = (
                booking.instructor_id if sender_id == booking.student_id else booking.student_id
            )

            # TODO: Check if recipient is online (future enhancement)
            # For now, always send email notifications

            # Send email notification
            self.notification_service.send_message_notification(
                recipient_id=recipient_id,
                booking=booking,
                sender_id=sender_id,
                message_content=content,
            )

        except Exception as e:
            # Log but don't fail the message send
            self.logger.error(f"Failed to send offline notification: {str(e)}")

    # Phase 3: Inbox state
    @BaseService.measure_operation("get_inbox_state")
    def get_inbox_state(
        self,
        user_id: str,
        user_role: str,
        state_filter: Optional[str] = None,  # None = active only, 'archived', 'trashed'
        type_filter: Optional[str] = None,  # None = all, 'student', 'platform'
    ) -> Dict[str, Any]:
        """
        Get all conversations for a user with unread counts and previews.

        Args:
            user_id: ID of the user
            user_role: 'instructor' or 'student'
            state_filter: Optional filter by state ('archived', 'trashed', or None for active)
            type_filter: Optional filter by type ('student', 'platform')

        Returns:
            Dict with conversations list, total_unread count, unread_conversations count, and state_counts
        """
        # Get all booking IDs that are archived or trashed for this user
        archived_ids = set(
            self.conversation_state_repository.get_booking_ids_by_state(user_id, "archived")
        )
        trashed_ids = set(
            self.conversation_state_repository.get_booking_ids_by_state(user_id, "trashed")
        )

        # Get all conversations from repository
        all_conversations = self.repository.get_inbox_state(user_id, user_role)
        is_instructor = user_role == "instructor"

        # Build conversation list with state information
        conversation_list = []
        for conv in all_conversations:
            # Get the OTHER user (not the current user)
            other_user = conv.student if is_instructor else conv.instructor
            unread = conv.instructor_unread_count if is_instructor else conv.student_unread_count

            # Determine conversation type (student vs platform)
            # Platform messages would be identified by a specific user or role
            # For now, assume all are 'student' unless we have platform message logic
            conv_type = "student"  # TODO: Add platform message detection if needed

            conversation_list.append(
                {
                    "id": conv.booking_id,
                    "type": conv_type,
                    "other_user": {
                        "id": other_user.id,
                        "name": f"{other_user.first_name} {other_user.last_name[0]}."
                        if other_user.last_name
                        else other_user.first_name,
                        "avatar_url": getattr(other_user, "avatar_url", None),
                    },
                    "unread_count": unread,
                    "last_message": {
                        "preview": conv.last_message_preview,
                        "at": conv.last_message_at.isoformat() if conv.last_message_at else None,
                        "is_mine": conv.last_message_sender_id == user_id,
                    }
                    if conv.last_message_id
                    else None,
                }
            )

        # Filter by state
        if state_filter == "archived":
            filtered_conversations = [c for c in conversation_list if c["id"] in archived_ids]
        elif state_filter == "trashed":
            filtered_conversations = [c for c in conversation_list if c["id"] in trashed_ids]
        else:
            # Default: active only (exclude archived and trashed)
            filtered_conversations = [
                c
                for c in conversation_list
                if c["id"] not in archived_ids and c["id"] not in trashed_ids
            ]

        # Filter by type (student vs platform)
        if type_filter == "student":
            filtered_conversations = [
                c for c in filtered_conversations if c.get("type") == "student"
            ]
        elif type_filter == "platform":
            filtered_conversations = [
                c for c in filtered_conversations if c.get("type") == "platform"
            ]

        # Calculate counts for active conversations
        active_conversations = [
            c
            for c in conversation_list
            if c["id"] not in archived_ids and c["id"] not in trashed_ids
        ]

        result: Dict[str, Any] = {
            "conversations": filtered_conversations,
            "total_unread": sum(c.get("unread_count", 0) for c in filtered_conversations),
            "unread_conversations": len(
                [c for c in filtered_conversations if c.get("unread_count", 0) > 0]
            ),
            "state_counts": {
                "active": len(active_conversations),
                "archived": len(archived_ids),
                "trashed": len(trashed_ids),
            },
        }

        return result

    @BaseService.measure_operation("generate_inbox_etag")
    def generate_inbox_etag(self, inbox_state: Dict[str, Any]) -> str:
        """
        Generate ETag hash from inbox state for caching.

        Args:
            inbox_state: The inbox state dictionary

        Returns:
            MD5 hash of the inbox state (hex digest)
        """
        from hashlib import md5
        import json

        # Sort keys for consistent hashing
        content = json.dumps(inbox_state, sort_keys=True, default=str)
        return md5(content.encode()).hexdigest()

    @BaseService.measure_operation("set_conversation_state")
    def set_conversation_state(self, user_id: str, booking_id: str, state: str) -> Dict[str, Any]:
        """
        Set conversation state (archive, trash, or restore).

        Args:
            user_id: ID of the user
            booking_id: ID of the booking/conversation
            state: New state ('active', 'archived', 'trashed')

        Returns:
            Dict with booking_id, state, and state_changed_at

        Raises:
            ValueError: If state is invalid
        """
        if state not in ("active", "archived", "trashed"):
            raise ValueError(f"Invalid state: {state}")

        with self.transaction():
            result = self.conversation_state_repository.set_state(
                user_id, state, booking_id=booking_id
            )

        return {
            "booking_id": booking_id,
            "state": result.state,
            "state_changed_at": result.state_changed_at.isoformat()
            if result.state_changed_at
            else None,
        }

    @BaseService.measure_operation("get_conversation_state")
    def get_conversation_state(self, user_id: str, booking_id: str) -> str:
        """
        Get conversation state for a user. Defaults to 'active' if no record.

        Args:
            user_id: ID of the user
            booking_id: ID of the booking/conversation

        Returns:
            State string ('active', 'archived', or 'trashed')
        """
        state_record = self.conversation_state_repository.get_state(user_id, booking_id=booking_id)
        state_value = state_record.state if state_record else "active"
        return cast(str, state_value)

    def _get_recipient_id(self, booking_id: str, sender_id: str) -> Optional[str]:
        """
        Get the other participant in the conversation.

        Args:
            booking_id: ID of the booking
            sender_id: ID of the sender

        Returns:
            User ID of the recipient, or None if booking not found
        """
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            return None
        if booking.student_id == sender_id:
            return str(booking.instructor_id)
        elif booking.instructor_id == sender_id:
            return str(booking.student_id)
        return None

    @BaseService.measure_operation("get_recipient_id")
    def get_recipient_id(self, booking_id: str, sender_id: str) -> Optional[str]:
        """
        Get the other participant in the conversation (public wrapper).

        Args:
            booking_id: ID of the booking
            sender_id: ID of the sender

        Returns:
            User ID of the recipient, or None if booking not found
        """
        return self._get_recipient_id(booking_id, sender_id)

    def _reset_conversation_unread_count(self, booking_id: str, user_id: str) -> None:
        """
        Reset the unread count in conversation_state for a specific user.

        Args:
            booking_id: ID of the booking/conversation
            user_id: ID of the user whose unread count should be reset
        """
        try:
            # Get user repository to fetch user
            from ..repositories.factory import RepositoryFactory

            user_repository = RepositoryFactory.create_user_repository(self.db)
            user = user_repository.get_by_id(user_id)
            if not user:
                return

            is_instructor = user.role == "instructor"

            # Use repository method to reset unread count
            self.repository.reset_conversation_unread_count(booking_id, user_id, is_instructor)

        except Exception as e:
            # Log but don't fail the operation
            self.logger.error(f"Failed to reset conversation_state unread count: {str(e)}")

    def _refresh_conversation_state_after_delete(
        self, booking_id: str, deleted_message_id: str
    ) -> None:
        """If the deleted message was the latest, update conversation_state to previous message."""
        try:
            conv_state = self.conversation_summary_repository.get_by_booking_id(booking_id)
            if not conv_state or conv_state.last_message_id != deleted_message_id:
                return

            latest_message = self.repository.get_latest_message_for_booking(booking_id)
            self.conversation_summary_repository.update_after_message_delete(
                booking_id, latest_message
            )
        except Exception as e:
            self.logger.error(f"Failed to refresh conversation_state after delete: {e}")
