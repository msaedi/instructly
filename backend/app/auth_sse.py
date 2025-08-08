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
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .auth import oauth2_scheme_optional
from .core.config import settings
from .database import get_db
from .models.user import User

logger = logging.getLogger(__name__)


async def get_current_user_sse(
    token_header: Optional[str] = Depends(oauth2_scheme_optional),
    token_query: Optional[str] = Query(None, alias="token"),
    token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    db: Session = Depends(get_db),
) -> User:
    """
    Get current user for SSE endpoints.

    Checks for authentication in this order:
    1. Authorization header (for testing/non-browser clients)
    2. Query parameter (for EventSource)
    3. Cookie (for browser-based EventSource with withCredentials)

    Args:
        token_header: Token from Authorization header
        token_query: Token from query parameter
        token_cookie: Token from cookie
        db: Database session

    Returns:
        User object if authenticated

    Raises:
        HTTPException: If no valid authentication found
    """
    # Try to get token from any source
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
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
        user_email: str = payload.get("sub")

        if user_email is None:
            raise credentials_exception

    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception

    # Get user from database
    user = db.query(User).filter(User.email == user_email).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    return user
