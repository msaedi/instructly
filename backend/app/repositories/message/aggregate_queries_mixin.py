"""Aggregate and enrichment queries for messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.message import Message, MessageReaction
from .mixin_base import MessageRepositoryMixinBase, _visible_message_filters


class MessageAggregateQueriesMixin(MessageRepositoryMixinBase):
    """Aggregate and enrichment queries for messages."""

    _visibility_filters = _visible_message_filters(cast(str, Message.conversation_id))[1:]

    def count_for_conversation(self, conversation_id: str) -> int:
        """Count visible messages for a conversation."""
        try:
            query = self.db.query(func.count(Message.id)).filter(
                *self._visible_message_filters(conversation_id)
            )
            return int(self._execute_scalar(query) or 0)
        except Exception as e:
            self.logger.error("Error counting messages for conversation: %s", str(e))
            raise RepositoryException(f"Failed to count messages for conversation: {str(e)}")

    def batch_get_latest_messages(self, conversation_ids: List[str]) -> Dict[str, Message]:
        """Fetch the newest non-deleted message for each conversation in one query."""
        if not conversation_ids:
            return {}

        try:
            latest_message_ids = (
                self.db.query(
                    Message.id.label("message_id"),
                    Message.conversation_id.label("conversation_id"),
                    func.row_number()
                    .over(
                        partition_by=Message.conversation_id,
                        order_by=(Message.created_at.desc(), Message.id.desc()),
                    )
                    .label("row_num"),
                )
                .filter(
                    Message.conversation_id.in_(conversation_ids),
                    *self._visibility_filters,
                )
                .subquery()
            )
            messages = (
                self.db.query(Message)
                .join(latest_message_ids, Message.id == latest_message_ids.c.message_id)
                .options(joinedload(Message.sender))
                .filter(latest_message_ids.c.row_num == 1)
                .all()
            )
            return {message.conversation_id: message for message in messages}
        except Exception as e:
            self.logger.error("Error fetching latest messages for conversations: %s", str(e))
            raise RepositoryException(
                f"Failed to fetch latest messages for conversations: {str(e)}"
            )

    def get_last_message_at_for_conversation(self, conversation_id: str) -> Optional[datetime]:
        """Get the latest visible message timestamp for a conversation."""
        try:
            query = self.db.query(func.max(Message.created_at)).filter(
                *self._visible_message_filters(conversation_id)
            )
            return cast(Optional[datetime], self._execute_scalar(query))
        except Exception as e:
            self.logger.error("Error getting last message time: %s", str(e))
            raise RepositoryException(f"Failed to get last message time: {str(e)}")

    def get_reaction_counts_for_message_ids(
        self, message_ids: Sequence[str]
    ) -> List[Tuple[str, str, int]]:
        """Return tuples of (message_id, emoji, count) for reactions on given messages."""
        try:
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
            self.logger.error("Error fetching reaction counts: %s", str(e))
            raise RepositoryException(f"Failed to fetch reaction counts: {str(e)}")

    def get_user_reactions_for_message_ids(
        self, message_ids: List[str], user_id: str
    ) -> List[Tuple[str, str]]:
        """Return tuples of (message_id, emoji) for reactions by the user."""
        try:
            rows = cast(
                List[Tuple[str, str]],
                (
                    self.db.query(MessageReaction.message_id, MessageReaction.emoji)
                    .filter(
                        MessageReaction.message_id.in_(message_ids),
                        MessageReaction.user_id == user_id,
                    )
                    .all()
                ),
            )
            return rows
        except Exception as e:
            self.logger.error("Error fetching user reactions: %s", str(e))
            raise RepositoryException(f"Failed to fetch user reactions: {str(e)}")
