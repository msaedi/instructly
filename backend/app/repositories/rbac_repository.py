# backend/app/repositories/rbac_repository.py
"""
RBAC Repository for InstaInstru Platform

Handles all Role-Based Access Control data operations including:
- Permission lookups and management
- UserPermission (permission overrides) management
- Role queries
- Complex permission checks

Fixes 20+ violations in PermissionService.
"""

import logging
from typing import List, Optional, cast

from sqlalchemy.orm import Session

from ..models.rbac import Permission, Role, UserPermission
from ..models.user import User

logger = logging.getLogger(__name__)


class RBACRepository:
    """
    Repository for RBAC (Role-Based Access Control) data access.

    Unlike other repositories, this doesn't extend BaseRepository because
    it manages multiple related models (Permission, Role, UserPermission).

    Centralizes all RBAC queries to fix violations in PermissionService.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.logger = logging.getLogger(__name__)

    # ==========================================
    # Permission Operations (4 violations fixed)
    # ==========================================

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        """
        Get a permission by its name.

        Used by: PermissionService.grant_permission(), revoke_permission()
        Fixes: 4 violations in PermissionService
        """
        try:
            result = self.db.query(Permission).filter_by(name=name).first()
            return cast(Optional[Permission], result)
        except Exception as e:
            self.logger.error(f"Error getting permission by name {name}: {str(e)}")
            return None

    def get_all_permissions(self) -> List[Permission]:
        """
        Get all permissions in the system.

        Used for administrative interfaces
        """
        try:
            return cast(List[Permission], self.db.query(Permission).all())
        except Exception as e:
            self.logger.error(f"Error getting all permissions: {str(e)}")
            return []

    # ==========================================
    # UserPermission Operations (6+ violations fixed)
    # ==========================================

    def get_user_permission(self, user_id: str, permission_id: str) -> Optional[UserPermission]:
        """
        Get a specific user permission override.

        Used by: PermissionService.grant_permission(), revoke_permission()
        Fixes: 2 violations in PermissionService
        """
        try:
            result = (
                self.db.query(UserPermission)
                .filter_by(user_id=user_id, permission_id=permission_id)
                .first()
            )
            return cast(Optional[UserPermission], result)
        except Exception as e:
            self.logger.error(
                f"Error getting user permission for user {user_id}, permission {permission_id}: {str(e)}"
            )
            return None

    def check_user_permission(self, user_id: str, permission_name: str) -> Optional[UserPermission]:
        """
        Check if user has a specific permission override.

        Used by: PermissionService.user_has_permission()
        Fixes: 2 violations in PermissionService

        Returns None if no override exists (meaning use role-based permissions)
        """
        try:
            result = (
                self.db.query(UserPermission)
                .join(Permission)
                .filter(UserPermission.user_id == user_id, Permission.name == permission_name)
                .first()
            )
            return cast(Optional[UserPermission], result)
        except Exception as e:
            self.logger.error(
                f"Error checking user permission for user {user_id}, permission {permission_name}: {str(e)}"
            )
            return None

    def get_user_permissions(self, user_id: str) -> List[UserPermission]:
        """
        Get all permission overrides for a user.

        Used by: PermissionService.get_user_permissions()
        Fixes: 1 violation in PermissionService
        """
        try:
            return cast(
                List[UserPermission],
                (
                    self.db.query(UserPermission)
                    .join(Permission)
                    .filter(UserPermission.user_id == user_id)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting user permissions for user {user_id}: {str(e)}")
            return []

    def add_user_permission(
        self, user_id: str, permission_id: str, granted: bool = True
    ) -> UserPermission:
        """
        Add or update a user permission override.

        Used by: PermissionService.grant_permission(), revoke_permission()
        Fixes: 2 violations in PermissionService (self.db.add)

        Note: Does NOT commit - service layer controls transaction
        """
        try:
            user_perm = UserPermission(
                user_id=user_id, permission_id=permission_id, granted=granted
            )
            self.db.add(user_perm)
            return user_perm
        except Exception as e:
            self.logger.error(f"Error adding user permission: {str(e)}")
            raise

    # ==========================================
    # Role Operations (2+ violations fixed)
    # ==========================================

    def get_role_by_name(self, name: str) -> Optional[Role]:
        """
        Get a role by its name.

        Used by: PermissionService.assign_role(), remove_role()
        Fixes: 4 violations in PermissionService
        """
        try:
            result = self.db.query(Role).filter_by(name=name).first()
            return cast(Optional[Role], result)
        except Exception as e:
            self.logger.error(f"Error getting role by name {name}: {str(e)}")
            return None

    def get_all_roles(self) -> List[Role]:
        """
        Get all roles in the system.

        Used for administrative interfaces
        """
        try:
            return cast(List[Role], self.db.query(Role).all())
        except Exception as e:
            self.logger.error(f"Error getting all roles: {str(e)}")
            return []

    def get_role_permissions(self, role_name: str) -> List[Permission]:
        """
        Get all permissions for a specific role.

        Used for role management interfaces
        """
        try:
            role = self.get_role_by_name(role_name)
            if role:
                return cast(List[Permission], role.permissions)
            return []
        except Exception as e:
            self.logger.error(f"Error getting role permissions for {role_name}: {str(e)}")
            return []

    # ==========================================
    # User-Role Operations
    # ==========================================

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID for role operations.

        Used by: PermissionService.assign_role(), remove_role()
        Fixes: 4 violations in PermissionService

        Note: This could use UserRepository, but included here to keep
        PermissionService simple with one repository dependency
        """
        try:
            result = self.db.query(User).filter_by(id=user_id).first()
            return cast(Optional[User], result)
        except Exception as e:
            self.logger.error(f"Error getting user by ID {user_id}: {str(e)}")
            return None

    # ==========================================
    # Utility Methods
    # ==========================================

    def permission_exists(self, permission_name: str) -> bool:
        """
        Check if a permission exists.

        Convenience method for validation
        """
        return self.get_permission_by_name(permission_name) is not None

    def role_exists(self, role_name: str) -> bool:
        """
        Check if a role exists.

        Convenience method for validation
        """
        return self.get_role_by_name(role_name) is not None
