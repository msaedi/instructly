# backend/app/services/instructor_service.py
"""
Instructor Service Layer

Handles all business logic related to instructor operations including
profile management, service updates with soft delete, and data transformations.
"""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException, NotFoundException
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User, UserRole
from ..repositories.factory import RepositoryFactory
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

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheService] = None,
        profile_repository=None,
        service_repository=None,
        user_repository=None,
        booking_repository=None,
    ):
        """Initialize instructor service with database, cache, and repositories."""
        super().__init__(db)
        self.cache_service = cache_service

        # Initialize repositories - use specialized InstructorProfileRepository for optimized queries
        self.profile_repository = profile_repository or RepositoryFactory.create_instructor_profile_repository(db)
        self.service_repository = service_repository or RepositoryFactory.create_base_repository(db, Service)
        self.user_repository = user_repository or RepositoryFactory.create_base_repository(db, User)
        self.booking_repository = booking_repository or RepositoryFactory.create_booking_repository(db)

    def get_instructor_profile(self, user_id: int, include_inactive_services: bool = False) -> Dict:
        """
        Get instructor profile with proper service filtering.

        OPTIMIZED: Uses eager loading to get all data in one query.

        Args:
            user_id: The user ID of the instructor
            include_inactive_services: Whether to include inactive services

        Returns:
            Dictionary with instructor profile data

        Raises:
            NotFoundException: If profile not found
        """
        # Use optimized repository method that eager loads relationships
        profile = self.profile_repository.get_by_user_id_with_details(
            user_id=user_id, include_inactive_services=include_inactive_services
        )

        if not profile:
            raise NotFoundException("Instructor profile not found")

        # Everything is already loaded - no additional queries
        return self._profile_to_dict(profile, include_inactive_services)

    def get_all_instructors(self, skip: int = 0, limit: int = 100) -> List[Dict]:
        """
        Get all instructor profiles with active services only.

        OPTIMIZED: Uses eager loading to prevent N+1 queries.
        Previously: 1 + 2N queries (201 queries for 100 instructors)
        Now: 1 query with joins

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of instructor profile dictionaries
        """
        # Use the optimized repository method that eager loads relationships
        profiles = self.profile_repository.get_all_with_details(
            skip=skip, limit=limit, include_inactive_services=False  # Only active services
        )

        # Convert to dictionaries - no additional queries needed since everything is loaded
        result = []
        for profile in profiles:
            result.append(self._profile_to_dict(profile))

        return result

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
        existing = self.profile_repository.exists(user_id=user.id)

        if existing:
            raise BusinessRuleException("Instructor profile already exists")

        with self.transaction():
            # Create profile
            profile_dict = profile_data.model_dump(exclude={"services"})
            profile_dict["user_id"] = user.id
            profile = self.profile_repository.create(**profile_dict)

            # Create services using bulk create
            services_data = []
            for service_data in profile_data.services:
                service_dict = service_data.model_dump()
                service_dict["instructor_profile_id"] = profile.id
                services_data.append(service_dict)

            if services_data:
                services = self.service_repository.bulk_create(services_data)
            else:
                services = []

            # Update user role
            self.user_repository.update(user.id, role=UserRole.INSTRUCTOR)

            self.db.commit()

            # Load user for response
            user = self.user_repository.get_by_id(user.id)
            profile.user = user
            profile.services = services

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
        profile = self.profile_repository.find_one_by(user_id=user_id)

        if not profile:
            raise NotFoundException("Instructor profile not found")

        with self.transaction():
            # Update basic fields
            basic_updates = update_data.model_dump(exclude={"services"}, exclude_unset=True)
            if basic_updates:
                self.profile_repository.update(profile.id, **basic_updates)

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
        profile = self.profile_repository.find_one_by(user_id=user_id)

        if not profile:
            raise NotFoundException("Instructor profile not found")

        with self.transaction():
            # Get all services for this profile
            services = self.service_repository.find_by(instructor_profile_id=profile.id)

            # Soft delete all active services
            for service in services:
                if service.is_active:
                    self.service_repository.update(service.id, is_active=False)

            # Flush to ensure services are updated
            self.db.flush()

            # Now delete the profile
            self.profile_repository.delete(profile.id)

            # Revert user role
            self.user_repository.update(user_id, role=UserRole.STUDENT)

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
        existing_services = self.service_repository.find_by(instructor_profile_id=profile_id)

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

                # Prepare updates
                updates = service_data.model_dump()

                # Reactivate if needed
                if not existing_service.is_active:
                    updates["is_active"] = True
                    logger.info(f"Reactivated service: {existing_service.skill}")

                # Update service
                self.service_repository.update(existing_service.id, **updates)
            else:
                # Create new service
                service_dict = service_data.model_dump()
                service_dict["instructor_profile_id"] = profile_id
                self.service_repository.create(**service_dict)
                logger.info(f"Created new service: {service_data.skill}")

        # Handle removed services (only process active ones)
        for skill_lower, service in services_by_skill.items():
            if skill_lower not in updated_skills and service.is_active:
                # Check for bookings using BookingRepository
                has_bookings = self.booking_repository.exists(service_id=service.id)

                if has_bookings:
                    # Soft delete
                    self.service_repository.update(service.id, is_active=False)
                    logger.info(
                        f"Soft deleted service '{service.skill}' (ID: {service.id}) " f"- has existing bookings"
                    )
                else:
                    # Hard delete
                    self.service_repository.delete(service.id)
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
        # Filter services based on include_inactive_services
        if hasattr(profile, "services"):
            if include_inactive_services:
                services = profile.services
            else:
                services = [s for s in profile.services if s.is_active]
        else:
            services = []

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
            "user": {"full_name": profile.user.full_name, "email": profile.user.email}
            if hasattr(profile, "user") and profile.user
            else None,
            "services": [
                {
                    "id": service.id,
                    "skill": service.skill,
                    "hourly_rate": service.hourly_rate,
                    "description": service.description,
                    "duration_override": service.duration_override,
                    "duration": service.duration if hasattr(service, "duration") else 60,
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
