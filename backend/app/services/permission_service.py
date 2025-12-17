# backend/app/services/permission_service.py
"""
Permission service for Role-Based Access Control.

This service handles permission checking for users, including both
role-based permissions and individual permission overrides.
"""

import asyncio
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Union

from sqlalchemy.orm import Session

from ..core.enums import PermissionName
from ..repositories.factory import RepositoryFactory
from .base import BaseService
from .permission_cache import (
    get_cached_permissions,
    invalidate_cached_permissions,
    set_cached_permissions,
)

if TYPE_CHECKING:
    from ..models.rbac import UserPermission
    from ..repositories.rbac_repository import RBACRepository
    from ..repositories.user_repository import UserRepository


class PermissionService(BaseService):
    """
    Service for managing user permissions and access control.

    This service provides methods to check if users have specific permissions,
    either through their roles or through individual permission grants/revokes.
    Includes simple in-memory caching for performance.
    """

    def __init__(self, db: Session):
        """Initialize the service with database session and repositories."""
        super().__init__(db)
        self._cache: Dict[str, bool] = {}  # Simple in-memory cache for permission checks
        self.user_repository: "UserRepository" = RepositoryFactory.create_user_repository(db)
        self.rbac_repository: "RBACRepository" = RepositoryFactory.create_rbac_repository(db)

    @BaseService.measure_operation("user_has_permission")
    def user_has_permission(
        self, user_id: str, permission_name: Union[str, PermissionName]
    ) -> bool:
        """
        Check if a user has a specific permission.

        This checks both role-based permissions and individual permission overrides.
        Results are cached for performance.

        Args:
            user_id: The ID of the user to check
            permission_name: The name of the permission to check (string or enum)

        Returns:
            True if the user has the permission, False otherwise
        """
        # Convert enum to string if needed
        permission_str = (
            permission_name.value
            if isinstance(permission_name, PermissionName)
            else permission_name
        )

        # Check cache first
        cache_key = f"{user_id}:{permission_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get user with roles and permissions
        user = self.user_repository.get_with_roles_and_permissions(user_id)

        if not user:
            self._cache[cache_key] = False
            return False

        # Check role-based permissions
        for role in user.roles:
            if any(p.name == permission_str for p in role.permissions):
                self._cache[cache_key] = True
                return True

        # Check individual permission overrides
        user_perm: Optional["UserPermission"] = self.rbac_repository.check_user_permission(
            user_id, permission_str
        )

        if user_perm:
            granted = bool(getattr(user_perm, "granted", False))
            self._cache[cache_key] = granted
            return granted

        self._cache[cache_key] = False
        return False

    @BaseService.measure_operation("get_user_permissions")
    def get_user_permissions(self, user_id: str) -> Set[str]:
        """
        Get all permissions for a user.

        This returns a set of all permission names the user has access to,
        considering both role-based permissions and individual overrides.

        Args:
            user_id: The ID of the user

        Returns:
            Set of permission names
        """
        user = self.user_repository.get_with_roles_and_permissions(user_id)

        if not user:
            return set()

        permissions = set()

        # Collect permissions from roles
        for role in user.roles:
            for permission in role.permissions:
                permissions.add(permission.name)

        # Apply individual permission overrides
        user_perms = self.rbac_repository.get_user_permissions(user_id)

        for up in user_perms:
            if up.granted:
                permissions.add(up.permission.name)
            else:
                permissions.discard(up.permission.name)

        return permissions

    @BaseService.measure_operation("get_user_permissions_cached")
    async def get_user_permissions_cached(self, user_id: str) -> Set[str]:
        """
        Get user permissions with Redis caching.

        Checks cache first, falls back to DB query if not cached.
        Use this in async contexts for better performance.

        Args:
            user_id: The ID of the user

        Returns:
            Set of permission names
        """
        # Try cache first
        cached = await get_cached_permissions(user_id)
        if cached is not None:
            return cached

        # Cache miss - query DB in thread pool to avoid blocking event loop
        # This is critical for SSE endpoints with many concurrent connections
        permissions = await asyncio.to_thread(self.get_user_permissions, user_id)

        # Cache for next time
        await set_cached_permissions(user_id, permissions)

        return permissions

    @BaseService.measure_operation("user_has_permission_cached")
    async def user_has_permission_cached(
        self, user_id: str, permission_name: Union[str, PermissionName]
    ) -> bool:
        """
        Check if a user has a specific permission (async with Redis caching).

        Use this in async contexts for better performance.

        Args:
            user_id: The ID of the user to check
            permission_name: The name of the permission to check

        Returns:
            True if the user has the permission, False otherwise
        """
        permission_str = (
            permission_name.value
            if isinstance(permission_name, PermissionName)
            else permission_name
        )

        permissions = await self.get_user_permissions_cached(user_id)
        return permission_str in permissions

    @BaseService.measure_operation("get_user_roles")
    def get_user_roles(self, user_id: str) -> List[str]:
        """
        Get all role names for a user.

        Args:
            user_id: The ID of the user

        Returns:
            List of role names
        """
        user = self.user_repository.get_with_roles(user_id)

        if not user:
            return []

        return [role.name for role in user.roles]

    @BaseService.measure_operation("grant_permission")
    def grant_permission(self, user_id: str, permission_name: str) -> bool:
        """
        Grant a specific permission to a user.

        This creates an individual permission override that grants the permission
        regardless of the user's roles.

        Args:
            user_id: The ID of the user
            permission_name: The name of the permission to grant

        Returns:
            True if successful, False if permission doesn't exist
        """
        # Check if permission exists
        permission = self.rbac_repository.get_permission_by_name(permission_name)
        if not permission:
            return False

        # Check if override already exists
        user_perm = self.rbac_repository.get_user_permission(user_id, permission.id)

        if user_perm:
            user_perm.granted = True
        else:
            user_perm = self.rbac_repository.add_user_permission(
                user_id, permission.id, granted=True
            )

        # repo-pattern-ignore: Transaction commit belongs in service layer
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("revoke_permission")
    def revoke_permission(self, user_id: str, permission_name: str) -> bool:
        """
        Revoke a specific permission from a user.

        This creates an individual permission override that revokes the permission
        even if the user has it through their roles.

        Args:
            user_id: The ID of the user
            permission_name: The name of the permission to revoke

        Returns:
            True if successful, False if permission doesn't exist
        """
        # Check if permission exists
        permission = self.rbac_repository.get_permission_by_name(permission_name)
        if not permission:
            return False

        # Check if override already exists
        user_perm = self.rbac_repository.get_user_permission(user_id, permission.id)

        if user_perm:
            user_perm.granted = False
        else:
            user_perm = self.rbac_repository.add_user_permission(
                user_id, permission.id, granted=False
            )

        # repo-pattern-ignore: Transaction commit belongs in service layer
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("assign_role")
    def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: The ID of the user
            role_name: The name of the role to assign

        Returns:
            True if successful, False if role doesn't exist or user already has it
        """
        # Get user and role
        user = self.rbac_repository.get_user_by_id(user_id)
        role = self.rbac_repository.get_role_by_name(role_name)

        if not user or not role:
            return False

        # Check if user already has this role
        if role in user.roles:
            return False

        # Assign role
        user.roles.append(role)
        # repo-pattern-ignore: Transaction commit belongs in service layer
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("remove_role")
    def remove_role(self, user_id: str, role_name: str) -> bool:
        """
        Remove a role from a user.

        Args:
            user_id: The ID of the user
            role_name: The name of the role to remove

        Returns:
            True if successful, False if role doesn't exist or user doesn't have it
        """
        # Get user and role
        user = self.rbac_repository.get_user_by_id(user_id)
        role = self.rbac_repository.get_role_by_name(role_name)

        if not user or not role:
            return False

        # Check if user has this role
        if role not in user.roles:
            return False

        # Remove role
        user.roles.remove(role)
        # repo-pattern-ignore: Transaction commit belongs in service layer
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    def _clear_user_cache(self, user_id: str) -> None:
        """Clear all cached entries for a specific user (in-memory only)."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self._cache[key]

        # Also invalidate Redis cache (fire-and-forget from sync context)
        try:
            try:
                loop = asyncio.get_running_loop()

                from ..core.config import settings

                if settings.is_testing:
                    return

                task = loop.create_task(invalidate_cached_permissions(user_id))

                def _consume_task_exception(t: asyncio.Task[None]) -> None:
                    if t.cancelled():
                        return
                    t.exception()

                task.add_done_callback(_consume_task_exception)
            except RuntimeError:
                # No running loop - we're in a sync context, use anyio
                import anyio

                anyio.from_thread.run(invalidate_cached_permissions, user_id)
        except Exception:
            # Redis invalidation is best-effort, don't fail the operation
            pass

    async def _clear_user_cache_async(self, user_id: str) -> None:
        """Clear all cached entries for a specific user (both in-memory and Redis)."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self._cache[key]

        # Also invalidate Redis cache
        await invalidate_cached_permissions(user_id)

    def clear_cache(self) -> None:  # no-metrics
        """Clear the entire permission cache."""
        self._cache.clear()
