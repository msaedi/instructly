# backend/app/services/messaging/sse_stream.py
"""
SSE Stream with fan-out multiplexer for scalable real-time messaging.

This module implements v4.0 architecture using Broadcaster:
- Single Redis PubSub connection shared across all SSE clients per worker
- Enables 500+ concurrent SSE users instead of ~30 with per-connection pattern
- Last-Event-ID for automatic catch-up on reconnect
- Proper async waiting (no busy-wait polling)

Architecture:
  N SSE clients → 1 Broadcaster instance → 1 Redis connection per worker
  (Previously: N SSE clients → N Redis connections → maxclients ceiling)

Event types:
- new_message: Includes SSE `id:` field for Last-Event-ID tracking
- reaction_update, read_receipt, typing_status, message_edited: No `id:` field
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.broadcast import get_broadcast
from app.core.config import settings
from app.models.message import Message
from app.repositories.message_repository import MessageRepository

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Configurable via settings.sse_heartbeat_interval
HEARTBEAT_INTERVAL = settings.sse_heartbeat_interval


async def ensure_db_health(db: Session) -> None:
    """Verify database connectivity before starting SSE stream."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(lambda: db.execute(text("SELECT 1"))),
            timeout=2.0,
        )
    except Exception as exc:
        logger.warning("[SSE] DB health check failed before stream: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        ) from exc


async def create_sse_stream(
    user_id: str,
    missed_messages: Optional[List[Message]] = None,
) -> AsyncGenerator[Dict[str, str], None]:
    """
    Create an SSE stream for a user using shared Broadcaster connection.

    This function is DB-free - all DB operations must be done before calling.
    This prevents holding DB sessions in "idle in transaction" state during
    long-running SSE connections.

    Architecture (v4.0 with Broadcaster):
    - Uses shared Redis PubSub connection via Broadcaster (1 connection per worker)
    - Supports 500+ concurrent SSE users instead of ~30 with per-connection pattern
    - Proper async waiting (no busy-wait polling)

    Args:
        user_id: The user's ULID
        missed_messages: Pre-fetched missed messages (from DB lookup done before streaming)

    Yields:
        SSE event dicts with keys: event, data, id (optional for new_message)
    """
    channel = f"user:{user_id}"

    # Step 1: Send any missed messages (pre-fetched by caller)
    if missed_messages:
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

    # Step 3: Subscribe via shared Broadcaster (1 Redis connection per worker)
    try:
        broadcast = get_broadcast()
        async with broadcast.subscribe(channel=channel) as subscriber:
            logger.info(
                f"[SSE-STREAM] Subscribed to channel {channel} via Broadcaster",
                extra={"user_id": user_id},
            )

            # Use a queue to decouple the subscriber from heartbeat timing.
            # This avoids the issue where asyncio.wait_for() cancels __anext__()
            # on timeout, corrupting the Broadcaster's internal state.
            message_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            async def reader_task() -> None:
                """Read from subscriber and forward to queue."""
                try:
                    async for event in subscriber:
                        await message_queue.put(("message", event))
                except Exception as e:
                    await message_queue.put(("error", e))
                finally:
                    await message_queue.put(("done", None))

            # Start the reader as a background task
            reader = asyncio.create_task(reader_task())

            # Step 4: Stream events with heartbeat
            try:
                while True:
                    try:
                        # Wait for message with timeout for heartbeat
                        msg_type, data = await asyncio.wait_for(
                            message_queue.get(),
                            timeout=HEARTBEAT_INTERVAL,
                        )

                        if msg_type == "message":
                            # Broadcaster returns Event objects with .channel and .message
                            try:
                                parsed_event = json.loads(data.message)
                                logger.debug(
                                    "[SSE-STREAM] Yielding event",
                                    extra={
                                        "user_id": user_id,
                                        "event_type": parsed_event.get("type"),
                                    },
                                )
                                try:
                                    yield format_redis_event(parsed_event, user_id)
                                except GeneratorExit:
                                    logger.info(
                                        f"[SSE-STREAM] Client disconnected for user {user_id}"
                                    )
                                    return  # Exit cleanly
                            except json.JSONDecodeError as e:
                                logger.warning(f"[SSE-STREAM] Invalid JSON in message: {e}")
                        elif msg_type == "error":
                            logger.error(f"[SSE-STREAM] Reader error for user {user_id}: {data}")
                            break
                        elif msg_type == "done":
                            logger.info(f"[SSE-STREAM] Subscription ended for user {user_id}")
                            break

                    except asyncio.TimeoutError:
                        # No message within timeout - send heartbeat
                        logger.debug(f"[SSE-HEARTBEAT] Sending heartbeat for user {user_id}")
                        try:
                            yield {
                                "event": "heartbeat",
                                "data": json.dumps(
                                    {
                                        "type": "heartbeat",
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    }
                                ),
                            }
                        except GeneratorExit:
                            logger.info(f"[SSE-STREAM] Client disconnected for user {user_id}")
                            return  # Exit cleanly
            finally:
                # Clean up the reader task
                reader.cancel()
                try:
                    await reader
                except asyncio.CancelledError:
                    pass

    except asyncio.CancelledError:
        logger.info(f"[SSE-STREAM] Stream cancelled for user {user_id}")
        raise
    except RuntimeError as e:
        if "generator" in str(e).lower():
            # Normal cleanup during client disconnect - not an error
            logger.debug(f"[SSE-STREAM] Generator cleanup for user {user_id}")
        else:
            # Broadcast not initialized or other runtime error
            logger.error(f"[SSE-STREAM] Broadcast error for user {user_id}: {e}")
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

    logger.info(f"[SSE-STREAM] User {user_id} unsubscribed from channel {channel}")


async def publish_to_user(user_id: str, message: Dict[str, Any]) -> None:
    """
    Publish a message to a user's channel via Broadcaster.

    Uses the shared Broadcaster connection for efficient publishing.

    Args:
        user_id: The target user's ULID
        message: The message payload (will be JSON serialized)
    """
    channel = f"user:{user_id}"
    try:
        broadcast = get_broadcast()
        await broadcast.publish(channel=channel, message=json.dumps(message))
        logger.debug(f"[SSE-PUBLISH] Published message to user {user_id}")
    except RuntimeError as e:
        # Broadcast not initialized
        logger.warning(f"[SSE-PUBLISH] Broadcast not initialized, cannot publish: {e}")
    except Exception as e:
        logger.error(f"[SSE-PUBLISH] Failed to publish to {channel}: {e}")


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

    conv_id = getattr(message, "conversation_id", None)
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


async def fetch_messages_after(
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
    message_repo = MessageRepository(db)
    from app.repositories.conversation_repository import ConversationRepository

    conversation_repo = ConversationRepository(db)
    conversations = await asyncio.to_thread(conversation_repo.find_for_user, user_id, 1000, 0)
    conversation_ids = [c.id for c in conversations]

    if conversation_ids:
        return await asyncio.to_thread(
            message_repo.get_messages_after_id_for_conversations,
            conversation_ids,
            after_message_id,
            100,
        )

    return []
