# backend/app/services/messaging/publisher.py
"""
High-level publishing functions for messaging events.

These functions handle:
- Building properly structured events
- Determining recipients from DB data
- Publishing to all relevant user channels

SECURITY: recipient_ids MUST come from database (booking participants),
never from client-provided data.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from app.services.messaging.events import (
    build_message_edited_event,
    build_new_message_event,
    build_reaction_update_event,
    build_read_receipt_event,
    build_typing_status_event,
)
from app.services.messaging.redis_pubsub import pubsub_manager

logger = logging.getLogger(__name__)


async def publish_new_message(
    message_id: str,
    content: str,
    sender_id: str,
    booking_id: str,
    recipient_ids: List[str],
    created_at: datetime,
    reactions: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Publish a new message event to all conversation participants.

    Args:
        message_id: ULID of the new message
        content: Message text content
        sender_id: ULID of sender
        booking_id: ULID of booking (conversation ID)
        recipient_ids: List of participant ULIDs (from DB, not client!)
        created_at: Message creation timestamp
        reactions: Optional list of reactions
    """
    event = build_new_message_event(
        message_id=message_id,
        content=content,
        sender_id=sender_id,
        booking_id=booking_id,
        recipient_ids=recipient_ids,
        created_at=created_at,
        reactions=reactions,
    )

    # Publish to all participants (including sender for multi-device sync)
    all_user_ids = list(set([sender_id] + recipient_ids))
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(f"[REDIS-PUBSUB] Published new_message {message_id} to {len(all_user_ids)} users")


async def publish_typing_status(
    conversation_id: str,
    user_id: str,
    recipient_ids: List[str],
    is_typing: bool = True,
) -> None:
    """
    Publish typing status to conversation participants.

    Best-effort delivery - if dropped, no big deal.

    Args:
        conversation_id: Booking ULID
        user_id: ULID of user who is typing
        recipient_ids: List of other participant ULIDs
        is_typing: True if typing started, False if stopped
    """
    event = build_typing_status_event(
        conversation_id=conversation_id,
        user_id=user_id,
        is_typing=is_typing,
    )

    # Don't send to the typer themselves
    other_users = [uid for uid in recipient_ids if uid != user_id]
    await pubsub_manager.publish_to_users(other_users, event)

    logger.debug(f"[REDIS-PUBSUB] Published typing_status to {len(other_users)} users")


async def publish_reaction_update(
    conversation_id: str,
    message_id: str,
    user_id: str,
    emoji: str,
    action: str,
    recipient_ids: List[str],
) -> None:
    """
    Publish reaction update to conversation participants.

    Args:
        conversation_id: Booking ULID
        message_id: ULID of message being reacted to
        user_id: ULID of user adding/removing reaction
        emoji: The emoji reaction
        action: "added" or "removed"
        recipient_ids: List of participant ULIDs
    """
    event = build_reaction_update_event(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        emoji=emoji,
        action=action,
    )

    # Send to all participants including reactor (multi-device)
    all_user_ids = list(set([user_id] + recipient_ids))
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published reaction_update ({action}) to {len(all_user_ids)} users"
    )


async def publish_message_edited(
    conversation_id: str,
    message_id: str,
    new_content: str,
    editor_id: str,
    edited_at: datetime,
    recipient_ids: List[str],
) -> None:
    """
    Publish message edit event to conversation participants.

    Args:
        conversation_id: Booking ULID
        message_id: ULID of edited message
        new_content: Updated message content
        editor_id: ULID of user who edited
        edited_at: Edit timestamp
        recipient_ids: List of participant ULIDs
    """
    event = build_message_edited_event(
        conversation_id=conversation_id,
        message_id=message_id,
        new_content=new_content,
        editor_id=editor_id,
        edited_at=edited_at,
    )

    all_user_ids = list(set([editor_id] + recipient_ids))
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published message_edited {message_id} to {len(all_user_ids)} users"
    )


async def publish_read_receipt(
    conversation_id: str,
    reader_id: str,
    message_ids: List[str],
    recipient_ids: List[str],
) -> None:
    """
    Publish read receipt to message senders.

    Args:
        conversation_id: Booking ULID
        reader_id: ULID of user who read messages
        message_ids: List of message ULIDs that were read
        recipient_ids: List of participant ULIDs
    """
    event = build_read_receipt_event(
        conversation_id=conversation_id,
        reader_id=reader_id,
        message_ids=message_ids,
    )

    # Send to other participants (not the reader)
    other_users = [uid for uid in recipient_ids if uid != reader_id]
    await pubsub_manager.publish_to_users(other_users, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published read_receipt for {len(message_ids)} messages "
        f"to {len(other_users)} users"
    )
