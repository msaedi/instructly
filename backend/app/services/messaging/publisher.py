# backend/app/services/messaging/publisher.py
"""
High-level publishing functions for messaging events.

These functions handle:
- Building properly structured events
- Fetching recipients from booking participants (defense in depth)
- Publishing to all relevant user channels via Broadcaster (v4.0)

SECURITY: Recipients are always fetched from DB inside these functions.
Callers pass booking_id, and we derive participants internally to prevent
any possibility of leaking messages to unauthorized users.

Architecture (v4.0 with Broadcaster):
- Uses shared Broadcaster connection for publishing
- Consistent with SSE streaming which also uses Broadcaster
- Single Redis connection pattern across the application
"""

import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.factory import RepositoryFactory
from app.services.messaging.events import (
    build_message_deleted_event,
    build_message_edited_event,
    build_new_message_event,
    build_reaction_update_event,
    build_read_receipt_event,
    build_typing_status_event,
)
from app.services.messaging.sse_stream import publish_to_user

logger = logging.getLogger(__name__)


async def _publish_to_users(user_ids: List[str], event: Dict[str, Any]) -> None:
    """
    Publish an event to multiple users via Broadcaster.

    Args:
        user_ids: List of user ULIDs to publish to
        event: Event dict to publish
    """
    for user_id in user_ids:
        await publish_to_user(user_id, event)


def _get_conversation_participants_sync(db: Session, conversation_id: str) -> List[str]:
    """
    Fetch participant IDs from conversation using repository pattern.

    Returns list of [student_id, instructor_id] or empty list if not found.

    NOTE: This is a sync function - must be called via asyncio.to_thread()
    from async context to avoid blocking the event loop.
    """
    repository = ConversationRepository(db)

    conversation = repository.get_by_id(conversation_id)
    if not conversation:
        logger.error(f"[PUBLISHER] Conversation not found: {conversation_id}")
        return []
    return [conversation.student_id, conversation.instructor_id]


def _get_sender_name_sync(db: Session, sender_id: str) -> Optional[str]:
    """
    Fetch sender name from database (sync).

    NOTE: This is a sync function - must be called via asyncio.to_thread()
    from async context to avoid blocking the event loop.
    """
    try:
        user_repo = RepositoryFactory.create_user_repository(db)
        sender = user_repo.get_by_id(sender_id)
        if sender and sender.first_name:
            return f"{sender.first_name} {sender.last_name or ''}".strip()
        return getattr(sender, "first_name", None) if sender else None
    except Exception:
        return None


async def publish_new_message(
    db: Session,
    message_id: str,
    content: str,
    sender_id: Optional[str],
    conversation_id: str,
    created_at: datetime,
    booking_id: Optional[str] = None,
    delivered_at: Optional[datetime] = None,
    reactions: Optional[List[Dict[str, Any]]] = None,
    message_type: str = "user",
    sender_name: Optional[str] = None,
) -> None:
    """
    Publish a new message event to all conversation participants.

    PERFORMANCE: All sync DB operations are wrapped in asyncio.to_thread()
    to prevent blocking the event loop under high concurrent load.

    Args:
        db: Database session for fetching conversation participants
        message_id: ULID of the new message
        content: Message text content
        sender_id: ULID of sender (None for system messages)
        conversation_id: ULID of conversation
        created_at: Message creation timestamp
        booking_id: Optional ULID of related booking
        delivered_at: Optional delivery timestamp
        reactions: Optional list of reactions
        message_type: Type of message ('user', 'system_booking_created', etc.)
    """
    # Fetch participants from conversation (defense in depth - no external input)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        logger.warning(
            f"[PUBLISHER] Cannot publish new_message: conversation {conversation_id} not found"
        )
        return

    # For user messages, exclude sender from recipients
    # For system messages (sender_id=None), all participants receive
    if sender_id:
        recipient_ids = [uid for uid in participants if uid != sender_id]
    else:
        recipient_ids = list(participants)

    # Fetch sender name if not provided (wrapped in to_thread())
    if sender_id and not sender_name:
        sender_name = await asyncio.to_thread(_get_sender_name_sync, db, sender_id)

    event = build_new_message_event(
        message_id=message_id,
        content=content,
        sender_id=sender_id,
        sender_name=sender_name,
        conversation_id=conversation_id,
        booking_id=booking_id,
        recipient_ids=recipient_ids,
        created_at=created_at,
        delivered_at=delivered_at,
        reactions=reactions,
        message_type=message_type,
    )

    # Publish to all participants (including sender for multi-device sync)
    all_user_ids = list(set(participants))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published new_message {message_id} to {len(all_user_ids)} users")


