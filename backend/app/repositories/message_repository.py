"""Message repository facade backed by focused internal mixins."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models.message import Message
from .base_repository import BaseRepository
from .message.aggregate_queries_mixin import MessageAggregateQueriesMixin
from .message.conversation_queries_mixin import (
    RESCHEDULE_DETECTION_WINDOW_MINUTES,
    MessageConversationQueriesMixin,
)
from .message.mixin_base import _visible_message_filters
from .message.mutation_mixin import MessageMutationMixin
from .message.read_state_mixin import MessageReadStateMixin
from .message.types import AtomicMarkResult


class MessageRepository(
    MessageAggregateQueriesMixin,
    MessageReadStateMixin,
    MessageMutationMixin,
    MessageConversationQueriesMixin,
    BaseRepository[Message],
):
    """Repository facade for message data access."""

    _visible_message_filters = staticmethod(_visible_message_filters)

    def __init__(self, db: Session):
        """Initialize with Message model."""
        super().__init__(db, Message)
        self.logger = logging.getLogger(__name__)


__all__ = ["AtomicMarkResult", "MessageRepository", "RESCHEDULE_DETECTION_WINDOW_MINUTES"]
