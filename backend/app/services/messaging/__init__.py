# backend/app/services/messaging/__init__.py
"""
Messaging services package.

Phase 1: Publishing to Redis Pub/Sub
Phase 2: Subscribing and dispatching (future)
"""

from app.services.messaging.events import (
    SCHEMA_VERSION,
    EventType,
    build_event,
)
from app.services.messaging.publisher import (
    publish_message_edited,
    publish_new_message,
    publish_reaction_update,
    publish_read_receipt,
    publish_typing_status,
)
from app.services.messaging.redis_pubsub import pubsub_manager

__all__ = [
    # Manager
    "pubsub_manager",
    # Publishers
    "publish_new_message",
    "publish_typing_status",
    "publish_reaction_update",
    "publish_message_edited",
    "publish_read_receipt",
    # Events
    "EventType",
    "SCHEMA_VERSION",
    "build_event",
]
