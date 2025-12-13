# backend/app/core/broadcast.py
"""
Shared broadcast manager for SSE multiplexing.

This replaces the per-connection Redis PubSub pattern with a single
shared connection per worker process, enabling 500+ concurrent SSE
clients instead of ~30.

Architecture:
- One Broadcaster instance per worker process
- Broadcaster internally maintains ONE Redis PubSub connection
- All SSE clients share this connection via internal asyncio queues
- Messages fan-out from Redis → Broadcaster → N asyncio queues → N SSE clients

Before: N SSE clients = N Redis connections (crashes at ~30-60)
After:  N SSE clients = 1 Redis connection (scales to 500+)
"""
import logging
from typing import Optional

from broadcaster import Broadcast

from .config import settings

logger = logging.getLogger(__name__)

# Single broadcast instance per worker process
# Broadcaster internally manages one Redis connection that multiplexes
# all channel subscriptions through internal asyncio queues
_broadcast: Optional[Broadcast] = None


def get_broadcast() -> Broadcast:
    """
    Get the shared broadcast instance.

    Raises:
        RuntimeError: If broadcast is not initialized (call connect_broadcast first)
    """
    if _broadcast is None:
        raise RuntimeError("Broadcast not initialized. Call connect_broadcast() during startup.")
    return _broadcast


def is_broadcast_initialized() -> bool:
    """
    Check if the broadcast instance is initialized.

    Used by health checks to verify SSE multiplexer is ready.

    Returns:
        True if broadcast is initialized and connected, False otherwise
    """
    return _broadcast is not None


async def connect_broadcast() -> None:
    """
    Connect to Redis via Broadcaster.

    Call during application startup (in lifespan manager).
    This establishes the single shared Redis PubSub connection.
    """
    global _broadcast

    redis_url = settings.redis_url or "redis://localhost:6379"
    _broadcast = Broadcast(redis_url)
    await _broadcast.connect()
    logger.info("[BROADCAST] Connected to Redis for SSE multiplexing: %s", redis_url)


async def disconnect_broadcast() -> None:
    """
    Disconnect from Redis.

    Call during application shutdown.
    """
    global _broadcast

    if _broadcast is not None:
        await _broadcast.disconnect()
        _broadcast = None
        logger.info("[BROADCAST] Disconnected from Redis")
