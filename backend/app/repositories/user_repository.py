# backend/app/repositories/user_repository.py
"""
User Repository for InstaInstru Platform

Handles all User data access operations, fixing 30+ repository pattern violations.
Provides methods for basic lookups, role checks, and user counts.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from ..database import with_db_retry
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

    def _apply_short_statement_timeout(self) -> None:
        try:
            self.db.execute(text("SET LOCAL statement_timeout = '5s'"))
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)

    # ==========================================
    # Basic Lookups (10+ violations fixed)
    # ==========================================

    def get_by_id(
        self,
        id: Any,
        load_relationships: bool = True,
        *,
        use_retry: bool = True,
        short_timeout: bool = False,
    ) -> Optional[User]:
        """
        Get user by ID.

        Used by: PermissionService, PrivacyService, ConflictChecker, timezone_utils
        Fixes: 10+ violations across services
        """

        def _query() -> Optional[User]:
            try:
                if id is None:
                    return None
                user_id = str(id)
                if short_timeout:
                    self._apply_short_statement_timeout()
                stmt = select(User).where(User.id == user_id)
                if load_relationships:
                    stmt = stmt.options(joinedload(User.roles))
                result = self.db.execute(stmt).scalars().first()
                return cast(Optional[User], result)
            except Exception as e:
                self.logger.error(f"Error getting user by ID {id}: {str(e)}")
                return None

        if not use_retry:
            return _query()
        return with_db_retry("get_user", _query, on_retry=self.db.rollback)

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Used by: AuthService and other authentication flows
        """
        try:
            return cast(
                Optional[User],
                self.db.query(User).filter(User.email == email).first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting user by email {email}: {str(e)}")
            return None

    def list_by_emails(self, emails: Sequence[str], *, case_insensitive: bool = True) -> list[User]:
        """Return users matching the supplied emails."""
        if not emails:
            return []
        try:
            if case_insensitive:
                lowered = [email.lower() for email in emails if email]
                if not lowered:
                    return []
                stmt = select(User).where(func.lower(User.email).in_(lowered))
            else:
                stmt = select(User).where(User.email.in_(list(emails)))
            return cast(list[User], self.db.execute(stmt).scalars().all())
        except Exception as e:
            self.logger.error(f"Error listing users by emails: {str(e)}")
            return []

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
            return cast(
                Optional[User],
                (
                    self.db.query(User)
                    .options(joinedload(User.roles).joinedload(Role.permissions))
                    .filter(User.id == user_id)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting user with roles/permissions {user_id}: {str(e)}")
            return None

    def get_by_email_with_roles_and_permissions(self, email: str) -> Optional[User]:
        """
        Get user by email with eager loaded roles and permissions.

        Used by: non-auth flows that still resolve users by email with eager role data.
        """
        try:
            return cast(
                Optional[User],
                (
                    self.db.query(User)
                    .options(joinedload(User.roles).joinedload(Role.permissions))
                    .filter(User.email == email)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(
                f"Error getting user by email with roles/permissions {email}: {str(e)}"
            )
            return None

    def get_by_id_with_roles_and_permissions(self, user_id: str) -> Optional[User]:
        """
        Get user by ID with eager loaded roles and permissions.

        Used by: auth_cache ID-first token resolution.
        """
        try:
            return cast(
                Optional[User],
                (
                    self.db.query(User)
                    .options(joinedload(User.roles).joinedload(Role.permissions))
                    .filter(User.id == user_id)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(
                f"Error getting user by id with roles/permissions {user_id}: {str(e)}"
            )
            return None

    def get_with_roles(self, user_id: str) -> Optional[User]:
        """
        Get user with roles only (lighter query).

        Used by: PermissionService.get_user_roles()
        Fixes: 2 violations in PermissionService
        """
        try:
            return cast(
                Optional[User],
                (
                    self.db.query(User)
                    .options(joinedload(User.roles))
                    .filter(User.id == user_id)
                    .first()
                ),
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

            return cast(
                Optional[User],
                (
                    self.db.query(User)
                    .join(User.roles)
                    .filter(User.id == user_id, Role.name == RoleName.INSTRUCTOR)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting instructor {user_id}: {str(e)}")
            return None

    def get_active_admin_users(self) -> List[User]:
        """Get all active users with the admin role."""
        from ..core.enums import RoleName

        try:
            return cast(
                List[User],
                (
                    self.db.query(User)
                    .join(User.roles)
                    .filter(Role.name == RoleName.ADMIN, User.is_active.is_(True))
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting active admin users: {str(e)}")
            return []

    def is_instructor(self, user_id: str) -> bool:
        """
        Check if user is an instructor (convenience method).

        Used by: Various services for quick role checks
        """
        return self.get_instructor(user_id) is not None

    def list_instructor_ids(self) -> list[str]:
        """
        Return all instructor user IDs.

        Used by scripts and services that need to iterate instructors without
        bypassing the repository pattern.
        """
        try:
            from ..core.enums import RoleName

            rows = (
                self.db.query(User.id)
                .join(User.roles)
                .filter(Role.name == RoleName.INSTRUCTOR)
                .all()
            )
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Error listing instructor ids: {str(e)}")
            return []

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
            return cast(int, self.db.query(User).count())
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
            return cast(int, self.db.query(User).filter_by(is_active=True).count())
        except Exception as e:
            self.logger.error(f"Error counting active users: {str(e)}")
            return 0

    def get_profile_picture_versions(self, user_ids: Sequence[str]) -> dict[str, Optional[int]]:
        """Return profile_picture_version values for the given user IDs."""

        if not user_ids:
            return {}

        try:
            self._apply_short_statement_timeout()
            stmt = select(User.id, User.profile_picture_version).where(User.id.in_(list(user_ids)))
            rows = self.db.execute(stmt).all()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            self.logger.error(f"Error loading profile picture versions: {str(e)}")
            return {}

    # ==========================================
    # Update Operations
    # ==========================================

    def update_profile(self, user_id: str, **kwargs: object) -> Optional[User]:
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

    def invalidate_all_tokens(self, user_id: str, *, trigger: str | None = None) -> bool:
        """Invalidate all active JWTs for a user via tokens_valid_after and cache eviction."""
        try:
            user = self.get_by_id(user_id, load_relationships=False, use_retry=False)
            if not user:
                return False

            user.tokens_valid_after = datetime.now(timezone.utc)
            self.db.commit()

            if trigger:
                try:
                    from ..monitoring.prometheus_metrics import prometheus_metrics

                    prometheus_metrics.record_token_revocation(trigger)
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)

            # Keep auth cache in sync so tokens_valid_after checks use the new floor immediately.
            from ..core.auth_cache import invalidate_cached_user_by_id_sync

            if not invalidate_cached_user_by_id_sync(user_id, self.db):
                self.logger.error(
                    "[AUTH-CACHE] Failed to invalidate cache after token invalidation for user %s"
                    " — stale tokens_valid_after may be served until cache TTL expires",
                    user_id,
                )
            return True
        except Exception as e:
            self.logger.error(f"Error invalidating all tokens for user {user_id}: {str(e)}")
            self.db.rollback()
            return False

    # ==========================================
    # Bulk Operations
    # ==========================================

    def get_by_ids(self, user_ids: Sequence[str]) -> list[User]:
        """
        Get multiple users by IDs.

        Used for batch operations
        """
        try:
            return cast(
                list[User],
                self.db.query(User).filter(User.id.in_(list(user_ids))).all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting users by IDs: {str(e)}")
            return []

    def get_all_active(self) -> list[User]:
        """
        Get all active users.

        Used for administrative operations
        """
        try:
            return cast(
                list[User],
                self.db.query(User).filter_by(is_active=True).all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting all active users: {str(e)}")
            return []

    def list_students_paginated(
        self,
        *,
        limit: int,
        offset: int = 0,
        since: Optional[datetime] = None,
        only_active: bool = True,
    ) -> list[User]:
        """
        Return paginated student users ordered by creation time.

        Args:
            limit: Maximum rows to return (required).
            offset: Number of rows to skip before returning results.
            since: Optional created_at lower bound (UTC).
            only_active: Restrict to active accounts when True.
        """

        from ..core.enums import RoleName

        try:
            query = self.db.query(User).filter(User.roles.any(Role.name == RoleName.STUDENT))

            if only_active:
                query = query.filter(User.is_active.is_(True))
            if since:
                query = query.filter(User.created_at >= since)

            query = query.order_by(User.created_at.asc(), User.id.asc())
            rows = query.offset(max(offset, 0)).limit(max(limit, 0)).all()
            return cast(list[User], rows)
        except Exception as exc:
            self.logger.error("Error listing student users: %s", exc)
            return []
