# backend/app/services/messaging/publisher.py
"""
High-level publishing functions for messaging events.

These functions handle:
- Building properly structured events
- Fetching recipients from booking participants (defense in depth)
- Publishing to all relevant user channels

SECURITY: Recipients are always fetched from DB inside these functions.
Callers pass booking_id, and we derive participants internally to prevent
any possibility of leaking messages to unauthorized users.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories.booking_repository import BookingRepository
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
from app.services.messaging.redis_pubsub import pubsub_manager

logger = logging.getLogger(__name__)


def _get_booking_participants(db: Session, booking_id: str) -> List[str]:
    """
    Fetch participant IDs from booking using repository pattern.

    Returns list of [student_id, instructor_id] or empty list if booking not found.
    """
    repository = BookingRepository(db)
    booking = repository.get_by_id(booking_id)
    if not booking:
        logger.warning(f"[PUBLISHER] Booking not found: {booking_id}")
        return []
    return [booking.student_id, booking.instructor_id]


def _get_conversation_participants(db: Session, conversation_id: str) -> List[str]:
    """
    Fetch participant IDs from conversation using repository pattern.

    This function handles the ID mismatch between routes (which may pass booking_id)
    and the new conversation-based architecture. It tries:
    1. Direct conversation lookup by ID
    2. Fallback: Look up booking by ID (routes often pass booking_id as conversation_id)

    Returns list of [student_id, instructor_id] or empty list if not found.
    """
    repository = ConversationRepository(db)

    # Try direct conversation lookup first
    conversation = repository.get_by_id(conversation_id)
    if conversation:
        return [conversation.student_id, conversation.instructor_id]

    # Fallback: The ID might be a booking_id (routes often pass booking_id as conversation_id)
    # Use the existing booking lookup function which already handles this case
    booking_participants = _get_booking_participants(db, conversation_id)
    if booking_participants:
        logger.debug(f"[PUBLISHER] Found participants via booking_id fallback: {conversation_id}")
        return booking_participants

    logger.warning(
        f"[PUBLISHER] Conversation not found (tried both conversation_id and booking_id): {conversation_id}"
    )
    return []


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
    participants = _get_conversation_participants(db, conversation_id)
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

    if sender_id and not sender_name:
        try:
            user_repo = RepositoryFactory.create_user_repository(db)
            sender = user_repo.get_by_id(sender_id)
            sender_name = (
                f"{sender.first_name} {sender.last_name}".strip()
                if sender and sender.first_name
                else getattr(sender, "first_name", None)
            )
        except Exception:
            sender_name = None

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
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(f"[REDIS-PUBSUB] Published new_message {message_id} to {len(all_user_ids)} users")


async def publish_typing_status(
    db: Session,
    conversation_id: str,
    user_id: str,
    user_name: str,
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
    participants = _get_conversation_participants(db, conversation_id)
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
    await pubsub_manager.publish_to_users(other_users, event)

    logger.debug(f"[REDIS-PUBSUB] Published typing_status to {len(other_users)} users")


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
    participants = _get_conversation_participants(db, conversation_id)
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
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published reaction_update ({action}) to {len(all_user_ids)} users"
    )


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
    participants = _get_conversation_participants(db, conversation_id)
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
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published message_edited {message_id} to {len(all_user_ids)} users"
    )


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
    participants = _get_conversation_participants(db, conversation_id)
    if not participants:
        return  # Silent fail for read receipts

    event = build_read_receipt_event(
        conversation_id=conversation_id,
        reader_id=reader_id,
        message_ids=message_ids,
    )

    # Send to other participants (not the reader)
    other_users = [uid for uid in participants if uid != reader_id]
    await pubsub_manager.publish_to_users(other_users, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published read_receipt for {len(message_ids)} messages "
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
    participants = _get_conversation_participants(db, conversation_id)
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
    await pubsub_manager.publish_to_users(all_user_ids, event)

    logger.debug(
        f"[REDIS-PUBSUB] Published message_deleted {message_id} to {len(all_user_ids)} users"
    )
