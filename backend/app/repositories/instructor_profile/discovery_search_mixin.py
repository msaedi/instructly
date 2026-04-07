"""Discovery and search queries for instructor profiles."""

from __future__ import annotations

import time
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.selectable import Subquery

from ...core.exceptions import RepositoryException
from ...models.address import InstructorServiceArea, RegionBoundary
from ...models.instructor import InstructorProfile
from ...models.service_catalog import (
    InstructorService as Service,
    ServiceCatalog,
    ServiceCategory,
    ServiceFormatPrice,
)
from ...models.subcategory import ServiceSubcategory
from ...models.user import User
from .mixin_base import InstructorProfileRepositoryMixinBase


class DiscoverySearchMixin(InstructorProfileRepositoryMixinBase):
    """Multi-criteria search and discovery helpers."""

    def _service_min_price_subquery(self) -> Subquery:
        """Subquery providing min hourly rate for each instructor service."""
        return cast(
            Subquery,
            self.db.query(
                ServiceFormatPrice.service_id.label("service_id"),
                func.min(ServiceFormatPrice.hourly_rate).label("min_hourly_rate"),
            )
            .group_by(ServiceFormatPrice.service_id)
            .subquery(),
        )

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

    def get_profiles_by_area(
        self, area: str, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """
        Get instructor profiles that service a specific area.

        UPDATED: Now filters to only include instructors with active account status.
        """
        try:
            base_query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .filter(User.account_status == "active")
            )
            base_query = self._apply_public_visibility(base_query)

            filtered_query = self._apply_area_filters(base_query, area)

            ordered_query = filtered_query.order_by(InstructorProfile.id.asc())

            return cast(
                List[InstructorProfile],
                ordered_query.options(
                    selectinload(InstructorProfile.user),
                    selectinload(InstructorProfile.user)
                    .selectinload(User.service_areas)
                    .selectinload(InstructorServiceArea.neighborhood),
                    selectinload(InstructorProfile.instructor_services).selectinload(
                        Service.catalog_entry
                    ),
                )
                .order_by(InstructorProfile.id.asc())
                .distinct()
                .offset(skip)
                .limit(limit)
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting profiles by area: %s", str(e))
            raise RepositoryException(f"Failed to get profiles by area: {str(e)}")

    def get_profiles_by_experience(
        self, min_years: int, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """Get instructor profiles with minimum years of experience."""
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
                    .order_by(InstructorProfile.id.asc())
                    .distinct()
                    .offset(skip)
                    .limit(limit)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Error getting profiles by experience: %s", str(e))
            raise RepositoryException(f"Failed to get profiles by experience: {str(e)}")

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
        """
        start_time = time.time()

        try:
            service_min_price_sq = self._service_min_price_subquery()
            query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .join(User.service_areas, isouter=True)
                .join(InstructorServiceArea.neighborhood, isouter=True)
                .join(Service, InstructorProfile.id == Service.instructor_profile_id)
                .outerjoin(service_min_price_sq, service_min_price_sq.c.service_id == Service.id)
                .join(ServiceCatalog, Service.service_catalog_id == ServiceCatalog.id)
                .join(ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id)
                .join(ServiceCategory, ServiceSubcategory.category_id == ServiceCategory.id)
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

            if search:
                search_term = f"%{search}%"
                search.lower()

                search_conditions = [
                    func.concat(User.first_name, " ", User.last_name).ilike(search_term),
                    InstructorProfile.bio.ilike(search_term),
                    ServiceCatalog.name.ilike(search_term),
                    ServiceCatalog.description.ilike(search_term),
                    ServiceCategory.name.ilike(search_term),
                ]

                if self.dialect_name == "postgresql":
                    search_conditions.append(
                        func.array_to_string(ServiceCatalog.search_terms, " ").ilike(search_term)
                    )

                query = query.filter(or_(*search_conditions))

            if service_catalog_id:
                query = query.filter(Service.service_catalog_id == service_catalog_id)

            if min_price is not None:
                query = query.filter(service_min_price_sq.c.min_hourly_rate >= min_price)

            if max_price is not None:
                query = query.filter(service_min_price_sq.c.min_hourly_rate <= max_price)

            if age_group:
                if self.dialect_name == "postgresql":
                    query = query.filter(
                        func.array_position(Service.age_groups, age_group).isnot(None)
                    )
                else:
                    like_pattern = f'%"{age_group}"%'
                    query = query.filter(Service.age_groups.like(like_pattern))

            query = query.filter(Service.is_active == True)
            query = query.filter(User.account_status == "active")
            query = self._apply_public_visibility(query)
            query = query.order_by(InstructorProfile.id.asc())

            profiles = cast(
                List[InstructorProfile],
                query.distinct().offset(skip).limit(limit).all(),
            )

            query_time = time.time() - start_time
            self.logger.info(
                "Filter query completed in %ss - Filters: search=%s, service_catalog_id=%s, price_range=%s, Results: %s profiles",
                f"{query_time:.3f}",
                bool(search),
                bool(service_catalog_id),
                bool(min_price or max_price),
                len(profiles),
            )

            if query_time > 0.5:
                self.logger.warning(
                    "Slow filter query detected (%ss) - Consider adding indexes for: %s %s %s",
                    f"{query_time:.3f}",
                    "search" if search else "",
                    "service_catalog_id" if service_catalog_id else "",
                    "price" if min_price or max_price else "",
                )

            return profiles

        except Exception as e:
            self.logger.error("Error finding profiles by filters: %s", str(e))
            raise RepositoryException(f"Failed to find profiles by filters: {str(e)}")

    def find_by_service_ids(
        self,
        service_catalog_ids: Sequence[str],
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit_per_service: int = 10,
    ) -> dict[str, List[InstructorProfile]]:
        """
        Find instructor profiles for multiple services in a single query.

        This is an N+1 optimization method that fetches instructors for all
        requested services at once, instead of querying per service.
        """
        start_time = time.time()

        if not service_catalog_ids:
            return {}

        try:
            service_min_price_sq = self._service_min_price_subquery()
            query = (
                self.db.query(InstructorProfile, Service.service_catalog_id)
                .join(InstructorProfile.user)
                .join(User.service_areas, isouter=True)
                .join(InstructorServiceArea.neighborhood, isouter=True)
                .join(Service, InstructorProfile.id == Service.instructor_profile_id)
                .outerjoin(service_min_price_sq, service_min_price_sq.c.service_id == Service.id)
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

            query = query.filter(Service.service_catalog_id.in_(service_catalog_ids))

            if min_price is not None:
                query = query.filter(service_min_price_sq.c.min_hourly_rate >= min_price)
            if max_price is not None:
                query = query.filter(service_min_price_sq.c.min_hourly_rate <= max_price)

            query = query.filter(Service.is_active == True)
            query = query.filter(User.account_status == "active")
            query = self._apply_public_visibility(query)
            query = query.order_by(Service.service_catalog_id, InstructorProfile.id.asc())
            results = query.distinct().all()

            grouped: dict[str, List[InstructorProfile]] = {sid: [] for sid in service_catalog_ids}
            for profile, service_catalog_id in results:
                if service_catalog_id in grouped:
                    if len(grouped[service_catalog_id]) < limit_per_service:
                        grouped[service_catalog_id].append(profile)

            query_time = time.time() - start_time
            total_profiles = sum(len(v) for v in grouped.values())
            self.logger.info(
                "Batch service query completed in %ss - Services: %s, Results: %s profiles",
                f"{query_time:.3f}",
                len(service_catalog_ids),
                total_profiles,
            )

            if query_time > 0.5:
                self.logger.warning(
                    "Slow batch query detected (%ss) for %s services",
                    f"{query_time:.3f}",
                    len(service_catalog_ids),
                )

            return grouped

        except Exception as e:
            self.logger.error("Error in batch service query: %s", str(e))
            raise RepositoryException(f"Failed to find profiles by service IDs: {str(e)}")
