"""Shared typing surface for message repository mixins."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, Optional, Tuple

from sqlalchemy.orm import Session

from ...models.message import Message


def _visible_message_filters(conversation_id: str) -> Tuple[Any, ...]:
    """Return filters for messages that should be visible in aggregates."""
    return (
        Message.conversation_id == conversation_id,
        Message.is_deleted == False,
        Message.deleted_at.is_(None),
    )


if TYPE_CHECKING:

    class MessageRepositoryMixinBase:
        """Typed attribute/method surface supplied by the message facade."""

        db: Session
        logger: logging.Logger
        model: type[Message]

        def _execute_scalar(self, query: Any) -> Any:
            ...

        def get_last_message_at_for_conversation(self, conversation_id: str) -> Optional[datetime]:
            ...

        @staticmethod
        def _visible_message_filters(conversation_id: str) -> Tuple[Any, ...]:
            ...

else:

    class MessageRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[Message]
