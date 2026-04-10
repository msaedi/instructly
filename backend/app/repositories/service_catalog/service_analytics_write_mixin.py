"""Write and bulk-update helpers for service analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, cast

from ...models.service_catalog import ServiceAnalytics
from .mixin_base import ServiceAnalyticsRepositoryMixinBase


class ServiceAnalyticsWriteMixin(ServiceAnalyticsRepositoryMixinBase):
    """Write and bulk-update helpers for service analytics."""

    def update(self, id: Any, **kwargs: Any) -> Optional[ServiceAnalytics]:
        """Override update to use service_catalog_id as primary key."""
        service_catalog_id = cast(str, id)
        entity = self.find_one_by(service_catalog_id=service_catalog_id)
        if not entity:
            return None

        for key, value in kwargs.items():
            setattr(entity, key, value)

        self.db.flush()
        self.db.refresh(entity)
        return entity

    def get_or_create(self, service_catalog_id: str) -> ServiceAnalytics:
        """Get existing analytics or create new with defaults."""
        analytics = self.find_one_by(service_catalog_id=service_catalog_id)

        if not analytics:
            analytics = self.create(
                service_catalog_id=service_catalog_id,
                search_count_7d=0,
                search_count_30d=0,
                booking_count_7d=0,
                booking_count_30d=0,
                active_instructors=0,
                last_calculated=datetime.now(timezone.utc),
            )

        return analytics

    def increment_search_count(self, service_catalog_id: str) -> None:
        """Increment search count for a service."""
        analytics = self.get_or_create(service_catalog_id)

        self.update(
            analytics.service_catalog_id,
            search_count_7d=analytics.search_count_7d + 1,
            search_count_30d=analytics.search_count_30d + 1,
        )

    def update_from_bookings(
        self, service_catalog_id: str, booking_stats: Mapping[str, Any]
    ) -> None:
        """Update analytics from booking statistics."""
        analytics = self.get_or_create(service_catalog_id)

        updates: Dict[str, Any] = {
            "booking_count_7d": booking_stats.get("count_7d", 0),
            "booking_count_30d": booking_stats.get("count_30d", 0),
            "avg_price_booked_cents": self._money_to_cents(booking_stats.get("avg_price")),
            "price_percentile_25_cents": self._money_to_cents(booking_stats.get("price_p25")),
            "price_percentile_50_cents": self._money_to_cents(booking_stats.get("price_p50")),
            "price_percentile_75_cents": self._money_to_cents(booking_stats.get("price_p75")),
            "most_booked_duration": booking_stats.get("most_popular_duration"),
            "completion_rate": booking_stats.get("completion_rate"),
            "avg_rating": booking_stats.get("avg_rating"),
            "last_calculated": datetime.now(timezone.utc),
        }

        updates = {key: value for key, value in updates.items() if value is not None}

        self.update(analytics.service_catalog_id, **updates)

    def get_or_create_bulk(self, service_catalog_ids: List[str]) -> Dict[str, ServiceAnalytics]:
        """Get or create analytics records for multiple services in bulk."""
        if not service_catalog_ids:
            return {}

        existing = cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics)
            .filter(ServiceAnalytics.service_catalog_id.in_(service_catalog_ids))
            .all(),
        )

        result: Dict[str, ServiceAnalytics] = {
            analytics.service_catalog_id: analytics for analytics in existing
        }

        now = datetime.now(timezone.utc)
        for service_id in service_catalog_ids:
            if service_id not in result:
                analytics = ServiceAnalytics(
                    service_catalog_id=service_id,
                    search_count_7d=0,
                    search_count_30d=0,
                    booking_count_7d=0,
                    booking_count_30d=0,
                    active_instructors=0,
                    last_calculated=now,
                )
                self.db.add(analytics)
                result[service_id] = analytics

        self.db.flush()
        return result

    def bulk_update_all(self, updates: List[Dict[str, Any]]) -> int:
        """Bulk update multiple analytics records using SQLAlchemy."""
        if not updates:
            return 0

        mappings: List[Dict[str, Any]] = []
        for update in updates:
            service_catalog_id = update.get("service_catalog_id")
            if not service_catalog_id:
                continue
            mappings.append(
                {
                    "service_catalog_id": service_catalog_id,
                    "booking_count_7d": update.get("booking_count_7d", 0),
                    "booking_count_30d": update.get("booking_count_30d", 0),
                    "active_instructors": update.get("active_instructors", 0),
                    "total_weekly_hours": update.get("total_weekly_hours"),
                    "avg_price_booked_cents": update.get(
                        "avg_price_booked_cents",
                        self._money_to_cents(update.get("avg_price_booked")),
                    ),
                    "price_percentile_25_cents": update.get(
                        "price_percentile_25_cents",
                        self._money_to_cents(update.get("price_percentile_25")),
                    ),
                    "price_percentile_50_cents": update.get(
                        "price_percentile_50_cents",
                        self._money_to_cents(update.get("price_percentile_50")),
                    ),
                    "price_percentile_75_cents": update.get(
                        "price_percentile_75_cents",
                        self._money_to_cents(update.get("price_percentile_75")),
                    ),
                    "most_booked_duration": update.get("most_booked_duration"),
                    "completion_rate": update.get("completion_rate"),
                    "supply_demand_ratio": update.get("supply_demand_ratio"),
                    "last_calculated": update.get("last_calculated"),
                }
            )

        if not mappings:
            return 0

        self.db.bulk_update_mappings(ServiceAnalytics, mappings)
        self.db.flush()
        self.db.expire_all()

        return len(mappings)
