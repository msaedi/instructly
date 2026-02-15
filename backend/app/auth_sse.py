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

from .auth import decode_access_token, is_access_token_payload, oauth2_scheme_optional
from .core.auth_cache import (
    create_transient_user,
    lookup_user_by_id_nonblocking,
)
from .core.cache_redis import get_async_cache_redis_client
from .core.config import settings
from .models.user import User
from .monitoring.prometheus_metrics import prometheus_metrics
from .services.token_blacklist_service import TokenBlacklistService
from .utils.cookies import session_cookie_candidates
from .utils.token_utils import parse_token_iat

logger = logging.getLogger(__name__)

SSE_KEY_PREFIX = "sse_key:"
SSE_TOKEN_TTL_SECONDS = 30


async def _get_user_from_sse_token(token: str) -> Optional[User]:
    """Resolve a short-lived SSE token to a transient user."""
    redis = await get_async_cache_redis_client()
    if redis is None:
        logger.warning("[SSE] Redis unavailable for SSE token lookup")
        return None

    key = f"{SSE_KEY_PREFIX}{token}"
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

    Checks for authentication in this order:
    1. Short-lived SSE token in query parameter (for browser EventSource clients)
    2. Authorization header JWT (for non-browser clients/tests)
    3. Session cookie JWT fallback (browser with credentials)

    User resolution uses shared auth cache + non-blocking lookup to avoid
    synchronous DB pressure during concurrent SSE connections.

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
        if not is_access_token_payload(payload):
            raise credentials_exception

        jti_obj = payload.get("jti")
        jti = jti_obj if isinstance(jti_obj, str) else None
        if not jti:
            try:
                prometheus_metrics.record_token_rejection("format_outdated")
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token format outdated, please re-login",
                headers={"WWW-Authenticate": "Bearer"},
            )

        blacklist = TokenBlacklistService()
        try:
            revoked = await blacklist.is_revoked(jti)
        except Exception as exc:
            logger.warning("SSE blacklist check failed for jti=%s (fail-closed): %s", jti, exc)
            revoked = True
        if revoked:
            try:
                prometheus_metrics.record_token_rejection("revoked")
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_obj = payload.get("sub")
        user_id = user_id_obj if isinstance(user_id_obj, str) else None

        if user_id is None:
            raise credentials_exception

    except (PyJWTError, InvalidIssuerError) as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception

    # =========================================================================
    # NON-BLOCKING USER LOOKUP (uses shared auth_cache module)
    # =========================================================================
    # This uses Redis cache + asyncio.to_thread for DB queries to avoid
    # blocking the event loop under load.
    user_data = await lookup_user_by_id_nonblocking(user_id)

    if user_data is None:
        raise credentials_exception

    iat_ts = parse_token_iat(payload)

    if iat_ts is not None:
        tokens_valid_after_ts = user_data.get("tokens_valid_after_ts")
        if isinstance(tokens_valid_after_ts, float):
            tokens_valid_after_ts = int(tokens_valid_after_ts)
        if isinstance(tokens_valid_after_ts, int) and iat_ts < tokens_valid_after_ts:
            try:
                prometheus_metrics.record_token_rejection("invalidated")
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create a TRANSIENT User object (not session-bound) from the dict
    # This avoids DetachedInstanceError when the original session is closed
    return create_transient_user(user_data)
