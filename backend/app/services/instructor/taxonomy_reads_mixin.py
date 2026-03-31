"""Taxonomy browse and catalog read models for InstructorService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, cast

from ...core.exceptions import NotFoundException
from ..base import BaseService
from .mixin_base import InstructorMixinBase, JsonDict, JsonList


class InstructorTaxonomyReadsMixin(InstructorMixinBase):
    """Catalog browse, taxonomy navigation, and service listing read models."""

    @BaseService.measure_operation("get_catalog_browse")
    def get_catalog_browse(self) -> Dict[str, Any]:
        """Get the full service taxonomy grouped by category."""
        cache_key = "catalog:browse"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                return cast(Dict[str, Any], cached_result)

        categories = self.category_repository.get_all_active()
        all_services = self.catalog_repository.list_services_with_categories()
        services_by_category: dict[str, list[Any]] = {}
        for service in all_services:
            subcategory = getattr(service, "subcategory", None)
            category = getattr(subcategory, "category", None)
            category_id = getattr(category, "id", None)
            if category_id:
                services_by_category.setdefault(category_id, []).append(service)

        categories_data: List[Dict[str, Any]] = []
        for category in sorted(categories, key=lambda item: item.display_order):
            services_list = [
                {
                    "id": service.id,
                    "name": service.name,
                    "subcategory_id": service.subcategory_id,
                    "eligible_age_groups": service.eligible_age_groups or [],
                    "description": service.description,
                    "display_order": service.display_order,
                }
                for service in services_by_category.get(category.id, [])
            ]
            categories_data.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "services": services_list,
                }
            )

        result: Dict[str, Any] = {"categories": categories_data}
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
        return result

    def _load_services_catalog_context(self) -> Dict[str, Any]:
        """Load catalog-wide category, analytics, and price-range context."""
        categories = self.category_repository.get_all_active()
        all_services = self.catalog_repository.get_active_services_with_categories(limit=None)
        analytics_by_service = self.analytics_repository.get_or_create_bulk(
            [service.id for service in all_services]
        )
        bulk_price_ranges = self.catalog_repository.get_bulk_price_ranges()
        services_by_category: dict[str, list[Any]] = {}
        for service in all_services:
            subcategory = getattr(service, "subcategory", None)
            category = getattr(subcategory, "category", None)
            category_id = getattr(category, "id", None)
            if category_id:
                services_by_category.setdefault(category_id, []).append(service)

        return {
            "categories": categories,
            "analytics_by_service": analytics_by_service,
            "bulk_price_ranges": bulk_price_ranges,
            "services_by_category": services_by_category,
        }

    def _build_service_rows_with_instructors(
        self,
        category_id: str,
        services_by_category: dict[str, list[Any]],
        analytics_by_service: dict[str, Any],
        bulk_price_ranges: dict[str, Any],
    ) -> JsonList:
        """Build sorted service rows with analytics and price range data."""
        services_with_analytics: List[JsonDict] = []
        for service in services_by_category.get(category_id, []):
            analytics = analytics_by_service.get(service.id)
            service_data: JsonDict = {
                "id": service.id,
                "subcategory_id": service.subcategory_id,
                "name": service.name,
                "slug": service.slug,
                "description": service.description,
                "search_terms": service.search_terms or [],
                "eligible_age_groups": service.eligible_age_groups or [],
                "display_order": service.display_order,
                "online_capable": service.online_capable,
                "requires_certification": service.requires_certification,
                "is_active": service.is_active,
                "active_instructors": analytics.active_instructors if analytics else 0,
                "demand_score": analytics.demand_score if analytics else 0,
                "is_trending": analytics.is_trending if analytics else False,
                "_original_display_order": service.display_order,
            }
            price_range = bulk_price_ranges.get(service.id)
            if price_range:
                service_data["actual_min_price"] = price_range["min"]
                service_data["actual_max_price"] = price_range["max"]
            services_with_analytics.append(service_data)

        services_with_analytics.sort(
            key=lambda item: (
                0 if item["active_instructors"] > 0 else 1,
                item["_original_display_order"],
            )
        )
        for service_data in services_with_analytics:
            del service_data["_original_display_order"]
        return cast(JsonList, services_with_analytics)

    @staticmethod
    def _build_all_services_metadata(
        categories: List[Any],
        categories_data: JsonList,
    ) -> JsonDict:
        """Build metadata for the full catalog + instructor-count response."""
        total_services = sum(len(category["services"]) for category in categories_data)
        return {
            "total_categories": len(categories),
            "total_services": total_services,
            "cached_for_seconds": 300,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @BaseService.measure_operation("get_all_services_with_instructors")
    def get_all_services_with_instructors(self) -> Dict[str, Any]:
        """Get all catalog services organized by category with instructor counts."""
        cache_key = "catalog:all-services-with-instructors"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                return cast(JsonDict, cached_result)

        context = self._load_services_catalog_context()
        categories = context["categories"]
        categories_data: JsonList = []
        for category in sorted(categories, key=lambda item: item.display_order):
            categories_data.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "subtitle": category.subtitle if hasattr(category, "subtitle") else "",
                    "description": category.description,
                    "icon_name": category.icon_name,
                    "services": self._build_service_rows_with_instructors(
                        category.id,
                        context["services_by_category"],
                        context["analytics_by_service"],
                        context["bulk_price_ranges"],
                    ),
                }
            )

        result: JsonDict = {
            "categories": categories_data,
            "metadata": self._build_all_services_metadata(categories, categories_data),
        }
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
        return result

    @BaseService.measure_operation("get_categories_with_subcategories")
    def get_categories_with_subcategories(self) -> List[Dict[str, Any]]:
        """Get all categories with subcategory briefs."""
        cache_key = "categories:with-subcategories"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonList, cached)

        categories, count_map = self.catalog_repository.get_categories_with_subcategories()
        result: JsonList = []
        for category in sorted(categories, key=lambda item: item.display_order):
            result.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "subtitle": getattr(category, "subtitle", None),
                    "description": category.description,
                    "display_order": category.display_order,
                    "icon_name": getattr(category, "icon_name", None),
                    "subcategories": [
                        {
                            "id": subcategory.id,
                            "name": subcategory.name,
                            "service_count": count_map.get(subcategory.id, 0),
                        }
                        for subcategory in sorted(
                            getattr(category, "subcategories", []),
                            key=lambda item: item.display_order,
                        )
                    ],
                }
            )

        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
        return result

    @BaseService.measure_operation("get_category_tree")
    def get_category_tree(self, category_id: str) -> Dict[str, Any]:
        """Get full 3-level tree for a category."""
        cache_key = f"categories:tree:{category_id}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonDict, cached)

        category = self.catalog_repository.get_category_tree(category_id)
        if not category:
            raise NotFoundException("Category not found")

        result: JsonDict = {
            "id": category.id,
            "name": category.name,
            "subtitle": getattr(category, "subtitle", None),
            "description": category.description,
            "display_order": category.display_order,
            "icon_name": getattr(category, "icon_name", None),
            "subcategories": [],
        }
        subcategories_list = cast(JsonList, result["subcategories"])
        for subcategory in sorted(
            getattr(category, "subcategories", []),
            key=lambda item: item.display_order,
        ):
            subcategories_list.append(
                {
                    "id": subcategory.id,
                    "name": subcategory.name,
                    "category_id": subcategory.category_id,
                    "display_order": subcategory.display_order,
                    "services": [
                        self._catalog_service_to_dict(service)
                        for service in getattr(subcategory, "services", [])
                    ],
                }
            )

        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
        return result

    @BaseService.measure_operation("get_subcategory_with_services")
    def get_subcategory_with_services(self, subcategory_id: str) -> Dict[str, Any]:
        """Get subcategory with its services."""
        cache_key = f"subcategory:services:{subcategory_id}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonDict, cached)

        subcategory = self.catalog_repository.get_subcategory_with_services(subcategory_id)
        if not subcategory:
            raise NotFoundException("Subcategory not found")

        result: JsonDict = {
            "id": subcategory.id,
            "name": subcategory.name,
            "category_id": subcategory.category_id,
            "display_order": subcategory.display_order,
            "services": [
                self._catalog_service_to_dict(service)
                for service in getattr(subcategory, "services", [])
            ],
        }
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=1800)
        return result

    @BaseService.measure_operation("get_subcategory_filters")
    def get_subcategory_filters(self, subcategory_id: str) -> List[Dict[str, Any]]:
        """Get filter definitions for a subcategory."""
        cache_key = f"subcategory:filters:{subcategory_id}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonList, cached)

        result = cast(
            JsonList,
            self.taxonomy_filter_repository.get_filters_for_subcategory(subcategory_id),
        )
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
        return result

    @BaseService.measure_operation("get_services_by_age_group")
    def get_services_by_age_group(self, age_group: str) -> List[Dict[str, Any]]:
        """Get services eligible for an age group."""
        cache_key = f"catalog:age-group:{age_group}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonList, cached)

        services = self.catalog_repository.get_services_by_eligible_age_group(age_group)
        result = [self._catalog_service_to_dict(service) for service in services]
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=1800)
        return result

    @BaseService.measure_operation("get_kids_available_services")
    def get_kids_available_services(self) -> List[Dict[str, Any]]:
        """Return catalog services with at least one active instructor offering to kids."""
        cache_key = "catalog:kids-available"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonList, cached)

        result = cast(JsonList, self.catalog_repository.get_services_available_for_kids_minimal())
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
        return result
