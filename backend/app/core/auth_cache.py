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

from ..core.cache_redis import get_async_cache_redis_client
from ..database import SessionLocal
from ..models.user import User  # Used in _user_to_dict type hint and create_transient_user

logger = logging.getLogger(__name__)

# Cache TTL for user lookups (30 minutes - roles/permissions rarely change)
# Increased from 5 min to reduce DB pressure under load (users can re-login if role changes)
USER_CACHE_TTL_SECONDS = 1800
USER_CACHE_PREFIX = "auth_user"
USER_CACHE_ID_PREFIX = f"{USER_CACHE_PREFIX}:id:"


def _cache_key_for_id(user_id: str) -> str:
    return f"{USER_CACHE_ID_PREFIX}{user_id}"


async def _get_auth_redis_client() -> Any:
    """Get the shared async Redis client for auth caching (or None if unavailable)."""
    try:
        return await get_async_cache_redis_client()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[AUTH-CACHE] Redis init failed, caching disabled: %s", e)
        return None


async def get_cached_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Try to get user data from Redis cache.

    Args:
        user_id: User ULID

    Returns:
        Dict with user data if cached, None otherwise
    """
    if not user_id:
        return None

    try:
        redis = await _get_auth_redis_client()
        if redis is None:
            return None

        cache_key = _cache_key_for_id(user_id)
        cached = await redis.get(cache_key)
        if cached:
            logger.debug("[AUTH-CACHE] Cache HIT for user %s", user_id)
            return cast(Dict[str, Any], json.loads(cached))

        logger.debug("[AUTH-CACHE] Cache MISS for user %s", user_id)
        return None
    except Exception as e:
        logger.warning("[AUTH-CACHE] Cache lookup failed: %s", e)
        return None


async def set_cached_user(user_id: str, user_data: Dict[str, Any]) -> None:
    """Cache user data in Redis.

    Args:
        user_id: User ULID
        user_data: Dict containing user attributes to cache
    """
    try:
        redis = await _get_auth_redis_client()
        if redis is None:
            return

        cache_user_id = str(user_data.get("id") or user_id or "").strip()
        if not cache_user_id:
            return

        cache_key = _cache_key_for_id(cache_user_id)
        payload = json.dumps(user_data)
        await redis.setex(cache_key, USER_CACHE_TTL_SECONDS, payload)

        logger.debug("[AUTH-CACHE] SET user %s (TTL=%ds)", cache_user_id, USER_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("[AUTH-CACHE] Cache write failed: %s", e)


async def invalidate_cached_user(user_id: str) -> bool:
    """Invalidate user data in Redis cache.

    Call this when user data changes (role change, beta access granted/revoked, etc.)
    to ensure the next request fetches fresh data from the database.

    Args:
        user_id: User ULID

    Returns:
        True if cache entry was deleted, False if not found or error
    """
    if not user_id:
        return False

    try:
        redis = await _get_auth_redis_client()
        if redis is None:
            return False

        cache_key = _cache_key_for_id(user_id)
        deleted_total = int(await redis.delete(cache_key))

        if deleted_total:
            logger.info("[AUTH-CACHE] INVALIDATED user %s", user_id)
        return bool(deleted_total)
    except Exception as e:
        logger.warning("[AUTH-CACHE] Cache invalidation failed: %s", e)
        return False


def invalidate_cached_user_by_id_sync(user_id: str, db_session: Any) -> bool:
    """Sync helper to invalidate user cache by user_id.

    Args:
        user_id: User's ULID
        db_session: Unused; kept for backward-compatible call signatures

    Returns:
        True if cache was invalidated, False otherwise
    """
    _ = db_session
    if not user_id:
        return False

    try:
        # Check if event loop is already running (e.g., in pytest)
        # Must check BEFORE creating coroutine to avoid unawaited coroutine warning
        try:
            loop = asyncio.get_running_loop()
            # Event loop is running - schedule as task (fire-and-forget)
            # Cache invalidation is best-effort, so this is acceptable
            task = loop.create_task(invalidate_cached_user(user_id))

            def _on_done(t: "asyncio.Task[bool]") -> None:
                if t.cancelled():
                    return
                exc = t.exception()
                if exc is not None:
                    logger.error(
                        "Fire-and-forget cache invalidation failed for user %s: %s",
                        user_id,
                        exc,
                    )

            if hasattr(task, "add_done_callback"):
                task.add_done_callback(_on_done)
            logger.debug("[AUTH-CACHE] Scheduled async invalidation for %s", user_id)
            return True
        except RuntimeError:
            # No running event loop - use asyncio.run()
            return asyncio.run(invalidate_cached_user(user_id))
    except Exception as e:
        logger.warning("[AUTH-CACHE] Sync invalidation failed: %s", e, exc_info=True)
        return False


def _user_to_dict(user: User, beta_access: Optional[Any] = None) -> Dict[str, Any]:
    """Extract user attributes to dict while session is still open.

    Args:
        user: User ORM object with active session
        beta_access: Optional BetaAccess ORM object to include in cached data

    Returns:
        Dict with user data including permissions and all fields needed by /auth/me
    """
    # Collect permissions from all roles (assumes roles+permissions are loaded)
    permissions: set[str] = set()
    role_names: list[str] = []
    for role in user.roles:
        role_names.append(role.name)
        for perm in role.permissions:
            permissions.add(perm.name)

    result: Dict[str, Any] = {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_student": user.is_student,
        "is_instructor": user.is_instructor,
        "is_admin": user.is_admin,
        "first_name": user.first_name,
        "last_name": user.last_name,
        # Additional fields for /auth/me endpoint (avoids re-querying)
        "phone": getattr(user, "phone", None),
        "zip_code": getattr(user, "zip_code", None),
        "timezone": getattr(user, "timezone", None),
        "profile_picture_version": getattr(user, "profile_picture_version", 0),
        "has_profile_picture": getattr(user, "has_profile_picture", False),
        # Keep this precomputed in cache so auth checks are integer comparisons.
        # Cache eviction for tokens_valid_after updates is handled by
        # invalidate_cached_user_by_id_sync().
        "tokens_valid_after_ts": (
            int(user.tokens_valid_after.timestamp())
            if getattr(user, "tokens_valid_after", None)
            else None
        ),
        # Role names for direct use in /auth/me response
        "roles": role_names,
        "permissions": list(permissions),  # Cache permissions for SSE permission checks
        # Beta access cached to avoid per-request DB query in /auth/me
        "beta_access": bool(beta_access),
        "beta_role": getattr(beta_access, "role", None) if beta_access else None,
        "beta_phase": getattr(beta_access, "phase", None) if beta_access else None,
        "beta_invited_by": getattr(beta_access, "invited_by_code", None) if beta_access else None,
    }

    return result


def _sync_user_lookup_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Synchronous user lookup by ID - returns dict to avoid detached ORM issues.

    Uses UserRepository to follow the repository pattern.
    Uses get_by_id_with_roles_and_permissions() to load permissions in one query.

    Also fetches beta_access to cache it and avoid per-request queries in /auth/me.

    Args:
        user_id: User's ULID

    Returns:
        Dict with user data if found, None otherwise
    """
    from ..repositories.beta_repository import BetaAccessRepository
    from ..repositories.user_repository import UserRepository

    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        # Use method that eager-loads roles+permissions in one query
        user = user_repo.get_by_id_with_roles_and_permissions(user_id)
        if user:
            # Also fetch beta_access to cache it (avoids per-request query in /auth/me)
            beta_repo = BetaAccessRepository(db)
            beta_access = beta_repo.get_latest_for_user(user.id)
            # Roles and permissions are explicitly loaded via joinedload
            return _user_to_dict(user, beta_access)
        return None
    finally:
        db.rollback()
        db.close()


