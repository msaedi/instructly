# backend/app/services/permission_service.py
"""
Permission service for Role-Based Access Control.

This service handles permission checking for users, including both
role-based permissions and individual permission overrides.
"""

from typing import List, Set, Union

from sqlalchemy.orm import Session, joinedload

from ..core.enums import PermissionName
from ..models.rbac import Permission, Role, UserPermission
from ..models.user import User
from .base import BaseService


class PermissionService(BaseService):
    """
    Service for managing user permissions and access control.

    This service provides methods to check if users have specific permissions,
    either through their roles or through individual permission grants/revokes.
    Includes simple in-memory caching for performance.
    """

    def __init__(self, db: Session):
        """Initialize the service with database session."""
        super().__init__(db)
        self._cache = {}  # Simple in-memory cache for permission checks

    @BaseService.measure_operation("user_has_permission")
    def user_has_permission(self, user_id: int, permission_name: Union[str, PermissionName]) -> bool:
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
        permission_str = permission_name.value if isinstance(permission_name, PermissionName) else permission_name

        # Check cache first
        cache_key = f"{user_id}:{permission_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get user with roles and permissions
        user = (
            self.db.query(User)
            .options(joinedload(User.roles).joinedload(Role.permissions))
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            self._cache[cache_key] = False
            return False

        # Check role-based permissions
        for role in user.roles:
            if any(p.name == permission_str for p in role.permissions):
                self._cache[cache_key] = True
                return True

        # Check individual permission overrides
        user_perm = (
            self.db.query(UserPermission)
            .join(Permission)
            .filter(UserPermission.user_id == user_id, Permission.name == permission_str)
            .first()
        )

        if user_perm:
            self._cache[cache_key] = user_perm.granted
            return user_perm.granted

        self._cache[cache_key] = False
        return False

    @BaseService.measure_operation("get_user_permissions")
    def get_user_permissions(self, user_id: int) -> Set[str]:
        """
        Get all permissions for a user.

        This returns a set of all permission names the user has access to,
        considering both role-based permissions and individual overrides.

        Args:
            user_id: The ID of the user

        Returns:
            Set of permission names
        """
        user = (
            self.db.query(User)
            .options(joinedload(User.roles).joinedload(Role.permissions))
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            return set()

        permissions = set()

        # Collect permissions from roles
        for role in user.roles:
            for permission in role.permissions:
                permissions.add(permission.name)

        # Apply individual permission overrides
        user_perms = self.db.query(UserPermission).join(Permission).filter(UserPermission.user_id == user_id).all()

        for up in user_perms:
            if up.granted:
                permissions.add(up.permission.name)
            else:
                permissions.discard(up.permission.name)

        return permissions

    @BaseService.measure_operation("get_user_roles")
    def get_user_roles(self, user_id: int) -> List[str]:
        """
        Get all role names for a user.

        Args:
            user_id: The ID of the user

        Returns:
            List of role names
        """
        user = self.db.query(User).options(joinedload(User.roles)).filter(User.id == user_id).first()

        if not user:
            return []

        return [role.name for role in user.roles]

    @BaseService.measure_operation("grant_permission")
    def grant_permission(self, user_id: int, permission_name: str) -> bool:
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
        permission = self.db.query(Permission).filter_by(name=permission_name).first()
        if not permission:
            return False

        # Check if override already exists
        user_perm = self.db.query(UserPermission).filter_by(user_id=user_id, permission_id=permission.id).first()

        if user_perm:
            user_perm.granted = True
        else:
            user_perm = UserPermission(user_id=user_id, permission_id=permission.id, granted=True)
            self.db.add(user_perm)

        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("revoke_permission")
    def revoke_permission(self, user_id: int, permission_name: str) -> bool:
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
        permission = self.db.query(Permission).filter_by(name=permission_name).first()
        if not permission:
            return False

        # Check if override already exists
        user_perm = self.db.query(UserPermission).filter_by(user_id=user_id, permission_id=permission.id).first()

        if user_perm:
            user_perm.granted = False
        else:
            user_perm = UserPermission(user_id=user_id, permission_id=permission.id, granted=False)
            self.db.add(user_perm)

        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("assign_role")
    def assign_role(self, user_id: int, role_name: str) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: The ID of the user
            role_name: The name of the role to assign

        Returns:
            True if successful, False if role doesn't exist or user already has it
        """
        # Get user and role
        user = self.db.query(User).filter_by(id=user_id).first()
        role = self.db.query(Role).filter_by(name=role_name).first()

        if not user or not role:
            return False

        # Check if user already has this role
        if role in user.roles:
            return False

        # Assign role
        user.roles.append(role)
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    @BaseService.measure_operation("remove_role")
    def remove_role(self, user_id: int, role_name: str) -> bool:
        """
        Remove a role from a user.

        Args:
            user_id: The ID of the user
            role_name: The name of the role to remove

        Returns:
            True if successful, False if role doesn't exist or user doesn't have it
        """
        # Get user and role
        user = self.db.query(User).filter_by(id=user_id).first()
        role = self.db.query(Role).filter_by(name=role_name).first()

        if not user or not role:
            return False

        # Check if user has this role
        if role not in user.roles:
            return False

        # Remove role
        user.roles.remove(role)
        self.db.commit()

        # Clear cache for this user
        self._clear_user_cache(user_id)

        return True

    def _clear_user_cache(self, user_id: int):
        """Clear all cached entries for a specific user."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self._cache[key]

    def clear_cache(self):
        """Clear the entire permission cache."""
        self._cache.clear()
