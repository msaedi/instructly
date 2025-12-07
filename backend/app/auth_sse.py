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
"""

import logging
from typing import Optional, cast

from fastapi import Depends, HTTPException, Query, Request, status
from jwt import InvalidIssuerError, PyJWTError

from .auth import decode_access_token, oauth2_scheme_optional
from .core.config import settings
from .database import SessionLocal
from .models.user import User
from .utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)


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
    # MANUAL DB SESSION MANAGEMENT
    # We create and close the session explicitly to prevent holding connections
    # in "idle in transaction" state during long-running SSE streams.
    # =========================================================================
    db = SessionLocal()
    try:
        # Get user from database
        user = cast(Optional[User], db.query(User).filter(User.email == user_email).first())

        if user is None:
            raise credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )

        # Eagerly load user attributes we need before closing session
        # Access attributes to ensure they're loaded into the object
        _ = user.id
        _ = user.email
        _ = user.is_active

        return user
    finally:
        db.close()
        logger.debug("[SSE-AUTH] DB session closed after user lookup")
