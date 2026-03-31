"""Search and discovery methods for InstructorService."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Sequence, Set, cast

from ..base import BaseService
from .mixin_base import InstructorMixinBase, JsonDict, JsonList

logger = logging.getLogger(__name__)


class InstructorDiscoveryMixin(InstructorMixinBase):
    """Instructor and service discovery methods."""

    @staticmethod
    def _normalize_taxonomy_filters(
        taxonomy_filter_selections: Optional[Dict[str, List[str]]],
    ) -> Dict[str, List[str]]:
        """Normalize taxonomy filter keys and values for repository matching."""
        normalized_taxonomy_filters: Dict[str, List[str]] = {}
        for raw_key, raw_values in (taxonomy_filter_selections or {}).items():
            key = str(raw_key).strip().lower()
            if not key:
                continue

            values: List[str] = []
            seen_values: Set[str] = set()
            for raw_value in raw_values or []:
                value = str(raw_value).strip().lower()
                if not value or value in seen_values:
                    continue
                seen_values.add(value)
                values.append(value)

            if values:
                normalized_taxonomy_filters[key] = values

        return normalized_taxonomy_filters

    def _serialize_filtered_results(self, profiles: Sequence[Any]) -> List[JsonDict]:
        """Serialize filtered instructor profiles using the public response shape."""
        instructors: List[JsonDict] = []
        for profile in profiles:
            instructor_dict = self._public_profile_to_dict(
                profile,
                include_inactive_services=False,
            )
            if instructor_dict["services"]:
                instructors.append(instructor_dict)
        return instructors

    def _apply_taxonomy_filters(
        self,
        instructors: List[JsonDict],
        normalized_taxonomy_filters: Dict[str, List[str]],
        subcategory_id: Optional[str],
    ) -> List[JsonDict]:
        """Filter serialized instructors down to services matching taxonomy selections."""
        if not normalized_taxonomy_filters and not subcategory_id:
            return instructors

        candidate_service_ids = [
            str(service["id"])
            for instructor in instructors
            for service in instructor.get("services", [])
            if service.get("id") is not None
        ]
        if not candidate_service_ids:
            return []

        matching_service_ids = self.taxonomy_filter_repository.find_matching_service_ids(
            service_ids=candidate_service_ids,
            subcategory_id=subcategory_id,
            filter_selections=normalized_taxonomy_filters,
            active_only=True,
        )
        if not matching_service_ids:
            return []

        filtered_instructors: List[JsonDict] = []
        for instructor in instructors:
            matching_services = [
                service
                for service in instructor.get("services", [])
                if str(service.get("id")) in matching_service_ids
            ]
            if matching_services:
                instructor_copy = dict(instructor)
                instructor_copy["services"] = matching_services
                filtered_instructors.append(instructor_copy)

        return filtered_instructors

    def _build_filtered_metadata(
        self,
        *,
        search: Optional[str],
        service_catalog_id: Optional[str],
        min_price: Optional[float],
        max_price: Optional[float],
        age_group: Optional[str],
        service_area_boroughs: Optional[Sequence[str]],
        normalized_taxonomy_filters: Dict[str, List[str]],
        subcategory_id: Optional[str],
        skip: int,
        limit: int,
        profiles: Sequence[Any],
        instructors: Sequence[JsonDict],
    ) -> JsonDict:
        """Build response metadata for instructor filtering endpoints."""
        applied_filters: JsonDict = {}
        if search:
            applied_filters["search"] = search
        if service_catalog_id:
            applied_filters["service_catalog_id"] = service_catalog_id
        if min_price is not None:
            applied_filters["min_price"] = min_price
        if max_price is not None:
            applied_filters["max_price"] = max_price
        if service_area_boroughs:
            applied_filters["service_area_boroughs"] = list(service_area_boroughs)
        if age_group is not None:
            applied_filters["age_group"] = age_group
        if subcategory_id:
            applied_filters["subcategory_id"] = subcategory_id
        if normalized_taxonomy_filters:
            applied_filters.update(normalized_taxonomy_filters)

        return {
            "filters_applied": applied_filters,
            "pagination": {"skip": skip, "limit": limit, "count": len(instructors)},
            "total_matches": len(profiles),
            "active_instructors": len(instructors),
        }

    @BaseService.measure_operation("get_instructors_filtered")
    def get_instructors_filtered(
        self,
        search: Optional[str] = None,
        service_catalog_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        age_group: Optional[str] = None,
        service_area_boroughs: Optional[Sequence[str]] = None,
        taxonomy_filter_selections: Optional[Dict[str, List[str]]] = None,
        subcategory_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Get instructor profiles based on filter criteria."""
        filter_info = {
            "search": search is not None,
            "service_catalog": service_catalog_id is not None,
            "price_range": min_price is not None or max_price is not None,
            "age_group": age_group is not None,
            "service_area_boroughs": bool(service_area_boroughs),
            "taxonomy_filters": bool(taxonomy_filter_selections),
            "subcategory_id": subcategory_id is not None,
            "filters_count": sum(
                [
                    search is not None,
                    service_catalog_id is not None,
                    min_price is not None,
                    max_price is not None,
                    age_group is not None,
                    bool(service_area_boroughs),
                    bool(taxonomy_filter_selections),
                    subcategory_id is not None,
                ]
            ),
        }
        logger.debug(
            (
                "Instructor filter request - Filters used: %s, Search: %s, "
                "Service Catalog: %s, Price: %s, Taxonomy: %s, Pagination: skip=%s, limit=%s"
            ),
            filter_info["filters_count"],
            filter_info["search"],
            filter_info["service_catalog"],
            filter_info["price_range"],
            filter_info["taxonomy_filters"],
            skip,
            limit,
        )

        profiles = self.profile_repository.find_by_filters(
            search=search,
            service_catalog_id=service_catalog_id,
            min_price=min_price,
            max_price=max_price,
            age_group=age_group,
            boroughs=service_area_boroughs,
            skip=skip,
            limit=limit,
        )
        instructors = self._serialize_filtered_results(profiles)
        normalized_taxonomy_filters = self._normalize_taxonomy_filters(taxonomy_filter_selections)
        instructors = self._apply_taxonomy_filters(
            instructors,
            normalized_taxonomy_filters,
            subcategory_id,
        )
        metadata = self._build_filtered_metadata(
            search=search,
            service_catalog_id=service_catalog_id,
            min_price=min_price,
            max_price=max_price,
            age_group=age_group,
            service_area_boroughs=service_area_boroughs,
            normalized_taxonomy_filters=normalized_taxonomy_filters,
            subcategory_id=subcategory_id,
            skip=skip,
            limit=limit,
            profiles=profiles,
            instructors=instructors,
        )

        if search:
            logger.debug(
                "Search %s returned %d active instructors (from %d total matches)",
                search,
                len(instructors),
                len(profiles),
            )
        if service_catalog_id:
            logger.debug(
                "Service catalog filter %s returned %d instructors",
                service_catalog_id,
                len(instructors),
            )
        if min_price is not None or max_price is not None:
            price_range = f"${min_price or 0}-${max_price or 'unlimited'}"
            logger.debug("Price range %s returned %d instructors", price_range, len(instructors))

        return {"instructors": instructors, "metadata": metadata}

    @BaseService.measure_operation("search_services_semantic")
    def search_services_semantic(
        self,
        query_embedding: List[float],
        category_id: Optional[str] = None,
        online_capable: Optional[bool] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Search services using semantic similarity."""
        similar_services = self.catalog_repository.find_similar_by_embedding(
            embedding=query_embedding,
            limit=limit * 2,
            threshold=threshold,
        )

        filtered_results = []
        for service, score in similar_services:
            if category_id and (
                not service.subcategory or service.subcategory.category_id != category_id
            ):
                continue
            if online_capable is not None and service.online_capable != online_capable:
                continue

            self.analytics_repository.increment_search_count(service.id)
            service_dict = self._catalog_service_to_dict(service)
            service_dict["similarity_score"] = score
            service_dict["analytics"] = self._get_service_analytics(service.id)
            filtered_results.append(service_dict)
            if len(filtered_results) >= limit:
                break

        return filtered_results

    @BaseService.measure_operation("get_popular_services")
    def get_popular_services(self, limit: int = 10, days: int = 30) -> List[Dict[str, Any]]:
        """Get most popular services based on booking data."""
        popular = self.catalog_repository.get_popular_services(limit=limit, days=days)
        results = []
        for item in popular:
            service_dict = self._catalog_service_to_dict(item["service"])
            service_dict["analytics"] = item["analytics"].to_dict()
            service_dict["popularity_score"] = item["popularity_score"]
            results.append(service_dict)
        return results

    @BaseService.measure_operation("get_trending_services")
    def get_trending_services(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get services trending upward in demand."""
        trending = self.catalog_repository.get_trending_services(limit=limit)
        results = []
        for service in trending:
            service_dict = self._catalog_service_to_dict(service)
            service_dict["analytics"] = self._get_service_analytics(service.id)
            results.append(service_dict)
        return results

    @BaseService.measure_operation("search_services_enhanced")
    def search_services_enhanced(
        self,
        query_text: Optional[str] = None,
        category_id: Optional[str] = None,
        online_capable: Optional[bool] = None,
        requires_certification: Optional[bool] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Enhanced service search with multiple filters and analytics."""
        services = self.catalog_repository.search_services(
            query_text=query_text,
            category_id=category_id,
            online_capable=online_capable,
            requires_certification=requires_certification,
            skip=skip,
            limit=limit,
        )

        results = []
        for service in services:
            service_dict = self._catalog_service_to_dict(service)
            service_dict["analytics"] = self._get_service_analytics(service.id)
            if min_price is not None or max_price is not None:
                instructors = self._get_instructors_for_service_in_price_range(
                    service.id,
                    min_price,
                    max_price,
                )
                service_dict["matching_instructors"] = len(instructors)
                service_dict["actual_price_range"] = self._calculate_price_range(instructors)
            results.append(service_dict)

            if query_text:
                self.analytics_repository.increment_search_count(service.id)

        metadata = {
            "query": query_text,
            "filters": {
                "category_id": category_id,
                "online_capable": online_capable,
                "requires_certification": requires_certification,
                "price_range": {"min": min_price, "max": max_price}
                if min_price or max_price
                else None,
            },
            "pagination": {"skip": skip, "limit": limit, "count": len(results)},
        }
        return {"services": results, "metadata": metadata}

    def _get_service_analytics(self, service_catalog_id: str) -> Dict[str, Any]:
        """Get or create analytics for a service."""
        analytics = self.analytics_repository.get_or_create(service_catalog_id)
        return cast(Dict[str, Any], analytics.to_dict()) if analytics else {}

    def _get_instructors_for_service_in_price_range(
        self,
        service_catalog_id: str,
        min_price: Optional[float],
        max_price: Optional[float],
    ) -> List[Any]:
        """Get instructors offering a service within price range."""
        all_services = self.service_repository.find_by(
            service_catalog_id=service_catalog_id,
            is_active=True,
        )

        filtered = []
        for service in all_services:
            service_min_rate = service.min_hourly_rate
            if service_min_rate is None:
                continue
            if min_price and service_min_rate < Decimal(str(min_price)):
                continue
            if max_price and service_min_rate > Decimal(str(max_price)):
                continue
            filtered.append(service)

        return filtered

    def _calculate_price_range(self, instructor_services: List[Any]) -> Dict[str, Any]:
        """Calculate actual price range from instructor services."""
        if not instructor_services:
            return {"min": None, "max": None}

        prices = [
            service.min_hourly_rate for service in instructor_services if service.min_hourly_rate
        ]
        if not prices:
            return {"min": None, "max": None}
        return {"min": min(prices), "max": max(prices), "avg": sum(prices) / len(prices)}

    @BaseService.measure_operation("get_top_services_per_category")
    def get_top_services_per_category(self, limit: int = 7) -> Dict[str, Any]:
        """Get top N services per category for homepage display."""
        cache_key = f"catalog:top-services:{limit}"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                logger.debug("Cache hit for top services per category")
                return cast(JsonDict, cached_result)

        categories = self.category_repository.get_all_active()
        categories_data: JsonList = []
        result: JsonDict = {
            "categories": categories_data,
            "metadata": {
                "services_per_category": limit,
                "total_categories": len(categories),
                "cached_for_seconds": 3600,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        for category in sorted(categories, key=lambda item: item.display_order):
            services_list: JsonList = []
            category_data: JsonDict = {
                "id": category.id,
                "name": category.name,
                "icon_name": category.icon_name,
                "services": services_list,
            }

            top_services = self.catalog_repository.get_active_services_with_categories(
                category_id=category.id,
                limit=limit,
            )
            for service in top_services:
                analytics = self.analytics_repository.get_or_create(service.id)
                active_instructors = analytics.active_instructors if analytics else 0
                if active_instructors > 0:
                    services_list.append(
                        {
                            "id": service.id,
                            "name": service.name,
                            "slug": service.slug,
                            "demand_score": analytics.demand_score if analytics else 0,
                            "active_instructors": active_instructors,
                            "is_trending": analytics.is_trending if analytics else False,
                            "display_order": service.display_order,
                        }
                    )

            categories_data.append(category_data)

        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
            logger.debug("Cached top %d services per category for 1 hour", limit)
        return result
