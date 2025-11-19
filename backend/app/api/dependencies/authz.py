# backend/app/api/dependencies/authz.py
"""
Authorization helpers for public API routes.

Provides reusable dependencies for role/scope enforcement and a guard that
ensures public-facing routes default to denying unauthenticated access unless
explicitly marked as open.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
import logging
import os
from typing import Optional, ParamSpec, Sequence, Set, Tuple, TypeVar, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    get_current_active_user_optional,
    get_current_user,
)
from app.auth_session import (
    get_user_from_bearer_header,
    get_user_from_session_cookie,
)
from app.core.config import settings
from app.database import get_db
from app.dependencies.permissions import (
    PermissionDependency,
    get_permission_service,
)
from app.models.user import User
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

OPTIONAL_AUTH_CALLS = {
    get_current_active_user_optional,
}

AUTH_MODULE_PREFIXES = (
    "app.api.dependencies.auth",
    "app.api.dependencies.authz",
    "app.dependencies.permissions",
)

AUTH_REQUIRED_NAMES = {
    "get_current_user",
    "get_current_active_user",
    "get_current_instructor",
    "get_current_student",
    "require_admin",
}


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


_HOSTED_COOKIE_DENY = {"preview", "prod", "production", "live"}
_SAFE_COOKIE_SITE_MODES = {"local", "dev", "development", "int", "test", "ci"}
_SAFE_COOKIE_ENVS = {"dev", "development", "ci", "test"}


def _cookie_auth_allowed(
    site_mode: str,
    *,
    env: Optional[str] = None,
    explicit: Optional[bool] = None,
) -> bool:
    normalized_mode = _norm(site_mode)
    if normalized_mode in _HOSTED_COOKIE_DENY:
        return False

    env_normalized = _norm(env)
    in_allowed_context = (
        normalized_mode in _SAFE_COOKIE_SITE_MODES or env_normalized in _SAFE_COOKIE_ENVS
    )

    if explicit is not None:
        if not explicit:
            return False
        return in_allowed_context

    return in_allowed_context


_OPEN_PHASE_HINTS = {
    "open",
    "open_beta",
    "openbeta",
    "ga",
    "general_availability",
    "public",
}

_PREVIEW_OPEN_PATHS = {"/bookings", "/bookings/"}
_PREVIEW_OPEN_PREFIXES = ("/bookings", "/api/search")
_OPEN_PHASE_OPEN_PREFIXES = ("/bookings", "/api/search")

P = ParamSpec("P")
R = TypeVar("R")


def require_roles(*roles: str) -> PermissionDependency:
    """Ensure the current user possesses at least one of the provided roles."""

    required = {role.lower() for role in roles}

    async def checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ) -> User:
        user_roles = {
            role_name.lower() for role_name in permission_service.get_user_roles(current_user.id)
        }
        if not required.intersection(user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User lacks required role(s): {', '.join(sorted(required))}",
            )
        return current_user

    return checker


def require_scopes(*scopes: str) -> PermissionDependency:
    """Ensure the current user has all specified scopes (permission names)."""

    required = {scope for scope in scopes}

    async def checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ) -> User:
        missing = [
            scope
            for scope in required
            if not permission_service.user_has_permission(current_user.id, scope)
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User missing required scope(s): {', '.join(sorted(missing))}",
            )
        return current_user

    return checker


def requires_roles(
    *roles: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator that annotates the endpoint with required roles."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        setattr(func, "_required_roles", list(roles))

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return await func(*args, **kwargs)

        return cast(Callable[P, Awaitable[R]], wrapper)

    return decorator


def requires_scopes(
    *scopes: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator that annotates the endpoint with required scopes."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        setattr(func, "_required_scopes", list(scopes))

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return await func(*args, **kwargs)

        return cast(Callable[P, Awaitable[R]], wrapper)

    return decorator


def _dependency_requires_auth(callable_obj: object) -> bool:
    if (
        getattr(callable_obj, "__module__", "") == __name__
        and getattr(callable_obj, "__name__", "") == "guard"
    ):
        return False
    if callable_obj in OPTIONAL_AUTH_CALLS:
        return False
    module = getattr(callable_obj, "__module__", "")
    name = getattr(callable_obj, "__name__", "")
    if any(module.startswith(prefix) for prefix in AUTH_MODULE_PREFIXES):
        if module.startswith("app.api.dependencies.auth") and name not in AUTH_REQUIRED_NAMES:
            return False
        return True
    return False


def public_guard(
    open_paths: Optional[Sequence[str]] = None,
    open_prefixes: Optional[Sequence[str]] = None,
) -> Callable[..., Awaitable[Optional[User]]]:
    """Deny-by-default guard for public routes."""

    open_path_set: Set[str] = set(open_paths or [])
    open_prefix_tuple: Tuple[str, ...] = tuple(open_prefixes or [])

    async def guard(
        request: Request,
        db: Session = Depends(get_db),
    ) -> Optional[User]:
        path = request.url.path
        normalized_path = path.rstrip("/") or "/"

        site_mode_raw = (os.getenv("SITE_MODE", "") or "").strip().lower()
        site_mode = site_mode_raw or settings.site_mode
        phase_env = (os.getenv("PHASE", "") or "").strip().lower()
        beta_phase_env = (os.getenv("BETA_PHASE", "") or "").strip().lower()
        phase_hint = phase_env or beta_phase_env

        dynamic_paths: set[str] = set()
        dynamic_prefixes: list[str] = []

        if site_mode == "preview":
            dynamic_paths.update(_PREVIEW_OPEN_PATHS)
            dynamic_prefixes.extend(_PREVIEW_OPEN_PREFIXES)

        if phase_hint and phase_hint in _OPEN_PHASE_HINTS:
            dynamic_prefixes.extend(_OPEN_PHASE_OPEN_PREFIXES)

        effective_path_set = open_path_set.union(dynamic_paths)
        current_user: Optional[User] = getattr(request.state, "current_user", None)
        if current_user is None:
            current_user = get_user_from_bearer_header(request, db)
        if current_user is None:
            current_user = get_user_from_session_cookie(request, db)
        if current_user:
            setattr(request.state, "current_user", current_user)

        if normalized_path in effective_path_set:
            return current_user

        effective_prefixes = open_prefix_tuple + tuple(dynamic_prefixes)

        if any(path.startswith(prefix) for prefix in effective_prefixes):
            return current_user

        route = request.scope.get("route")
        requires_auth = False
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            for dep in dependant.dependencies or []:
                call = getattr(dep, "call", None)
                if call is not None and _dependency_requires_auth(call):
                    requires_auth = True
                    break

        if requires_auth and current_user is None:
            logger.debug(
                "public_guard_missing_user path=%s auth_header=%s site_mode=%s phase=%s",
                path,
                bool(request.headers.get("authorization")),
                site_mode,
                phase_hint,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        return current_user

    return guard
