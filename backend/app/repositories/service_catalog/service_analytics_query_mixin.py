"""Read-oriented queries for service analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence, Tuple, cast

from sqlalchemy import select
from sqlalchemy.sql import func

from ...models.service_catalog import ServiceAnalytics, ServiceCatalog
from .mixin_base import ServiceAnalyticsRepositoryMixinBase


class ServiceAnalyticsQueryMixin(ServiceAnalyticsRepositoryMixinBase):
    """Read-oriented queries for service analytics."""

    def get_by_id(self, id: Any, load_relationships: bool = True) -> Optional[ServiceAnalytics]:
        """Override get_by_id to use service_catalog_id as primary key."""
        service_catalog_id = cast(str, id)
        return self.find_one_by(service_catalog_id=service_catalog_id)

    def count_all(self) -> int:
        """Return total number of analytics records."""
        return self.db.query(func.count(ServiceAnalytics.service_catalog_id)).scalar() or 0

    def get_most_recent(self) -> Optional[ServiceAnalytics]:
        """Return the most recently calculated analytics record."""
        return cast(
            Optional[ServiceAnalytics],
            self.db.query(ServiceAnalytics)
            .order_by(ServiceAnalytics.last_calculated.desc())
            .first(),
        )

    def get_stale_analytics(self, hours: int = 24) -> List[ServiceAnalytics]:
        """Get analytics records that need updating."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        return cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics).filter(ServiceAnalytics.last_calculated < cutoff).all(),
        )

    def get_services_needing_analytics(self) -> List[str]:
        """Get service IDs that don't have analytics records."""
        existing = select(ServiceAnalytics.service_catalog_id).subquery()
        existing_ids = select(existing.c.service_catalog_id)

        missing_rows = cast(
            Sequence[Tuple[str]],
            (
                self._apply_active_catalog_predicate(
                    self.db.query(ServiceCatalog.id).filter(
                        ServiceCatalog.is_active == True, ~ServiceCatalog.id.in_(existing_ids)
                    )
                ).all()
            ),
        )

        return [row[0] for row in missing_rows]

    def get_all(self, skip: int = 0, limit: int = 10000) -> List[ServiceAnalytics]:
        """Get all analytics records."""
        return cast(
            List[ServiceAnalytics],
            self.db.query(ServiceAnalytics).offset(skip).limit(limit).all(),
        )
