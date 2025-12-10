# backend/app/core/auth_cache.py
"""
Shared authentication caching utilities for non-blocking auth lookups.

This module provides Redis-backed caching for user authentication lookups
to prevent event loop blocking under load. The pattern is:

1. Check Redis cache first (instant, non-blocking)
2. On cache miss: Run sync DB query in thread pool (non-blocking)
3. Cache the result for subsequent requests

CRITICAL: This solves the event loop blocking problem that occurs when
synchronous database queries run in the main async event loop. Under load
(75+ concurrent users), sync queries that normally take 1-5ms can take
100-600ms, causing request queue buildup and cascading timeouts.

Used by:
- app/auth_sse.py (SSE endpoint authentication)
- app/api/dependencies/auth.py (main auth dependency)
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, cast

from ..core.config import settings
from ..database import SessionLocal
from ..models.user import User  # Used in _user_to_dict type hint and create_transient_user

logger = logging.getLogger(__name__)

# Cache TTL for user lookups (5 minutes - balance freshness vs DB pressure)
USER_CACHE_TTL_SECONDS = 300
USER_CACHE_PREFIX = "auth_user:"

# Module-level Redis client singleton (lazy init)
_auth_redis_client = None


def _get_auth_redis_client() -> Any:
    """Get or create sync Redis client for auth caching.

    Returns None if Redis is unavailable (graceful degradation).
    """
    global _auth_redis_client
    if _auth_redis_client is None:
        try:
            from redis import from_url

            redis_url = settings.redis_url or "redis://localhost:6379"
            _auth_redis_client = from_url(redis_url, decode_responses=True)
            _auth_redis_client.ping()  # Verify connection
            logger.info("[AUTH-CACHE] Redis client initialized for user caching")
        except Exception as e:
            logger.warning("[AUTH-CACHE] Redis init failed, caching disabled: %s", e)
            return None
    return _auth_redis_client


async def get_cached_user(email: str) -> Optional[Dict[str, Any]]:
    """Try to get user data from Redis cache.

    Args:
        email: User's email address

    Returns:
        Dict with user data if cached, None otherwise
    """
    try:
        redis = _get_auth_redis_client()
        if redis is None:
            return None

        cache_key = f"{USER_CACHE_PREFIX}{email}"
        cached = redis.get(cache_key)
        if cached:
            logger.debug("[AUTH-CACHE] Cache HIT for user %s", email)
            return cast(Dict[str, Any], json.loads(cached))
        logger.debug("[AUTH-CACHE] Cache MISS for user %s", email)
        return None
    except Exception as e:
        logger.warning("[AUTH-CACHE] Cache lookup failed: %s", e)
        return None


async def set_cached_user(email: str, user_data: Dict[str, Any]) -> None:
    """Cache user data in Redis.

    Args:
        email: User's email address
        user_data: Dict containing user attributes to cache
    """
    try:
        redis = _get_auth_redis_client()
        if redis is None:
            return

        cache_key = f"{USER_CACHE_PREFIX}{email}"
        redis.setex(cache_key, USER_CACHE_TTL_SECONDS, json.dumps(user_data))
        logger.debug("[AUTH-CACHE] SET user %s (TTL=%ds)", email, USER_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("[AUTH-CACHE] Cache write failed: %s", e)


def _user_to_dict(user: User) -> Dict[str, Any]:
    """Extract user attributes to dict while session is still open.

    Args:
        user: User ORM object with active session

    Returns:
        Dict with user data
    """
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_student": user.is_student,
        "is_instructor": user.is_instructor,
        "is_admin": user.is_admin,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _sync_user_lookup(email: str) -> Optional[Dict[str, Any]]:
    """Synchronous user lookup - returns dict to avoid detached ORM issues.

    CRITICAL: This function creates its own SQLAlchemy session because:
    1. SQLAlchemy sessions are NOT thread-safe
    2. We run this in asyncio.to_thread() to avoid blocking the event loop
    3. We return a dict (not ORM object) to avoid DetachedInstanceError

    Uses UserRepository to follow the repository pattern.

    Args:
        email: User's email address

    Returns:
        Dict with user data if found, None otherwise
    """
    from ..repositories.user_repository import UserRepository

    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if user:
            # Extract attributes BEFORE closing session, return as dict
            # Roles are eager-loaded via lazy="selectin" on the relationship
            return _user_to_dict(user)
        return None
    finally:
        db.rollback()  # Clean up transaction before returning to pool
        db.close()


def _sync_user_lookup_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Synchronous user lookup by ID - returns dict to avoid detached ORM issues.

    Uses UserRepository to follow the repository pattern.

    Args:
        user_id: User's ULID

    Returns:
        Dict with user data if found, None otherwise
    """
    from ..repositories.user_repository import UserRepository

    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        if user:
            # Roles are eager-loaded via lazy="selectin" on the relationship
            return _user_to_dict(user)
        return None
    finally:
        db.rollback()
        db.close()


async def lookup_user_nonblocking(email: str) -> Optional[Dict[str, Any]]:
    """Look up user by email without blocking the event loop.

    This is the main entry point for non-blocking user lookups:
    1. Check Redis cache first
    2. On cache miss, run sync DB query in thread pool
    3. Cache the result for subsequent requests

    Args:
        email: User's email address

    Returns:
        Dict with user data if found, None otherwise
    """
    # First, try Redis cache
    cached_data = await get_cached_user(email)
    if cached_data:
        return cached_data

    # Cache miss - run sync DB query in thread pool
    user_data = await asyncio.to_thread(_sync_user_lookup, email)

    if user_data:
        # Cache for subsequent requests
        await set_cached_user(email, user_data)

    return user_data


async def lookup_user_by_id_nonblocking(user_id: str) -> Optional[Dict[str, Any]]:
    """Look up user by ID without blocking the event loop.

    Note: ID lookups are not cached (used for impersonation, less frequent).

    Args:
        user_id: User's ULID

    Returns:
        Dict with user data if found, None otherwise
    """
    return await asyncio.to_thread(_sync_user_lookup_by_id, user_id)


def create_transient_user(user_data: Dict[str, Any]) -> User:
    """Create a transient (non-session-bound) User object from cached data.

    This creates a User object that is NOT attached to any SQLAlchemy session.
    It can be safely used after the original session is closed.

    IMPORTANT: This user object cannot lazy-load relationships. Only the
    attributes explicitly copied from user_data will be available.

    The role-based properties (is_student, is_instructor, is_admin) are stored
    as private attributes that override the property getters.

    Args:
        user_data: Dict containing user attributes

    Returns:
        Transient User object
    """
    user = User()
    user.id = user_data.get("id")
    user.email = user_data.get("email")
    user.is_active = user_data.get("is_active", True)
    user.first_name = user_data.get("first_name")
    user.last_name = user_data.get("last_name")

    # Store role flags as private attributes so they don't trigger lazy loading
    # The properties on User will try to access the roles relationship,
    # but we need to bypass that for transient users
    # Using setattr() for dynamic attributes that aren't declared on the model
    setattr(user, "_cached_is_student", user_data.get("is_student", False))
    setattr(user, "_cached_is_instructor", user_data.get("is_instructor", False))
    setattr(user, "_cached_is_admin", user_data.get("is_admin", False))

    return user


# For tests - allow patching the Redis client getter
def _reset_redis_client() -> None:
    """Reset the Redis client singleton (for testing only)."""
    global _auth_redis_client
    _auth_redis_client = None
