"""Helpers for resolving authenticated users from cookies or Authorization headers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth import decode_access_token, is_access_token_payload
from app.monitoring.prometheus_metrics import prometheus_metrics
from app.repositories.user_repository import UserRepository
from app.services.token_blacklist_service import TokenBlacklistService
from app.utils.cookies import session_cookie_candidates
from app.utils.token_utils import parse_token_iat

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)


def _lookup_active_user(
    user_identifier: str,
    db: Session,
    token_iat: int | None = None,
) -> Optional["User"]:
    if not user_identifier:
        return None
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_identifier, use_retry=False)
    if not user or not getattr(user, "is_active", False):
        return None

    # Token invalidation check by user-wide floor timestamp.
    if token_iat is not None:
        tokens_valid_after = getattr(user, "tokens_valid_after", None)
        if tokens_valid_after and token_iat < int(tokens_valid_after.timestamp()):
            try:
                prometheus_metrics.record_token_rejection("invalidated")
            except Exception:
                logger.debug("Failed to record invalidated token rejection metric", exc_info=True)
            return None

    return user


def _decode_token_claims(token: str) -> tuple[str, int | None] | None:
    """Decode JWT claims and enforce jti + revocation checks."""
    from jwt import PyJWTError

    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        return None
    except Exception:
        logger.debug("Token decode failed in session auth helper", exc_info=True)
        return None

    if not is_access_token_payload(payload):
        return None

    jti_obj = payload.get("jti")
    jti = jti_obj if isinstance(jti_obj, str) else None
    if not jti:
        try:
            prometheus_metrics.record_token_rejection("format_outdated")
        except Exception:
            logger.debug("Failed to record format_outdated token rejection metric", exc_info=True)
        return None

    try:
        if TokenBlacklistService().is_revoked_sync(jti):
            try:
                prometheus_metrics.record_token_rejection("revoked")
            except Exception:
                logger.debug("Failed to record revoked token rejection metric", exc_info=True)
            return None
    except Exception:
        logger.warning("Blacklist sync check failed in session auth helper", exc_info=True)
        # Defensive fail-closed fallback if sync bridge errors unexpectedly.
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None

    iat_ts = parse_token_iat(payload)

    return subject, iat_ts


def _decode_subject(token: str) -> Optional[str]:
    claims = _decode_token_claims(token)
    if claims is None:
        return None
    return claims[0]


def get_user_from_session_cookie(request: Request, db: Session) -> Optional[User]:
    """Return the authenticated user resolved from session cookies, if present."""

    cookies = getattr(request, "cookies", {}) or {}
    for cookie_name in session_cookie_candidates():
        token = cookies.get(cookie_name)
        if not token:
            continue
        claims = _decode_token_claims(token)
        if claims:
            user_identifier, iat_ts = claims
            user = _lookup_active_user(user_identifier, db, token_iat=iat_ts)
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
    claims = _decode_token_claims(token)
    if not claims:
        return None
    user_identifier, iat_ts = claims
    return _lookup_active_user(user_identifier, db, token_iat=iat_ts)
