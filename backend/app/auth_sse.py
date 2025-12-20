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
1. Query parameter (?sse_token=xxx) - Short-lived SSE token for EventSource
2. Authorization header - For non-browser clients and testing
3. Cookie - Fallback for browsers with withCredentials support

This module is necessary because SSE requires different auth handling
than regular REST endpoints due to browser API constraints.

PERFORMANCE OPTIMIZATION (v4.1):
--------------------------------
User lookups are cached in Redis to reduce DB connection pressure during load.
With 100+ concurrent SSE connections, each needing auth, DB pool exhaustion
causes Supabase to drop connections. Caching reduces DB hits by ~95%.

Uses shared auth_cache module for Redis caching and non-blocking DB lookups.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from jwt import InvalidIssuerError, PyJWTError

from .auth import decode_access_token, oauth2_scheme_optional
from .core.auth_cache import (
    create_transient_user,
    lookup_user_by_id_nonblocking,
    lookup_user_nonblocking,
)
from .core.cache_redis import get_async_cache_redis_client
from .core.config import settings
from .models.user import User
from .utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)

SSE_TOKEN_PREFIX = "sse_token:"
SSE_TOKEN_TTL_SECONDS = 30


async def _get_user_from_sse_token(token: str) -> Optional[User]:
    """Resolve a short-lived SSE token to a transient user."""
    redis = await get_async_cache_redis_client()
    if redis is None:
        logger.warning("[SSE] Redis unavailable for SSE token lookup")
        return None

    key = f"{SSE_TOKEN_PREFIX}{token}"
    user_id_raw = await redis.get(key)
    if not user_id_raw:
        return None

    # One-time token - delete after use
    await redis.delete(key)

    user_id = (
        user_id_raw.decode() if isinstance(user_id_raw, (bytes, bytearray)) else str(user_id_raw)
    )
    user_data = await lookup_user_by_id_nonblocking(user_id)
    if not user_data:
        return None

    if not user_data.get("is_active", True):
        return None

    return create_transient_user(user_data)


async def get_current_user_sse(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme_optional),
    token_query: Optional[str] = Query(None, alias="sse_token"),
) -> User:
    """
    Get current user for SSE endpoints.

    CRITICAL: This function uses manual DB session management to prevent holding
    connections in "idle in transaction" state during long-running SSE streams.
    FastAPI's Depends(get_db) cleanup only runs AFTER the response completes,
    which for SSE can be 30+ seconds.

    Checks for authentication in this order:
    1. Authorization header (for testing/non-browser clients)
    2. Short-lived SSE token in query parameter (for EventSource)
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

    if token_query:
        sse_user = await _get_user_from_sse_token(token_query)
        if sse_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired SSE token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return sse_user

    token = token_header or token_cookie

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
    # NON-BLOCKING USER LOOKUP (uses shared auth_cache module)
    # =========================================================================
    # This uses Redis cache + asyncio.to_thread for DB queries to avoid
    # blocking the event loop under load.
    user_data = await lookup_user_nonblocking(user_email)

    if user_data is None:
        raise credentials_exception

    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create a TRANSIENT User object (not session-bound) from the dict
    # This avoids DetachedInstanceError when the original session is closed
    return create_transient_user(user_data)
