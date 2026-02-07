# backend/app/repositories/subcategory_repository.py
"""
Repository for service subcategory data access.

Provides queries for the middle tier of the 3-level taxonomy:
  Category → Subcategory → Service

Also handles the subcategory→filter join for filter dropdowns.
"""

import logging
from typing import List, Optional, cast

from sqlalchemy.orm import Session, joinedload, selectinload

from ..models.filter import SubcategoryFilter, SubcategoryFilterOption
from ..models.service_catalog import ServiceCategory
from ..models.subcategory import ServiceSubcategory
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SubcategoryRepository(BaseRepository[ServiceSubcategory]):
    """Repository for ServiceSubcategory queries."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ServiceSubcategory)

    def get_by_slug(self, slug: str) -> Optional[ServiceSubcategory]:
        """Look up subcategory by slug, eagerly loading category + services.

        Args:
            slug: URL-friendly identifier (e.g., "piano").

        Returns:
            Subcategory with category and services loaded, or None.
        """
        return cast(
            Optional[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .options(
                joinedload(ServiceSubcategory.category),
                selectinload(ServiceSubcategory.services),
            )
            .filter(ServiceSubcategory.slug == slug)
            .first(),
        )

    def get_by_category(
        self, category_id: str, active_only: bool = True
    ) -> List[ServiceSubcategory]:
        """All subcategories for a category, ordered by display_order.

        Args:
            category_id: ULID of the parent category.
            active_only: Only return active subcategories.

        Returns:
            Ordered list of subcategories.
        """
        query = (
            self.db.query(ServiceSubcategory)
            .filter(ServiceSubcategory.category_id == category_id)
            .order_by(ServiceSubcategory.display_order)
        )

        if active_only:
            query = query.filter(ServiceSubcategory.is_active.is_(True))

        return cast(List[ServiceSubcategory], query.all())

    def get_with_filters(self, subcategory_id: str) -> Optional[ServiceSubcategory]:
        """Load subcategory with its filter definitions and valid options.

        This powers the filter dropdowns on the frontend.
        Eagerly loads the full chain:
          subcategory → subcategory_filters → filter_definition
          subcategory_filters → filter_options → filter_option

        Args:
            subcategory_id: ULID of the subcategory.

        Returns:
            Subcategory with filter tree loaded, or None.
        """
        return cast(
            Optional[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .options(
                selectinload(ServiceSubcategory.subcategory_filters).joinedload(
                    SubcategoryFilter.filter_definition
                ),
                selectinload(ServiceSubcategory.subcategory_filters)
                .selectinload(SubcategoryFilter.filter_options)
                .joinedload(SubcategoryFilterOption.filter_option),
            )
            .filter(ServiceSubcategory.id == subcategory_id)
            .first(),
        )

    def get_by_category_slug(
        self, category_slug: str, subcategory_slug: str
    ) -> Optional[ServiceSubcategory]:
        """Resolve /category-slug/subcategory-slug URL pattern.

        Joins through category to validate both slugs match.

        Args:
            category_slug: Category URL slug.
            subcategory_slug: Subcategory URL slug.

        Returns:
            Subcategory with category and services loaded, or None.
        """
        return cast(
            Optional[ServiceSubcategory],
            self.db.query(ServiceSubcategory)
            .join(
                ServiceCategory,
                ServiceSubcategory.category_id == ServiceCategory.id,
            )
            .options(
                joinedload(ServiceSubcategory.category),
                selectinload(ServiceSubcategory.services),
            )
            .filter(
                ServiceCategory.slug == category_slug,
                ServiceSubcategory.slug == subcategory_slug,
            )
            .first(),
        )
