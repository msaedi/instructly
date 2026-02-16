# backend/app/services/auth_service.py
"""
Authentication Service for InstaInstru Platform

Handles user registration, authentication, and user retrieval operations.
Follows the service layer pattern to keep business logic out of routes.

FIXED: Added @measure_operation decorators to all public methods
"""

import logging
import re
from typing import Any, Dict, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import DUMMY_HASH_FOR_TIMING_ATTACK, get_password_hash, verify_password
from ..core.enums import RoleName
from ..core.exceptions import NotFoundException, ValidationException
from ..models.instructor import InstructorProfile
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from .base import BaseService, CacheInvalidationProtocol
from .permission_service import PermissionService

logger = logging.getLogger(__name__)
_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class AuthService(BaseService):
    """Service for handling authentication operations."""

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheInvalidationProtocol] = None,
        user_repository: Any | None = None,
        instructor_repository: Any | None = None,
    ) -> None:
        """Initialize authentication service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)

        # Initialize repositories using BaseRepository pattern
        self.user_repository = user_repository or RepositoryFactory.create_base_repository(db, User)
        self.instructor_repository = (
            instructor_repository or RepositoryFactory.create_base_repository(db, InstructorProfile)
        )
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )
        # Avoid instantiating TFA service here to keep auth lightweight and avoid config/key coupling

    @BaseService.measure_operation("register_user")
    def register_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        zip_code: str,
        phone: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Optional[User]:
        """
        Register a new user.

        Returns None (without raising) when the email already exists,
        to prevent email enumeration. The caller must return a generic
        response regardless of the return value.
        """
        self.log_operation("register_user", email=email, role=role)

        # Check if email already exists — return None instead of raising
        existing_user = self.get_user_by_email(email)
        if existing_user:
            self.logger.info("Registration attempt for existing email")
            # Timing normalization — match Argon2id hash cost of real registration
            get_password_hash("dummy_timing_normalization_padding")
            return None

        # Hash the password
        hashed_password = get_password_hash(password)

        # Get timezone from zip code
        from app.core.timezone_service import get_timezone_from_zip

        timezone = get_timezone_from_zip(zip_code) if zip_code else "America/New_York"
        self.logger.info(f"Setting timezone {timezone} for zip code {zip_code}")

        try:
            with self.transaction():
                # Create user without role (will be assigned via RBAC)
                user: User = self.user_repository.create(
                    email=email,
                    hashed_password=hashed_password,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    zip_code=zip_code,
                    timezone=timezone,
                )

                # Assign role using PermissionService
                permission_service = PermissionService(self.db)
                role_name = role or RoleName.STUDENT  # Default to student if not specified
                permission_service.assign_role(user.id, role_name)

                # Refresh user to get roles
                # repo-pattern-ignore: Refresh after create belongs in service layer
                self.db.refresh(user)

                # If registering as instructor, create profile with safe defaults
                if role_name == RoleName.INSTRUCTOR:
                    # Derive initial service area (prefer neighborhood) and city for bio
                    service_area_guess = "Manhattan"
                    city_guess = "New York"  # bio should use city, not borough
                    region_boundary_id: Optional[str] = None
                    try:
                        if zip_code:
                            import anyio

                            from app.repositories.region_boundary_repository import (
                                RegionBoundaryRepository,
                            )
                            from app.services.geocoding.factory import create_geocoding_provider

                            provider = create_geocoding_provider()
                            geocoded = anyio.run(provider.geocode, zip_code)
                            if geocoded:
                                # City for bio if available
                                if getattr(geocoded, "city", None):
                                    city_guess = geocoded.city

                                rb_repo = RegionBoundaryRepository(self.db)
                                region = rb_repo.find_region_by_point(
                                    lat=float(geocoded.latitude),
                                    lng=float(geocoded.longitude),
                                    region_type="nyc",
                                )
                                if region and region.get("region_name"):
                                    service_area_guess = region["region_name"]
                                    ids = rb_repo.find_region_ids_by_partial_names(
                                        [service_area_guess]
                                    )
                                    region_boundary_id = ids.get(service_area_guess)
                                elif getattr(geocoded, "city", None):
                                    # Fallback to city when neighborhood unavailable
                                    service_area_guess = geocoded.city
                                    ids = rb_repo.find_region_ids_by_partial_names(
                                        [service_area_guess]
                                    )
                                    region_boundary_id = region_boundary_id or ids.get(
                                        service_area_guess
                                    )
                        if region_boundary_id is None and service_area_guess:
                            from app.repositories.region_boundary_repository import (
                                RegionBoundaryRepository,
                            )

                            rb_repo = RegionBoundaryRepository(self.db)
                            ids = rb_repo.find_region_ids_by_partial_names([service_area_guess])
                            region_boundary_id = ids.get(service_area_guess)
                    except Exception as _e:
                        self.logger.debug(f"ZIP→neighborhood/city lookup failed: {str(_e)}")

                    # Build a friendly default bio using first name and city
                    first_name = getattr(user, "first_name", "") or ""
                    default_bio = f"{first_name} is a {city_guess}-based instructor."

                    _instructor_profile = self.instructor_repository.create(
                        user_id=user.id,
                        # Provide defaults that satisfy response schema validation
                        bio=default_bio,
                        years_experience=0,
                        min_advance_booking_hours=1,
                        buffer_time_minutes=15,
                    )

                    if region_boundary_id:
                        self.service_area_repository.upsert_area(
                            instructor_id=user.id,
                            neighborhood_id=region_boundary_id,
                            coverage_type="primary",
                            is_active=True,
                        )

                    from .instructor_lifecycle_service import InstructorLifecycleService

                    lifecycle_service = InstructorLifecycleService(self.db)
                    lifecycle_service.record_registration(user.id, is_founding=False)

                self.logger.info(f"Successfully registered user: {email} with role: {role}")
                return user

        except IntegrityError as e:
            self.logger.info(f"Race condition on registration for {email}: {str(e)}")
            # Timing normalization — same as existing-email case
            get_password_hash("dummy_timing_normalization_padding")
            return None
        except Exception as e:
            self.logger.error(f"Error registering user {email}: {str(e)}")
            raise ValidationException(f"Error creating user: {str(e)}")

    @BaseService.measure_operation("fetch_user_for_auth")
    def fetch_user_for_auth(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user data needed for authentication WITHOUT verifying password.

        This method is designed to allow early DB connection release before
        Argon2id verification. Returns user data as a dict so the ORM object
        can be detached from the session.

        PERFORMANCE: Call this, then close DB session, then verify password.
        This reduces DB connection hold time from ~200ms to ~5-20ms.

        Args:
            email: User's email

        Returns:
            Dict with user data if found, None otherwise.
            Dict contains: id, email, hashed_password, account_status, totp_enabled,
                          first_name, last_name, and any other fields needed for login.
        """
        user = self.get_user_by_email(email)
        if not user:
            self.logger.debug(f"User not found for auth: {email}")
            return None

        # Extract all needed fields to memory so ORM object can be detached
        result: Dict[str, Any] = {
            "id": user.id,
            "email": user.email,
            "hashed_password": user.hashed_password,
            "account_status": getattr(user, "account_status", None),
            "totp_enabled": getattr(user, "totp_enabled", False),
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "is_active": getattr(user, "is_active", True),
            # Include user object reference for 2FA check (will be detached)
            "_user_obj": user,
        }

        # Fetch beta claims here (in the same thread-wrapped call) to avoid
        # create_access_token doing its own blocking DB lookup later
        try:
            from app.repositories.beta_repository import BetaAccessRepository

            beta_repo = BetaAccessRepository(self.db)
            beta = beta_repo.get_latest_for_user(user.id)
            if beta:
                result["_beta_claims"] = {
                    "beta_access": True,
                    "beta_role": beta.role,
                    "beta_phase": beta.phase,
                    "beta_invited_by": beta.invited_by_code,
                }
        except Exception as e:
            self.logger.debug(f"Could not fetch beta claims: {e}")

        return result

    @BaseService.measure_operation("authenticate_user")
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user by email and password (synchronous version).

        NOTE: This method holds the DB connection during Argon2id verification.
        For high-throughput scenarios, use fetch_user_for_auth() + verify_password_async()
        with explicit DB release between them.

        Args:
            email: User's email
            password: Plain text password to verify

        Returns:
            User object if authentication successful, None otherwise
        """
        self.logger.info(f"Authentication attempt for user: {email}")

        user = self.get_user_by_email(email)
        if not user:
            self.logger.warning(f"Authentication failed - user not found: {email}")
            return None

        if not verify_password(password, user.hashed_password):
            self.logger.warning(f"Authentication failed - incorrect password: {email}")
            return None

        # Check account status - deactivated users cannot login
        if hasattr(user, "account_status") and user.account_status == "deactivated":
            self.logger.warning(f"Authentication failed - account deactivated: {email}")
            return None

        self.logger.info(f"Successful authentication for user: {email}")
        return user

    @BaseService.measure_operation("authenticate_user_async")
    async def authenticate_user_async(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user by email and password (async version - non-blocking).

        Uses thread pool executor for Argon2id verification to avoid blocking
        the event loop during password hashing. Use this in async route handlers.

        Args:
            email: User's email
            password: Plain text password to verify

        Returns:
            User object if authentication successful, None otherwise
        """
        from ..auth import verify_password_async

        self.logger.info(f"Authentication attempt (async) for user: {email}")

        user = self.get_user_by_email(email)
        if not user:
            self.logger.warning(f"Authentication failed - user not found: {email}")
            # Prevent timing attacks - still do a fake verification with proper Argon2id hash
            await verify_password_async(password, DUMMY_HASH_FOR_TIMING_ATTACK)
            return None

        if not await verify_password_async(password, user.hashed_password):
            self.logger.warning(f"Authentication failed - incorrect password: {email}")
            return None

        # Check account status - deactivated users cannot login
        if hasattr(user, "account_status") and user.account_status == "deactivated":
            self.logger.warning(f"Authentication failed - account deactivated: {email}")
            return None

        self.logger.info(f"Successful authentication (async) for user: {email}")
        return user

    @BaseService.measure_operation("get_user_by_email")
    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by identifier, preferring email and falling back to ULID.

        Args:
            email: User email or ULID identifier

        Returns:
            User object or None if not found
        """
        try:
            identifier = (email or "").strip()
            if not identifier:
                return None

            result = self.user_repository.find_one_by(email=identifier)
            if result is not None:
                return cast(Optional[User], result)

            if _ULID_PATTERN.fullmatch(identifier.upper()):
                return self.get_user_by_id(identifier)
            return None
        except Exception as e:
            self.logger.error(f"Error getting user by email {email}: {str(e)}")
            return None

    @BaseService.measure_operation("get_user_by_id")
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User's ID

        Returns:
            User object or None if not found
        """
        try:
            return self.user_repository.get_by_id(user_id)
        except Exception as e:
            self.logger.error(f"Error getting user by ID {user_id}: {str(e)}")
            return None

    @BaseService.measure_operation("get_current_user")
    def get_current_user(self, identifier: str) -> User:
        """
        Get current user by identifier, raising exception if not found.

        Args:
            identifier: User identifier from JWT token (ULID preferred, email fallback)

        Returns:
            User object

        Raises:
            NotFoundException: If user not found
        """
        user = self.get_user_by_email(identifier)
        if not user:
            self.logger.error(f"Current user not found: {identifier}")
            raise NotFoundException("User not found")

        return user

    @BaseService.measure_operation("release_connection")
    def release_connection(self) -> None:
        """
        Release the database connection to free resources.

        Used to release DB connection before CPU-intensive operations like Argon2id
        to improve throughput under load. The connection will be returned to the pool.
        """
        try:
            self.db.close()
        except Exception:
            self.logger.debug("Failed to close DB session during release_connection", exc_info=True)
