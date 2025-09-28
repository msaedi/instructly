"""Cookie utilities for consistent session handling."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import Response

from app.core.config import settings

_HOSTED_SITE_MODES = {"preview", "prod", "beta", "production", "live"}


def _current_site_mode() -> str:
    try:
        return settings.site_mode
    except Exception:
        return "local"


def _is_hosted() -> bool:
    """Return True when running in a hosted environment (preview/beta/prod)."""
    return _current_site_mode() in _HOSTED_SITE_MODES


def session_cookie_base_name(site_mode: Optional[str] = None) -> str:
    """Return the base session cookie name for the provided site mode."""
    mode = (site_mode or _current_site_mode()).lower()
    if mode == "preview":
        return "sid_preview"
    if mode in {"prod", "beta", "production", "live"}:
        return "sid_prod"
    return "access_token"


def session_cookie_candidates(site_mode: Optional[str] = None) -> List[str]:
    """Return possible cookie names (new + legacy) for the current site mode."""
    mode = (site_mode or _current_site_mode()).lower()
    base = session_cookie_base_name(mode)
    candidates: List[str] = []
    if mode in _HOSTED_SITE_MODES:
        candidates.append(f"__Host-{base}")
    candidates.append(base)
    return candidates


def set_session_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    max_age: Optional[int] = None,
    expires: Optional[datetime | int] = None,
) -> str:
    """Set a session cookie scoped to the API host.

    Hosted environments (preview/beta/prod) use the ``__Host-`` prefix, require ``Secure``
    and ``Path=/`` attributes, and intentionally omit ``Domain`` so the cookie is
    restricted to the API host itself.

    Args:
        response: FastAPI response instance.
        name: Base cookie name (without ``__Host-`` prefix).
        value: Cookie payload.
        max_age: Optional ``Max-Age`` to set.
        expires: Optional ``Expires`` timestamp/value.

    Returns:
        The actual cookie name written to the response headers.
    """

    hosted = _is_hosted()
    cookie_name = f"__Host-{name}" if hosted else name

    cookie_kwargs = {
        "key": cookie_name,
        "value": value,
        "httponly": True,
        "samesite": "lax",
        "secure": hosted,
        "path": "/",
    }

    if max_age is not None:
        cookie_kwargs["max_age"] = max_age
    if expires is not None:
        cookie_kwargs["expires"] = expires

    response.set_cookie(**cookie_kwargs)
    return cookie_name


def expire_parent_domain_cookie(response: Response, legacy_name: str, parent_domain: str) -> None:
    """Expire a legacy parent-domain cookie for gentle migrations."""
    response.set_cookie(
        key=legacy_name,
        value="deleted",
        domain=parent_domain,
        path="/",
        expires=0,
        max_age=0,
        httponly=True,
        secure=_is_hosted(),
        samesite="lax",
    )
