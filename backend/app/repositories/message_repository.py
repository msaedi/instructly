# backend/app/repositories/message_repository.py
"""
Message Repository for the chat system.

Implements all data access operations for message management
following the TRUE 100% repository pattern.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import NotFoundException, RepositoryException
from ..models.conversation import Conversation
from ..models.message import MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED, Message, MessageNotification
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

# Time window (in minutes) to detect if a cancellation is part of a reschedule operation.
# When a booking is rescheduled, the system creates a "reschedule" message first,
# then triggers a "cancel" for the old booking. This window prevents duplicate messages.
# 1 minute is sufficient since both operations happen in the same request cycle.
RESCHEDULE_DETECTION_WINDOW_MINUTES = 1


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

    def get_unread_messages_by_conversation(
        self, conversation_id: str, user_id: str
    ) -> List[Message]:
        """
        Get unread messages for a user in a conversation (across all bookings).

        Phase 7: Used for SSE read receipt publishing when messages span multiple bookings.

        Args:
            conversation_id: ID of the conversation
            user_id: ID of the user

        Returns:
            List of unread messages in the conversation
        """
        try:
            return cast(
                List[Message],
                (
                    self.db.query(Message)
                    .join(MessageNotification)
                    .filter(
                        and_(
                            Message.conversation_id == conversation_id,
                            Message.is_deleted == False,
                            Message.deleted_at.is_(None),
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
            self.logger.error(f"Error fetching unread messages by conversation: {str(e)}")
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
            # Update notifications
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

            # Update Message.read_by field for persistence
            if count > 0:
                read_at = datetime.now(timezone.utc).isoformat()
                messages = self.db.query(Message).filter(Message.id.in_(message_ids)).all()

                for message in messages:
                    # Get existing read_by array or initialize empty list
                    read_by = message.read_by if message.read_by else []

                    # Check if user hasn't already read this message
                    if not any(r.get("user_id") == user_id for r in read_by):
                        read_by.append({"user_id": user_id, "read_at": read_at})
                        message.read_by = read_by
                        # Force SQLAlchemy to detect the change
                        from sqlalchemy.orm.attributes import flag_modified

                        flag_modified(message, "read_by")

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
                        Message.deleted_at.is_(None),
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

    def soft_delete_message(self, message_id: str, user_id: str) -> Optional[Message]:
        """
        Soft delete a message by marking deletion metadata.

        Args:
            message_id: ID of the message to delete
            user_id: ULID of the user performing the deletion

        Returns:
            The updated message or None if not found
        """
        try:
            message = cast(
                Optional[Message],
                self.db.query(Message).filter(Message.id == message_id).first(),
            )
            if not message:
                return None

            message.is_deleted = True
            now = datetime.now(timezone.utc)
            message.deleted_at = now
            message.deleted_by = user_id
            message.updated_at = now
            self.logger.info(f"Soft deleted message {message_id} by user {user_id}")
            return message

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

    # Phase 2: SSE catch-up support
    def get_messages_after_id_for_conversations(
        self, conversation_ids: List[str], after_message_id: str, limit: int = 100
    ) -> List[Message]:
        """
        Get messages created after a given message ID for specified conversations.

        Args:
            conversation_ids: List of conversation IDs
            after_message_id: Last-Event-ID (message ULID)
            limit: Maximum messages to return
        """
        try:
            if not conversation_ids:
                return []

            return cast(
                List[Message],
                (
                    self.db.query(Message)
                    .filter(
                        and_(
                            Message.conversation_id.in_(conversation_ids),
                            Message.id > after_message_id,
                        )
                    )
                    .order_by(Message.id)
                    .limit(limit)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error fetching messages after ID (conversation): {str(e)}")
            raise RepositoryException(f"Failed to fetch messages after ID: {str(e)}")

    # Per-user-pair conversation support
    def create_conversation_message(
        self,
        conversation_id: str,
        sender_id: Optional[str],
        content: str,
        message_type: str = "user",
        booking_id: Optional[str] = None,
    ) -> Message:
        """
        Create a new message for a conversation (per-user-pair messaging).

        For system messages (booking created, cancelled, etc.), sender_id should be None.

        Args:
            conversation_id: ID of the conversation
            sender_id: ID of the sender, or None for system messages
            content: Message content
            message_type: Type of message (user, system_booking_created, etc.)
            booking_id: Optional booking ID to associate with message

        Returns:
            Created message

        Raises:
            RepositoryException: If creation fails
        """
        try:
            from ..core.ulid_helper import generate_ulid

            message = Message(
                id=generate_ulid(),
                conversation_id=conversation_id,
                booking_id=booking_id,
                sender_id=sender_id,
                content=content,
                message_type=message_type,
                created_at=datetime.now(timezone.utc),
                delivered_at=datetime.now(timezone.utc),
            )
            self.db.add(message)
            self.db.flush()

            # Create notification for the recipient to power read receipts
            if sender_id:
                conversation = (
                    self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
                )
                if conversation:
                    recipient_id = (
                        conversation.instructor_id
                        if sender_id == conversation.student_id
                        else conversation.student_id
                    )
                    notification = MessageNotification(
                        message_id=message.id,
                        user_id=recipient_id,
                        is_read=False,
                    )
                    self.db.add(notification)
                    self.db.flush()

            self.logger.info(
                f"Created conversation message {message.id} in conversation {conversation_id}"
            )
            return message

        except Exception as e:
            self.logger.error(f"Error creating conversation message: {str(e)}")
            raise RepositoryException(f"Failed to create conversation message: {str(e)}")

    def find_by_conversation(
        self,
        conversation_id: str,
        limit: int = 50,
        before_cursor: Optional[str] = None,
        booking_id_filter: Optional[str] = None,
    ) -> List[Message]:
        """
        Find messages for a conversation with cursor-based pagination.

        Messages are returned in descending order (newest first).

        Args:
            conversation_id: ID of the conversation
            limit: Maximum number of messages to return
            before_cursor: Message ID to paginate before (returns older messages)
            booking_id_filter: Optional booking ID to filter messages

        Returns:
            List of messages ordered by created_at descending
        """
        try:
            query = self.db.query(Message).filter(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.is_deleted == False,
                    Message.deleted_at.is_(None),
                )
            )

            if booking_id_filter:
                query = query.filter(Message.booking_id == booking_id_filter)

            if before_cursor:
                cursor_message = self.db.query(Message).filter(Message.id == before_cursor).first()
                if cursor_message:
                    query = query.filter(Message.created_at < cursor_message.created_at)

            query = query.options(
                joinedload(Message.sender),
                joinedload(Message.reaction_list),  # Eager load reactions for API response
            )
            query = query.order_by(Message.created_at.desc())

            return cast(List[Message], query.limit(limit).all())

        except Exception as e:
            self.logger.error(f"Error fetching messages for conversation: {str(e)}")
            raise RepositoryException(f"Failed to fetch messages for conversation: {str(e)}")

    def has_recent_reschedule_message(
        self,
        conversation_id: str,
        since_minutes: int = RESCHEDULE_DETECTION_WINDOW_MINUTES,
    ) -> bool:
        """
        Check if a reschedule system message was created recently in a conversation.

        Used to suppress cancellation messages when part of a reschedule operation.

        Args:
            conversation_id: ID of the conversation
            since_minutes: Look back window in minutes (default: RESCHEDULE_DETECTION_WINDOW_MINUTES)

        Returns:
            True if a reschedule message was found in the time window
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            exists = (
                self.db.query(Message.id)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.message_type == MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
                    Message.created_at > cutoff,
                )
                .first()
            )
            return exists is not None
        except Exception:
            return False
