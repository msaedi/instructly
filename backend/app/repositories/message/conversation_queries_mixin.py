"""Conversation timeline queries and writes for messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, cast

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...core.ulid_helper import generate_ulid
from ...models.conversation import Conversation
from ...models.message import MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED, Message, MessageNotification
from .mixin_base import MessageRepositoryMixinBase

RESCHEDULE_DETECTION_WINDOW_MINUTES = 1


class MessageConversationQueriesMixin(MessageRepositoryMixinBase):
    """Conversation timeline queries and writes for messages."""

    def get_messages_after_id_for_conversations(
        self, conversation_ids: List[str], after_message_id: str, limit: int = 100
    ) -> List[Message]:
        """Get messages created after a given message ID for specified conversations."""
        try:
            if not conversation_ids:
                return []

            after_message = self.db.query(Message).filter(Message.id == after_message_id).first()
            if after_message and after_message.created_at:
                return cast(
                    List[Message],
                    (
                        self.db.query(Message)
                        .filter(
                            and_(
                                Message.conversation_id.in_(conversation_ids),
                                or_(
                                    Message.created_at > after_message.created_at,
                                    and_(
                                        Message.created_at == after_message.created_at,
                                        Message.id > after_message_id,
                                    ),
                                ),
                            )
                        )
                        .order_by(Message.created_at, Message.id)
                        .limit(limit)
                        .all()
                    ),
                )
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
            self.logger.error("Error fetching messages after ID (conversation): %s", str(e))
            raise RepositoryException(f"Failed to fetch messages after ID: {str(e)}")

    def create_conversation_message(
        self,
        conversation_id: str,
        sender_id: Optional[str],
        content: str,
        message_type: str = "user",
        booking_id: Optional[str] = None,
    ) -> Message:
        """Create a new message for a conversation (per-user-pair messaging)."""
        try:
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
            conversation = cast(
                Optional[Conversation],
                self.db.query(Conversation).filter(Conversation.id == conversation_id).first(),
            )
            if conversation:
                conversation.last_message_at = message.created_at
                conversation.updated_at = datetime.now(timezone.utc)

            if sender_id and conversation:
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
                "Created conversation message %s in conversation %s", message.id, conversation_id
            )
            return message

        except Exception as e:
            self.logger.error("Error creating conversation message: %s", str(e))
            raise RepositoryException(f"Failed to create conversation message: {str(e)}")

    def find_by_conversation(
        self,
        conversation_id: str,
        limit: int = 50,
        before_cursor: Optional[str] = None,
        booking_id_filter: Optional[str] = None,
    ) -> List[Message]:
        """Find messages for a conversation with cursor-based pagination."""
        try:
            query = self.db.query(Message).filter(Message.conversation_id == conversation_id)

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
            self.logger.error("Error fetching messages for conversation: %s", str(e))
            raise RepositoryException(f"Failed to fetch messages for conversation: {str(e)}")

    def has_recent_reschedule_message(
        self,
        conversation_id: str,
        since_minutes: int = RESCHEDULE_DETECTION_WINDOW_MINUTES,
    ) -> bool:
        """
        Check if a reschedule system message was created recently in a conversation.

        Used to suppress cancellation messages when part of a reschedule operation.
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
