# backend/app/repositories/message_repository.py
"""
Message Repository for the chat system.

Implements all data access operations for message management
following the TRUE 100% repository pattern.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import NotFoundException, RepositoryException
from ..models.booking import Booking
from ..models.message import Message, MessageNotification
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository[Message]):
    """
    Repository for message data access.

    Handles all database operations for the chat system,
    including messages and notifications.
    """

    def __init__(self, db: Session):
        """Initialize with Message model."""
        super().__init__(db, Message)
        self.logger = logging.getLogger(__name__)

    def create_message(self, booking_id: int, sender_id: int, content: str) -> Message:
        """
        Create a new message for a booking.

        Args:
            booking_id: ID of the booking
            sender_id: ID of the sender
            content: Message content

        Returns:
            Created message

        Raises:
            RepositoryException: If creation fails
        """
        try:
            message = Message(booking_id=booking_id, sender_id=sender_id, content=content)
            self.db.add(message)
            self.db.flush()  # Get the ID without committing

            # Create notification for the recipient
            recipient_id = self._get_recipient_id(booking_id, sender_id)
            if recipient_id:
                notification = MessageNotification(message_id=message.id, user_id=recipient_id, is_read=False)
                self.db.add(notification)

            self.logger.info(f"Created message {message.id} for booking {booking_id}")
            return message

        except Exception as e:
            self.logger.error(f"Error creating message: {str(e)}")
            raise RepositoryException(f"Failed to create message: {str(e)}")

    def get_messages_for_booking(self, booking_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        """
        Get messages for a booking with pagination.

        Args:
            booking_id: ID of the booking
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            List of messages ordered by creation time
        """
        try:
            return (
                self.db.query(Message)
                .filter(and_(Message.booking_id == booking_id, Message.is_deleted == False))
                .options(joinedload(Message.sender))
                .order_by(Message.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error fetching messages for booking {booking_id}: {str(e)}")
            raise RepositoryException(f"Failed to fetch messages: {str(e)}")

    def get_unread_messages(self, booking_id: int, user_id: int) -> List[Message]:
        """
        Get unread messages for a user in a booking.

        Args:
            booking_id: ID of the booking
            user_id: ID of the user

        Returns:
            List of unread messages
        """
        try:
            return (
                self.db.query(Message)
                .join(MessageNotification)
                .filter(
                    and_(
                        Message.booking_id == booking_id,
                        Message.is_deleted == False,
                        MessageNotification.user_id == user_id,
                        MessageNotification.is_read == False,
                    )
                )
                .options(joinedload(Message.sender))
                .order_by(Message.created_at)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error fetching unread messages: {str(e)}")
            raise RepositoryException(f"Failed to fetch unread messages: {str(e)}")

    def mark_messages_as_read(self, message_ids: List[int], user_id: int) -> int:
        """
        Mark messages as read for a user.

        Args:
            message_ids: List of message IDs to mark as read
            user_id: ID of the user

        Returns:
            Number of messages marked as read
        """
        try:
            count = (
                self.db.query(MessageNotification)
                .filter(
                    and_(
                        MessageNotification.message_id.in_(message_ids),
                        MessageNotification.user_id == user_id,
                        MessageNotification.is_read == False,
                    )
                )
                .update(
                    {MessageNotification.is_read: True, MessageNotification.read_at: datetime.now(timezone.utc)},
                    synchronize_session=False,
                )
            )

            self.logger.info(f"Marked {count} messages as read for user {user_id}")
            return count

        except Exception as e:
            self.logger.error(f"Error marking messages as read: {str(e)}")
            raise RepositoryException(f"Failed to mark messages as read: {str(e)}")

    def get_unread_count_for_user(self, user_id: int) -> int:
        """
        Get total unread message count for a user.

        Args:
            user_id: ID of the user

        Returns:
            Total number of unread messages
        """
        try:
            return (
                self.db.query(func.count(MessageNotification.id))
                .join(Message)
                .filter(
                    and_(
                        MessageNotification.user_id == user_id,
                        MessageNotification.is_read == False,
                        Message.is_deleted == False,
                    )
                )
                .scalar()
            ) or 0

        except Exception as e:
            self.logger.error(f"Error counting unread messages: {str(e)}")
            raise RepositoryException(f"Failed to count unread messages: {str(e)}")

    def get_booking_participants(self, booking_id: int) -> Optional[Tuple[int, int]]:
        """
        Get the student and instructor IDs for a booking.

        Args:
            booking_id: ID of the booking

        Returns:
            Tuple of (student_id, instructor_id) or None if booking not found
        """
        try:
            booking = self.db.query(Booking.student_id, Booking.instructor_id).filter(Booking.id == booking_id).first()

            if booking:
                return (booking.student_id, booking.instructor_id)
            return None

        except Exception as e:
            self.logger.error(f"Error fetching booking participants: {str(e)}")
            raise RepositoryException(f"Failed to fetch booking participants: {str(e)}")

    def _get_recipient_id(self, booking_id: int, sender_id: int) -> Optional[int]:
        """
        Get the recipient ID for a message notification.

        Args:
            booking_id: ID of the booking
            sender_id: ID of the sender

        Returns:
            ID of the recipient, or None if not found
        """
        participants = self.get_booking_participants(booking_id)
        if not participants:
            return None

        student_id, instructor_id = participants
        # Return the other participant
        return instructor_id if sender_id == student_id else student_id

    def get_latest_message_for_booking(self, booking_id: int) -> Optional[Message]:
        """
        Get the most recent message for a booking.

        Args:
            booking_id: ID of the booking

        Returns:
            Latest message or None
        """
        try:
            return (
                self.db.query(Message)
                .filter(and_(Message.booking_id == booking_id, Message.is_deleted == False))
                .order_by(Message.created_at.desc())
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error fetching latest message: {str(e)}")
            raise RepositoryException(f"Failed to fetch latest message: {str(e)}")

    def delete_message(self, message_id: int) -> bool:
        """
        Soft delete a message.

        Args:
            message_id: ID of the message to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            message = self.db.query(Message).filter(Message.id == message_id).first()
            if message:
                message.is_deleted = True
                message.updated_at = datetime.now(timezone.utc)
                self.logger.info(f"Soft deleted message {message_id}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error deleting message: {str(e)}")
            raise RepositoryException(f"Failed to delete message: {str(e)}")
