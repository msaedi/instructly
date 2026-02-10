# backend/app/services/catalog_browse_service.py
"""
Read-only service for browsing the 3-level taxonomy.

Converts repository ORM results into Phase 3 Pydantic-compatible dicts
for slug-based catalog navigation:
    /categories → list categories
    /categories/{slug} → category detail
    /categories/{cat_slug}/{sub_slug} → subcategory detail with services + filters
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException
from ..repositories.factory import RepositoryFactory
from .base import BaseService

logger = logging.getLogger(__name__)


class CatalogBrowseService(BaseService):
    """Browse categories → subcategories → services → filters. Read-only."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.category_repo = RepositoryFactory.create_category_repository(db)
        self.subcategory_repo = RepositoryFactory.create_subcategory_repository(db)
        self.catalog_repo = RepositoryFactory.create_service_catalog_repository(db)
        self.filter_repo = RepositoryFactory.create_taxonomy_filter_repository(db)

    # ── Categories ────────────────────────────────────────────────

    @BaseService.measure_operation("list_categories")
    def list_categories(self) -> List[Dict[str, Any]]:
        """All active categories with subcategory counts.

        Returns list of dicts compatible with CategorySummary schema.
        """
        categories = self.category_repo.get_all_active(include_subcategories=True)
        results: List[Dict[str, Any]] = []
        for cat in categories:
            active_subs = [s for s in (cat.subcategories or []) if s.is_active]
            results.append(
                {
                    "id": cat.id,
                    "slug": cat.slug,
                    "name": cat.name,
                    "description": cat.description,
                    "subcategory_count": len(active_subs),
                }
            )
        return results

    @BaseService.measure_operation("get_category")
    def get_category(self, slug: str) -> Dict[str, Any]:
        """Category by slug with subcategory listing.

        Returns dict compatible with CategoryDetail schema.
        Raises NotFoundException if not found.
        """
        cat = self.category_repo.get_by_slug(slug)
        if cat is None:
            raise NotFoundException(f"Category '{slug}' not found")

        active_subs = [s for s in (cat.subcategories or []) if s.is_active]
        subcategories = []
        for sub in sorted(active_subs, key=lambda s: s.display_order):
            svc_count = len([svc for svc in (sub.services or []) if svc.is_active])
            subcategories.append(
                {
                    "id": sub.id,
                    "slug": sub.slug,
                    "name": sub.name,
                    "description": sub.description,
                    "service_count": svc_count,
                }
            )

        return {
            "id": cat.id,
            "slug": cat.slug,
            "name": cat.name,
            "description": cat.description,
            "meta_title": cat.meta_title,
            "meta_description": cat.meta_description,
            "subcategories": subcategories,
        }

    # ── Subcategories ─────────────────────────────────────────────

    @BaseService.measure_operation("get_subcategory")
    def get_subcategory(self, category_slug: str, subcategory_slug: str) -> Dict[str, Any]:
        """Subcategory by two-slug URL with services + filters.

        Validates that the category_slug matches the subcategory's parent.
        Returns dict compatible with SubcategoryDetail schema.
        Raises NotFoundException if not found or slug mismatch.
        """
        sub = self.subcategory_repo.get_by_category_slug(category_slug, subcategory_slug)
        if sub is None:
            raise NotFoundException(
                f"Subcategory '{subcategory_slug}' not found under category '{category_slug}'"
            )

        # Build services list
        active_services = [svc for svc in (sub.services or []) if svc.is_active]
        services = []
        for svc in sorted(active_services, key=lambda s: (s.display_order or 0, s.name)):
            services.append(
                {
                    "id": svc.id,
                    "subcategory_id": svc.subcategory_id,
                    "category_name": sub.category.name if sub.category else None,
                    "name": svc.name,
                    "slug": svc.slug,
                    "description": svc.description,
                    "search_terms": svc.search_terms or [],
                    "eligible_age_groups": svc.eligible_age_groups or [],
                    "display_order": svc.display_order,
                    "online_capable": svc.online_capable,
                    "requires_certification": svc.requires_certification,
                }
            )

        # Build filters list
        filters = self.filter_repo.get_filters_for_subcategory(sub.id)

        # Build category info
        category_info = (
            {
                "id": sub.category.id,
                "name": sub.category.name,
                "subtitle": sub.category.subtitle,
                "description": sub.category.description,
                "display_order": sub.category.display_order,
                "icon_name": sub.category.icon_name,
            }
            if sub.category
            else {}
        )

        return {
            "id": sub.id,
            "slug": sub.slug,
            "name": sub.name,
            "description": sub.description,
            "meta_title": sub.meta_title,
            "meta_description": sub.meta_description,
            "category": category_info,
            "services": services,
            "filters": filters,
        }

    # ── Services ──────────────────────────────────────────────────

    @BaseService.measure_operation("get_service")
    def get_service(self, service_id: str) -> Dict[str, Any]:
        """Single service detail.

        Returns dict compatible with ServiceCatalogDetail schema.
        Raises NotFoundException if not found.
        """
        svc = self.catalog_repo.get_service_with_subcategory(service_id)
        if svc is None:
            raise NotFoundException(f"Service '{service_id}' not found")

        sub_name = svc.subcategory.name if svc.subcategory else None
        sub_id = svc.subcategory_id

        return {
            "id": svc.id,
            "slug": svc.slug,
            "name": svc.name,
            "eligible_age_groups": svc.eligible_age_groups or [],
            "default_duration_minutes": svc.default_duration_minutes or 60,
            "description": svc.description,
            "price_floor_in_person_cents": svc.price_floor_in_person_cents,
            "price_floor_online_cents": svc.price_floor_online_cents,
            "subcategory_id": sub_id,
            "subcategory_name": sub_name,
        }

    @BaseService.measure_operation("list_services_for_subcategory")
    def list_services_for_subcategory(self, subcategory_id: str) -> List[Dict[str, Any]]:
        """All active services in a subcategory.

        Returns list of dicts compatible with ServiceCatalogSummary schema.
        """
        services = self.catalog_repo.get_by_subcategory(subcategory_id)
        return [
            {
                "id": svc.id,
                "slug": svc.slug,
                "name": svc.name,
                "eligible_age_groups": svc.eligible_age_groups or [],
                "default_duration_minutes": svc.default_duration_minutes or 60,
            }
            for svc in services
        ]

    # ── Filters ───────────────────────────────────────────────────

    @BaseService.measure_operation("get_filters_for_subcategory")
    def get_filters_for_subcategory(self, subcategory_id: str) -> List[Dict[str, Any]]:
        """Filter definitions + valid options for a subcategory.

        Returns list of dicts compatible with FilterWithOptions schema.
        """
        return self.filter_repo.get_filters_for_subcategory(subcategory_id)
