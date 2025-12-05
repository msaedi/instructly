# backend/app/services/messaging/events.py
"""
Messaging event type definitions and builders.

All events follow this structure:
{
    "type": str,           # Event type identifier
    "schema_version": int, # Schema version (currently 1)
    "timestamp": str,      # ISO 8601 timestamp
    "payload": dict        # Event-specific data
}
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    """Valid messaging event types."""

    NEW_MESSAGE = "new_message"
    TYPING_STATUS = "typing_status"
    REACTION_UPDATE = "reaction_update"
    MESSAGE_EDITED = "message_edited"
    READ_RECEIPT = "read_receipt"
    MESSAGE_DELETED = "message_deleted"


# Current schema version - increment when payload structure changes
SCHEMA_VERSION = 1


def build_event(event_type: EventType, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a properly structured event.

    Args:
        event_type: The type of event
        payload: Event-specific payload data

    Returns:
        Complete event dict ready for publishing
    """
    return {
        "type": event_type.value,
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def build_new_message_event(
    message_id: str,
    content: str,
    sender_id: Optional[str],
    conversation_id: str,
    recipient_ids: List[str],
    created_at: datetime,
    booking_id: Optional[str] = None,
    delivered_at: Optional[datetime] = None,
    reactions: Optional[List[Dict[str, Any]]] = None,
    message_type: str = "user",
) -> Dict[str, Any]:
    """Build a new_message event."""
    return build_event(
        EventType.NEW_MESSAGE,
        {
            "message": {
                "id": message_id,
                "content": content,
                "sender_id": sender_id,
                "booking_id": booking_id,
                "created_at": created_at.isoformat(),
                "delivered_at": delivered_at.isoformat() if delivered_at else None,
                "edited_at": None,
                "reactions": reactions or [],
                "message_type": message_type,
            },
            "conversation_id": conversation_id,
            "booking_id": booking_id,  # Include for backward compatibility
            "sender_id": sender_id,
            "recipient_ids": recipient_ids,
            "message_type": message_type,
        },
    )


def build_typing_status_event(
    conversation_id: str,
    user_id: str,
    is_typing: bool = True,
) -> Dict[str, Any]:
    """Build a typing_status event."""
    return build_event(
        EventType.TYPING_STATUS,
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "is_typing": is_typing,
        },
    )


def build_reaction_update_event(
    conversation_id: str,
    message_id: str,
    user_id: str,
    emoji: str,
    action: str,  # "added" or "removed"
) -> Dict[str, Any]:
    """Build a reaction_update event."""
    return build_event(
        EventType.REACTION_UPDATE,
        {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "user_id": user_id,
            "emoji": emoji,
            "action": action,
        },
    )


def build_message_edited_event(
    conversation_id: str,
    message_id: str,
    new_content: str,
    editor_id: str,
    edited_at: datetime,
) -> Dict[str, Any]:
    """Build a message_edited event."""
    return build_event(
        EventType.MESSAGE_EDITED,
        {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "new_content": new_content,
            "edited_at": edited_at.isoformat(),
            "editor_id": editor_id,
            "data": {"content": new_content},
        },
    )


def build_read_receipt_event(
    conversation_id: str,
    reader_id: str,
    message_ids: List[str],
) -> Dict[str, Any]:
    """Build a read_receipt event."""
    return build_event(
        EventType.READ_RECEIPT,
        {
            "conversation_id": conversation_id,
            "reader_id": reader_id,
            "message_ids": message_ids,
            "read_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def build_message_deleted_event(
    conversation_id: str,
    message_id: str,
    deleted_by: str,
    deleted_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build a message_deleted event."""
    return build_event(
        EventType.MESSAGE_DELETED,
        {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "deleted_by": deleted_by,
            "deleted_at": (deleted_at or datetime.now(timezone.utc)).isoformat(),
        },
    )
