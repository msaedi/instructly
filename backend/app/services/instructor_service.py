# backend/app/services/instructor_service.py
"""
Instructor Service Layer

Handles all business logic related to instructor operations including
profile management, service updates with soft delete, and data transformations.

UPDATED IN v65: Added performance metrics to all public methods for observability.
Now tracks timing for all instructor operations to earn those MEGAWATTS! ⚡
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Set, cast
from unittest.mock import Mock

import anyio
from sqlalchemy.orm import Session

from ..core.enums import RoleName
from ..core.exceptions import BusinessRuleException, NotFoundException, ServiceException
from ..models.instructor import InstructorPreferredPlace, InstructorProfile
from ..models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..repositories.instructor_preferred_place_repository import (
    InstructorPreferredPlaceRepository,
)
from ..schemas.instructor import (
    InstructorProfileCreate,
    InstructorProfileUpdate,
    PreferredPublicSpaceIn,
    PreferredTeachingLocationIn,
    ServiceCreate,
)
from .base import BaseService
from .cache_service import CacheServiceSyncAdapter
from .config_service import ConfigService
from .geocoding.factory import create_geocoding_provider
from .pricing_service import PricingService
from .stripe_service import StripeService

logger = logging.getLogger(__name__)


JsonDict = Dict[str, Any]
JsonList = List[JsonDict]


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
        cache_service: Optional[CacheServiceSyncAdapter] = None,
        profile_repository: Optional[Any] = None,
        service_repository: Optional[Any] = None,
        user_repository: Optional[Any] = None,
        booking_repository: Optional[Any] = None,
        preferred_place_repository: Optional[InstructorPreferredPlaceRepository] = None,
    ):
        """Initialize instructor service with database, cache, and repositories."""
        super().__init__(db)
        self.cache_service = cache_service

        # Initialize repositories - use specialized InstructorProfileRepository for optimized queries
        self.profile_repository = (
            profile_repository or RepositoryFactory.create_instructor_profile_repository(db)
        )
        self.service_repository = service_repository or RepositoryFactory.create_base_repository(
            db, Service
        )
        self.user_repository = user_repository or RepositoryFactory.create_base_repository(db, User)
        self.booking_repository = booking_repository or RepositoryFactory.create_booking_repository(
            db
        )
        # Add catalog repositories - use specialized repository for search capabilities
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.category_repository = RepositoryFactory.create_base_repository(db, ServiceCategory)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)
        self.preferred_place_repository = (
            preferred_place_repository
            or RepositoryFactory.create_instructor_preferred_place_repository(db)
        )
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )

    @BaseService.measure_operation("get_instructor_profile")
    def get_instructor_profile(
        self, user_id: str, include_inactive_services: bool = False
    ) -> Dict[str, Any]:
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

    @BaseService.measure_operation("get_instructor_user")
    def get_instructor_user(self, user_id: str) -> "User":
        """
        Get the User object for an instructor, validating they have a profile.

        Used for public availability endpoints that need the User object
        for timezone calculations.

        Args:
            user_id: The instructor user ID or instructor profile ID

        Returns:
            User object

        Raises:
            NotFoundException: If user not found or doesn't have instructor profile
        """
        user: Optional[User] = self.user_repository.get_by_id(user_id)
        if user:
            profile = self.profile_repository.get_by_user_id(user.id)
            if not profile:
                raise NotFoundException("Instructor not found")
            return user

        profile = self.profile_repository.get_by_id(user_id)
        if not profile:
            raise NotFoundException("Instructor not found")

        resolved_user: Optional[User] = self.user_repository.get_by_id(profile.user_id)
        if not resolved_user:
            raise NotFoundException("Instructor not found")
        return resolved_user

    @BaseService.measure_operation("get_all_instructors")
    def get_all_instructors(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
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
            skip=skip,
            limit=limit,
            include_inactive_services=False,  # Only active services
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
        service_catalog_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        age_group: Optional[str] = None,
        service_area_boroughs: Optional[Sequence[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Get instructor profiles based on filter criteria.

        Uses the repository's find_by_filters method to efficiently query instructors
        matching the provided filters. Only returns instructors with active services.

        Args:
            search: Text search across name, bio, and services
            service_catalog_id: Filter by specific service catalog ID
            min_price: Minimum hourly rate filter
            max_price: Maximum hourly rate filter
            service_area_boroughs: Optional collection of borough labels to filter by
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
            "age_group": age_group is not None,
            "service_area_boroughs": bool(service_area_boroughs),
            "filters_count": sum(
                [
                    search is not None,
                    service_catalog_id is not None,
                    min_price is not None,
                    max_price is not None,
                    age_group is not None,
                    bool(service_area_boroughs),
                ]
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
            age_group=age_group,
            boroughs=service_area_boroughs,
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
        applied_filters: JsonDict = {}
        if search:
            applied_filters["search"] = search
        if service_catalog_id:
            applied_filters["service_catalog_id"] = service_catalog_id
        if min_price is not None:
            applied_filters["min_price"] = min_price
        if max_price is not None:
            applied_filters["max_price"] = max_price
        if service_area_boroughs:
            applied_filters["service_area_boroughs"] = list(service_area_boroughs)
        if age_group is not None:
            applied_filters["age_group"] = age_group

        metadata: JsonDict = {
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
            logger.info(
                f"Service catalog filter '{service_catalog_id}' returned {len(instructors)} instructors"
            )

        if min_price is not None or max_price is not None:
            price_range = f"${min_price or 0}-${max_price or 'unlimited'}"
            logger.info(f"Price range {price_range} returned {len(instructors)} instructors")

        return {"instructors": instructors, "metadata": metadata}

    @BaseService.measure_operation("create_instructor_profile")
    def create_instructor_profile(
        self, user: User, profile_data: InstructorProfileCreate
    ) -> Dict[str, Any]:
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
            refreshed_user = self.user_repository.get_by_id(user.id)
            profile.user = refreshed_user or user
            profile.instructor_services = services

        logger.info(f"Created instructor profile for user {user.id}")

        return self._profile_to_dict(profile)

    @BaseService.measure_operation("get_public_instructor_profile")
    def get_public_instructor_profile(self, instructor_id: str) -> Optional[Dict[str, Any]]:
        """Return a public-facing instructor profile when visible (cached for 5 minutes)."""
        # Try cache first (5-minute TTL for instructor profiles)
        cache_key = f"instructor:public:{instructor_id}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for instructor profile: {instructor_id}")
                return cast(JsonDict, cached)

        profile = self.profile_repository.get_public_by_id(instructor_id)
        if not profile:
            return None

        result = self._profile_to_dict(profile)

        # Cache for 5 minutes (300 seconds)
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            logger.debug(f"Cached instructor profile: {instructor_id}")

        return result

    @BaseService.measure_operation("update_instructor_profile")
    def update_instructor_profile(
        self, user_id: str, update_data: InstructorProfileUpdate
    ) -> Dict[str, Any]:
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
            # Update basic fields (exclude service + preferred place payloads handled separately)
            basic_updates = update_data.model_dump(
                exclude={"services", "preferred_teaching_locations", "preferred_public_spaces"},
                exclude_unset=True,
            )

            # If services are being updated but bio/areas are still empty, set smart defaults
            if update_data.services is not None:
                missing_bio = not getattr(profile, "bio", None) or not str(profile.bio).strip()
                if "bio" not in basic_updates and missing_bio:
                    # Generate a bio like: "John is a New York-based yoga, tennis, and painting instructor."
                    try:
                        user_record = cast("User | None", self.user_repository.get_by_id(user_id))
                        first_name = getattr(user_record, "first_name", "") or ""
                        # Determine city from zip via geocoding
                        city = "New York"
                        try:
                            if user_record and getattr(user_record, "zip_code", None):
                                provider = create_geocoding_provider()
                                geocoded = anyio.run(provider.geocode, user_record.zip_code)
                                if geocoded and getattr(geocoded, "city", None):
                                    city = geocoded.city
                        except Exception:
                            pass

                        # Resolve skill names from catalog ids
                        skill_names: List[str] = []
                        try:
                            for svc in update_data.services or []:
                                catalog_entry = self.catalog_repository.get_by_id(
                                    svc.service_catalog_id
                                )
                                if catalog_entry and getattr(catalog_entry, "name", None):
                                    # Use lowercase for natural phrasing (e.g., 'yoga')
                                    skill_names.append(str(catalog_entry.name).strip().lower())
                        except Exception:
                            pass

                        def _oxford_join(items: List[str]) -> str:
                            if not items:
                                return ""
                            if len(items) == 1:
                                return items[0]
                            if len(items) == 2:
                                return f"{items[0]} and {items[1]}"
                            return ", ".join(items[:-1]) + f", and {items[-1]}"

                        skills_phrase = _oxford_join(skill_names)
                        if skills_phrase:
                            basic_updates[
                                "bio"
                            ] = f"{first_name} is a {city}-based {skills_phrase} instructor."
                        else:
                            basic_updates["bio"] = f"{first_name} is a {city}-based instructor."
                    except Exception:
                        # Last-resort fallback
                        basic_updates["bio"] = "Experienced instructor"

            if basic_updates:
                self.profile_repository.update(profile.id, **basic_updates)

            # Handle service updates if provided
            if update_data.services is not None:
                self._update_services(profile.id, update_data.services)

            # Replace preferred teaching locations if provided
            if update_data.preferred_teaching_locations is not None:
                self._replace_preferred_places(
                    instructor_id=user_id,
                    kind="teaching_location",
                    items=update_data.preferred_teaching_locations,
                )

            # Replace preferred public spaces if provided
            if update_data.preferred_public_spaces is not None:
                self._replace_preferred_places(
                    instructor_id=user_id,
                    kind="public_space",
                    items=update_data.preferred_public_spaces,
                )

        # Invalidate caches
        if self.cache_service:
            self._invalidate_instructor_caches(user_id)

        # Return fresh data
        return self.get_instructor_profile(user_id)

    @BaseService.measure_operation("delete_instructor_profile")
    def delete_instructor_profile(self, user_id: str) -> None:
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
            self.service_repository.flush()

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

        try:
            from .availability_service import AvailabilityService

            availability_service = AvailabilityService(self.db)
            purged = availability_service.delete_orphan_availability_for_instructor(
                user_id, keep_days_with_bookings=True
            )
            logger.info(
                "instructor_delete: purged_orphan_days=%s instructor_id=%s", purged, user_id
            )
        except Exception as cleanup_error:  # pragma: no cover - defensive log
            logger.warning(
                "instructor_delete: failed to purge orphan availability for %s (%s)",
                user_id,
                cleanup_error,
            )

    @BaseService.measure_operation("instructor.go_live")
    def go_live(self, user_id: str) -> InstructorProfile:
        """Activate instructor profile if prerequisites are met."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        config_service = ConfigService(self.db)
        pricing_service = PricingService(self.db)
        stripe_service = StripeService(
            self.db, config_service=config_service, pricing_service=pricing_service
        )
        connect_status = (
            stripe_service.check_account_status(profile.id)
            if profile.id
            else {"has_account": False, "onboarding_completed": False}
        )

        skills_ok = bool(getattr(profile, "skills_configured", False))
        identity_ok = bool(getattr(profile, "identity_verified_at", None))
        connect_ok = bool(connect_status.get("onboarding_completed"))
        bgc_ok = (getattr(profile, "bgc_status", "") or "").lower() == "passed"

        missing: list[str] = []
        if not skills_ok:
            missing.append("skills")
        if not identity_ok:
            missing.append("identity")
        if not connect_ok:
            missing.append("stripe_connect")
        if not bgc_ok:
            missing.append("background_check")

        if missing:
            raise BusinessRuleException(
                "Prerequisites not met",
                code="GO_LIVE_PREREQUISITES",
                details={"missing": missing},
            )

        with self.transaction():
            if not getattr(profile, "onboarding_completed_at", None):
                updated_profile = self.profile_repository.update(
                    profile.id,
                    is_live=True,
                    onboarding_completed_at=datetime.now(timezone.utc),
                    skills_configured=True
                    if not getattr(profile, "skills_configured", False)
                    else profile.skills_configured,
                )
            else:
                updated_profile = self.profile_repository.update(profile.id, is_live=True)

        if updated_profile is None:
            raise ServiceException("Failed to update instructor profile", code="update_failed")

        return updated_profile

    # Private helper methods

    def _validate_catalog_ids(self, catalog_ids: List[str]) -> None:
        """
        Validate that all catalog IDs exist in the database.

        Args:
            catalog_ids: List of catalog IDs to validate

        Raises:
            ValidationException: If any catalog ID is invalid
        """
        # Use repository to check existence
        valid_ids: Set[str] = set()
        for catalog_id in catalog_ids:
            if self.catalog_repository.exists(id=catalog_id, is_active=True):
                valid_ids.add(catalog_id)

        # Check for invalid IDs
        invalid_ids = set(catalog_ids) - valid_ids
        if invalid_ids:
            raise BusinessRuleException(
                f"Invalid service catalog IDs: {', '.join(map(str, invalid_ids))}"
            )

    def _update_services(self, profile_id: str, services_data: List[ServiceCreate]) -> None:
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
        services_by_catalog_id = {
            service.service_catalog_id: service for service in existing_services
        }

        # Track which services are in the update
        updated_catalog_ids: Set[str] = set()

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
                    catalog_name = (
                        service.catalog_entry.name if service.catalog_entry else "Unknown"
                    )
                    logger.info(
                        f"Soft deleted service '{catalog_name}' (ID: {service.id}) "
                        f"- has existing bookings"
                    )
                else:
                    # Hard delete
                    self.service_repository.delete(service.id)
                    catalog_name = (
                        service.catalog_entry.name if service.catalog_entry else "Unknown"
                    )
                    logger.info(
                        f"Hard deleted service '{catalog_name}' (ID: {service.id}) "
                        f"- no bookings"
                    )

        # Update skills_configured based on whether services exist after update
        has_active_services = bool(services_data)
        self.profile_repository.update(profile_id, skills_configured=has_active_services)

    def _replace_preferred_places(
        self,
        instructor_id: str,
        kind: str,
        items: Sequence[PreferredTeachingLocationIn | PreferredPublicSpaceIn],
    ) -> None:
        """Replace preferred place rows for a given instructor/kind atomically."""

        normalized: list[tuple[str, Optional[str]]] = []
        seen_addresses: set[str] = set()

        for item in items:
            address = item.address.strip()
            key = address.lower()
            if key in seen_addresses:
                raise BusinessRuleException(
                    "Duplicate addresses are not allowed for preferred places"
                )
            seen_addresses.add(key)

            label: Optional[str] = getattr(item, "label", None)
            if label is not None:
                label = label.strip()
                if not label:
                    label = None

            normalized.append((address, label))

        if len(normalized) > 2:
            raise BusinessRuleException("At most two preferred places per category are allowed")

        self.preferred_place_repository.delete_for_kind(instructor_id, kind)
        # Clear identity map to avoid stale preferred_places during the same session
        self.preferred_place_repository.flush()
        self.db.expire_all()

        for position, (address, label) in enumerate(normalized):
            self.preferred_place_repository.create_for_kind(
                instructor_id=instructor_id,
                kind=kind,
                address=address,
                label=label,
                position=position,
            )

    def _profile_to_dict(
        self, profile: InstructorProfile, include_inactive_services: bool = False
    ) -> Dict[str, Any]:
        """
        Convert instructor profile to dictionary.

        Args:
            profile: InstructorProfile ORM object
            include_inactive_services: Whether to include inactive services

        Returns:
            Dictionary representation of profile
        """
        svcs_source = getattr(profile, "services", None)
        if svcs_source is None:
            svcs_source = getattr(profile, "instructor_services", []) or []
        if isinstance(svcs_source, Mock):
            services: list[Any] = []
        else:
            try:
                services = list(svcs_source or [])
            except TypeError:
                services = []

        if not include_inactive_services:
            services = [s for s in services if getattr(s, "is_active", True)]
        user = getattr(profile, "user", None)
        preferred_places: Sequence[InstructorPreferredPlace]
        if user is not None and hasattr(user, "preferred_places"):
            raw_places = getattr(user, "preferred_places", None)
            try:
                preferred_places = list(raw_places or [])
            except TypeError:
                preferred_places = []
        else:
            preferred_places = self.preferred_place_repository.list_for_instructor(profile.user_id)

        teaching_locations: List[Dict[str, Any]] = []
        public_spaces: List[Dict[str, Any]] = []

        if preferred_places:
            teaching_places = sorted(
                [p for p in preferred_places if p.kind == "teaching_location"],
                key=lambda place: place.position,
            )
            public_places = sorted(
                [p for p in preferred_places if p.kind == "public_space"],
                key=lambda place: place.position,
            )

            for place in teaching_places:
                teaching_entry: Dict[str, Any] = {"address": place.address}
                if place.label:
                    teaching_entry["label"] = place.label
                teaching_locations.append(teaching_entry)

            for place in public_places:
                public_entry: Dict[str, Any] = {"address": place.address}
                if place.label:
                    public_entry["label"] = place.label
                public_spaces.append(public_entry)

        service_area_records = []
        if profile.user and hasattr(profile.user, "service_areas"):
            service_area_records = list(profile.user.service_areas)
        else:
            service_area_records = self.service_area_repository.list_for_instructor(profile.user_id)
        service_area_neighborhoods: list[dict[str, Any]] = []
        boroughs: set[str] = set()

        for area in service_area_records:
            region = getattr(area, "neighborhood", None)
            region_code: Optional[str] = None
            region_name: Optional[str] = None
            borough: Optional[str] = None
            region_meta: Optional[dict[str, Any]] = None
            if region is not None:
                region_code = getattr(region, "region_code", None)
                region_name = getattr(region, "region_name", None)
                borough = getattr(region, "parent_region", None)
                meta_candidate = getattr(region, "region_metadata", None)
                if isinstance(meta_candidate, dict):
                    region_meta = meta_candidate
            if region_meta:
                region_code = (
                    region_code or region_meta.get("nta_code") or region_meta.get("ntacode")
                )
                region_name = region_name or region_meta.get("nta_name") or region_meta.get("name")
                borough = borough or region_meta.get("borough")

            if borough:
                boroughs.add(borough)

            service_area_neighborhoods.append(
                {
                    "neighborhood_id": area.neighborhood_id,
                    "ntacode": region_code,
                    "name": region_name,
                    "borough": borough,
                }
            )

        sorted_boroughs = sorted(boroughs)
        if sorted_boroughs:
            if len(sorted_boroughs) <= 2:
                service_area_summary = ", ".join(sorted_boroughs)
            else:
                service_area_summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
        else:
            service_area_summary = ""

        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "bio": profile.bio,
            "years_experience": profile.years_experience,
            "min_advance_booking_hours": profile.min_advance_booking_hours,
            "buffer_time_minutes": profile.buffer_time_minutes,
            "preferred_teaching_locations": teaching_locations,
            "preferred_public_spaces": public_spaces,
            "service_area_neighborhoods": service_area_neighborhoods,
            "service_area_boroughs": sorted_boroughs,
            "service_area_summary": service_area_summary,
            # Onboarding status
            "skills_configured": getattr(profile, "skills_configured", False),
            "identity_verified_at": getattr(profile, "identity_verified_at", None),
            "background_check_uploaded_at": getattr(profile, "background_check_uploaded_at", None),
            "onboarding_completed_at": getattr(profile, "onboarding_completed_at", None),
            "is_live": getattr(profile, "is_live", False),
            "is_founding_instructor": getattr(profile, "is_founding_instructor", False),
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "user": {
                "id": profile.user.id,
                "first_name": profile.user.first_name,
                "last_initial": profile.user.last_name[0] if profile.user.last_name else "",
                # No email or full last_name for privacy protection
            }
            if hasattr(profile, "user") and profile.user
            else None,
            "services": [
                {
                    "id": service.id,
                    "service_catalog_id": service.service_catalog_id,
                    "service_catalog_name": service.catalog_entry.name
                    if service.catalog_entry
                    else "Unknown Service",
                    "name": service.catalog_entry.name
                    if service.catalog_entry
                    else "Unknown Service",
                    "hourly_rate": service.hourly_rate,
                    "description": service.description,
                    "age_groups": service.age_groups,
                    "levels_taught": service.levels_taught,
                    "location_types": service.location_types,
                    "duration_options": service.duration_options,
                    "is_active": service.is_active,
                }
                for service in sorted(services, key=lambda s: s.service_catalog_id)
            ],
        }

    def _invalidate_instructor_caches(self, user_id: str) -> None:
        """Invalidate all caches related to an instructor."""
        if not self.cache_service:
            return

        # Clear profile caches (both internal and public)
        self.cache_service.delete(f"instructor:profile:{user_id}")
        self.cache_service.delete(f"instructor:public:{user_id}")

        # Clear availability caches
        self.cache_service.invalidate_instructor_availability(user_id)

        # Clear any listing caches
        self.cache_service.delete_pattern("instructors:list:*")
        self.cache_service.clear_prefix("catalog:services:")
        self.cache_service.clear_prefix("catalog:top-services:")
        self.cache_service.clear_prefix("catalog:all-services")
        self.cache_service.clear_prefix("catalog:kids-available")
        self.cache_service.clear_prefix("service_catalog:list")
        self.cache_service.clear_prefix("service_catalog:search")
        self.cache_service.clear_prefix("service_catalog:trending")

        logger.debug(f"Invalidated caches for instructor {user_id}")

    # Catalog-aware methods
    @BaseService.measure_operation("get_available_catalog_services")
    def get_available_catalog_services(
        self, category_slug: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
        debug_mode = os.getenv("AVAILABILITY_PERF_DEBUG") == "1"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                if debug_mode:
                    logger.debug("[catalog] cache hit for %s", cache_key)
                return cast(JsonList, cached_result)

        # Get category ID if slug provided
        category_id = None
        if category_slug:
            category = self.category_repository.find_one_by(slug=category_slug)
            if not category:
                raise NotFoundException(f"Category '{category_slug}' not found")
            category_id = category.id

        # Use optimized repository method with eager loading
        services = self.catalog_repository.get_active_services_with_categories(
            category_id=category_id
        )

        # Convert to dictionaries (no N+1 queries since categories are loaded)
        result = [self._catalog_service_to_dict(service) for service in services]

        if debug_mode:
            logger.debug("[catalog] cache miss for %s; storing %d entries", cache_key, len(result))

        # Cache for 5 minutes (300 seconds)
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            if debug_mode:
                logger.debug("[catalog] cached %d entries for 5 minutes", len(result))

        return result

    @BaseService.measure_operation("get_service_categories")
    def get_service_categories(self) -> List[Dict[str, Any]]:
        """Get all service categories (cached for 1 hour)."""
        # Try cache first (1-hour TTL for categories - they rarely change)
        cache_key = "categories:all"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                logger.debug("Cache hit for service categories")
                return cast(JsonList, cached)

        categories = self.category_repository.get_all()
        result = [
            {
                "id": cat.id,
                "name": cat.name,
                "subtitle": getattr(cat, "subtitle", None),
                "slug": cat.slug,
                "description": cat.description,
                "display_order": cat.display_order,
                "icon_name": getattr(cat, "icon_name", None),
            }
            for cat in sorted(categories, key=lambda x: x.display_order)
        ]

        # Cache for 1 hour (3600 seconds)
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
            logger.debug("Cached service categories for 1 hour")

        return result

    @BaseService.measure_operation("create_instructor_service_from_catalog")
    def create_instructor_service_from_catalog(
        self,
        instructor_id: str,
        catalog_service_id: str,
        hourly_rate: float,
        custom_description: Optional[str] = None,
        duration_options: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
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

    def _catalog_service_to_dict(self, service: ServiceCatalog) -> Dict[str, Any]:
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

    def _instructor_service_to_dict(self, service: Service) -> Dict[str, Any]:
        """Convert instructor service to dictionary with catalog info."""
        catalog_name = service.catalog_entry.name if service.catalog_entry else "Unknown Service"
        return {
            "id": service.id,
            "catalog_service_id": service.service_catalog_id,
            "service_catalog_name": catalog_name,
            "name": catalog_name,
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
    ) -> List[Dict[str, Any]]:
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
            embedding=query_embedding,
            limit=limit * 2,
            threshold=threshold,  # Get more to filter
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
    def get_popular_services(self, limit: int = 10, days: int = 30) -> List[Dict[str, Any]]:
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
    def get_trending_services(self, limit: int = 10) -> List[Dict[str, Any]]:
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
    ) -> Dict[str, Any]:
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
                instructors = self._get_instructors_for_service_in_price_range(
                    service.id, min_price, max_price
                )
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
                "price_range": {"min": min_price, "max": max_price}
                if min_price or max_price
                else None,
            },
            "pagination": {"skip": skip, "limit": limit, "count": len(results)},
        }

        return {"services": results, "metadata": metadata}

    def _get_service_analytics(self, service_catalog_id: str) -> Dict[str, Any]:
        """Get or create analytics for a service."""
        analytics = self.analytics_repository.get_or_create(service_catalog_id)
        return analytics.to_dict() if analytics else {}

    def _get_instructors_for_service_in_price_range(
        self, service_catalog_id: str, min_price: Optional[float], max_price: Optional[float]
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

    def _calculate_price_range(self, instructor_services: List[Service]) -> Dict[str, Any]:
        """Calculate actual price range from instructor services."""
        if not instructor_services:
            return {"min": None, "max": None}

        prices = [s.hourly_rate for s in instructor_services]
        return {"min": min(prices), "max": max(prices), "avg": sum(prices) / len(prices)}

    @BaseService.measure_operation("get_top_services_per_category")
    def get_top_services_per_category(self, limit: int = 7) -> Dict[str, Any]:
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
                logger.debug("Cache hit for top services per category")
                return cast(JsonDict, cached_result)

        # Get all categories
        categories = self.category_repository.get_all()

        categories_data: JsonList = []
        result: JsonDict = {
            "categories": categories_data,
            "metadata": {
                "services_per_category": limit,
                "total_categories": len(categories),
                "cached_for_seconds": 3600,  # 1 hour
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # For each category, get top N services by display_order
        for category in sorted(categories, key=lambda c: c.display_order):
            # Always create category data - never hide categories
            services_list: JsonList = []
            category_data: JsonDict = {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "icon_name": category.icon_name,
                "services": services_list,
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
                    services_list.append(
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
            categories_data.append(category_data)

        # Cache for 1 hour
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
            logger.debug(f"Cached top {limit} services per category for 1 hour")

        return result

    @BaseService.measure_operation("get_all_services_with_instructors")
    def get_all_services_with_instructors(self) -> Dict[str, Any]:
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
                logger.debug("Cache hit for all services with instructors")
                return cast(JsonDict, cached_result)

        # Get all categories
        categories = self.category_repository.get_all()

        categories_data: JsonList = []
        result: JsonDict = {
            "categories": categories_data,
            "metadata": {
                "total_categories": len(categories),
                "cached_for_seconds": 300,  # 5 minutes
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # For each category, get ALL services (not just top N)
        for category in sorted(categories, key=lambda c: c.display_order):
            services_list: JsonList = []
            category_data: JsonDict = {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "subtitle": category.subtitle if hasattr(category, "subtitle") else "",
                "description": category.description,
                "icon_name": category.icon_name,
                "services": services_list,
            }

            # Get ALL services for this category (ordered by display_order)
            services = self.catalog_repository.get_active_services_with_categories(
                category_id=category.id,
                limit=None,  # No limit - get all services
            )

            # Collect services with analytics data
            services_with_analytics: JsonList = []
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
                    instructor_services = self._get_instructors_for_service_in_price_range(
                        service.id, None, None
                    )
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
                services_list.append(service_data)

            # Always add the category, even if empty
            categories_data.append(category_data)

        # Add total service count to metadata
        total_services = sum(len(cat["services"]) for cat in categories_data)
        metadata = cast(JsonDict, result["metadata"])
        metadata["total_services"] = total_services

        # Cache for 5 minutes
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            logger.debug(f"Cached all {total_services} services with instructor data for 5 minutes")

        return result

    @BaseService.measure_operation("get_kids_available_services")
    def get_kids_available_services(self) -> List[Dict[str, Any]]:
        """
        Return catalog services that have at least one active instructor offering to kids.

        Uses a short-lived cache (5 minutes) similar to catalog endpoints.
        """
        cache_key = "catalog:kids-available"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonList, cached)

        # Delegate to repository per repository pattern
        result = cast(JsonList, self.catalog_repository.get_services_available_for_kids_minimal())

        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)

        return result


# Dependency injection
def get_instructor_service(
    db: Session, cache_service: Optional[CacheServiceSyncAdapter] = None
) -> InstructorService:
    """Get instructor service instance for dependency injection."""
    return InstructorService(db, cache_service)
