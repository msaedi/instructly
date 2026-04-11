"""Browse-oriented queries and eager-loading helpers for catalog services."""

from __future__ import annotations

from typing import Any, List, Optional, cast

from sqlalchemy.orm import joinedload

from ...models.service_catalog import ServiceCatalog
from ...models.subcategory import ServiceSubcategory
from .mixin_base import ServiceCatalogRepositoryMixinBase


class CatalogBrowseMixin(ServiceCatalogRepositoryMixinBase):
    """Browse-oriented queries and eager-loading helpers for catalog services."""

    def _apply_eager_loading(self, query: Any) -> Any:
        """Apply eager loading for subcategory→category relationship."""
        return query.options(
            joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category)
        )

    def get_active_services_with_categories(
        self, category_id: Optional[str] = None, skip: int = 0, limit: Optional[int] = None
    ) -> List[ServiceCatalog]:
        """
        Get active services with categories eagerly loaded, ordered by display_order.

        Optimized for the catalog endpoint to prevent N+1 queries.
        """
        query = (
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.is_active == True)
        )
        query = self._apply_active_catalog_predicate(query)

        if category_id:
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            ).filter(ServiceSubcategory.category_id == category_id)

        query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)

        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        return cast(List[ServiceCatalog], query.all())

    def list_services_with_categories(
        self,
        *,
        include_inactive: bool = False,
    ) -> List[ServiceCatalog]:
        """List catalog services with subcategory→category eagerly loaded."""
        query = self.db.query(ServiceCatalog).options(
            joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category)
        )
        if not include_inactive:
            query = self._apply_active_catalog_predicate(query)
        query = query.order_by(ServiceCatalog.display_order, ServiceCatalog.name)
        return cast(List[ServiceCatalog], query.all())

    def get_by_slug(self, slug: str) -> Optional[ServiceCatalog]:
        """Look up a service by its URL slug."""
        return cast(
            Optional[ServiceCatalog],
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.slug == slug, ServiceCatalog.is_active.is_(True))
            .first(),
        )

    def get_by_subcategory(
        self, subcategory_id: str, active_only: bool = True
    ) -> List[ServiceCatalog]:
        """All services for a subcategory, ordered by display_order."""
        query = (
            self.db.query(ServiceCatalog)
            .filter(ServiceCatalog.subcategory_id == subcategory_id)
            .order_by(ServiceCatalog.display_order, ServiceCatalog.name)
        )

        if active_only:
            query = self._apply_active_catalog_predicate(query)

        return cast(List[ServiceCatalog], query.all())

    def get_service_with_subcategory(self, service_id: str) -> Optional[ServiceCatalog]:
        """Single service with subcategory+category eager-loaded."""
        return cast(
            Optional[ServiceCatalog],
            self.db.query(ServiceCatalog)
            .options(joinedload(ServiceCatalog.subcategory).joinedload(ServiceSubcategory.category))
            .filter(ServiceCatalog.id == service_id)
            .first(),
        )