async def publish_typing_status(
    db: Session,
    conversation_id: str,
    user_id: str,
    user_name: Optional[str] = None,
    is_typing: bool = True,
) -> None:
    """
    Publish typing status to conversation participants.

    Best-effort delivery - if dropped, no big deal.

    Args:
        db: Database session for fetching conversation participants
        conversation_id: Conversation ULID
        user_id: ULID of user who is typing
        is_typing: True if typing started, False if stopped
    """
    # Fetch participants from conversation (defense in depth)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        return  # Silent fail for ephemeral typing indicators

    event = build_typing_status_event(
        conversation_id=conversation_id,
        user_id=user_id,
        user_name=user_name,
        is_typing=is_typing,
    )

    # Don't send to the typer themselves
    other_users = [uid for uid in participants if uid != user_id]
    await _publish_to_users(other_users, event)

    logger.debug(f"[BROADCAST] Published typing_status to {len(other_users)} users")


async def publish_reaction_update(
    db: Session,
    conversation_id: str,
    message_id: str,
    user_id: str,
    emoji: str,
    action: str,
) -> None:
    """
    Publish reaction update to conversation participants.

    Args:
        db: Database session for fetching conversation participants
        conversation_id: Conversation ULID
        message_id: ULID of message being reacted to
        user_id: ULID of user adding/removing reaction
        emoji: The emoji reaction
        action: "added" or "removed"
    """
    # Fetch participants from conversation (defense in depth)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        logger.warning(
            f"[PUBLISHER] Cannot publish reaction_update: conversation {conversation_id} not found"
        )
        return

    event = build_reaction_update_event(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        emoji=emoji,
        action=action,
    )

    # Send to all participants including reactor (multi-device)
    all_user_ids = list(set(participants))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published reaction_update ({action}) to {len(all_user_ids)} users")


async def publish_message_edited(
    db: Session,
    conversation_id: str,
    message_id: str,
    new_content: str,
    editor_id: str,
    edited_at: datetime,
) -> None:
    """
    Publish message edit event to conversation participants.

    Args:
        db: Database session for fetching conversation participants
        conversation_id: Conversation ULID
        message_id: ULID of edited message
        new_content: Updated message content
        editor_id: ULID of user who edited
        edited_at: Edit timestamp
    """
    # Fetch participants from conversation (defense in depth)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        logger.warning(
            f"[PUBLISHER] Cannot publish message_edited: conversation {conversation_id} not found"
        )
        return

    event = build_message_edited_event(
        conversation_id=conversation_id,
        message_id=message_id,
        new_content=new_content,
        editor_id=editor_id,
        edited_at=edited_at,
    )

    all_user_ids = list(set(participants))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published message_edited {message_id} to {len(all_user_ids)} users")


async def publish_read_receipt(
    db: Session,
    conversation_id: str,
    reader_id: str,
    message_ids: List[str],
) -> None:
    """
    Publish read receipt to message senders.

    Args:
        db: Database session for fetching conversation participants
        conversation_id: Conversation ULID
        reader_id: ULID of user who read messages
        message_ids: List of message ULIDs that were read
    """
    # Fetch participants from conversation (defense in depth)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        return  # Silent fail for read receipts

    event = build_read_receipt_event(
        conversation_id=conversation_id,
        reader_id=reader_id,
        message_ids=message_ids,
    )

    # Send to other participants (not the reader)
    other_users = [uid for uid in participants if uid != reader_id]
    await _publish_to_users(other_users, event)

    logger.debug(
        f"[BROADCAST] Published read_receipt for {len(message_ids)} messages "
        f"to {len(other_users)} users"
    )


