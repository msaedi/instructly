# backend/app/repositories/message_repository.py
"""
Message Repository for the chat system.

Implements all data access operations for message management
following the TRUE 100% repository pattern.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Mapping, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, func
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import NotFoundException, RepositoryException
from ..models.booking import Booking
from ..models.message import Message, MessageNotification
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

    def create_message(self, booking_id: str, sender_id: str, content: str) -> Message:
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
                notification = MessageNotification(
                    message_id=message.id, user_id=recipient_id, is_read=False
                )
                self.db.add(notification)

            self.logger.info(f"Created message {message.id} for booking {booking_id}")
            return message

        except Exception as e:
            self.logger.error(f"Error creating message: {str(e)}")
            raise RepositoryException(f"Failed to create message: {str(e)}")

    def get_messages_for_booking(
        self, booking_id: str, limit: int = 50, offset: int = 0
    ) -> List[Message]:
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
            return cast(
                List[Message],
                (
                    self.db.query(Message)
                    .filter(and_(Message.booking_id == booking_id, Message.is_deleted == False))
                    .options(joinedload(Message.sender))
                    .order_by(Message.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error fetching messages for booking {booking_id}: {str(e)}")
            raise RepositoryException(f"Failed to fetch messages: {str(e)}")

    def get_unread_messages(self, booking_id: str, user_id: str) -> List[Message]:
        """
        Get unread messages for a user in a booking.

        Args:
            booking_id: ID of the booking
            user_id: ID of the user

        Returns:
            List of unread messages
        """
        try:
            return cast(
                List[Message],
                (
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
                ),
            )
        except Exception as e:
            self.logger.error(f"Error fetching unread messages: {str(e)}")
            raise RepositoryException(f"Failed to fetch unread messages: {str(e)}")

    def mark_messages_as_read(self, message_ids: List[str], user_id: str) -> int:
        """
        Mark messages as read for a user.

        Args:
            message_ids: List of message IDs to mark as read
            user_id: ID of the user

        Returns:
            Number of messages marked as read
        """
        try:
            count = cast(
                int,
                (
                    self.db.query(MessageNotification)
                    .filter(
                        and_(
                            MessageNotification.message_id.in_(message_ids),
                            MessageNotification.user_id == user_id,
                            MessageNotification.is_read == False,
                        )
                    )
                    .update(
                        {
                            MessageNotification.is_read: True,
                            MessageNotification.read_at: datetime.now(timezone.utc),
                        },
                        synchronize_session=False,
                    )
                ),
            )

            self.logger.info(f"Marked {count} messages as read for user {user_id}")
            return count

        except Exception as e:
            self.logger.error(f"Error marking messages as read: {str(e)}")
            raise RepositoryException(f"Failed to mark messages as read: {str(e)}")

    def get_unread_count_for_user(self, user_id: str) -> int:
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

    # --- Aggregations & helpers for services ---
    def get_read_receipts_for_message_ids(
        self, message_ids: Sequence[str]
    ) -> List[Tuple[str, str, Optional[datetime]]]:
        """
        Return tuples of (message_id, user_id, read_at) for read notifications on given messages.
        """
        try:
            rows = cast(
                List[Tuple[str, str, Optional[datetime]]],
                (
                    self.db.query(
                        MessageNotification.message_id,
                        MessageNotification.user_id,
                        MessageNotification.read_at,
                    )
                    .filter(
                        and_(
                            MessageNotification.message_id.in_(message_ids),
                            MessageNotification.is_read == True,
                        )
                    )
                    .all()
                ),
            )
            return rows
        except Exception as e:
            self.logger.error(f"Error fetching read receipts: {str(e)}")
            raise RepositoryException(f"Failed to fetch read receipts: {str(e)}")

    def get_reaction_counts_for_message_ids(
        self, message_ids: Sequence[str]
    ) -> List[Tuple[str, str, int]]:
        """
        Return tuples of (message_id, emoji, count) for reactions on given messages.
        """
        try:
            from ..models.message import MessageReaction

            rows = cast(
                Sequence[Tuple[str, str, Any]],
                (
                    self.db.query(
                        MessageReaction.message_id,
                        MessageReaction.emoji,
                        func.count(MessageReaction.id),
                    )
                    .filter(MessageReaction.message_id.in_(message_ids))
                    .group_by(MessageReaction.message_id, MessageReaction.emoji)
                    .all()
                ),
            )
            return [(mid, emoji, int(cnt)) for (mid, emoji, cnt) in rows]
        except Exception as e:
            self.logger.error(f"Error fetching reaction counts: {str(e)}")
            raise RepositoryException(f"Failed to fetch reaction counts: {str(e)}")

    def get_user_reactions_for_message_ids(
        self, message_ids: List[str], user_id: str
    ) -> List[Tuple[str, str]]:
        """
        Return tuples of (message_id, emoji) for reactions by the user on given messages.
        """
        try:
            from ..models.message import MessageReaction

            rows = cast(
                List[Tuple[str, str]],
                (
                    self.db.query(MessageReaction.message_id, MessageReaction.emoji)
                    .filter(
                        and_(
                            MessageReaction.message_id.in_(message_ids),
                            MessageReaction.user_id == user_id,
                        )
                    )
                    .all()
                ),
            )
            return rows
        except Exception as e:
            self.logger.error(f"Error fetching user reactions: {str(e)}")
            raise RepositoryException(f"Failed to fetch user reactions: {str(e)}")

    def has_user_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        """Check if a user has already reacted with emoji to a message."""
        try:
            from ..models.message import MessageReaction

            exists = (
                self.db.query(MessageReaction)
                .filter(
                    and_(
                        MessageReaction.message_id == message_id,
                        MessageReaction.user_id == user_id,
                        MessageReaction.emoji == emoji,
                    )
                )
                .first()
            )
            return exists is not None
        except Exception as e:
            self.logger.error(f"Error checking reaction existence: {str(e)}")
            raise RepositoryException(f"Failed to check reaction existence: {str(e)}")

    def apply_message_edit(self, message_id: str, new_content: str) -> bool:
        """
        Create a MessageEdit history row and update the Message content and edited_at.
        """
        try:
            from datetime import datetime, timezone

            from ..models.message import MessageEdit

            message = self.db.query(Message).filter(Message.id == message_id).first()
            if not message:
                return False
            # Save history
            self.db.add(MessageEdit(message_id=message_id, original_content=message.content))
            # Update message
            message.content = new_content
            message.edited_at = datetime.now(timezone.utc)
            return True
        except Exception as e:
            self.logger.error(f"Error applying message edit: {str(e)}")
            raise RepositoryException(f"Failed to apply message edit: {str(e)}")

    def notify_booking_channel(self, booking_id: str, payload: Mapping[str, Any]) -> None:
        """Send a JSON payload to the booking chat LISTEN/NOTIFY channel.

        This is allowed at repository level for DB adjacency per repo pattern rules.
        """
        try:
            import json as _json

            from sqlalchemy import text

            self.db.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": f"booking_chat_{booking_id}", "payload": _json.dumps(payload)},
            )
            # Ensure NOTIFY is flushed on platforms where autocommit is disabled
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            # Non-fatal
            logger.warning(f"notify_booking_channel failed: {e}")

    def get_booking_participants(self, booking_id: str) -> Optional[Tuple[str, str]]:
        """
        Get the student and instructor IDs for a booking.

        Args:
            booking_id: ID of the booking

        Returns:
            Tuple of (student_id, instructor_id) or None if booking not found
        """
        try:
            booking_row = cast(
                Optional[Row[Any]],
                (
                    self.db.query(Booking.student_id, Booking.instructor_id)
                    .filter(Booking.id == booking_id)
                    .first()
                ),
            )

            if booking_row is None:
                return None

            mapping = booking_row._mapping
            student_id = cast(Optional[str], mapping.get("student_id"))
            instructor_id = cast(Optional[str], mapping.get("instructor_id"))

            if student_id is None or instructor_id is None:
                return None
            return (student_id, instructor_id)

        except Exception as e:
            self.logger.error(f"Error fetching booking participants: {str(e)}")
            raise RepositoryException(f"Failed to fetch booking participants: {str(e)}")

    def _get_recipient_id(self, booking_id: str, sender_id: str) -> Optional[str]:
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

    def get_latest_message_for_booking(self, booking_id: str) -> Optional[Message]:
        """
        Get the most recent message for a booking.

        Args:
            booking_id: ID of the booking

        Returns:
            Latest message or None
        """
        try:
            return cast(
                Optional[Message],
                (
                    self.db.query(Message)
                    .filter(and_(Message.booking_id == booking_id, Message.is_deleted == False))
                    .order_by(Message.created_at.desc())
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error fetching latest message: {str(e)}")
            raise RepositoryException(f"Failed to fetch latest message: {str(e)}")

    def delete_message(self, message_id: str) -> bool:
        """
        Soft delete a message.

        Args:
            message_id: ID of the message to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            message = cast(
                Optional[Message],
                self.db.query(Message).filter(Message.id == message_id).first(),
            )
            if message:
                message.is_deleted = True
                message.updated_at = datetime.now(timezone.utc)
                self.logger.info(f"Soft deleted message {message_id}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error deleting message: {str(e)}")
            raise RepositoryException(f"Failed to delete message: {str(e)}")

    # Phase 2: reactions
    def add_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        try:
            from ..models.message import MessageReaction

            # Ensure message exists
            if not self.db.query(Message).filter(Message.id == message_id).first():
                raise NotFoundException("Message not found")
            # Avoid unique constraint violation
            exists = (
                self.db.query(MessageReaction)
                .filter(
                    MessageReaction.message_id == message_id,
                    MessageReaction.user_id == user_id,
                    MessageReaction.emoji == emoji,
                )
                .first()
            )
            if exists:
                return True
            reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
            self.db.add(reaction)
            self.logger.info(f"Added reaction {emoji} by {user_id} on message {message_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding reaction: {str(e)}")
            raise RepositoryException(f"Failed to add reaction: {str(e)}")

    def remove_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        try:
            from ..models.message import MessageReaction

            q = self.db.query(MessageReaction).filter(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
            if q.first() is None:
                return False
            q.delete(synchronize_session=False)
            self.logger.info(f"Removed reaction {emoji} by {user_id} on message {message_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error removing reaction: {str(e)}")
            raise RepositoryException(f"Failed to remove reaction: {str(e)}")
