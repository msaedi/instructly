# backend/app/models/user.py
"""
User model for InstaInstru platform.

This module defines the User model which serves as the base for both
instructors and students in the system. It includes authentication fields,
role management, and relationships to various user-specific data.

Classes:
    UserRole: Enum defining the possible user roles
    User: Main user model for authentication and role management
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base
from .favorite import UserFavorite

if TYPE_CHECKING:
    from .address import InstructorServiceArea

logger = logging.getLogger(__name__)


# UserRole enum removed - now using RBAC system with roles table


class User(Base):
    """
    Main user model for authentication and profile management.

    This model handles user authentication, role assignment, and serves as
    the central point for user-related relationships. Both instructors and
    students are represented by this model, differentiated by the role field.

    Attributes:
        id: Primary key
        email: Unique email address used for login
        hashed_password: Bcrypt hashed password
        first_name: User's first name
        last_name: User's last name
        phone: User's phone number (optional)
        zip_code: User's zip code (required)
        timezone: User's timezone (defaults to America/New_York)
        is_active: Whether the user account is active
        account_status: Lifecycle status (active, suspended, deactivated)
        created_at: Account creation timestamp
        updated_at: Last update timestamp

    Relationships:
        roles: Many-to-many with Role through user_roles table
        instructor_profile: One-to-one with InstructorProfile (instructors only)
        blackout_dates: One-to-many with BlackoutDate (instructors only)
        password_reset_tokens: One-to-many with PasswordResetToken

    Note:
        Availability data is stored in availability_days table (bitmap format).
        See app.models.availability_day for the AvailabilityDay model.

    Note:
        The old recurring_availability relationship has been removed as part
        of the system refactoring to use only date-specific availability.
    """

    __tablename__ = "users"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=True)
    zip_code = Column(String(10), nullable=False)
    is_active = Column(Boolean, default=True)
    # Role removed - now using RBAC system with user_roles table
    # Account lifecycle status - active, suspended, or deactivated
    # Check constraint in migration ensures valid values
    account_status = Column(String(20), nullable=False, default="active")
    timezone = Column(String(50), nullable=False, default="America/New_York")
    # Profile picture metadata (versioned, private storage)
    profile_picture_key = Column(String(255), nullable=True)
    profile_picture_uploaded_at = Column(DateTime(timezone=True), nullable=True)
    profile_picture_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 2FA fields
    totp_secret = Column(String(255), nullable=True)  # Encrypted at rest via service layer
    totp_enabled = Column(Boolean, nullable=False, default=False)
    totp_verified_at = Column(DateTime(timezone=True), nullable=True)
    # Use generic JSON in the model for cross-dialect compatibility (SQLite in tests)
    # The migration creates JSONB on Postgres for better operator support
    backup_codes = Column(JSON, nullable=True)
    two_factor_setup_at = Column(DateTime(timezone=True), nullable=True)
    two_factor_last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # RBAC relationship
    roles = relationship(
        "Role", secondary="user_roles", back_populates="users", lazy="selectin"
    )  # Eager load roles

    instructor_profile = relationship("InstructorProfile", back_populates="user", uselist=False)

    preferred_places = relationship(
        "InstructorPreferredPlace",
        back_populates="instructor",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InstructorPreferredPlace.position",
    )

    # Availability relationships
    # Note: Availability data is stored in availability_days table (bitmap format)
    blackout_dates = relationship(
        "BlackoutDate", back_populates="instructor", cascade="all, delete-orphan"
    )

    # Password reset relationships
    password_reset_tokens = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )

    # Payment relationships
    stripe_customer = relationship(
        "StripeCustomer", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    payment_methods = relationship(
        "PaymentMethod", back_populates="user", cascade="all, delete-orphan"
    )
    platform_credits = relationship(
        "PlatformCredit", back_populates="user", cascade="all, delete-orphan"
    )

    # Referral relationships
    referral_codes = relationship(
        "ReferralCode",
        back_populates="referrer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    referral_rewards_earned = relationship(
        "ReferralReward",
        back_populates="referrer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ReferralReward.referrer_user_id",
    )
    referral_rewards_received = relationship(
        "ReferralReward",
        back_populates="referred_user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ReferralReward.referred_user_id",
    )
    referral_attributions_received = relationship(
        "ReferralAttribution",
        back_populates="referred_user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ReferralAttribution.referred_user_id",
    )
    wallet_transactions = relationship(
        "WalletTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    referral_limit = relationship(
        "ReferralLimit",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    service_areas: Mapped[list["InstructorServiceArea"]] = relationship(
        "InstructorServiceArea",
        back_populates="instructor",
        lazy="select",  # Changed from selectin - only load when explicitly accessed
        cascade="all, delete-orphan",
    )

    # Favorites relationships
    # Favorites where this user is the student (instructors they've favorited)
    student_favorites = relationship(
        "UserFavorite",
        foreign_keys=[UserFavorite.student_id],
        back_populates="student",
        cascade="all, delete-orphan",
    )

    # Favorites where this user is the instructor (students who favorited them)
    instructor_favorites = relationship(
        "UserFavorite",
        foreign_keys=[UserFavorite.instructor_id],
        back_populates="instructor",
        cascade="all, delete-orphan",
    )

    # Search history for personalization
    # Specify foreign_keys to resolve ambiguity with converted_to_user_id
    search_history = relationship(
        "SearchHistory",
        foreign_keys="SearchHistory.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Conversation state relationships (archive/trash)
    conversation_states = relationship(
        "ConversationUserState",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Initialize a new user."""
        super().__init__(**kwargs)
        # Only log actual new user creations (with role), not transient/cache reconstructions
        role = kwargs.get("role")
        if role:
            logger.info(f"Creating new {role} user with email: {kwargs.get('email', 'unknown')}")

    def __repr__(self) -> str:
        """String representation of the User object."""
        role_names = [role.name for role in self.roles] if self.roles else ["no roles"]
        return f"<User {self.email} ({', '.join(role_names)})>"

    @property
    def role(self) -> Optional[str]:
        """Get primary role name for backward compatibility."""
        return self.roles[0].name if self.roles else None

    @property
    def is_instructor(self) -> bool:
        """Check if user has instructor role.

        For transient users (created from cache), returns the cached value.
        """
        # Check for cached value first (for transient users from auth cache)
        cached = getattr(self, "_cached_is_instructor", None)
        if cached is not None:
            return bool(cached)

        from app.core.enums import RoleName

        roles = cast(list[Any], getattr(self, "roles", []) or [])
        for role in roles:
            role_name = cast(str, getattr(role, "name", ""))
            if role_name == RoleName.INSTRUCTOR:
                return True
        return False

    @property
    def is_student(self) -> bool:
        """Check if user has student role.

        For transient users (created from cache), returns the cached value.
        """
        # Check for cached value first (for transient users from auth cache)
        cached = getattr(self, "_cached_is_student", None)
        if cached is not None:
            return bool(cached)

        from app.core.enums import RoleName

        roles = cast(list[Any], getattr(self, "roles", []) or [])
        for role in roles:
            role_name = cast(str, getattr(role, "name", ""))
            if role_name == RoleName.STUDENT:
                return True
        return False

    @property
    def is_admin(self) -> bool:
        """Check if the user has admin role.

        For transient users (created from cache), returns the cached value.
        """
        # Check for cached value first (for transient users from auth cache)
        cached = getattr(self, "_cached_is_admin", None)
        if cached is not None:
            return bool(cached)

        from app.core.enums import RoleName

        roles = cast(list[Any], getattr(self, "roles", []) or [])
        for role in roles:
            role_name = cast(str, getattr(role, "name", ""))
            if role_name == RoleName.ADMIN:
                return True
        return False

    # Account status helper properties
    @property
    def is_account_active(self) -> bool:
        """Check if the account is in active status."""
        status = cast(str, getattr(self, "account_status", ""))
        return status == "active"

    @property
    def is_suspended(self) -> bool:
        """Check if the account is suspended."""
        status = cast(str, getattr(self, "account_status", ""))
        return status == "suspended"

    @property
    def is_deactivated(self) -> bool:
        """Check if the account is deactivated."""
        status = cast(str, getattr(self, "account_status", ""))
        return status == "deactivated"

    @property
    def can_receive_bookings(self) -> bool:
        """Check if the user can receive bookings (active instructors only)."""
        return self.is_account_active and self.is_instructor

    @property
    def can_login(self) -> bool:
        """Check if the user can login (active or suspended, but not deactivated)."""
        status = cast(str, getattr(self, "account_status", ""))
        return status in {"active", "suspended"}

    @property
    def has_profile_picture(self) -> bool:
        """Whether the user has an uploaded profile picture."""
        return bool(self.profile_picture_key) and (self.profile_picture_version or 0) > 0

    def can_change_status_to(self, new_status: str) -> bool:
        """
        Check if the user can change to the specified account status.

        Args:
            new_status: The desired new status ('active', 'suspended', or 'deactivated')

        Returns:
            bool: True if the status change is allowed, False otherwise

        Rules:
            - Students cannot change status (always active)
            - Instructors can change between any valid status
            - new_status must be one of the allowed values
        """
        # Validate the new status is allowed
        if new_status not in ["active", "suspended", "deactivated"]:
            return False

        # Students are always active and cannot change status
        if self.is_student:
            return False

        # Instructors can change to any valid status
        return True
