# backend/app/dependencies/permissions.py
"""
Permission dependencies for FastAPI endpoints.

These dependencies provide decorators and functions to check user permissions
before allowing access to protected endpoints.
"""

from typing import Union

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_user
from ..core.enums import PermissionName
from ..database import get_db
from ..models.user import User
from ..services.permission_service import PermissionService


def get_permission_service(db: Session = Depends(get_db)) -> PermissionService:
    """
    Get an instance of the permission service.

    Args:
        db: Database session from dependency injection

    Returns:
        PermissionService instance
    """
    return PermissionService(db)


def require_permission(permission_name: Union[str, PermissionName]):
    """
    Create a dependency that requires a specific permission.

    This returns a dependency function that checks if the current user
    has the specified permission. If not, it raises a 403 Forbidden error.

    Args:
        permission_name: The name of the permission required

    Returns:
        Dependency function that validates the permission

    Example:
        @router.get("/analytics", dependencies=[Depends(require_permission("view_analytics"))])
        async def get_analytics():
            return {"data": "analytics"}
    """

    async def permission_checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ):
        if not permission_service.user_has_permission(current_user.id, permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have required permission: {permission_name}",
            )
        return current_user

    return permission_checker


def require_any_permission(*permission_names: str):
    """
    Create a dependency that requires at least one of the specified permissions.

    Args:
        *permission_names: Variable number of permission names

    Returns:
        Dependency function that validates at least one permission
    """

    async def permission_checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ):
        for permission_name in permission_names:
            if permission_service.user_has_permission(current_user.id, permission_name):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have any of the required permissions: {', '.join(permission_names)}",
        )

    return permission_checker


def require_all_permissions(*permission_names: str):
    """
    Create a dependency that requires all of the specified permissions.

    Args:
        *permission_names: Variable number of permission names

    Returns:
        Dependency function that validates all permissions
    """

    async def permission_checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ):
        missing_permissions = []

        for permission_name in permission_names:
            if not permission_service.user_has_permission(current_user.id, permission_name):
                missing_permissions.append(permission_name)

        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is missing required permissions: {', '.join(missing_permissions)}",
            )

        return current_user

    return permission_checker


def require_role(role_name: str):
    """
    Create a dependency that requires a specific role.

    This is a convenience function for backward compatibility and simple
    role-based checks.

    Args:
        role_name: The name of the role required

    Returns:
        Dependency function that validates the role
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
        permission_service: PermissionService = Depends(get_permission_service),
    ):
        user_roles = permission_service.get_user_roles(current_user.id)

        if role_name not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have required role: {role_name}",
            )

        return current_user

    return role_checker


class PermissionChecker:
    """
    Class-based permission checker for use in route definitions.

    This provides a cleaner syntax for checking permissions in routes.

    Example:
        checker = PermissionChecker()

        @router.get("/analytics")
        async def get_analytics(user: User = Depends(checker.require("view_analytics"))):
            return {"data": "analytics"}
    """

    def __init__(self):
        self._cache = {}

    def require(self, permission_name: str):
        """Get or create a permission checker for the specified permission."""
        if permission_name not in self._cache:
            self._cache[permission_name] = require_permission(permission_name)
        return self._cache[permission_name]

    def require_any(self, *permission_names: str):
        """Get or create a checker that requires any of the permissions."""
        cache_key = f"any:{','.join(sorted(permission_names))}"
        if cache_key not in self._cache:
            self._cache[cache_key] = require_any_permission(*permission_names)
        return self._cache[cache_key]

    def require_all(self, *permission_names: str):
        """Get or create a checker that requires all of the permissions."""
        cache_key = f"all:{','.join(sorted(permission_names))}"
        if cache_key not in self._cache:
            self._cache[cache_key] = require_all_permissions(*permission_names)
        return self._cache[cache_key]


# Global instance for convenience
permission_checker = PermissionChecker()
