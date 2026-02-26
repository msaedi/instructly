# backend/app/services/messaging/__init__.py
"""
Messaging services package (v4.0 with Broadcaster).

Architecture:
- SSE streaming uses Broadcaster for fan-out multiplexing (1 Redis connection per worker)
- Publishing uses Broadcaster for consistent Redis connection management
- Enables 500+ concurrent SSE users instead of ~30 with per-connection pattern

Phases:
- Phase 1: Publishing to Redis Pub/Sub
- Phase 2: Redis-only SSE streaming with Last-Event-ID support
- Phase 3: Broadcaster integration for scalability
"""

from app.services.messaging.events import (
    SCHEMA_VERSION,
    EventType,
    build_event,
)
from app.services.messaging.publisher import (
    publish_message_deleted,
    publish_message_deleted_direct,
    publish_message_edited,
    publish_message_edited_direct,
    publish_new_message,
    publish_new_message_direct,
    publish_reaction_update,
    publish_reaction_update_direct,
    publish_read_receipt,
    publish_read_receipt_direct,
    publish_typing_status,
    publish_typing_status_direct,
)
from app.services.messaging.sse_stream import create_sse_stream, ensure_db_health, publish_to_user

__all__ = [
    # Publishers (DB-based - fetch participants internally)
    "publish_new_message",
    "publish_typing_status",
    "publish_reaction_update",
    "publish_message_edited",
    "publish_read_receipt",
    "publish_message_deleted",
    # Publishers (Direct - accept pre-fetched participant IDs, no DB required)
    "publish_new_message_direct",
    "publish_typing_status_direct",
    "publish_read_receipt_direct",
    "publish_message_edited_direct",
    "publish_message_deleted_direct",
    "publish_reaction_update_direct",
    "publish_to_user",  # Broadcaster-based publish
    # SSE Stream (uses Broadcaster v4.0)
    "create_sse_stream",
    "ensure_db_health",
    # Events
    "EventType",
    "SCHEMA_VERSION",
    "build_event",
]
