# backend/app/services/messaging/redis_pubsub.py
"""
Redis Pub/Sub Manager for messaging notifications.

This module handles publishing messaging events to Redis channels.
Subscribing is handled separately in Phase 2.

Design decisions:
- Async Redis client (non-blocking)
- Fire-and-forget publishing (failures logged, not raised)
- User channels: "user:{user_id}"
- All events include schema_version for future evolution
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    """
    Singleton manager for Redis Pub/Sub publishing.

    Uses async Redis client to avoid blocking the event loop.
    Publishing is fire-and-forget - if Redis fails, we log but don't
    raise. Messages are safe in Postgres; clients sync on reconnect.
    """

    _instance: Optional["RedisPubSubManager"] = None
    _initialized: bool

    def __new__(cls) -> "RedisPubSubManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._redis: Any = None  # Redis[str] at runtime
        self._initialized = True
        self._publish_count: int = 0
        self._error_count: int = 0
        logger.debug("[REDIS-PUBSUB] RedisPubSubManager singleton created")

    async def initialize(self, redis: Any) -> None:
        """Initialize with async Redis client."""
        self._redis = redis
        logger.info("[REDIS-PUBSUB] RedisPubSubManager initialized with Redis client")

    @property
    def is_initialized(self) -> bool:
        """Check if manager is ready for publishing."""
        return self._redis is not None

    def get_stats(self) -> Dict[str, Any]:
        """Get publishing statistics."""
        return {
            "initialized": self.is_initialized,
            "publish_count": self._publish_count,
            "error_count": self._error_count,
        }

    async def publish_to_user(self, user_id: str, event: Dict[str, Any]) -> int:
        """
        Publish an event to a user's channel.

        Args:
            user_id: Target user's ULID
            event: Event dict (must include type, schema_version, timestamp, payload)

        Returns:
            Number of subscribers who received the message (0 if failed)
        """
        if self._redis is None:
            logger.warning("[REDIS-PUBSUB] Redis not initialized, skipping publish")
            return 0

        channel = f"user:{user_id}"
        payload = json.dumps(event)

        try:
            result: int = await self._redis.publish(channel, payload)
            self._publish_count += 1
            logger.debug(
                f"[REDIS-PUBSUB] Published {event.get('type')} to {channel} "
                f"(subscribers: {result})"
            )
            return result
        except Exception as e:
            # Fire-and-forget: log error but don't fail the request
            self._error_count += 1
            logger.error(f"[REDIS-PUBSUB] Failed to publish to {channel}: {e}")
            return 0

    async def publish_to_users(
        self,
        user_ids: List[str],
        event: Dict[str, Any],
    ) -> Dict[str, int]:
        """
        Publish an event to multiple users' channels.

        Args:
            user_ids: List of target user ULIDs
            event: Event dict to publish

        Returns:
            Dict mapping user_id to subscriber count
        """
        results: Dict[str, int] = {}
        for user_id in user_ids:
            results[user_id] = await self.publish_to_user(user_id, event)
        return results


# Global singleton instance
pubsub_manager = RedisPubSubManager()
