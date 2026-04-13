"""Unread state and receipt operations for messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple, cast

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.message import Message, MessageNotification
from .mixin_base import MessageRepositoryMixinBase, _visible_message_filters
from .types import AtomicMarkResult


class MessageReadStateMixin(MessageRepositoryMixinBase):
    """Unread state and receipt operations for messages."""

    _visibility_filters = _visible_message_filters(cast(str, Message.conversation_id))[1:]

    def get_unread_messages_by_conversation(
        self, conversation_id: str, user_id: str
    ) -> List[Message]:
        """
        Get unread messages for a user in a conversation (across all bookings).

        Phase 7: Used for SSE read receipt publishing when messages span multiple bookings.
        """
        try:
            return cast(
                List[Message],
                (
                    self.db.query(Message)
                    .join(MessageNotification)
                    .filter(
                        *self._visible_message_filters(conversation_id),
                        MessageNotification.user_id == user_id,
                        MessageNotification.is_read == False,
                    )
                    .options(joinedload(Message.sender))
                    .order_by(Message.created_at)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Error fetching unread messages by conversation: %s", str(e))
            raise RepositoryException(f"Failed to fetch unread messages: {str(e)}")

    def _update_message_read_by(self, message_ids: List[str], user_id: str) -> None:
        """Append read_by entries for messages (best-effort)."""
        if not message_ids:
            return

        read_at = datetime.now(timezone.utc).isoformat()
        messages = self.db.query(Message).filter(Message.id.in_(message_ids)).all()

        for message in messages:
            read_by = message.read_by if message.read_by else []
            if any(r.get("user_id") == user_id for r in read_by):
                continue
            read_by.append({"user_id": user_id, "read_at": read_at})
            message.read_by = read_by
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(message, "read_by")

    def mark_messages_as_read(self, message_ids: List[str], user_id: str) -> int:
        """Mark messages as read for a user."""
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

            if count > 0:
                self._update_message_read_by(message_ids, user_id)

            self.logger.info("Marked %s messages as read for user %s", count, user_id)
            return count

        except Exception as e:
            self.logger.error("Error marking messages as read: %s", str(e))
            raise RepositoryException(f"Failed to mark messages as read: {str(e)}")

    def mark_unread_messages_read_atomic(
        self, conversation_id: str, user_id: str
    ) -> AtomicMarkResult:
        """Atomically mark unread messages as read and return message IDs."""
        try:
            visible_message_ids = select(Message.id).where(
                *self._visible_message_filters(conversation_id)
            )
            result = self.db.execute(
                update(MessageNotification)
                .where(
                    MessageNotification.message_id.in_(visible_message_ids),
                    MessageNotification.user_id == user_id,
                    MessageNotification.is_read == False,
                )
                .values(
                    is_read=True,
                    read_at=func.now(),
                )
                .returning(MessageNotification.message_id, MessageNotification.read_at)
            )
            rows = result.fetchall()
            message_ids = [str(row.message_id) for row in rows]
            timestamp = rows[0].read_at if rows else None
            if message_ids:
                self._update_message_read_by(message_ids, user_id)
            return AtomicMarkResult(
                rowcount=len(rows),
                message_ids=message_ids,
                timestamp=timestamp,
            )
        except Exception as e:
            self.logger.error("Error marking messages as read atomically: %s", str(e))
            raise RepositoryException(f"Failed to mark messages as read atomically: {str(e)}")

    def get_unread_count_for_user(self, user_id: str) -> int:
        """Get total unread message count for a user."""
        try:
            return (
                self.db.query(func.count(MessageNotification.id))
                .join(Message)
                .filter(
                    MessageNotification.user_id == user_id,
                    MessageNotification.is_read == False,
                    *self._visibility_filters,
                )
                .scalar()
            ) or 0

        except Exception as e:
            self.logger.error("Error counting unread messages: %s", str(e))
            raise RepositoryException(f"Failed to count unread messages: {str(e)}")

    def get_read_receipts_for_message_ids(
        self, message_ids: List[str]
    ) -> List[Tuple[str, str, Optional[datetime]]]:
        """Return tuples of (message_id, user_id, read_at) for read notifications."""
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
            self.logger.error("Error fetching read receipts: %s", str(e))
            raise RepositoryException(f"Failed to fetch read receipts: {str(e)}")
