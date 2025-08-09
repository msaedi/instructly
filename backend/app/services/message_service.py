# backend/app/services/message_service.py
"""
Message Service for chat functionality.

Handles business logic for the messaging system including:
- Message creation and validation
- Access control and permissions
- Notification management
- Email notifications for offline users
"""

import json
import logging
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.enums import PermissionName
from ..core.exceptions import ForbiddenException, NotFoundException, ServiceException, ValidationException
from ..models.booking import Booking, BookingStatus
from ..models.message import Message
from ..repositories.factory import RepositoryFactory
from ..repositories.message_repository import MessageRepository
from .base import BaseService
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


def measure_operation(func):
    """Decorator for performance monitoring (stub for now)."""
    return func


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
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

    @measure_operation
    def send_message(self, booking_id: int, sender_id: int, content: str) -> Message:
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

        # Create the message
        with self.transaction():
            message = self.repository.create_message(booking_id=booking_id, sender_id=sender_id, content=content)

            # Send email notification if recipient is offline
            self._send_offline_notification(booking, sender_id, content)

            self.logger.info(f"Message sent: booking={booking_id}, sender={sender_id}")
            return message

    @measure_operation
    def get_message_history(self, booking_id: int, user_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
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

        messages = self.repository.get_messages_for_booking(booking_id=booking_id, limit=limit, offset=offset)

        # Reverse to get chronological order (oldest first)
        messages = list(reversed(messages))

        # Ensure read_by is hydrated from notifications for current user view consistency
        try:
            # Assemble read_by from repository
            ids = [m.id for m in messages]
            read_rows = self.repository.get_read_receipts_for_message_ids(ids)
            message_id_to_reads = {}
            for mid, uid, read_at in read_rows:
                message_id_to_reads.setdefault(mid, []).append(
                    {
                        "user_id": uid,
                        "read_at": read_at.isoformat() if read_at else None,
                    }
                )
            for m in messages:
                if not getattr(m, "read_by", None):
                    setattr(m, "read_by", message_id_to_reads.get(m.id, []))

            # Reactions summary and my reactions via repository
            reaction_rows = self.repository.get_reaction_counts_for_message_ids(ids)
            my_reaction_rows = self.repository.get_user_reactions_for_message_ids(ids, user_id)
            message_id_to_reactions = {}
            for mid, emoji, cnt in reaction_rows:
                d = message_id_to_reactions.setdefault(mid, {})
                d[emoji] = int(cnt)
            message_id_to_my = {}
            for mid, emoji in my_reaction_rows:
                lst = message_id_to_my.setdefault(mid, [])
                lst.append(emoji)
            for m in messages:
                setattr(m, "reactions", message_id_to_reactions.get(m.id, {}))
                setattr(m, "my_reactions", message_id_to_my.get(m.id, []))
        except Exception:
            pass

        return messages

    @measure_operation
    def get_unread_count(self, user_id: int) -> int:
        """
        Get total unread message count for a user.

        Args:
            user_id: ID of the user

        Returns:
            Total number of unread messages
        """
        return self.repository.get_unread_count_for_user(user_id)

    @measure_operation
    def send_typing_indicator(self, booking_id: int, user_id: int, user_name: str) -> None:
        """Broadcast a typing indicator for a booking (ephemeral)."""
        # Verify access
        if not self._user_has_booking_access(booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")
        from datetime import datetime, timezone

        payload = {
            "type": "typing_status",
            "booking_id": booking_id,
            "user_id": user_id,
            "user_name": user_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.notify_booking_channel(booking_id, payload)

    @measure_operation
    def mark_messages_as_read(self, message_ids: List[int], user_id: int) -> int:
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
            return count

    @measure_operation
    def mark_booking_messages_as_read(self, booking_id: int, user_id: int) -> int:
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
            return self.mark_messages_as_read(message_ids, user_id)
        return 0

    @measure_operation
    def delete_message(self, message_id: int, user_id: int) -> bool:
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

        with self.transaction():
            return self.repository.delete_message(message_id)

    # Phase 2: reactions
    @measure_operation
    def add_reaction(self, message_id: int, user_id: int, emoji: str) -> bool:
        # Access: user must be participant of the booking of this message
        message = self.repository.get_by_id(message_id)
        if not message:
            raise NotFoundException("Message not found")
        if not self._user_has_booking_access(message.booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")
        with self.transaction():
            # Toggle behavior: if exists, remove; else add (through repository)
            exists = self.repository.has_user_reaction(message_id, user_id, emoji)
            action = "added"
            if exists:
                self.repository.remove_reaction(message_id, user_id, emoji)
                action = "removed"
                ok = True
            else:
                ok = self.repository.add_reaction(message_id, user_id, emoji)

            # Notify via NOTIFY for SSE consumers through repository
            payload = {
                "type": "reaction_update",
                "message_id": message_id,
                "emoji": emoji,
                "user_id": user_id,
                "action": action,
            }
            self.repository.notify_booking_channel(message.booking_id, payload)
            return ok

    @measure_operation
    def remove_reaction(self, message_id: int, user_id: int, emoji: str) -> bool:
        message = self.repository.get_by_id(message_id)
        if not message:
            return False
        if not self._user_has_booking_access(message.booking_id, user_id):
            raise ForbiddenException("You don't have access to this booking")
        with self.transaction():
            ok = self.repository.remove_reaction(message_id, user_id, emoji)
            payload = {
                "type": "reaction_update",
                "message_id": message_id,
                "emoji": emoji,
                "user_id": user_id,
                "action": "removed",
            }
            self.repository.notify_booking_channel(message.booking_id, payload)
            return ok

    @measure_operation
    def edit_message(self, message_id: int, user_id: int, new_content: str) -> bool:
        # validate
        if not new_content or not new_content.strip():
            raise ValidationException("Message content cannot be empty")
        message = self.repository.get_by_id(message_id)
        if not message:
            return False
        if message.sender_id != user_id:
            raise ForbiddenException("You can only edit your own messages")
        # within 5 minutes
        try:
            from datetime import datetime, timedelta, timezone

            from ..core.config import settings

            window_minutes = getattr(settings, "message_edit_window_minutes", 5)
            if (datetime.now(timezone.utc) - message.created_at) > timedelta(minutes=window_minutes):
                raise ValidationException("Edit window has expired")
        except Exception:
            pass
        with self.transaction():
            # Save history and apply edit through repository
            ok = self.repository.apply_message_edit(message_id, new_content.strip())
            # Notify
            payload = {
                "type": "message_edited",
                "message_id": message_id,
                "content": new_content.strip(),
                "edited_at": None,
            }
            self.repository.notify_booking_channel(message.booking_id, payload)
            return ok

    def _user_has_booking_access(self, booking_id: int, user_id: int) -> bool:
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

    def _get_booking(self, booking_id: int) -> Booking:
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

    def _send_offline_notification(self, booking: Booking, sender_id: int, content: str):
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
            recipient_id = booking.instructor_id if sender_id == booking.student_id else booking.student_id

            # TODO: Check if recipient is online (future enhancement)
            # For now, always send email notifications

            # Send email notification
            self.notification_service.send_message_notification(
                recipient_id=recipient_id, booking=booking, sender_id=sender_id, message_content=content
            )

        except Exception as e:
            # Log but don't fail the message send
            self.logger.error(f"Failed to send offline notification: {str(e)}")
