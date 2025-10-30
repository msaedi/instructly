# backend/app/api/dependencies/authz.py
"""
Authorization helpers for public API routes.

Provides reusable dependencies for role/scope enforcement and a guard that
ensures public-facing routes default to denying unauthenticated access unless
explicitly marked as open.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional, Sequence, Set, Tuple

from fastapi import Depends, HTTPException, Request, status

from app.api.dependencies.auth import (
    get_current_active_user_optional,
    get_current_user,
)
from app.dependencies.permissions import (
    PermissionDependency,
    get_permission_service,
)
from app.models.user import User
from app.services.permission_service import PermissionService

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
        current_user: Optional[User] = Depends(get_current_active_user_optional),
    ) -> Optional[User]:
        path = request.url.path

        if path in open_path_set or any(path.startswith(prefix) for prefix in open_prefix_tuple):
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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        return current_user

    return guard
