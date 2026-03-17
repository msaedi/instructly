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

from ..core.cache_redis import get_async_cache_redis_client

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
        redis = await get_async_cache_redis_client()
        if redis is None:
            logger.warning("[PERM-CACHE] Redis unavailable, falling back to DB")
            return None
        cached = await redis.get(f"permissions:{user_id}")
        if cached:
            logger.info("[PERM-CACHE] HIT for user %s", user_id)
            return set(json.loads(cached))
        logger.info("[PERM-CACHE] MISS for user %s", user_id)
        return None
    except Exception as e:
        logger.warning("[PERM-CACHE] Error reading cache: %s", e)
        return None


async def set_cached_permissions(user_id: str, permissions: Set[str]) -> None:
    """
    Cache user permissions in Redis.

    Args:
        user_id: The user's ID
        permissions: Set of permission names
    """
    try:
        redis = await get_async_cache_redis_client()
        if redis is None:
            logger.warning("[PERM-CACHE] Redis unavailable, skipping cache write")
            return
        await redis.setex(
            f"permissions:{user_id}",
            PERMISSION_CACHE_TTL,
            json.dumps(list(permissions)),
        )
        logger.info("[PERM-CACHE] SET %s permissions for user %s", len(permissions), user_id)
    except Exception as e:
        logger.warning("Error writing permission cache: %s", e)


async def invalidate_cached_permissions(user_id: str) -> None:
    """
    Invalidate cached permissions for a user.

    Call this when user's permissions change (role change, etc.)
    """
    try:
        redis = await get_async_cache_redis_client()
        if redis is None:
            logger.warning("[PERM-CACHE] Redis unavailable, skipping cache invalidation")
            return
        await redis.delete(f"permissions:{user_id}")
        logger.debug("[PERM-CACHE] Invalidated permission cache for user %s", user_id)
    except Exception as e:
        logger.warning("Error invalidating permission cache: %s", e)
