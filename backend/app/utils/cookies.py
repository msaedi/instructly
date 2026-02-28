"""Cookie utilities for consistent session handling."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import Response

from app.core.config import settings


def _current_site_mode() -> str:
    try:
        return settings.site_mode
    except Exception:
        return "local"


def session_cookie_base_name(site_mode: Optional[str] = None) -> str:
    """Return the environment-aware session cookie name.

    Preview → ``sid_preview``, Production → ``sid``, Local → whatever is configured.
    """
    mode = (site_mode or _current_site_mode()).lower()
    configured = getattr(settings, "session_cookie_name", "") or "sid"
    # Environment-aware names when using the default cookie name
    if configured in {"sid", "access_token"}:
        if mode == "preview":
            return "sid_preview"
        if mode in {"prod", "beta", "production", "live"}:
            return "sid"
    return configured


def session_cookie_candidates(site_mode: Optional[str] = None) -> List[str]:
    """Return possible cookie names for the current site mode."""
    mode = (site_mode or _current_site_mode()).lower()
    base = session_cookie_base_name(mode)
    if base:
        return [base]
    return []


def refresh_cookie_base_name(site_mode: Optional[str] = None) -> str:
    """Return the environment-aware refresh cookie name."""
    mode = (site_mode or _current_site_mode()).lower()
    if mode == "preview":
        return "rid_preview"
    return "rid"


def _effective_cookie_domain(origin: str | None = None) -> str | None:
    """Determine cookie domain, dynamically handling beta-local subdomain access.

    Hosted/production modes already have ``session_cookie_domain`` set to
    ``.instainstru.com`` by ``_derive_cookie_policy``.  In local mode the
    setting is ``None`` — fine for ``localhost`` but breaks cross-subdomain
    access when the request originates from ``beta-local.instainstru.com``.
    This helper detects that case via the *Origin* header and returns
    ``.instainstru.com`` so the cookie is shared between frontend and API
    subdomains.
    """
    if settings.session_cookie_domain:
        return settings.session_cookie_domain
    if origin:
        from urllib.parse import urlparse

        host = (urlparse(origin).hostname or "").lower()
        if host == "instainstru.com" or host.endswith(".instainstru.com"):
            return ".instainstru.com"
    return None


def set_session_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    max_age: Optional[int] = None,
    expires: Optional[datetime | int] = None,
    domain: Optional[str] = None,
) -> str:
    """Set a session cookie shared across frontend and API origins.

    Hosted environments use a parent-domain cookie (``Domain=.instainstru.com``)
    so the session works across the frontend proxy and the direct API host.

    Args:
        response: FastAPI response instance.
        name: Cookie name (e.g. ``sid_preview``, ``sid``).
        value: Cookie payload.
        max_age: Optional ``Max-Age`` to set.
        expires: Optional ``Expires`` timestamp/value.
        domain: Explicit domain override; falls back to ``settings.session_cookie_domain``.

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


def set_refresh_cookie(
    response: Response,
    value: str,
    *,
    max_age: Optional[int] = None,
    expires: Optional[datetime | int] = None,
    domain: Optional[str] = None,
) -> str:
    """Set the refresh token cookie scoped to the refresh endpoint path."""

    cookie_name = refresh_cookie_base_name()

    cookie_kwargs = {
        "key": cookie_name,
        "value": value,
        "httponly": True,
        "samesite": (settings.session_cookie_samesite or "lax"),
        "secure": bool(settings.session_cookie_secure),
        "path": "/api/v1/auth/refresh",
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


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    *,
    origin: str | None = None,
) -> None:
    """Set both access and refresh cookies on a response.

    Shared helper used by all login paths (login, login-with-session, 2FA verify).

    Args:
        origin: The request ``Origin`` header.  Passed to
            :func:`_effective_cookie_domain` so the cookie domain is set
            correctly when the request comes from a ``*.instainstru.com``
            subdomain in local mode.
    """
    domain = _effective_cookie_domain(origin)
    set_session_cookie(
        response,
        session_cookie_base_name(settings.site_mode),
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        domain=domain,
    )
    set_refresh_cookie(
        response,
        refresh_token,
        max_age=settings.refresh_token_lifetime_days * 24 * 60 * 60,
        domain=domain,
    )


def delete_refresh_cookie(response: Response, *, domain: Optional[str] = None) -> str:
    """Delete the refresh token cookie using its scoped refresh path."""

    cookie_name = refresh_cookie_base_name()
    cookie_domain = domain if domain is not None else settings.session_cookie_domain
    if cookie_name.startswith("__Host-"):
        cookie_domain = None

    response.delete_cookie(
        key=cookie_name,
        path="/api/v1/auth/refresh",
        domain=cookie_domain,
        secure=bool(settings.session_cookie_secure),
        httponly=True,
        samesite=(settings.session_cookie_samesite or "lax"),
    )
    return cookie_name
