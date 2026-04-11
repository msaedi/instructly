"""Ranking and analytics-driven catalog queries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple, cast

from ...models.service_catalog import ServiceAnalytics, ServiceCatalog
from .mixin_base import ServiceCatalogRepositoryMixinBase
from .types import PopularServiceMetrics


class RankingAnalyticsMixin(ServiceCatalogRepositoryMixinBase):
    """Ranking and analytics-driven catalog queries."""

    def get_popular_services(self, limit: int = 10, days: int = 30) -> List[PopularServiceMetrics]:
        """Get most popular services based on analytics."""
        query = (
            self.db.query(ServiceCatalog, ServiceAnalytics)
            .join(ServiceAnalytics, ServiceCatalog.id == ServiceAnalytics.service_catalog_id)
            .filter(ServiceCatalog.is_active == True)
        )
        query = self._apply_active_catalog_predicate(query)

        if days == 7:
            query = query.order_by(ServiceAnalytics.booking_count_7d.desc())
        else:
            query = query.order_by(ServiceAnalytics.booking_count_30d.desc())

        results = cast(List[Tuple[ServiceCatalog, ServiceAnalytics]], query.limit(limit).all())

        return [
            cast(
                PopularServiceMetrics,
                {
                    "service": service,
                    "analytics": analytics,
                    "popularity_score": float(getattr(analytics, "demand_score", 0.0)),
                },
            )
            for service, analytics in results
        ]

    def get_trending_services(self, limit: int = 10) -> List[ServiceCatalog]:
        """Get services that are trending upward in demand."""
        trend_subquery = self.db.query(
            ServiceAnalytics.service_catalog_id,
            (ServiceAnalytics.search_count_7d / 7.0).label("avg_7d"),
            (ServiceAnalytics.search_count_30d / 30.0).label("avg_30d"),
        ).subquery()

        query = (
            self.db.query(ServiceCatalog)
            .join(trend_subquery, ServiceCatalog.id == trend_subquery.c.service_catalog_id)
            .filter(
                ServiceCatalog.is_active == True,
                trend_subquery.c.avg_7d > trend_subquery.c.avg_30d * 1.2,
            )
            .order_by((trend_subquery.c.avg_7d - trend_subquery.c.avg_30d).desc())
        )
        query = self._apply_active_catalog_predicate(query)

        return cast(List[ServiceCatalog], query.limit(limit).all())

    def update_display_order_by_popularity(self) -> int:
        """Update display_order based on popularity metrics."""
        query = (
            self.db.query(
                ServiceCatalog.id,
                ServiceAnalytics.booking_count_30d,
                ServiceAnalytics.search_count_30d,
            )
            .join(ServiceAnalytics, ServiceCatalog.id == ServiceAnalytics.service_catalog_id)
            .filter(ServiceCatalog.is_active == True)
        )
        query = self._apply_active_catalog_predicate(query)
        results = query.order_by(
            (ServiceAnalytics.booking_count_30d * 2 + ServiceAnalytics.search_count_30d).desc()
        ).all()

        if not results:
            return 0

        now_utc = datetime.now(timezone.utc)
        mappings = [
            {"id": service_id, "display_order": idx + 1, "updated_at": now_utc}
            for idx, (service_id, _, _) in enumerate(results)
        ]
        self.db.bulk_update_mappings(ServiceCatalog, mappings)
        self.db.flush()
        self.db.expire_all()

        return len(mappings)
