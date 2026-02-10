# backend/app/repositories/category_repository.py
"""
Repository for service category data access.

Provides queries for the top level of the 3-level taxonomy:
  Category → Subcategory → Service
"""

import logging
from typing import List, Optional, cast

from sqlalchemy.orm import Session, selectinload

from ..models.service_catalog import ServiceCategory
from ..models.subcategory import ServiceSubcategory
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CategoryRepository(BaseRepository[ServiceCategory]):
    """Repository for ServiceCategory queries."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ServiceCategory)

    def get_all_active(self, include_subcategories: bool = False) -> List[ServiceCategory]:
        """Get all categories ordered by display_order.

        Args:
            include_subcategories: Eagerly load active subcategories.

        Returns:
            Categories ordered by display_order.
        """
        query = self.db.query(ServiceCategory).order_by(ServiceCategory.display_order)

        if include_subcategories:
            query = query.options(selectinload(ServiceCategory.subcategories))

        return cast(List[ServiceCategory], query.all())

    def get_by_slug(self, slug: str) -> Optional[ServiceCategory]:
        """Look up category by URL slug, eagerly loading subcategories.

        Args:
            slug: URL-friendly identifier (e.g., "music").

        Returns:
            Category with subcategories loaded, or None.
        """
        return cast(
            Optional[ServiceCategory],
            self.db.query(ServiceCategory)
            .options(
                selectinload(ServiceCategory.subcategories).selectinload(
                    ServiceSubcategory.services
                )
            )
            .filter(ServiceCategory.slug == slug)
            .first(),
        )

    def get_with_full_tree(self, category_id: str) -> Optional[ServiceCategory]:
        """Load category with subcategories and their services.

        Full 3-level tree: Category → Subcategories → Services.

        Args:
            category_id: ULID of the category.

        Returns:
            Category with full tree loaded, or None.
        """
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
