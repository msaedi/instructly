# backend/app/services/instructor_service.py
"""
Instructor Service Layer

Handles all business logic related to instructor operations including
profile management, service updates with soft delete, and data transformations.

UPDATED IN v65: Added performance metrics to all public methods for observability.
Now tracks timing for all instructor operations to earn those MEGAWATTS! ⚡
"""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException, NotFoundException
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService as Service
from ..models.service_catalog import ServiceCatalog, ServiceCategory
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
        # Add catalog repositories
        self.catalog_repository = RepositoryFactory.create_base_repository(db, ServiceCatalog)
        self.category_repository = RepositoryFactory.create_base_repository(db, ServiceCategory)

    @BaseService.measure_operation("get_instructor_profile")
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

    @BaseService.measure_operation("get_all_instructors")
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

    @BaseService.measure_operation("get_instructors_filtered")
    def get_instructors_filtered(
        self,
        search: Optional[str] = None,
        service_catalog_id: Optional[int] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict:
        """
        Get instructor profiles based on filter criteria.

        Uses the repository's find_by_filters method to efficiently query instructors
        matching the provided filters. Only returns instructors with active services.

        Args:
            search: Text search across name, bio, and services
            service_catalog_id: Filter by specific service catalog ID
            min_price: Minimum hourly rate filter
            max_price: Maximum hourly rate filter
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            Dictionary containing:
                - instructors: List of instructor profile dictionaries (active services only)
                - metadata: Information about applied filters and results
        """
        # Log filter usage for analytics
        filter_info = {
            "search": search is not None,
            "service_catalog": service_catalog_id is not None,
            "price_range": min_price is not None or max_price is not None,
            "filters_count": sum(
                [search is not None, service_catalog_id is not None, min_price is not None, max_price is not None]
            ),
        }

        logger.info(
            f"Instructor filter request - "
            f"Filters used: {filter_info['filters_count']}, "
            f"Search: {filter_info['search']}, "
            f"Service Catalog: {filter_info['service_catalog']}, "
            f"Price: {filter_info['price_range']}, "
            f"Pagination: skip={skip}, limit={limit}"
        )

        # Call repository method with filters
        profiles = self.profile_repository.find_by_filters(
            search=search,
            service_catalog_id=service_catalog_id,
            min_price=min_price,
            max_price=max_price,
            skip=skip,
            limit=limit,
        )

        # Convert to dictionaries, ensuring only active services are included
        instructors = []
        for profile in profiles:
            # _profile_to_dict with include_inactive_services=False filters out inactive services
            instructor_dict = self._profile_to_dict(profile, include_inactive_services=False)

            # Only include instructors that have at least one active service after filtering
            if instructor_dict["services"]:
                instructors.append(instructor_dict)

        # Build metadata about applied filters
        applied_filters = {}
        if search:
            applied_filters["search"] = search
        if service_catalog_id:
            applied_filters["service_catalog_id"] = service_catalog_id
        if min_price is not None:
            applied_filters["min_price"] = min_price
        if max_price is not None:
            applied_filters["max_price"] = max_price

        metadata = {
            "filters_applied": applied_filters,
            "pagination": {"skip": skip, "limit": limit, "count": len(instructors)},
            "total_matches": len(profiles),  # Total found by repository
            "active_instructors": len(instructors),  # After filtering inactive services
        }

        # Log search results for analytics
        if search:
            logger.info(
                f"Search '{search}' returned {len(instructors)} active instructors "
                f"(from {len(profiles)} total matches)"
            )

        if service_catalog_id:
            logger.info(f"Service catalog filter '{service_catalog_id}' returned {len(instructors)} instructors")

        if min_price is not None or max_price is not None:
            price_range = f"${min_price or 0}-${max_price or 'unlimited'}"
            logger.info(f"Price range {price_range} returned {len(instructors)} instructors")

        return {"instructors": instructors, "metadata": metadata}

    @BaseService.measure_operation("create_instructor_profile")
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
            # Validate catalog IDs before creating anything
            if profile_data.services:
                catalog_ids = [service.service_catalog_id for service in profile_data.services]
                self._validate_catalog_ids(catalog_ids)

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
            profile.instructor_services = services

            logger.info(f"Created instructor profile for user {user.id}")

            return self._profile_to_dict(profile)

    @BaseService.measure_operation("update_instructor_profile")
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

    @BaseService.measure_operation("delete_instructor_profile")
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

    def _validate_catalog_ids(self, catalog_ids: List[int]) -> None:
        """
        Validate that all catalog IDs exist in the database.

        Args:
            catalog_ids: List of catalog IDs to validate

        Raises:
            ValidationException: If any catalog ID is invalid
        """
        from app.models.service_catalog import ServiceCatalog

        # Get all valid catalog IDs
        valid_ids = set(self.db.query(ServiceCatalog.id).filter(ServiceCatalog.id.in_(catalog_ids)).all())
        valid_ids = {id[0] for id in valid_ids}  # Extract IDs from tuples

        # Check for invalid IDs
        invalid_ids = set(catalog_ids) - valid_ids
        if invalid_ids:
            raise BusinessRuleException(f"Invalid service catalog IDs: {', '.join(map(str, invalid_ids))}")

    def _update_services(self, profile_id: int, services_data: List[ServiceCreate]) -> None:
        """
        Update services with soft/hard delete logic.

        Args:
            profile_id: Instructor profile ID
            services_data: List of service updates
        """
        # Validate all catalog IDs exist
        if services_data:
            catalog_ids = [service.service_catalog_id for service in services_data]
            self._validate_catalog_ids(catalog_ids)

        # Get all existing services (including inactive)
        existing_services = self.service_repository.find_by(instructor_profile_id=profile_id)

        # Create lookup map by catalog ID
        services_by_catalog_id = {service.service_catalog_id: service for service in existing_services}

        # Track which services are in the update
        updated_catalog_ids: Set[int] = set()

        # Process updates and new services
        for service_data in services_data:
            catalog_id = service_data.service_catalog_id
            updated_catalog_ids.add(catalog_id)

            if catalog_id in services_by_catalog_id:
                # Update existing service
                existing_service = services_by_catalog_id[catalog_id]

                # Prepare updates
                updates = service_data.model_dump()

                # Reactivate if needed
                if not existing_service.is_active:
                    updates["is_active"] = True
                    logger.info(f"Reactivated service: catalog_id {catalog_id}")

                # Update service
                self.service_repository.update(existing_service.id, **updates)
            else:
                # Create new service
                service_dict = service_data.model_dump()
                service_dict["instructor_profile_id"] = profile_id
                self.service_repository.create(**service_dict)
                logger.info(f"Created new service: catalog_id {catalog_id}")

        # Handle removed services (only process active ones)
        for catalog_id, service in services_by_catalog_id.items():
            if catalog_id not in updated_catalog_ids and service.is_active:
                # Check for bookings using BookingRepository
                has_bookings = self.booking_repository.exists(instructor_service_id=service.id)

                if has_bookings:
                    # Soft delete
                    self.service_repository.update(service.id, is_active=False)
                    catalog_name = service.catalog_entry.name if service.catalog_entry else "Unknown"
                    logger.info(f"Soft deleted service '{catalog_name}' (ID: {service.id}) " f"- has existing bookings")
                else:
                    # Hard delete
                    self.service_repository.delete(service.id)
                    catalog_name = service.catalog_entry.name if service.catalog_entry else "Unknown"
                    logger.info(f"Hard deleted service '{catalog_name}' (ID: {service.id}) " f"- no bookings")

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
        if hasattr(profile, "instructor_services"):
            if include_inactive_services:
                services = profile.instructor_services
            else:
                services = [s for s in profile.instructor_services if s.is_active]
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
                    "service_catalog_id": service.service_catalog_id,
                    "name": service.catalog_entry.name if service.catalog_entry else "Unknown Service",
                    "hourly_rate": service.hourly_rate,
                    "description": service.description,
                    "duration_options": service.duration_options,
                    "is_active": service.is_active,
                }
                for service in sorted(services, key=lambda s: s.service_catalog_id)
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

    # Catalog-aware methods
    @BaseService.measure_operation("get_available_catalog_services")
    def get_available_catalog_services(self, category_slug: Optional[str] = None) -> List[Dict]:
        """
        Get available services from the catalog.

        Args:
            category_slug: Optional category filter

        Returns:
            List of catalog service dictionaries
        """
        if category_slug:
            category = self.category_repository.find_one_by(slug=category_slug)
            if not category:
                raise NotFoundException(f"Category '{category_slug}' not found")
            services = self.catalog_repository.find_by(category_id=category.id, is_active=True)
        else:
            services = self.catalog_repository.find_by(is_active=True)

        return [self._catalog_service_to_dict(service) for service in services]

    @BaseService.measure_operation("get_service_categories")
    def get_service_categories(self) -> List[Dict]:
        """Get all service categories."""
        categories = self.category_repository.get_all()
        return [
            {
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "description": cat.description,
                "display_order": cat.display_order,
            }
            for cat in sorted(categories, key=lambda x: x.display_order)
        ]

    @BaseService.measure_operation("create_instructor_service_from_catalog")
    def create_instructor_service_from_catalog(
        self,
        instructor_id: int,
        catalog_service_id: int,
        hourly_rate: float,
        custom_description: Optional[str] = None,
        duration_options: Optional[List[int]] = None,
    ) -> Dict:
        """
        Create an instructor service linked to a catalog entry.

        Args:
            instructor_id: Instructor's user ID
            catalog_service_id: ID of the catalog service
            hourly_rate: Instructor's rate for this service
            custom_description: Optional custom description
            duration_options: Optional custom durations (uses catalog defaults if not provided)

        Returns:
            Created service dictionary

        Raises:
            NotFoundException: If instructor or catalog service not found
            BusinessRuleException: If service already exists
        """
        # Get instructor profile
        profile = self.profile_repository.find_one_by(user_id=instructor_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        # Get catalog service
        catalog_service = self.catalog_repository.get_by_id(catalog_service_id)
        if not catalog_service:
            raise NotFoundException("Catalog service not found")

        # Check if already exists
        existing = self.service_repository.find_one_by(
            instructor_profile_id=profile.id, service_catalog_id=catalog_service_id, is_active=True
        )
        if existing:
            raise BusinessRuleException(f"You already offer {catalog_service.name}")

        with self.transaction():
            # Create the instructor service
            service = self.service_repository.create(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service_id,
                hourly_rate=hourly_rate,
                description=custom_description,
                duration_options=duration_options or catalog_service.typical_duration_options,
                is_active=True,
            )

            self.db.commit()

            # Invalidate caches
            if self.cache_service:
                self._invalidate_instructor_caches(instructor_id)

            logger.info(f"Created service {catalog_service.name} for instructor {instructor_id}")

            # Return with catalog details
            service.catalog_entry = catalog_service
            return self._instructor_service_to_dict(service)

    def _catalog_service_to_dict(self, service: ServiceCatalog) -> Dict:
        """Convert catalog service to dictionary."""
        return {
            "id": service.id,
            "category_id": service.category_id,
            "category": service.category.name if service.category else None,
            "name": service.name,
            "slug": service.slug,
            "description": service.description,
            "search_terms": service.search_terms or [],  # Default to empty list if None
            "typical_duration_options": service.typical_duration_options or [60],  # Default if None
            "min_recommended_price": service.min_recommended_price,
            "max_recommended_price": service.max_recommended_price,
        }

    def _instructor_service_to_dict(self, service: Service) -> Dict:
        """Convert instructor service to dictionary with catalog info."""
        return {
            "id": service.id,
            "catalog_service_id": service.service_catalog_id,
            "name": service.catalog_entry.name if service.catalog_entry else "Unknown",  # From catalog
            "category": service.category,  # From catalog
            "hourly_rate": service.hourly_rate,
            "description": service.description or service.catalog_entry.description,
            "duration_options": service.duration_options,
            "is_active": service.is_active,
            "created_at": service.created_at,
            "updated_at": service.updated_at,
        }


# Dependency injection
def get_instructor_service(db: Session, cache_service: Optional[CacheService] = None) -> InstructorService:
    """Get instructor service instance for dependency injection."""
    return InstructorService(db, cache_service)
