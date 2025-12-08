# backend/app/services/permission_cache.py
"""
Permission caching service.

Caches user permissions in Redis to reduce DB queries during
high-frequency operations like SSE authentication.

The in-memory cache in PermissionService is request-scoped (cleared per request).
This Redis-based cache persists across requests with a configurable TTL.
"""

import json
import logging
from typing import Optional, Set

from ..core.redis import get_async_redis_client

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
PERMISSION_CACHE_TTL = 300


async def get_cached_permissions(user_id: str) -> Optional[Set[str]]:
    """
    Get user permissions from Redis cache.

    Returns:
        Set of permission names if cached, None if not cached.
    """
    try:
        redis = await get_async_redis_client()
        cached = await redis.get(f"permissions:{user_id}")
        if cached:
            logger.debug(f"Permission cache HIT for user {user_id}")
            return set(json.loads(cached))
        logger.debug(f"Permission cache MISS for user {user_id}")
        return None
    except Exception as e:
        logger.warning(f"Error reading permission cache: {e}")
        return None


async def set_cached_permissions(user_id: str, permissions: Set[str]) -> None:
    """
    Cache user permissions in Redis.

    Args:
        user_id: The user's ID
        permissions: Set of permission names
    """
    try:
        redis = await get_async_redis_client()
        await redis.setex(
            f"permissions:{user_id}",
            PERMISSION_CACHE_TTL,
            json.dumps(list(permissions)),
        )
        logger.debug(f"Cached {len(permissions)} permissions for user {user_id}")
    except Exception as e:
        logger.warning(f"Error writing permission cache: {e}")


async def invalidate_cached_permissions(user_id: str) -> None:
    """
    Invalidate cached permissions for a user.

    Call this when user's permissions change (role change, etc.)
    """
    try:
        redis = await get_async_redis_client()
        await redis.delete(f"permissions:{user_id}")
        logger.debug(f"Invalidated permission cache for user {user_id}")
    except Exception as e:
        logger.warning(f"Error invalidating permission cache: {e}")
