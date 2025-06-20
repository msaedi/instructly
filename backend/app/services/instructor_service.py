# backend/app/services/instructor_service.py
"""
Instructor Service Layer

Handles all business logic related to instructor operations including
profile management, service updates with soft delete, and data transformations.
"""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import BusinessRuleException, NotFoundException
from ..models.booking import Booking
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User, UserRole
from ..schemas.instructor import InstructorProfileCreate, InstructorProfileUpdate, ServiceCreate
from .base import BaseService
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class InstructorService(BaseService):
    """
    Service layer for instructor-related operations.

    Centralizes business logic and ensures proper handling of:
    - Profile creation and updates
    - Service soft/hard delete logic
    - Cache invalidation
    - Data transformation for API responses
    """

    def __init__(self, db: Session, cache_service: Optional[CacheService] = None):
        """Initialize instructor service with database and cache."""
        super().__init__(db)
        self.cache_service = cache_service

    def get_instructor_profile(self, user_id: int, include_inactive_services: bool = False) -> Dict:
        """
        Get instructor profile with proper service filtering.

        Args:
            user_id: The user ID of the instructor
            include_inactive_services: Whether to include inactive services

        Returns:
            Dictionary with instructor profile data

        Raises:
            NotFoundException: If profile not found
        """
        profile = (
            self.db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
            .filter(InstructorProfile.user_id == user_id)
            .first()
        )

        if not profile:
            raise NotFoundException("Instructor profile not found")

        return self._profile_to_dict(profile, include_inactive_services)

    def get_all_instructors(self, skip: int = 0, limit: int = 100) -> List[Dict]:
        """
        Get all instructor profiles with active services only.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of instructor profile dictionaries
        """
        profiles = (
            self.db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
            .offset(skip)
            .limit(limit)
            .all()
        )

        return [self._profile_to_dict(p) for p in profiles]

    def create_instructor_profile(self, user: User, profile_data: InstructorProfileCreate) -> Dict:
        """
        Create a new instructor profile.

        Args:
            user: The user becoming an instructor
            profile_data: Profile creation data

        Returns:
            Created profile dictionary

        Raises:
            BusinessRuleException: If profile already exists
        """
        # Check if profile already exists
        existing = self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user.id).first()

        if existing:
            raise BusinessRuleException("Instructor profile already exists")

        with self.transaction():
            # Create profile
            profile_dict = profile_data.model_dump(exclude={"services"})
            profile = InstructorProfile(user_id=user.id, **profile_dict)
            self.db.add(profile)
            self.db.flush()

            # Create services
            for service_data in profile_data.services:
                service = Service(instructor_profile_id=profile.id, **service_data.model_dump())
                self.db.add(service)

            # Update user role
            user.role = UserRole.INSTRUCTOR

            self.db.commit()

            # Refresh to get all relationships
            self.db.refresh(profile)

            logger.info(f"Created instructor profile for user {user.id}")

            return self._profile_to_dict(profile)

    def update_instructor_profile(self, user_id: int, update_data: InstructorProfileUpdate) -> Dict:
        """
        Update instructor profile with proper soft delete handling.

        Args:
            user_id: The user ID of the instructor
            update_data: Profile update data

        Returns:
            Updated profile dictionary

        Raises:
            NotFoundException: If profile not found
        """
        profile = self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()

        if not profile:
            raise NotFoundException("Instructor profile not found")

        with self.transaction():
            # Update basic fields
            basic_updates = update_data.model_dump(exclude={"services"}, exclude_unset=True)
            for field, value in basic_updates.items():
                setattr(profile, field, value)

            # Handle service updates if provided
            if update_data.services is not None:
                self._update_services(profile.id, update_data.services)

            self.db.commit()

            # Invalidate caches
            if self.cache_service:
                self._invalidate_instructor_caches(user_id)

            # Return fresh data
            return self.get_instructor_profile(user_id)

    def delete_instructor_profile(self, user_id: int) -> None:
        """
        Delete instructor profile and revert to student role.

        Soft deletes all services to preserve booking history.

        Args:
            user_id: The user ID of the instructor

        Raises:
            NotFoundException: If profile not found
        """
        profile = self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()

        if not profile:
            raise NotFoundException("Instructor profile not found")

        with self.transaction():
            # Soft delete all active services
            for service in profile.services:
                if service.is_active:
                    service.deactivate()

            # Delete the profile
            self.db.delete(profile)

            # Revert user role
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user.role = UserRole.STUDENT

            self.db.commit()

            # Invalidate caches
            if self.cache_service:
                self._invalidate_instructor_caches(user_id)

            logger.info(f"Deleted instructor profile for user {user_id}")

    # Private helper methods

    def _update_services(self, profile_id: int, services_data: List[ServiceCreate]) -> None:
        """
        Update services with soft/hard delete logic.

        Args:
            profile_id: Instructor profile ID
            services_data: List of service updates
        """
        # Get all existing services (including inactive)
        existing_services = self.db.query(Service).filter(Service.instructor_profile_id == profile_id).all()

        # Create lookup map
        services_by_skill = {service.skill.lower(): service for service in existing_services}

        # Track which services are in the update
        updated_skills: Set[str] = set()

        # Process updates and new services
        for service_data in services_data:
            skill_lower = service_data.skill.lower()
            updated_skills.add(skill_lower)

            if skill_lower in services_by_skill:
                # Update existing service
                existing_service = services_by_skill[skill_lower]

                # Reactivate if needed
                if not existing_service.is_active:
                    existing_service.activate()
                    logger.info(f"Reactivated service: {existing_service.skill}")

                # Update fields
                for field, value in service_data.model_dump().items():
                    setattr(existing_service, field, value)
            else:
                # Create new service
                new_service = Service(instructor_profile_id=profile_id, **service_data.model_dump())
                self.db.add(new_service)
                logger.info(f"Created new service: {service_data.skill}")

        # Handle removed services (only process active ones)
        for skill_lower, service in services_by_skill.items():
            if skill_lower not in updated_skills and service.is_active:
                # Check for bookings
                has_bookings = self.db.query(Booking).filter(Booking.service_id == service.id).first() is not None

                if has_bookings:
                    # Soft delete
                    service.deactivate()
                    logger.info(
                        f"Soft deleted service '{service.skill}' (ID: {service.id}) " f"- has existing bookings"
                    )
                else:
                    # Hard delete
                    self.db.delete(service)
                    logger.info(f"Hard deleted service '{service.skill}' (ID: {service.id}) " f"- no bookings")

    def _profile_to_dict(self, profile: InstructorProfile, include_inactive_services: bool = False) -> Dict:
        """
        Convert instructor profile to dictionary.

        Args:
            profile: InstructorProfile ORM object
            include_inactive_services: Whether to include inactive services

        Returns:
            Dictionary representation of profile
        """
        # Get services based on filter
        services = profile.services if include_inactive_services else profile.active_services

        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "bio": profile.bio,
            "areas_of_service": profile.areas_of_service,
            "years_experience": profile.years_experience,
            "min_advance_booking_hours": profile.min_advance_booking_hours,
            "buffer_time_minutes": profile.buffer_time_minutes,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "user": {"full_name": profile.user.full_name, "email": profile.user.email},
            "services": [
                {
                    "id": service.id,
                    "skill": service.skill,
                    "hourly_rate": service.hourly_rate,
                    "description": service.description,
                    "duration_override": service.duration_override,
                    "duration": service.duration,
                    "is_active": service.is_active,
                }
                for service in sorted(services, key=lambda s: s.skill)
            ],
        }

    def _invalidate_instructor_caches(self, user_id: int) -> None:
        """Invalidate all caches related to an instructor."""
        if not self.cache_service:
            return

        # Clear profile cache
        self.cache_service.delete(f"instructor:profile:{user_id}")

        # Clear availability caches
        self.cache_service.invalidate_instructor_availability(user_id)

        # Clear any listing caches
        self.cache_service.delete_pattern("instructors:list:*")

        logger.debug(f"Invalidated caches for instructor {user_id}")


# Dependency injection
def get_instructor_service(db: Session, cache_service: Optional[CacheService] = None) -> InstructorService:
    """Get instructor service instance for dependency injection."""
    return InstructorService(db, cache_service)
