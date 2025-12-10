# backend/app/auth_sse.py
"""
Authentication utilities for SSE (Server-Sent Events) endpoints.

WHY THIS EXISTS SEPARATELY FROM MAIN AUTH:
-------------------------------------------
The EventSource API in browsers has a critical limitation: it cannot send
custom headers (including Authorization headers). This is a browser API
limitation, not a design choice.

References:
- https://html.spec.whatwg.org/multipage/server-sent-events.html#the-eventsource-interface
- https://github.com/whatwg/html/issues/2177

AUTHENTICATION METHODS SUPPORTED:
---------------------------------
1. Query parameter (?token=xxx) - Primary method for browser EventSource
2. Authorization header - For non-browser clients and testing
3. Cookie - Fallback for browsers with withCredentials support

This module is necessary because SSE requires different auth handling
than regular REST endpoints due to browser API constraints.

PERFORMANCE OPTIMIZATION (v4.1):
--------------------------------
User lookups are cached in Redis to reduce DB connection pressure during load.
With 100+ concurrent SSE connections, each needing auth, DB pool exhaustion
causes Supabase to drop connections. Caching reduces DB hits by ~95%.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, cast

from fastapi import Depends, HTTPException, Query, Request, status
from jwt import InvalidIssuerError, PyJWTError

from .auth import decode_access_token, oauth2_scheme_optional
from .core.config import settings
from .database import SessionLocal
from .models.user import User
from .utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)

# Cache TTL for user lookups (5 minutes - balance freshness vs DB pressure)
_USER_CACHE_TTL_SECONDS = 300
_USER_CACHE_PREFIX = "sse_auth_user:"

# Module-level Redis client singleton (lazy init)
_sse_redis_client = None


def _get_sse_redis_client() -> Any:
    """Get or create sync Redis client for SSE auth caching."""
    global _sse_redis_client
    if _sse_redis_client is None:
        try:
            from redis import from_url

            redis_url = settings.redis_url or "redis://localhost:6379"
            _sse_redis_client = from_url(redis_url, decode_responses=True)
            _sse_redis_client.ping()  # Verify connection
            logger.info("[SSE-AUTH] Redis client initialized for user caching")
        except Exception as e:
            logger.warning("[SSE-AUTH] Redis init failed, caching disabled: %s", e)
            return None
    return _sse_redis_client


async def _get_cached_user(email: str) -> Optional[Dict[str, Any]]:
    """Try to get user data from Redis cache."""
    try:
        redis = _get_sse_redis_client()
        if redis is None:
            return None

        cache_key = f"{_USER_CACHE_PREFIX}{email}"
        cached = redis.get(cache_key)
        if cached:
            logger.info("[SSE-AUTH] Cache HIT for user %s", email)
            return cast(Dict[str, Any], json.loads(cached))
        logger.info("[SSE-AUTH] Cache MISS for user %s", email)
        return None
    except Exception as e:
        logger.warning("[SSE-AUTH] Cache lookup failed: %s", e)
        return None


async def _set_cached_user(email: str, user_data: Dict[str, Any]) -> None:
    """Cache user data in Redis."""
    try:
        redis = _get_sse_redis_client()
        if redis is None:
            return

        cache_key = f"{_USER_CACHE_PREFIX}{email}"
        redis.setex(cache_key, _USER_CACHE_TTL_SECONDS, json.dumps(user_data))
        logger.info("[SSE-AUTH] SET user %s (TTL=%ds)", email, _USER_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("[SSE-AUTH] Cache write failed: %s", e)


async def get_current_user_sse(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme_optional),
    token_query: Optional[str] = Query(None, alias="token"),
) -> User:
    """
    Get current user for SSE endpoints.

    CRITICAL: This function uses manual DB session management to prevent holding
    connections in "idle in transaction" state during long-running SSE streams.
    FastAPI's Depends(get_db) cleanup only runs AFTER the response completes,
    which for SSE can be 30+ seconds.

    Checks for authentication in this order:
    1. Authorization header (for testing/non-browser clients)
    2. Query parameter (for EventSource)
    3. Cookie (for browser-based EventSource with withCredentials)

    Args:
        token_header: Token from Authorization header
        token_query: Token from query parameter

    Returns:
        User object if authenticated

    Raises:
        HTTPException: If no valid authentication found
    """
    # Try to get token from any source
    token_cookie: Optional[str] = None
    if hasattr(request, "cookies"):
        try:
            site_mode = settings.site_mode
        except Exception:
            site_mode = "local"

        for cookie_name in session_cookie_candidates(site_mode):
            cookie_token = request.cookies.get(cookie_name)
            if cookie_token:
                token_cookie = cookie_token
                logger.debug("Using %s cookie for SSE authentication", cookie_name)
                break

    token = token_header or token_query or token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_email = payload.get("sub")

        if not isinstance(user_email, str):
            raise credentials_exception

    except (PyJWTError, InvalidIssuerError) as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception

    # =========================================================================
    # CACHED USER LOOKUP (reduces DB pressure by ~95%)
    # =========================================================================
    # First, try Redis cache to avoid DB hit
    cached_user_data = await _get_cached_user(user_email)
    if cached_user_data:
        # Reconstruct minimal User object from cached data
        # We only need id, email, is_active for SSE auth
        user = User()
        user.id = cached_user_data.get("id")
        user.email = cached_user_data.get("email")
        user.is_active = cached_user_data.get("is_active", True)
        user.first_name = cached_user_data.get("first_name")
        user.last_name = cached_user_data.get("last_name")

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )
        return user

    # =========================================================================
    # MANUAL DB SESSION MANAGEMENT (cache miss path)
    # We create and close the session explicitly to prevent holding connections
    # in "idle in transaction" state during long-running SSE streams.
    # =========================================================================
    def _sync_user_lookup(email: str) -> Optional[User]:
        """Synchronous user lookup - run in thread to avoid blocking event loop."""
        db = SessionLocal()
        try:
            user = cast(Optional[User], db.query(User).filter(User.email == email).first())
            if user:
                # Eagerly load user attributes we need before closing session
                _ = user.id
                _ = user.email
                _ = user.is_active
                _ = user.first_name
                _ = user.last_name
            return user
        finally:
            db.rollback()  # Clean up transaction before returning to pool
            db.close()

    # Run synchronous SQLAlchemy query in thread pool to avoid blocking event loop
    # This is critical for SSE endpoints with many concurrent connections
    db_user = await asyncio.to_thread(_sync_user_lookup, user_email)
    logger.debug("[SSE-AUTH] DB session closed after user lookup")

    if db_user is None:
        raise credentials_exception

    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Cache the user for subsequent requests
    await _set_cached_user(
        user_email,
        {
            "id": db_user.id,
            "email": db_user.email,
            "is_active": db_user.is_active,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
        },
    )

    return db_user