async def publish_message_deleted(
    db: Session,
    conversation_id: str,
    message_id: str,
    deleted_by: str,
) -> None:
    """Publish message deleted event to conversation participants."""
    # Fetch participants from conversation (defense in depth)
    # Wrapped in to_thread() to avoid blocking event loop under load
    participants = await asyncio.to_thread(_get_conversation_participants_sync, db, conversation_id)
    if not participants:
        logger.warning(
            f"[PUBLISHER] Cannot publish message_deleted: conversation {conversation_id} not found"
        )
        return

    event = build_message_deleted_event(
        conversation_id=conversation_id,
        message_id=message_id,
        deleted_by=deleted_by,
    )

    # Send to all participants (both sides)
    all_user_ids = list(set(participants))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published message_deleted {message_id} to {len(all_user_ids)} users")


# =============================================================================
# DIRECT PUBLISH FUNCTIONS (No DB required)
#
# These functions accept pre-fetched participant IDs instead of db session.
# Use these when the service layer has already fetched the notification context.
# This keeps routes free of DB access while maintaining notification capability.
# =============================================================================


async def publish_read_receipt_direct(
    participant_ids: List[str],
    conversation_id: str,
    reader_id: str,
    message_ids: List[str],
) -> None:
    """
    Publish read receipt to participants (no DB required).

    Args:
        participant_ids: Pre-fetched list of [student_id, instructor_id]
        conversation_id: Conversation ULID
        reader_id: ULID of user who read messages
        message_ids: List of message ULIDs that were read
    """
    if not participant_ids:
        return  # Silent fail for read receipts

    event = build_read_receipt_event(
        conversation_id=conversation_id,
        reader_id=reader_id,
        message_ids=message_ids,
    )

    # Send to other participants (not the reader)
    other_users = [uid for uid in participant_ids if uid != reader_id]
    await _publish_to_users(other_users, event)

    logger.debug(
        f"[BROADCAST] Published read_receipt for {len(message_ids)} messages "
        f"to {len(other_users)} users"
    )


async def publish_message_edited_direct(
    participant_ids: List[str],
    conversation_id: str,
    message_id: str,
    new_content: str,
    editor_id: str,
    edited_at: datetime,
) -> None:
    """
    Publish message edit event (no DB required).

    Args:
        participant_ids: Pre-fetched list of conversation participants
        conversation_id: Conversation ULID
        message_id: ULID of edited message
        new_content: Updated message content
        editor_id: ULID of user who edited
        edited_at: Edit timestamp
    """
    if not participant_ids:
        logger.warning(
            f"[PUBLISHER] Cannot publish message_edited: no participants for {conversation_id}"
        )
        return

    event = build_message_edited_event(
        conversation_id=conversation_id,
        message_id=message_id,
        new_content=new_content,
        editor_id=editor_id,
        edited_at=edited_at,
    )

    all_user_ids = list(set(participant_ids))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published message_edited {message_id} to {len(all_user_ids)} users")


async def publish_message_deleted_direct(
    participant_ids: List[str],
    conversation_id: str,
    message_id: str,
    deleted_by: str,
) -> None:
    """
    Publish message deleted event (no DB required).

    Args:
        participant_ids: Pre-fetched list of conversation participants
        conversation_id: Conversation ULID
        message_id: ULID of deleted message
        deleted_by: ULID of user who deleted
    """
    if not participant_ids:
        logger.warning(
            f"[PUBLISHER] Cannot publish message_deleted: no participants for {conversation_id}"
        )
        return

    event = build_message_deleted_event(
        conversation_id=conversation_id,
        message_id=message_id,
        deleted_by=deleted_by,
    )

    all_user_ids = list(set(participant_ids))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published message_deleted {message_id} to {len(all_user_ids)} users")


