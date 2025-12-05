# backend/app/services/messaging/sse_stream.py
"""
Redis-only SSE stream with Last-Event-ID support.

This module implements v3.1 architecture:
- Redis Pub/Sub as the ONLY real-time source
- Last-Event-ID for automatic catch-up on reconnect
- No deduplication needed (single source)

Event types:
- new_message: Includes SSE `id:` field for Last-Event-ID tracking
- reaction_update, read_receipt, typing_status, message_edited: No `id:` field
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message import Message
from app.repositories.message_repository import MessageRepository
from app.services.messaging.redis_pubsub import pubsub_manager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Configurable via settings.sse_heartbeat_interval
HEARTBEAT_INTERVAL = settings.sse_heartbeat_interval


async def create_sse_stream(
    user_id: str,
    db: Session,
    last_event_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, str], None]:
    """
    Create an SSE stream for a user.

    Args:
        user_id: The user's ULID
        db: Database session
        last_event_id: Last-Event-ID header from reconnecting client

    Yields:
        SSE event dicts with keys: event, data, id (optional for new_message)
    """
    # Step 1: Catch up from DB if reconnecting
    if last_event_id:
        logger.info(
            f"[SSE-STREAM] Client reconnecting with Last-Event-ID: {last_event_id}",
            extra={"user_id": user_id, "last_event_id": last_event_id},
        )
        missed_messages = fetch_messages_after(db, user_id, last_event_id)
        logger.info(
            f"[SSE-STREAM] Sending {len(missed_messages)} missed messages",
            extra={"user_id": user_id, "count": len(missed_messages)},
        )

        for msg in missed_messages:
            yield format_message_from_db(msg, user_id)

    # Step 2: Send connected event
    yield {
        "event": "connected",
        "data": json.dumps(
            {
                "user_id": user_id,
                "status": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
    }

    # Step 3: Subscribe to Redis
    try:
        async with pubsub_manager.subscribe(user_id) as pubsub:
            logger.info(
                f"[SSE-STREAM] Subscribed to Redis for user {user_id}",
                extra={"user_id": user_id},
            )

            # Step 4: Stream events with heartbeat
            async for event in stream_with_heartbeat(pubsub, HEARTBEAT_INTERVAL, user_id=user_id):
                if event.get("_heartbeat"):
                    logger.info(f"[SSE-HEARTBEAT] Sending heartbeat for user {user_id}")
                    # Heartbeats use simplified format without schema_version.
                    # Unlike new_message/reaction events, heartbeats are purely for
                    # connection keep-alive and never need versioned parsing.
                    # Clients should treat heartbeats as opaque ping events.
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {
                                "type": "heartbeat",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        ),
                    }
                else:
                    logger.debug(
                        "[SSE-STREAM] Yielding event",
                        extra={"user_id": user_id, "event_type": event.get("type")},
                    )
                    yield format_redis_event(event, user_id)

    except asyncio.CancelledError:
        logger.info(f"[SSE-STREAM] Stream cancelled for user {user_id}")
        raise
    except RuntimeError as e:
        # Redis not initialized
        logger.error(f"[SSE-STREAM] Redis error for user {user_id}: {e}")
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "error": "service_unavailable",
                    "message": "Real-time service temporarily unavailable",
                }
            ),
        }
    except Exception as e:
        logger.error(
            f"[SSE-STREAM] Unexpected error for user {user_id}: {e}",
            exc_info=True,
        )
        raise


async def stream_with_heartbeat(
    pubsub: Any,
    interval: int,
    user_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Wrap a Redis PubSub to inject heartbeats.

    Yields events from Redis, plus heartbeat markers every `interval` seconds.
    """
    last_activity = time.monotonic()
    while True:
        # Poll Redis with a short timeout (non-blocking)
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

        if message is not None and message.get("type") == "message":
            try:
                event = json.loads(message["data"])
                last_activity = time.monotonic()
                yield event
            except json.JSONDecodeError as e:
                logger.warning(f"[SSE-STREAM] Invalid JSON in Redis message: {e}")
        else:
            elapsed = time.monotonic() - last_activity
            if elapsed >= interval:
                logger.debug(
                    "[SSE-HEARTBEAT] Timeout triggered, generating heartbeat",
                    extra={
                        "user_id": user_id,
                        "interval": interval,
                        "idle_seconds": round(elapsed, 1),
                    },
                )
                last_activity = time.monotonic()
                yield {"_heartbeat": True}


