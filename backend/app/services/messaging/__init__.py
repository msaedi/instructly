# backend/app/services/messaging/__init__.py
"""
Messaging services package.

Phase 1: Publishing to Redis Pub/Sub
Phase 2: Redis-only SSE streaming with Last-Event-ID support
"""

from app.services.messaging.events import (
    SCHEMA_VERSION,
    EventType,
    build_event,
)
from app.services.messaging.publisher import (
    publish_message_deleted,
    publish_message_edited,
    publish_new_message,
    publish_reaction_update,
    publish_read_receipt,
    publish_typing_status,
)
from app.services.messaging.redis_pubsub import pubsub_manager
from app.services.messaging.sse_stream import create_sse_stream

__all__ = [
    # Manager
    "pubsub_manager",
    # Publishers
    "publish_new_message",
    "publish_typing_status",
    "publish_reaction_update",
    "publish_message_edited",
    "publish_read_receipt",
    "publish_message_deleted",
    # SSE Stream (Phase 2)
    "create_sse_stream",
    # Events
    "EventType",
    "SCHEMA_VERSION",
    "build_event",
]
