"""Helpers for resolving authenticated users from cookies or Authorization headers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.repositories.user_repository import UserRepository
from app.utils.cookies import session_cookie_candidates

if TYPE_CHECKING:
    from app.models.user import User


def _lookup_active_user(email: str, db: Session) -> Optional["User"]:
    if not email:
        return None
    user = UserRepository(db).get_by_email(email)
    if user and getattr(user, "is_active", False):
        return user
    return None


def _decode_email(token: str) -> Optional[str]:
    from jwt import PyJWTError

    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        return None
    except Exception:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def get_user_from_session_cookie(request: Request, db: Session) -> Optional[User]:
    """Return the authenticated user resolved from session cookies, if present."""

    cookies = getattr(request, "cookies", {}) or {}
    for cookie_name in session_cookie_candidates():
        token = cookies.get(cookie_name)
        if not token:
            continue
        email = _decode_email(token)
        if email:
            user = _lookup_active_user(email, db)
            if user:
                return user
    return None


def get_user_from_bearer_header(request: Request, db: Session) -> Optional[User]:
    """Return the authenticated user resolved from a Bearer Authorization header."""

    auth_header = (request.headers.get("authorization") or "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    email = _decode_email(token)
    if not email:
        return None
    return _lookup_active_user(email, db)
