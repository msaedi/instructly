# backend/app/repositories/user_repository.py
"""
User Repository for InstaInstru Platform

Handles all User data access operations, fixing 30+ repository pattern violations.
Provides methods for basic lookups, role checks, and user counts.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from ..models.rbac import Role
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Repository for User data access.

    Centralizes all user queries to fix violations in:
    - PermissionService (user lookups with roles)
    - PrivacyService (user counts and lookups)
    - ConflictChecker (instructor validation)
    - timezone_utils (user lookups)
    """

    def __init__(self, db: Session):
        """Initialize with User model."""
        super().__init__(db, User)
        self.logger = logging.getLogger(__name__)

    # ==========================================
    # Basic Lookups (10+ violations fixed)
    # ==========================================

    def get_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Used by: PermissionService, PrivacyService, ConflictChecker, timezone_utils
        Fixes: 10+ violations across services
        """
        try:
            return self.db.query(User).filter(User.id == user_id).first()
        except Exception as e:
            self.logger.error(f"Error getting user by ID {user_id}: {str(e)}")
            return None

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Used by: AuthService and other authentication flows
        """
        try:
            return self.db.query(User).filter(User.email == email).first()
        except Exception as e:
            self.logger.error(f"Error getting user by email {email}: {str(e)}")
            return None

    # ==========================================
    # With Relationships (6+ violations fixed)
    # ==========================================

    def get_with_roles_and_permissions(self, user_id: str) -> Optional[User]:
        """
        Get user with eager loaded roles and permissions.

        Used by: PermissionService.user_has_permission()
        Fixes: 6 violations in PermissionService
        """
        try:
            return (
                self.db.query(User)
                .options(joinedload(User.roles).joinedload(Role.permissions))
                .filter(User.id == user_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting user with roles/permissions {user_id}: {str(e)}")
            return None

    def get_with_roles(self, user_id: str) -> Optional[User]:
        """
        Get user with roles only (lighter query).

        Used by: PermissionService.get_user_roles()
        Fixes: 2 violations in PermissionService
        """
        try:
            return (
                self.db.query(User)
                .options(joinedload(User.roles))
                .filter(User.id == user_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting user with roles {user_id}: {str(e)}")
            return None

    # ==========================================
    # Role-Specific Queries (2 violations fixed)
    # ==========================================

    def get_instructor(self, user_id: str) -> Optional[User]:
        """
        Get user if they have instructor role.

        Used by: ConflictChecker for instructor validation
        Fixes: 2 violations in ConflictChecker

        Note: Uses join with roles table since User has many-to-many with Role
        """
        try:
            from ..core.enums import RoleName

            return (
                self.db.query(User)
                .join(User.roles)
                .filter(User.id == user_id, Role.name == RoleName.INSTRUCTOR)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting instructor {user_id}: {str(e)}")
            return None

    def is_instructor(self, user_id: str) -> bool:
        """
        Check if user is an instructor (convenience method).

        Used by: Various services for quick role checks
        """
        return self.get_instructor(user_id) is not None

    # ==========================================
    # Count Operations (2+ violations fixed)
    # ==========================================

    def count_all(self) -> int:
        """
        Get total user count.

        Used by: PrivacyService.get_privacy_stats()
        Fixes: 1 violation in PrivacyService
        """
        try:
            return self.db.query(User).count()
        except Exception as e:
            self.logger.error(f"Error counting all users: {str(e)}")
            return 0

    def count_active(self) -> int:
        """
        Get active user count.

        Used by: PrivacyService.get_privacy_stats()
        Fixes: 1 violation in PrivacyService
        """
        try:
            return self.db.query(User).filter_by(is_active=True).count()
        except Exception as e:
            self.logger.error(f"Error counting active users: {str(e)}")
            return 0

    # ==========================================
    # Update Operations
    # ==========================================

    def update_profile(self, user_id: str, **kwargs) -> Optional[User]:
        """
        Update user profile fields.

        Used by: auth.py update_current_user endpoint
        Fixes: Direct database access in routes

        Args:
            user_id: User ID to update
            **kwargs: Fields to update (first_name, last_name, phone, zip_code, timezone)

        Returns:
            Updated user or None if not found
        """
        try:
            user = self.get_by_id(user_id)
            if not user:
                return None

            # Update provided fields
            for field, value in kwargs.items():
                if hasattr(user, field) and value is not None:
                    setattr(user, field, value)

            self.db.commit()
            self.db.refresh(user)
            return user

        except Exception as e:
            self.logger.error(f"Error updating user profile {user_id}: {str(e)}")
            self.db.rollback()
            return None

    def clear_profile_picture(self, user_id: str) -> bool:
        """Clear profile picture metadata for a user."""
        try:
            user = self.get_by_id(user_id)
            if not user:
                return False
            user.profile_picture_key = None
            user.profile_picture_uploaded_at = None
            user.profile_picture_version = 0
            self.db.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error clearing user profile picture {user_id}: {str(e)}")
            self.db.rollback()
            return False

    def update_password(self, user_id: str, hashed_password: str) -> bool:
        """
        Update only the user's hashed password.

        Args:
            user_id: User ID to update
            hashed_password: New hashed password

        Returns:
            True if updated, False otherwise
        """
        try:
            user = self.get_by_id(user_id)
            if not user:
                return False
            user.hashed_password = hashed_password
            self.db.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating user password {user_id}: {str(e)}")
            self.db.rollback()
            return False

    # ==========================================
    # Bulk Operations
    # ==========================================

    def get_by_ids(self, user_ids: list[int]) -> list[User]:
        """
        Get multiple users by IDs.

        Used for batch operations
        """
        try:
            return self.db.query(User).filter(User.id.in_(user_ids)).all()
        except Exception as e:
            self.logger.error(f"Error getting users by IDs: {str(e)}")
            return []

    def get_all_active(self) -> list[User]:
        """
        Get all active users.

        Used for administrative operations
        """
        try:
            return self.db.query(User).filter_by(is_active=True).all()
        except Exception as e:
            self.logger.error(f"Error getting all active users: {str(e)}")
            return []