async def lookup_user_nonblocking(user_identifier: str) -> Optional[Dict[str, Any]]:
    """Backward-compatible alias for ULID-based non-blocking user lookup."""
    return await lookup_user_by_id_nonblocking(user_identifier)


async def lookup_user_by_id_nonblocking(user_id: str) -> Optional[Dict[str, Any]]:
    """Look up user by ID without blocking the event loop.

    Args:
        user_id: User's ULID

    Returns:
        Dict with user data if found, None otherwise
    """
    cached_data = await get_cached_user(user_id)
    if cached_data:
        return cached_data

    user_data = await asyncio.to_thread(_sync_user_lookup_by_id, user_id)
    if user_data:
        await set_cached_user(user_id, user_data)
    return user_data


def create_transient_user(user_data: Dict[str, Any]) -> User:
    """Create a transient (non-session-bound) User object from cached data.

    This creates a User object that is NOT attached to any SQLAlchemy session.
    It can be safely used after the original session is closed.

    IMPORTANT: This user object cannot lazy-load relationships. Only the
    attributes explicitly copied from user_data will be available.

    The transient user fully emulates an ORM user:
    - The `roles` attribute is populated with mock Role objects
    - The `is_student`, `is_instructor`, `is_admin` properties work normally
    - Route handlers can check roles without knowing about transient vs ORM users
    - Permissions are cached for SSE permission checks (no DB query needed)
    - All fields needed by /auth/me are populated (phone, timezone, etc.)

    Args:
        user_data: Dict containing user attributes

    Returns:
        Transient User object
    """
    from ..core.enums import RoleName
    from ..models.rbac import Role

    # Pass email to constructor to avoid "unknown user" log noise
    # Note: 'role' is a read-only property, so we only pass email
    user = User(email=user_data.get("email", "transient"))
    user.id = user_data.get("id")
    user.is_active = user_data.get("is_active", True)
    user.first_name = user_data.get("first_name")
    user.last_name = user_data.get("last_name")

    # Additional fields for /auth/me endpoint (no re-querying needed)
    user.phone = user_data.get("phone")
    user.zip_code = user_data.get("zip_code")
    user.timezone = user_data.get("timezone")
    user.profile_picture_version = user_data.get("profile_picture_version", 0)
    # has_profile_picture is a property, store the underlying value
    setattr(user, "_cached_has_profile_picture", user_data.get("has_profile_picture", False))

    # Populate roles so routes can check them normally (e.g., `for role in user.roles`)
    # This allows transient users to fully emulate ORM users
    roles = []
    if user_data.get("is_instructor"):
        role = Role()
        role.name = RoleName.INSTRUCTOR
        roles.append(role)
    if user_data.get("is_student"):
        role = Role()
        role.name = RoleName.STUDENT
        roles.append(role)
    if user_data.get("is_admin"):
        role = Role()
        role.name = RoleName.ADMIN
        roles.append(role)
    user.roles = roles

    # Also store cached flags for the property getters (belt and suspenders)
    setattr(user, "_cached_is_student", user_data.get("is_student", False))
    setattr(user, "_cached_is_instructor", user_data.get("is_instructor", False))
    setattr(user, "_cached_is_admin", user_data.get("is_admin", False))

    # Store cached permissions for SSE permission checks (avoids DB query)
    setattr(user, "_cached_permissions", set(user_data.get("permissions", [])))

    # Store cached role names for /auth/me response (avoids re-extracting)
    setattr(user, "_cached_role_names", list(user_data.get("roles", [])))

    # Store cached beta_access for /auth/me (avoids per-request DB query)
    setattr(user, "_cached_beta_access", user_data.get("beta_access", False))
    setattr(user, "_cached_beta_role", user_data.get("beta_role"))
    setattr(user, "_cached_beta_phase", user_data.get("beta_phase"))
    setattr(user, "_cached_beta_invited_by", user_data.get("beta_invited_by"))

    return user


def user_has_cached_permission(user: User, permission_name: str) -> bool:
    """Check if user has a permission using cached data (no DB query).

    For transient users (from auth cache), this uses the cached permissions set.
    For ORM users, falls back to iterating roles.permissions.

    Args:
        user: User object (transient or ORM)
        permission_name: Name of the permission to check

    Returns:
        True if user has the permission, False otherwise
    """
    # First check cached permissions (works for transient users)
    cached_perms = getattr(user, "_cached_permissions", None)
    if cached_perms is not None:
        return permission_name in cached_perms

    # Fallback for ORM users - iterate relationships
    # NOTE: This may trigger lazy loading if roles/permissions aren't loaded
    for role in user.roles:
        for perm in role.permissions:
            if perm.name == permission_name:
                return True
    return False


# For tests - allow patching the Redis client getter
def _reset_redis_client() -> None:
    """Reset the Redis client singleton (for testing only)."""
    # The caching Redis client is managed per-event-loop in app.core.cache_redis.
    # Tests that need to influence Redis behavior should patch _get_auth_redis_client().
    return