async def publish_reaction_update_direct(
    participant_ids: List[str],
    conversation_id: str,
    message_id: str,
    user_id: str,
    emoji: str,
    action: str,
) -> None:
    """
    Publish reaction update (no DB required).

    Args:
        participant_ids: Pre-fetched list of conversation participants
        conversation_id: Conversation ULID
        message_id: ULID of message being reacted to
        user_id: ULID of user adding/removing reaction
        emoji: The emoji reaction
        action: "added" or "removed"
    """
    if not participant_ids:
        logger.warning(
            f"[PUBLISHER] Cannot publish reaction_update: no participants for {conversation_id}"
        )
        return

    event = build_reaction_update_event(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        emoji=emoji,
        action=action,
    )

    all_user_ids = list(set(participant_ids))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published reaction_update ({action}) to {len(all_user_ids)} users")


async def publish_typing_status_direct(
    participant_ids: List[str],
    conversation_id: str,
    user_id: str,
    user_name: Optional[str] = None,
    is_typing: bool = True,
) -> None:
    """
    Publish typing status (no DB required).

    Best-effort delivery - if dropped, no big deal.

    Args:
        participant_ids: Pre-fetched list of conversation participants
        conversation_id: Conversation ULID
        user_id: ULID of user who is typing
        user_name: Optional display name
        is_typing: True if typing started, False if stopped
    """
    if not participant_ids:
        return  # Silent fail for ephemeral typing indicators

    event = build_typing_status_event(
        conversation_id=conversation_id,
        user_id=user_id,
        user_name=user_name,
        is_typing=is_typing,
    )

    # Don't send to the typer themselves
    other_users = [uid for uid in participant_ids if uid != user_id]
    await _publish_to_users(other_users, event)

    logger.debug(f"[BROADCAST] Published typing_status to {len(other_users)} users")


async def publish_new_message_direct(
    participant_ids: List[str],
    message_id: str,
    content: str,
    sender_id: Optional[str],
    sender_name: Optional[str],
    conversation_id: str,
    created_at: datetime,
    booking_id: Optional[str] = None,
    delivered_at: Optional[datetime] = None,
    reactions: Optional[List[Dict[str, Any]]] = None,
    message_type: str = "user",
) -> None:
    """
    Publish a new message event (no DB required).

    Args:
        participant_ids: Pre-fetched list of conversation participants
        message_id: ULID of the new message
        content: Message text content
        sender_id: ULID of sender (None for system messages)
        sender_name: Sender display name
        conversation_id: ULID of conversation
        created_at: Message creation timestamp
        booking_id: Optional ULID of related booking
        delivered_at: Optional delivery timestamp
        reactions: Optional list of reactions
        message_type: Type of message ('user', 'system_booking_created', etc.)
    """
    if not participant_ids:
        logger.warning(
            f"[PUBLISHER] Cannot publish new_message: no participants for {conversation_id}"
        )
        return

    # For user messages, exclude sender from recipients
    # For system messages (sender_id=None), all participants receive
    if sender_id:
        recipient_ids = [uid for uid in participant_ids if uid != sender_id]
    else:
        recipient_ids = list(participant_ids)

    event = build_new_message_event(
        message_id=message_id,
        content=content,
        sender_id=sender_id,
        sender_name=sender_name,
        conversation_id=conversation_id,
        booking_id=booking_id,
        recipient_ids=recipient_ids,
        created_at=created_at,
        delivered_at=delivered_at,
        reactions=reactions,
        message_type=message_type,
    )

    # Publish to all participants (including sender for multi-device sync)
    all_user_ids = list(set(participant_ids))
    await _publish_to_users(all_user_ids, event)

    logger.debug(f"[BROADCAST] Published new_message {message_id} to {len(all_user_ids)} users")
