"""Service catalog repository facade backed by focused internal mixins."""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional, TypeVar, cast

from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import text

from ..models.instructor import InstructorProfile
from ..models.service_catalog import (
    InstructorService,
    ServiceAnalytics,
    ServiceCatalog,
    ServiceCategory,
    ServiceFormatPrice,
)
from ..models.subcategory import ServiceSubcategory
from ..models.user import User
from .base_repository import BaseRepository
from .service_catalog.catalog_browse_mixin import CatalogBrowseMixin
from .service_catalog.catalog_search_mixin import CatalogSearchMixin
from .service_catalog.embedding_maintenance_mixin import EmbeddingMaintenanceMixin
from .service_catalog.instructor_supply_pricing_mixin import InstructorSupplyPricingMixin
from .service_catalog.ranking_analytics_mixin import RankingAnalyticsMixin
from .service_catalog.service_analytics_query_mixin import ServiceAnalyticsQueryMixin
from .service_catalog.service_analytics_write_mixin import ServiceAnalyticsWriteMixin
from .service_catalog.taxonomy_query_mixin import TaxonomyQueryMixin
from .service_catalog.types import MinimalServiceInfo, PopularServiceMetrics

logger = logging.getLogger(__name__)

TQuery = TypeVar("TQuery")

_pg_trgm_available: Optional[bool] = None
_pg_trgm_lock = threading.Lock()


def _money_to_cents(value: Any) -> int:
    """Convert a dollar amount to cents, returning 0 for None."""
    if value is None:
        return 0
    return int(round(float(value) * 100))


def _check_pg_trgm(db: Session) -> bool:
    """Check pg_trgm availability, cached across all repository instances."""
    global _pg_trgm_available
    if _pg_trgm_available is not None:
        return _pg_trgm_available
    with _pg_trgm_lock:
        if _pg_trgm_available is not None:
            return _pg_trgm_available
        try:
            result = db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            ).first()
            _pg_trgm_available = result is not None
        except Exception as exc:
            logger.warning("pg_trgm_detection_failed", extra={"error": str(exc)})
            _pg_trgm_available = False
        return _pg_trgm_available


def _apply_active_catalog_predicate(query: Query[TQuery]) -> Query[TQuery]:
    """Ensure catalog queries exclude soft-deleted or inactive entries."""
    if hasattr(ServiceCatalog, "is_active"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.is_active.is_(True)))
    if hasattr(ServiceCatalog, "is_deleted"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.is_deleted.is_(False)))
    if hasattr(ServiceCatalog, "deleted_at"):
        query = cast(Query[TQuery], query.filter(ServiceCatalog.deleted_at.is_(None)))
    return query


def _apply_instructor_service_active_filter(query: Query[TQuery]) -> Query[TQuery]:
    """Ensure instructor service soft deletes are excluded."""
    if hasattr(InstructorService, "is_active"):
        query = cast(Query[TQuery], query.filter(InstructorService.is_active.is_(True)))
    if hasattr(InstructorService, "is_deleted"):
        query = cast(Query[TQuery], query.filter(InstructorService.is_deleted.is_(False)))
    if hasattr(InstructorService, "deleted_at"):
        query = cast(Query[TQuery], query.filter(InstructorService.deleted_at.is_(None)))
    return query


def _escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE metacharacters (%, _, \\)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ServiceCatalogRepository(
    CatalogSearchMixin,
    CatalogBrowseMixin,
    TaxonomyQueryMixin,
    InstructorSupplyPricingMixin,
    RankingAnalyticsMixin,
    EmbeddingMaintenanceMixin,
    BaseRepository[ServiceCatalog],
):
    """Repository facade for service catalog data access."""

    _apply_active_catalog_predicate = staticmethod(_apply_active_catalog_predicate)
    _apply_instructor_service_active_filter = staticmethod(_apply_instructor_service_active_filter)
    _escape_like = staticmethod(_escape_like)

    def __init__(self, db: Session):
        """Initialize with ServiceCatalog model."""
        super().__init__(db, ServiceCatalog)
        self._pg_trgm_available = _check_pg_trgm(db)


class ServiceAnalyticsRepository(
    ServiceAnalyticsWriteMixin,
    ServiceAnalyticsQueryMixin,
    BaseRepository[ServiceAnalytics],
):
    """Repository facade for service analytics data access."""

    _apply_active_catalog_predicate = staticmethod(_apply_active_catalog_predicate)
    _money_to_cents = staticmethod(_money_to_cents)

    def __init__(self, db: Session):
        """Initialize with ServiceAnalytics model."""
        super().__init__(db, ServiceAnalytics)


__all__ = [
    "InstructorProfile",
    "InstructorService",
    "MinimalServiceInfo",
    "PopularServiceMetrics",
    "ServiceAnalytics",
    "ServiceAnalyticsRepository",
    "ServiceCatalog",
    "ServiceCatalogRepository",
    "ServiceCategory",
    "ServiceFormatPrice",
    "ServiceSubcategory",
    "User",
    "_apply_active_catalog_predicate",
    "_apply_instructor_service_active_filter",
    "_check_pg_trgm",
    "_escape_like",
    "_money_to_cents",
]
