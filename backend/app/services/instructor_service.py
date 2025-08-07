# backend/app/services/instructor_service.py
"""
Instructor Service Layer

Handles all business logic related to instructor operations including
profile management, service updates with soft delete, and data transformations.

UPDATED IN v65: Added performance metrics to all public methods for observability.
Now tracks timing for all instructor operations to earn those MEGAWATTS! ⚡
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from ..core.enums import RoleName
from ..core.exceptions import BusinessRuleException, NotFoundException
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService as Service
from ..models.service_catalog import ServiceCatalog, ServiceCategory
from ..models.user import User
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
        # Add catalog repositories - use specialized repository for search capabilities
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.category_repository = RepositoryFactory.create_base_repository(db, ServiceCategory)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)

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
            self.user_repository.update(user.id, role=RoleName.INSTRUCTOR)

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
            # repo-pattern-ignore: Flush for ensuring services are updated belongs in service layer
            self.db.flush()

            # Now delete the profile
            self.profile_repository.delete(profile.id)

            # Revert user role - remove instructor role and add student role
            from app.services.permission_service import PermissionService

            permission_service = PermissionService(self.db)
            permission_service.remove_role(user_id, RoleName.INSTRUCTOR)
            permission_service.assign_role(user_id, RoleName.STUDENT)

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
        # Use repository to check existence
        valid_ids = set()
        for catalog_id in catalog_ids:
            if self.catalog_repository.exists(id=catalog_id, is_active=True):
                valid_ids.add(catalog_id)

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

        Optimized with eager loading and 5-minute caching to balance performance
        with analytics-driven order updates.

        Args:
            category_slug: Optional category filter

        Returns:
            List of catalog service dictionaries
        """
        # Try cache first (5-minute TTL for analytics freshness)
        cache_key = f"catalog:services:{category_slug or 'all'}"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for catalog services: {cache_key}")
                return cached_result

        # Get category ID if slug provided
        category_id = None
        if category_slug:
            category = self.category_repository.find_one_by(slug=category_slug)
            if not category:
                raise NotFoundException(f"Category '{category_slug}' not found")
            category_id = category.id

        # Use optimized repository method with eager loading
        services = self.catalog_repository.get_active_services_with_categories(category_id=category_id)

        # Convert to dictionaries (no N+1 queries since categories are loaded)
        result = [self._catalog_service_to_dict(service) for service in services]

        # Cache for 5 minutes (300 seconds)
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            logger.debug(f"Cached {len(result)} catalog services for 5 minutes")

        return result

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
                duration_options=duration_options or [60],  # Default to 60 minutes if not specified
                is_active=True,
            )

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
            "display_order": service.display_order,
            "online_capable": service.online_capable,
            "requires_certification": service.requires_certification,
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

    # New methods for enhanced search and analytics

    @BaseService.measure_operation("search_services_semantic")
    def search_services_semantic(
        self,
        query_embedding: List[float],
        category_id: Optional[int] = None,
        online_capable: Optional[bool] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List[Dict]:
        """
        Search services using semantic similarity.

        Args:
            query_embedding: 384-dimension embedding vector
            category_id: Optional category filter
            online_capable: Optional online capability filter
            limit: Maximum results to return
            threshold: Minimum similarity threshold (0-1)

        Returns:
            List of services with similarity scores
        """
        # Get similar services using vector search
        similar_services = self.catalog_repository.find_similar_by_embedding(
            embedding=query_embedding, limit=limit * 2, threshold=threshold  # Get more to filter
        )

        # Apply additional filters if provided
        filtered_results = []
        for service, score in similar_services:
            if category_id and service.category_id != category_id:
                continue
            if online_capable is not None and service.online_capable != online_capable:
                continue

            # Increment search analytics
            self.analytics_repository.increment_search_count(service.id)

            # Add to results
            service_dict = self._catalog_service_to_dict(service)
            service_dict["similarity_score"] = score
            service_dict["analytics"] = self._get_service_analytics(service.id)
            filtered_results.append(service_dict)

            if len(filtered_results) >= limit:
                break

        return filtered_results

    @BaseService.measure_operation("get_popular_services")
    def get_popular_services(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """
        Get most popular services based on booking data.

        Args:
            limit: Number of services to return
            days: Time period (7 or 30 days)

        Returns:
            List of popular services with metrics
        """
        popular = self.catalog_repository.get_popular_services(limit=limit, days=days)

        results = []
        for item in popular:
            service_dict = self._catalog_service_to_dict(item["service"])
            service_dict["analytics"] = item["analytics"].to_dict()
            service_dict["popularity_score"] = item["popularity_score"]
            results.append(service_dict)

        return results

    @BaseService.measure_operation("get_trending_services")
    def get_trending_services(self, limit: int = 10) -> List[Dict]:
        """
        Get services trending upward in demand.

        Args:
            limit: Number of services to return

        Returns:
            List of trending services
        """
        trending = self.catalog_repository.get_trending_services(limit=limit)

        results = []
        for service in trending:
            service_dict = self._catalog_service_to_dict(service)
            service_dict["analytics"] = self._get_service_analytics(service.id)
            results.append(service_dict)

        return results

    @BaseService.measure_operation("search_services_enhanced")
    def search_services_enhanced(
        self,
        query_text: Optional[str] = None,
        category_id: Optional[int] = None,
        online_capable: Optional[bool] = None,
        requires_certification: Optional[bool] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict:
        """
        Enhanced service search with multiple filters and analytics.

        Args:
            query_text: Text search query
            category_id: Filter by category
            online_capable: Filter by online capability
            requires_certification: Filter by certification requirement
            min_price: Minimum price filter
            max_price: Maximum price filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            Dictionary with services and metadata
        """
        # Search services using repository
        services = self.catalog_repository.search_services(
            query_text=query_text,
            category_id=category_id,
            online_capable=online_capable,
            requires_certification=requires_certification,
            skip=skip,
            limit=limit,
        )

        # Build results with analytics
        results = []
        for service in services:
            service_dict = self._catalog_service_to_dict(service)

            # Add analytics data
            service_dict["analytics"] = self._get_service_analytics(service.id)

            # Add instructor count and price range if needed
            if min_price is not None or max_price is not None:
                instructors = self._get_instructors_for_service_in_price_range(service.id, min_price, max_price)
                service_dict["matching_instructors"] = len(instructors)
                service_dict["actual_price_range"] = self._calculate_price_range(instructors)

            results.append(service_dict)

            # Track search analytics
            if query_text:
                self.analytics_repository.increment_search_count(service.id)

        # Build metadata
        metadata = {
            "query": query_text,
            "filters": {
                "category_id": category_id,
                "online_capable": online_capable,
                "requires_certification": requires_certification,
                "price_range": {"min": min_price, "max": max_price} if min_price or max_price else None,
            },
            "pagination": {"skip": skip, "limit": limit, "count": len(results)},
        }

        return {"services": results, "metadata": metadata}

    def _get_service_analytics(self, service_catalog_id: int) -> Dict:
        """Get or create analytics for a service."""
        analytics = self.analytics_repository.get_or_create(service_catalog_id)
        return analytics.to_dict() if analytics else {}

    def _get_instructors_for_service_in_price_range(
        self, service_catalog_id: int, min_price: Optional[float], max_price: Optional[float]
    ) -> List[Service]:
        """Get instructors offering a service within price range."""
        query_filters = {"service_catalog_id": service_catalog_id, "is_active": True}

        all_services = self.service_repository.find_by(**query_filters)

        # Filter by price
        filtered = []
        for service in all_services:
            if min_price and service.hourly_rate < min_price:
                continue
            if max_price and service.hourly_rate > max_price:
                continue
            filtered.append(service)

        return filtered

    def _calculate_price_range(self, instructor_services: List[Service]) -> Dict:
        """Calculate actual price range from instructor services."""
        if not instructor_services:
            return {"min": None, "max": None}

        prices = [s.hourly_rate for s in instructor_services]
        return {"min": min(prices), "max": max(prices), "avg": sum(prices) / len(prices)}

    @BaseService.measure_operation("get_top_services_per_category")
    def get_top_services_per_category(self, limit: int = 7) -> Dict:
        """
        Get top N services per category for homepage display.

        Optimized for performance with aggressive caching (1 hour) since
        analytics update daily. Returns only what the homepage needs.

        Args:
            limit: Number of services per category (default: 7)

        Returns:
            Dictionary with categories and their top services
        """
        # Try cache first (1 hour TTL for homepage optimization)
        cache_key = f"catalog:top-services:{limit}"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for top services per category")
                return cached_result

        # Get all categories
        categories = self.category_repository.get_all()

        result = {
            "categories": [],
            "metadata": {
                "services_per_category": limit,
                "total_categories": len(categories),
                "cached_for_seconds": 3600,  # 1 hour
                "updated_at": datetime.now().isoformat(),
            },
        }

        # For each category, get top N services by display_order
        for category in sorted(categories, key=lambda c: c.display_order):
            # Always create category data - never hide categories
            category_data = {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "icon_name": category.icon_name,
                "services": [],
            }

            # Get top services for this category (already ordered by display_order)
            top_services = self.catalog_repository.get_active_services_with_categories(
                category_id=category.id, limit=limit
            )

            # Add only essential service data for homepage, filtering by active instructors
            for service in top_services:
                # Get analytics for demand score
                analytics = self.analytics_repository.get_or_create(service.id)

                # Only include services with active instructors
                active_instructors = analytics.active_instructors if analytics else 0
                if active_instructors > 0:
                    category_data["services"].append(
                        {
                            "id": service.id,
                            "name": service.name,
                            "slug": service.slug,
                            "demand_score": analytics.demand_score if analytics else 0,
                            "active_instructors": active_instructors,
                            "is_trending": analytics.is_trending if analytics else False,
                            "display_order": service.display_order,
                        }
                    )

            # Always add the category, even if it has no services with active instructors
            result["categories"].append(category_data)

        # Cache for 1 hour
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
            logger.debug(f"Cached top {limit} services per category for 1 hour")

        return result

    @BaseService.measure_operation("get_all_services_with_instructors")
    def get_all_services_with_instructors(self) -> Dict:
        """
        Get all catalog services organized by category with active instructor counts.

        This is an optimized endpoint for the All Services page that combines
        catalog data with analytics in a single request. Uses 5-minute caching
        to balance performance with data freshness.

        Returns:
            Dictionary with categories and their services, including active instructor counts
        """
        # Try cache first (5-minute TTL for analytics freshness)
        cache_key = "catalog:all-services-with-instructors"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for all services with instructors")
                return cached_result

        # Get all categories
        categories = self.category_repository.get_all()

        result = {
            "categories": [],
            "metadata": {
                "total_categories": len(categories),
                "cached_for_seconds": 300,  # 5 minutes
                "updated_at": datetime.now().isoformat(),
            },
        }

        # For each category, get ALL services (not just top N)
        for category in sorted(categories, key=lambda c: c.display_order):
            category_data = {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "subtitle": category.subtitle if hasattr(category, "subtitle") else "",
                "description": category.description,
                "icon_name": category.icon_name,
                "services": [],
            }

            # Get ALL services for this category (ordered by display_order)
            services = self.catalog_repository.get_active_services_with_categories(
                category_id=category.id, limit=None  # No limit - get all services
            )

            # Collect services with analytics data
            services_with_analytics = []
            for service in services:
                # Get analytics for demand score and instructor count
                analytics = self.analytics_repository.get_or_create(service.id)

                # Include ALL services, even those without instructors
                active_instructors = analytics.active_instructors if analytics else 0

                service_data = {
                    "id": service.id,
                    "category_id": service.category_id,
                    "name": service.name,
                    "slug": service.slug,
                    "description": service.description,
                    "search_terms": service.search_terms or [],
                    "display_order": service.display_order,
                    "online_capable": service.online_capable,
                    "requires_certification": service.requires_certification,
                    "is_active": service.is_active,
                    # Analytics data
                    "active_instructors": active_instructors,
                    "instructor_count": active_instructors,  # Alias for frontend compatibility
                    "demand_score": analytics.demand_score if analytics else 0,
                    "is_trending": analytics.is_trending if analytics else False,
                    # Store original display order for secondary sorting
                    "_original_display_order": service.display_order,
                }

                # Add price range if we have instructors
                if active_instructors > 0:
                    # Get price range from instructor services
                    instructor_services = self._get_instructors_for_service_in_price_range(service.id, None, None)
                    if instructor_services:
                        price_range = self._calculate_price_range(instructor_services)
                        service_data["actual_min_price"] = price_range["min"]
                        service_data["actual_max_price"] = price_range["max"]

                services_with_analytics.append(service_data)

            # Sort services: active services first (by display_order), then inactive services (by display_order)
            services_with_analytics.sort(
                key=lambda s: (
                    0 if s["active_instructors"] > 0 else 1,  # Active services come first
                    s["_original_display_order"],  # Then sort by display order within each group
                )
            )

            # Remove the temporary sorting field and add to category
            for service_data in services_with_analytics:
                del service_data["_original_display_order"]
                category_data["services"].append(service_data)

            # Always add the category, even if empty
            result["categories"].append(category_data)

        # Add total service count to metadata
        total_services = sum(len(cat["services"]) for cat in result["categories"])
        result["metadata"]["total_services"] = total_services

        # Cache for 5 minutes
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            logger.debug(f"Cached all {total_services} services with instructor data for 5 minutes")

        return result


# Dependency injection
def get_instructor_service(db: Session, cache_service: Optional[CacheService] = None) -> InstructorService:
    """Get instructor service instance for dependency injection."""
    return InstructorService(db, cache_service)
