"""Instructor supply and pricing aggregation queries."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple, cast

from sqlalchemy import distinct
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import func

from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService, ServiceCatalog, ServiceFormatPrice
from ...models.user import User
from .mixin_base import ServiceCatalogRepositoryMixinBase
from .types import MinimalServiceInfo


class InstructorSupplyPricingMixin(ServiceCatalogRepositoryMixinBase):
    """Instructor supply and pricing aggregation queries."""

    def count_active_instructors_bulk(self, service_catalog_ids: List[str]) -> Dict[str, int]:
        """Count active instructors for multiple services in a single query."""
        if not service_catalog_ids:
            return {}

        query = (
            self.db.query(
                InstructorService.service_catalog_id,
                func.count(InstructorService.id).label("count"),
            )
            .join(
                InstructorProfile,
                InstructorProfile.id == InstructorService.instructor_profile_id,
            )
            .filter(
                InstructorService.service_catalog_id.in_(service_catalog_ids),
                InstructorProfile.is_live.is_(True),
            )
        )
        query = self._apply_instructor_service_active_filter(query)
        query = query.group_by(InstructorService.service_catalog_id)

        results = query.all()
        counts = {str(service_catalog_id): 0 for service_catalog_id in service_catalog_ids}
        counts.update({str(row.service_catalog_id): row.count for row in results})
        return counts

    def get_services_available_for_kids_minimal(self) -> List[MinimalServiceInfo]:
        """
        Return minimal info for catalog services that have at least one active instructor
        whose age_groups includes 'kids'.
        """
        try:
            query = (
                self.db.query(
                    distinct(ServiceCatalog.id).label("id"),
                    ServiceCatalog.name.label("name"),
                    ServiceCatalog.slug.label("slug"),
                )
                .join(InstructorService, InstructorService.service_catalog_id == ServiceCatalog.id)
                .join(
                    InstructorProfile,
                    InstructorService.instructor_profile_id == InstructorProfile.id,
                )
                .join(User, InstructorProfile.user_id == User.id)
                .filter(InstructorService.is_active == True)
                .filter(User.account_status == "active")
            )
            query = self._apply_instructor_service_active_filter(query)
            query = self._apply_active_catalog_predicate(query)

            if self.dialect_name == "postgresql":
                query = query.filter(
                    func.array_position(InstructorService.age_groups, "kids").isnot(None)
                )
            else:
                query = query.filter(InstructorService.age_groups.like('%"kids"%'))

            rows = cast(Sequence[Any], query.all())
            return [
                cast(MinimalServiceInfo, {"id": row.id, "name": row.name, "slug": row.slug})
                for row in rows
            ]
        except OperationalError:
            self.logger.error("db_connection_error_in_kids_services", exc_info=True)
            raise
        except Exception as exc:
            self.logger.warning(
                "kids_available_services_degraded",
                extra={"error": str(exc)},
                exc_info=True,
            )
            return []

    def get_bulk_price_ranges(self) -> Dict[str, Dict[str, Any]]:
        """
        Get min/max hourly rates per service_catalog_id in a single query.

        Only includes active instructor services from live instructor profiles.
        """
        rows = cast(
            Sequence[Tuple[str, Any, Any]],
            self.db.query(
                InstructorService.service_catalog_id,
                func.min(ServiceFormatPrice.hourly_rate).label("min_price"),
                func.max(ServiceFormatPrice.hourly_rate).label("max_price"),
            )
            .join(ServiceFormatPrice, ServiceFormatPrice.service_id == InstructorService.id)
            .join(
                InstructorProfile,
                InstructorProfile.id == InstructorService.instructor_profile_id,
            )
            .filter(
                InstructorService.is_active == True,
                InstructorProfile.is_live == True,
            )
            .group_by(InstructorService.service_catalog_id)
            .all(),
        )
        return {row[0]: {"min": float(row[1]), "max": float(row[2])} for row in rows}
