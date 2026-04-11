"""Taxonomy-focused category and subcategory queries."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from ...models.service_catalog import ServiceCatalog, ServiceCategory
from ...models.subcategory import ServiceSubcategory
from .mixin_base import ServiceCatalogRepositoryMixinBase


class TaxonomyQueryMixin(ServiceCatalogRepositoryMixinBase):
    """Taxonomy-focused category and subcategory queries."""

    def get_categories_with_subcategories(
        self,
    ) -> Tuple[List[ServiceCategory], Dict[str, int]]:
        """Fetch all categories with subcategories and service counts."""
        categories = cast(
            List[ServiceCategory],
            self.db.query(ServiceCategory)
            .options(selectinload(ServiceCategory.subcategories))
            .order_by(ServiceCategory.display_order)
            .all(),
        )

        count_rows = (
            self.db.query(
                ServiceCatalog.subcategory_id,
                func.count(ServiceCatalog.id).label("service_count"),
            )
            .group_by(ServiceCatalog.subcategory_id)
            .all()
        )
        count_map: Dict[str, int] = {row.subcategory_id: row.service_count for row in count_rows}

        return categories, count_map

    def get_category_tree(self, category_id: str) -> Optional[ServiceCategory]:
        """Full 3-level tree: category → subcategories → services."""
        return cast(
            Optional[ServiceCategory],
            self.db.query(ServiceCategory)
            .options(
                selectinload(ServiceCategory.subcategories).selectinload(
                    ServiceSubcategory.services
                )
            )
            .filter(ServiceCategory.id == category_id)
            .first(),
        )

    def get_subcategory_with_services(self, subcategory_id: str) -> Optional[ServiceSubcategory]:
        """Single subcategory with its services eager-loaded."""
        return cast(
            Optional[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .options(selectinload(ServiceSubcategory.services))
            .filter(ServiceSubcategory.id == subcategory_id)
            .first(),
        )

    def get_subcategories_by_category(self, category_id: str) -> List[ServiceSubcategory]:
        """All subcategories for a category, ordered by display_order."""
        return cast(
            List[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .filter(ServiceSubcategory.category_id == category_id)
            .order_by(ServiceSubcategory.display_order)
            .all(),
        )

    def get_subcategory_ids_for_catalog_ids(self, service_catalog_ids: List[str]) -> Dict[str, str]:
        """Fetch subcategory IDs for a batch of service catalog IDs."""
        unique_catalog_ids = [
            service_id for service_id in dict.fromkeys(service_catalog_ids) if service_id
        ]
        if not unique_catalog_ids:
            return {}

        rows = (
            self.db.query(ServiceCatalog.id, ServiceCatalog.subcategory_id)
            .filter(ServiceCatalog.id.in_(unique_catalog_ids))
            .all()
        )
        return {
            str(catalog_id): str(subcategory_id)
            for catalog_id, subcategory_id in rows
            if catalog_id and subcategory_id
        }

    def get_active_catalog_ids(self, catalog_ids: List[str]) -> set[str]:
        """Return the subset of provided catalog IDs that are currently active."""
        unique_catalog_ids = [catalog_id for catalog_id in dict.fromkeys(catalog_ids) if catalog_id]
        if not unique_catalog_ids:
            return set()

        rows = self.db.query(ServiceCatalog.id).filter(ServiceCatalog.id.in_(unique_catalog_ids))
        rows = self._apply_active_catalog_predicate(rows).all()
        return {str(catalog_id) for (catalog_id,) in rows if catalog_id}