def format_redis_event(event: Dict[str, Any], user_id: str) -> Dict[str, str]:
    """
    Format a Redis event for SSE output.

    - new_message events get an `id` field for Last-Event-ID tracking
    - Other events (reactions, read receipts, typing) do NOT get `id`
    """
    event_type = event.get("type", "unknown")
    payload = event.get("payload", event)

    # Add is_mine flag for new_message
    if event_type == "new_message":
        message_data = payload.get("message", {})
        payload["is_mine"] = message_data.get("sender_id") == user_id

        # Extract message ID for SSE id field
        message_id = message_data.get("id")

        result: Dict[str, str] = {
            "event": "new_message",
            "data": json.dumps(payload),
        }
        if message_id:
            result["id"] = message_id
        return result

    elif event_type == "reaction_update":
        return {
            "event": "reaction_update",
            "data": json.dumps(payload),
        }

    elif event_type == "read_receipt":
        return {
            "event": "read_receipt",
            "data": json.dumps(payload),
        }

    elif event_type == "typing_status":
        return {
            "event": "typing_status",
            "data": json.dumps(payload),
        }

    elif event_type == "message_edited":
        return {
            "event": "message_edited",
            "data": json.dumps(payload),
        }
    elif event_type == "message_deleted":
        return {
            "event": "message_deleted",
            "data": json.dumps(payload),
        }

    else:
        # Unknown event type - pass through without id
        logger.warning(f"[SSE-STREAM] Unknown event type: {event_type}")
        return {
            "event": event_type,
            "data": json.dumps(payload),
        }


def format_message_from_db(message: Message, user_id: str) -> Dict[str, str]:
    """
    Format a Message model as an SSE event (for catch-up).

    These are missed messages fetched from the database on reconnect.
    """

    def _iso(dt: Any) -> Optional[str]:
        """Safely convert datetime-like objects to ISO strings."""
        from datetime import date, datetime

        if isinstance(dt, (datetime, date)):
            return dt.isoformat()
        return None

    def _safe_attr(obj: Any, attr: str, default: Any = None) -> Any:
        """Avoid Mock auto-creation by checking __dict__ instead of getattr on missing attrs."""
        raw = getattr(obj, "__dict__", {})
        if isinstance(raw, dict) and attr in raw:
            return raw[attr]
        return default

    is_deleted = bool(_safe_attr(message, "is_deleted", False))
    deleted_at_iso = _iso(_safe_attr(message, "deleted_at", None))
    deleted_by = _safe_attr(message, "deleted_by", None)

    # Use conversation_id if available, fall back to booking_id for legacy messages
    conv_id = getattr(message, "conversation_id", None) or message.booking_id
    msg_type = getattr(message, "message_type", "user") or "user"

    payload = {
        "message": {
            "id": message.id,
            "content": "This message was deleted" if is_deleted else message.content,
            "sender_id": message.sender_id,
            "booking_id": message.booking_id,
            "created_at": _iso(getattr(message, "created_at", None)),
            "edited_at": _iso(getattr(message, "edited_at", None)),
            "delivered_at": _iso(getattr(message, "delivered_at", None)),
            "reactions": [],  # Reactions loaded separately if needed
            "is_deleted": is_deleted,
            "deleted_at": deleted_at_iso,
            "deleted_by": deleted_by,
            "message_type": msg_type,
        },
        "conversation_id": conv_id,
        "booking_id": message.booking_id,  # Include for backward compatibility
        "is_mine": message.sender_id == user_id,
        "message_type": msg_type,
    }

    return {
        "id": message.id,
        "event": "new_message",
        "data": json.dumps(payload),
    }


def fetch_messages_after(
    db: Session,
    user_id: str,
    after_message_id: str,
) -> List[Message]:
    """
    Fetch messages created after the given message ID.

    Since ULIDs are lexicographically sortable by time,
    `id > after_message_id` returns newer messages.

    Args:
        db: Database session
        user_id: User's ULID
        after_message_id: Last-Event-ID (message ULID)

    Returns:
        List of messages after the given ID, ordered by ID
    """
    repository = MessageRepository(db)

    # Get user's booking IDs (bookings where user is student or instructor)
    booking_ids = repository.get_user_booking_ids(user_id)

    if not booking_ids:
        return []

    # Fetch messages after the last seen ID
    return repository.get_messages_after_id(booking_ids, after_message_id, limit=100)
