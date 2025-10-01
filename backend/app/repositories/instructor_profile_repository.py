# backend/app/repositories/instructor_profile_repository.py
"""
Instructor Profile Repository for InstaInstru Platform

Handles all data access operations for instructor profiles with
optimized queries for relationships (user and services).

This repository eliminates N+1 query problems by using eager loading
for commonly accessed relationships.
"""

from datetime import datetime
import logging
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, Session, selectinload

from ..core.bgc_policy import must_be_verified_for_public
from ..core.exceptions import RepositoryException
from ..models.address import InstructorServiceArea, RegionBoundary
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class InstructorProfileRepository(BaseRepository[InstructorProfile]):
    """
    Repository for instructor profile data access.

    Provides optimized queries with eager loading for user and services
    relationships to prevent N+1 query problems.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorProfile model."""
        super().__init__(db, InstructorProfile)
        self.logger = logging.getLogger(__name__)

    def _apply_verified_filter(self, query: Query) -> Query:
        """Restrict results to verified instructors when required."""

        if must_be_verified_for_public():
            query = query.filter(InstructorProfile.bgc_status == "passed")
        return query

    def get_by_user_id(self, user_id: str) -> Optional[InstructorProfile]:
        """
        Get instructor profile by user ID.

        Used by PrivacyService for data export and deletion.

        Args:
            user_id: The user ID to look up

        Returns:
            InstructorProfile if found, None otherwise
        """
        return cast(
            Optional[InstructorProfile],
            self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first(),
        )

    def get_all_with_details(
        self, skip: int = 0, limit: int = 100, include_inactive_services: bool = False
    ) -> List[InstructorProfile]:
        """
        Get all instructor profiles with user and services eager loaded.

        This method solves the N+1 query problem by loading all related
        data in a single query with joins.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        UPDATED: Now filters to only include instructors with active account status.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            List of InstructorProfile objects with all relationships loaded
        """
        try:
            query = self.db.query(InstructorProfile)
            query = query.join(InstructorProfile.user)
            query = query.join(User.service_areas, isouter=True)
            query = query.join(InstructorServiceArea.neighborhood, isouter=True)
            query = query.filter(User.account_status == "active")
            query = self._apply_verified_filter(query)
            query = query.options(
                selectinload(InstructorProfile.user)
                .selectinload(User.service_areas)
                .selectinload(InstructorServiceArea.neighborhood),
                selectinload(InstructorProfile.instructor_services).selectinload(
                    Service.catalog_entry
                ),
            )
            query = query.order_by(InstructorProfile.id)
            query = query.distinct().offset(skip).limit(limit)

            profiles = cast(List[InstructorProfile], query.all())

            # Return profiles with all services loaded
            # Let the service layer handle filtering
            return profiles

        except Exception as e:
            self.logger.error(f"Error getting all profiles with details: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profiles: {str(e)}")

    def get_by_user_id_with_details(
        self, user_id: str, include_inactive_services: bool = False
    ) -> Optional[InstructorProfile]:
        """
        Get a single instructor profile by user_id with all relationships loaded.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        Args:
            user_id: The user ID
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            InstructorProfile with all relationships loaded, or None if not found
        """
        try:
            profile = cast(
                Optional[InstructorProfile],
                (
                    self.db.query(InstructorProfile)
                    .join(InstructorProfile.user)
                    .join(User.service_areas, isouter=True)
                    .join(InstructorServiceArea.neighborhood, isouter=True)
                    .options(
                        selectinload(InstructorProfile.user)
                        .selectinload(User.service_areas)
                        .selectinload(InstructorServiceArea.neighborhood),
                        selectinload(InstructorProfile.instructor_services).selectinload(
                            Service.catalog_entry
                        ),
                    )
                    .filter(InstructorProfile.user_id == user_id)
                    .first()
                ),
            )

            # Return profile with all services loaded
            # Let the service layer handle filtering
            return profile

        except Exception as e:
            self.logger.error(f"Error getting profile by user_id: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profile: {str(e)}")

    def get_profiles_by_area(
        self, area: str, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """
        Get instructor profiles that service a specific area.

        UPDATED: Now filters to only include instructors with active account status.

        Args:
            area: The area to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles that service the area
        """
        try:
            base_query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .filter(User.account_status == "active")
            )
            base_query = self._apply_verified_filter(base_query)

            filtered_query = self._apply_area_filters(base_query, area)

            return cast(
                List[InstructorProfile],
                filtered_query.options(
                    selectinload(InstructorProfile.user),
                    selectinload(InstructorProfile.user)
                    .selectinload(User.service_areas)
                    .selectinload(InstructorServiceArea.neighborhood),
                    selectinload(InstructorProfile.instructor_services).selectinload(
                        Service.catalog_entry
                    ),
                )
                .distinct()
                .offset(skip)
                .limit(limit)
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by area: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by area: {str(e)}")

    def get_profiles_by_experience(
        self, min_years: int, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """
        Get instructor profiles with minimum years of experience.

        Args:
            min_years: Minimum years of experience
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles with sufficient experience
        """
        try:
            return cast(
                List[InstructorProfile],
                (
                    self.db.query(InstructorProfile)
                    .join(InstructorProfile.user)
                    .join(User.service_areas, isouter=True)
                    .join(InstructorServiceArea.neighborhood, isouter=True)
                    .filter(User.account_status == "active")
                    .options(
                        selectinload(InstructorProfile.user),
                        selectinload(InstructorProfile.user)
                        .selectinload(User.service_areas)
                        .selectinload(InstructorServiceArea.neighborhood),
                        selectinload(InstructorProfile.instructor_services).selectinload(
                            Service.catalog_entry
                        ),
                    )
                    .filter(InstructorProfile.years_experience >= min_years)
                    .distinct()
                    .offset(skip)
                    .limit(limit)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by experience: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by experience: {str(e)}")

    def count_profiles(self) -> int:
        """
        Count total number of instructor profiles.

        Returns:
            Number of profiles
        """
        try:
            return cast(int, self.db.query(InstructorProfile).count())
        except Exception as e:
            self.logger.error(f"Error counting active profiles: {str(e)}")
            raise RepositoryException(f"Failed to count profiles: {str(e)}")

    def update_bgc(
        self,
        instructor_id: str,
        *,
        status: str,
        report_id: str | None,
        env: str,
    ) -> None:
        """Persist background check metadata for a specific instructor profile."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_status = status
            profile.bgc_report_id = report_id
            profile.bgc_env = env

            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for instructor {instructor_id}"
            ) from exc

    def update_bgc_by_report_id(
        self,
        report_id: str,
        *,
        status: str,
        completed_at: datetime | None = None,
    ) -> int:
        """Update background check fields based on a Checkr report identifier."""

        try:
            profile = self.find_one_by(bgc_report_id=report_id)
            if not profile:
                return 0

            profile.bgc_status = status
            if completed_at is not None:
                profile.bgc_completed_at = completed_at

            self.db.flush()
            return 1
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for report %s: %s",
                report_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for report {report_id}"
            ) from exc

    def _apply_area_filters(self, query: Any, area: str) -> Any:
        """Apply borough/neighborhood filters to the provided query."""

        normalized = (area or "").strip()
        if not normalized:
            return query

        normalized_lower = normalized.lower()

        return (
            query.join(User.service_areas)
            .join(InstructorServiceArea.neighborhood)
            .filter(
                or_(
                    func.lower(RegionBoundary.parent_region) == normalized_lower,
                    func.lower(RegionBoundary.region_name) == normalized_lower,
                    func.lower(RegionBoundary.region_code) == normalized_lower,
                )
            )
        )

    def find_by_filters(
        self,
        search: Optional[str] = None,
        service_catalog_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        age_group: Optional[str] = None,
        boroughs: Optional[Sequence[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[InstructorProfile]:
        """
        Find instructor profiles based on multiple filter criteria.

        All filters are applied with AND logic - profiles must match ALL provided filters.

        Args:
            search: Text search across user name, bio, and service skills (case-insensitive)
            service_catalog_id: Filter by specific service catalog ID
            min_price: Minimum hourly rate filter
            max_price: Maximum hourly rate filter
            boroughs: Optional collection of borough names to filter by (case-insensitive)
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            List of InstructorProfile objects matching all provided filters
        """
        import time

        start_time = time.time()

        try:
            # Start with base query including eager loading
            query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .join(User.service_areas, isouter=True)
                .join(InstructorServiceArea.neighborhood, isouter=True)
                .join(Service, InstructorProfile.id == Service.instructor_profile_id)
                .join(ServiceCatalog, Service.service_catalog_id == ServiceCatalog.id)
                .join(ServiceCategory, ServiceCatalog.category_id == ServiceCategory.id)
                .options(
                    selectinload(InstructorProfile.user),
                    selectinload(InstructorProfile.user)
                    .selectinload(User.service_areas)
                    .selectinload(InstructorServiceArea.neighborhood),
                    selectinload(InstructorProfile.instructor_services).selectinload(
                        Service.catalog_entry
                    ),
                )
            )

            if boroughs:
                normalized_boroughs = [
                    b.lower() for b in boroughs if isinstance(b, str) and b.strip()
                ]
                if normalized_boroughs:
                    query = query.filter(
                        func.lower(RegionBoundary.parent_region).in_(normalized_boroughs)
                    )

            # Apply search filter if provided
            if search:
                search_term = f"%{search}%"
                search.lower()

                # Build search conditions
                search_conditions = [
                    func.concat(User.first_name, " ", User.last_name).ilike(search_term),
                    InstructorProfile.bio.ilike(search_term),
                    ServiceCatalog.name.ilike(search_term),
                    ServiceCatalog.description.ilike(search_term),
                    ServiceCategory.name.ilike(search_term),
                ]

                # Only use array_to_string for PostgreSQL
                # Check if we're using PostgreSQL by looking at the dialect
                if hasattr(self.db.bind, "dialect") and self.db.bind.dialect.name == "postgresql":
                    search_conditions.append(
                        func.array_to_string(ServiceCatalog.search_terms, " ").ilike(search_term)
                    )

                query = query.filter(or_(*search_conditions))

            # Apply service catalog filter if provided
            if service_catalog_id:
                query = query.filter(Service.service_catalog_id == service_catalog_id)

            # Apply price range filters if provided
            if min_price is not None:
                query = query.filter(Service.hourly_rate >= min_price)

            if max_price is not None:
                query = query.filter(Service.hourly_rate <= max_price)

            # Apply age group filter if provided
            if age_group:
                # Use PostgreSQL array_position for reliable membership check on arrays
                if hasattr(self.db.bind, "dialect") and self.db.bind.dialect.name == "postgresql":
                    query = query.filter(
                        func.array_position(Service.age_groups, age_group).isnot(None)
                    )
                else:
                    like_pattern = f'%"{age_group}"%'
                    query = query.filter(Service.age_groups.like(like_pattern))

            # Ensure we only get active services and active instructors
            query = query.filter(Service.is_active == True)
            query = query.filter(User.account_status == "active")
            query = self._apply_verified_filter(query)

            # Remove duplicates (since joins can create multiple rows per profile)
            # and apply pagination
            profiles = cast(
                List[InstructorProfile],
                query.distinct().offset(skip).limit(limit).all(),
            )

            # Log query performance
            query_time = time.time() - start_time
            self.logger.info(
                f"Filter query completed in {query_time:.3f}s - "
                f"Filters: search={bool(search)}, service_catalog_id={bool(service_catalog_id)}, "
                f"price_range={bool(min_price or max_price)}, "
                f"Results: {len(profiles)} profiles"
            )

            # Log slow queries for optimization
            if query_time > 0.5:  # 500ms threshold
                self.logger.warning(
                    f"Slow filter query detected ({query_time:.3f}s) - "
                    f"Consider adding indexes for: "
                    f"{'search' if search else ''} "
                    f"{'service_catalog_id' if service_catalog_id else ''} "
                    f"{'price' if min_price or max_price else ''}"
                )

            return profiles

        except Exception as e:
            self.logger.error(f"Error finding profiles by filters: {str(e)}")
            raise RepositoryException(f"Failed to find profiles by filters: {str(e)}")

    # Override the base eager loading method
    def _apply_eager_loading(self, query: Any) -> Any:
        """
        Apply eager loading for commonly accessed relationships.

        This is called by BaseRepository methods like get_by_id()
        when load_relationships=True.
        """
        return query.options(
            selectinload(InstructorProfile.user)
            .selectinload(User.service_areas)
            .selectinload(InstructorServiceArea.neighborhood),
            selectinload(InstructorProfile.instructor_services).selectinload(Service.catalog_entry),
        )
