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
    """Return the configured base session cookie name."""
    mode = (site_mode or _current_site_mode()).lower()
    configured = getattr(settings, "session_cookie_name", "") or "access_token"
    if configured == "access_token":
        if mode == "preview":
            return "sid_preview"
        if mode in {"prod", "beta", "production", "live"}:
            return "sid_prod"
    return configured


def session_cookie_candidates(site_mode: Optional[str] = None) -> List[str]:
    """Return possible cookie names (new + legacy) for the current site mode."""
    mode = (site_mode or _current_site_mode()).lower()
    base = session_cookie_base_name(mode)
    candidates: List[str] = []
    if base:
        candidates.append(base)
    legacy = "access_token"
    if mode == "preview":
        legacy = "sid_preview"
    elif mode in {"prod", "beta", "production", "live"}:
        legacy = "sid_prod"
    if legacy not in candidates:
        candidates.append(legacy)
    return candidates


def set_session_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    max_age: Optional[int] = None,
    expires: Optional[datetime | int] = None,
    domain: Optional[str] = None,
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

    cookie_name = name or session_cookie_base_name()

    cookie_kwargs = {
        "key": cookie_name,
        "value": value,
        "httponly": True,
        "samesite": (settings.session_cookie_samesite or "lax"),
        "secure": bool(settings.session_cookie_secure),
        "path": "/",
    }

    cookie_domain = domain
    if cookie_domain is None:
        cookie_domain = settings.session_cookie_domain

    if cookie_name.startswith("__Host-"):
        cookie_domain = None

    if cookie_domain:
        cookie_kwargs["domain"] = cookie_domain

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
