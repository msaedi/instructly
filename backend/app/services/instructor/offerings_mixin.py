from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, cast

from ...core.exceptions import BusinessRuleException, NotFoundException
from ...models.service_catalog import InstructorService as Service, ServiceCatalog
from ...schemas.instructor import ServiceCreate
from ..base import BaseService
from .mixin_base import InstructorMixinBase, JsonList, get_instructor_service_module

logger = logging.getLogger(__name__)


class InstructorOfferingsMixin(InstructorMixinBase):
    def _validate_service_payloads(
        self,
        instructor_id: str,
        services_data: List[ServiceCreate],
    ) -> dict[str, dict[str, Any]]:
        validated_services: dict[str, dict[str, Any]] = {}
        if not services_data:
            return validated_services

        self._validate_catalog_ids([service.service_catalog_id for service in services_data])
        for service_data in services_data:
            catalog_id = service_data.service_catalog_id
            catalog_service = self.catalog_repository.get_by_id(catalog_id)
            if not catalog_service:
                raise NotFoundException("Catalog service not found")

            normalized_payload = service_data.model_dump()
            self._validate_age_groups_subset(catalog_service, normalized_payload.get("age_groups"))
            if normalized_payload.get("filter_selections"):
                is_valid, errors = self.taxonomy_filter_repository.validate_filter_selections(
                    subcategory_id=catalog_service.subcategory_id,
                    selections=normalized_payload["filter_selections"],
                )
                if not is_valid:
                    raise BusinessRuleException(f"Invalid filter selections: {'; '.join(errors)}")

            normalized_prices = self._normalize_format_prices(
                normalized_payload.pop("format_prices", [])
            )
            self.validate_service_format_prices(
                instructor_id=instructor_id,
                catalog_service=catalog_service,
                format_prices=normalized_prices,
            )
            validated_services[catalog_id] = {
                "catalog_service": catalog_service,
                "payload": normalized_payload,
                "format_prices": normalized_prices,
            }

        return validated_services

    def _upsert_services(
        self,
        profile_id: str,
        services_data: List[ServiceCreate],
        services_by_catalog_id: dict[str, Service],
        validated_services: dict[str, dict[str, Any]],
    ) -> Set[str]:
        updated_catalog_ids: Set[str] = set()
        for service_data in services_data:
            catalog_id = service_data.service_catalog_id
            updated_catalog_ids.add(catalog_id)
            validated_payload = validated_services[catalog_id]
            updates = dict(validated_payload["payload"])
            normalized_prices = validated_payload["format_prices"]

            existing_service = services_by_catalog_id.get(catalog_id)
            if existing_service:
                if not existing_service.is_active:
                    updates["is_active"] = True
                    logger.info("Reactivated service: catalog_id %s", catalog_id)
                for key, value in updates.items():
                    setattr(existing_service, key, value)
                self.service_repository.update(existing_service.id, **updates)
                existing_service.format_prices = (
                    self.service_format_pricing_repository.sync_format_prices(
                        existing_service.id, normalized_prices
                    )
                )
                continue

            create_payload = dict(updates)
            create_payload["instructor_profile_id"] = profile_id
            created_service = self.service_repository.create(**create_payload)
            created_service.format_prices = (
                self.service_format_pricing_repository.sync_format_prices(
                    created_service.id,
                    normalized_prices,
                )
            )
            logger.info("Created new service: catalog_id %s", catalog_id)

        return updated_catalog_ids

    def _remove_stale_services(
        self,
        services_by_catalog_id: dict[str, Service],
        updated_catalog_ids: Set[str],
    ) -> None:
        for catalog_id, service in services_by_catalog_id.items():
            if catalog_id in updated_catalog_ids or not service.is_active:
                continue

            has_bookings = self.booking_repository.exists(instructor_service_id=service.id)
            catalog_name = service.catalog_entry.name if service.catalog_entry else "Unknown"
            if has_bookings:
                self.service_repository.update(service.id, is_active=False)
                logger.info(
                    "Soft deleted service '%s' (ID: %s) - has existing bookings",
                    catalog_name,
                    service.id,
                )
            else:
                self.service_repository.delete(service.id)
                logger.info(
                    "Hard deleted service '%s' (ID: %s) - no bookings",
                    catalog_name,
                    service.id,
                )

    def _update_services(
        self, profile_id: str, instructor_id: str, services_data: List[ServiceCreate]
    ) -> bool:
        existing_services = self.service_repository.find_by(instructor_profile_id=profile_id)
        had_active_services = any(service.is_active for service in existing_services)
        services_by_catalog_id = {
            service.service_catalog_id: service for service in existing_services
        }
        validated_services = self._validate_service_payloads(instructor_id, services_data)
        updated_catalog_ids = self._upsert_services(
            profile_id,
            services_data,
            services_by_catalog_id,
            validated_services,
        )
        self._remove_stale_services(services_by_catalog_id, updated_catalog_ids)

        has_active_services = bool(services_data)
        self.profile_repository.update(profile_id, skills_configured=has_active_services)
        return (not had_active_services) and has_active_services

    @BaseService.measure_operation("get_available_catalog_services")
    def get_available_catalog_services(
        self, category_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        perf_debug = getattr(self, "_availability_perf_debug", False)
        cache_key = f"catalog:services:{category_id or 'all'}"
        if self.cache_service:
            cached_result = self.cache_service.get(cache_key)
            if cached_result:
                if perf_debug:
                    logger.debug("[catalog] cache hit for %s", cache_key)
                return cast(JsonList, cached_result)

        services = self.catalog_repository.get_active_services_with_categories(
            category_id=category_id
        )
        result = [self._catalog_service_to_dict(service) for service in services]

        if perf_debug:
            logger.debug("[catalog] cache miss for %s; storing %d entries", cache_key, len(result))
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
            if perf_debug:
                logger.debug("[catalog] cached %d entries for 5 minutes", len(result))
        return result

    @BaseService.measure_operation("get_service_categories")
    def get_service_categories(self) -> List[Dict[str, Any]]:
        cache_key = "categories:all"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                logger.debug("Cache hit for service categories")
                return cast(JsonList, cached)

        categories = self.category_repository.get_all_active()
        result = [
            {
                "id": category.id,
                "name": category.name,
                "subtitle": getattr(category, "subtitle", None),
                "description": category.description,
                "display_order": category.display_order,
                "icon_name": getattr(category, "icon_name", None),
            }
            for category in sorted(categories, key=lambda item: item.display_order)
        ]
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=3600)
            logger.debug("Cached service categories for 1 hour")
        return result

    @BaseService.measure_operation("create_instructor_service_from_catalog")
    def create_instructor_service_from_catalog(
        self,
        instructor_id: str,
        catalog_service_id: str,
        format_prices: List[Dict[str, Any]],
        custom_description: Optional[str] = None,
        duration_options: Optional[List[int]] = None,
        filter_selections: Optional[Dict[str, List[str]]] = None,
        age_groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        profile = self.profile_repository.find_one_by(user_id=instructor_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        catalog_service = self.catalog_repository.get_by_id(catalog_service_id)
        if not catalog_service:
            raise NotFoundException("Catalog service not found")

        merged_filter_selections = dict(filter_selections or {})
        if merged_filter_selections:
            is_valid, errors = self.taxonomy_filter_repository.validate_filter_selections(
                subcategory_id=catalog_service.subcategory_id,
                selections=merged_filter_selections,
            )
            if not is_valid:
                raise BusinessRuleException(f"Invalid filter selections: {'; '.join(errors)}")

        self._validate_age_groups_subset(catalog_service, age_groups)
        normalized_prices = self._normalize_format_prices(format_prices)
        self.validate_service_format_prices(
            instructor_id=instructor_id,
            catalog_service=catalog_service,
            format_prices=normalized_prices,
        )

        existing = self.service_repository.find_one_by(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service_id,
            is_active=True,
        )
        if existing:
            raise BusinessRuleException(f"You already offer {catalog_service.name}")

        with self.transaction():
            create_kwargs: Dict[str, Any] = {
                "instructor_profile_id": profile.id,
                "service_catalog_id": catalog_service_id,
                "description": custom_description,
                "duration_options": duration_options or [60],
                "is_active": True,
            }
            if merged_filter_selections:
                create_kwargs["filter_selections"] = merged_filter_selections
            if age_groups:
                create_kwargs["age_groups"] = age_groups
            service = self.service_repository.create(**create_kwargs)
            service.format_prices = self.service_format_pricing_repository.sync_format_prices(
                service.id,
                normalized_prices,
            )

        if self.cache_service:
            self._invalidate_instructor_caches(instructor_id)

        instructor_service_module = get_instructor_service_module()
        instructor_service_module.invalidate_on_service_change(service.id, "create")

        logger.info("Created service %s for instructor %s", catalog_service.name, instructor_id)
        service.catalog_entry = catalog_service
        return self._instructor_service_to_dict(service)

    def _catalog_service_to_dict(self, service: ServiceCatalog) -> Dict[str, Any]:
        return {
            "id": service.id,
            "subcategory_id": service.subcategory_id,
            "category_name": service.category_name,
            "name": service.name,
            "slug": service.slug,
            "description": service.description,
            "search_terms": service.search_terms or [],
            "eligible_age_groups": service.eligible_age_groups or [],
            "display_order": service.display_order,
            "online_capable": service.online_capable,
            "requires_certification": service.requires_certification,
        }

    def _instructor_service_to_dict(self, service: Service) -> Dict[str, Any]:
        catalog_name = service.catalog_entry.name if service.catalog_entry else "Unknown Service"
        return {
            "id": service.id,
            "catalog_service_id": service.service_catalog_id,
            "service_catalog_name": catalog_name,
            "name": catalog_name,
            "category": service.category,
            "min_hourly_rate": service.min_hourly_rate,
            "format_prices": service.serialized_format_prices,
            "description": service.description or service.catalog_entry.description,
            "filter_selections": service.filter_selections or {},
            "duration_options": service.duration_options,
            "offers_travel": getattr(service, "offers_travel", False),
            "offers_at_location": getattr(service, "offers_at_location", False),
            "offers_online": getattr(service, "offers_online", False),
            "is_active": service.is_active,
            "created_at": service.created_at,
            "updated_at": service.updated_at,
        }

    @BaseService.measure_operation("update_filter_selections")
    def update_filter_selections(
        self,
        instructor_id: str,
        instructor_service_id: str,
        filter_selections: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        profile = self.profile_repository.find_one_by(user_id=instructor_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        service = self.service_repository.find_one_by(id=instructor_service_id)
        if not service:
            raise NotFoundException("Instructor service not found")
        if service.instructor_profile_id != profile.id:
            raise BusinessRuleException("You do not own this service")

        catalog_service = self.catalog_repository.get_by_id(service.service_catalog_id)
        if not catalog_service:
            raise NotFoundException("Catalog service not found")

        if filter_selections:
            is_valid, errors = self.taxonomy_filter_repository.validate_filter_selections(
                subcategory_id=catalog_service.subcategory_id,
                selections=filter_selections,
            )
            if not is_valid:
                raise BusinessRuleException(f"Invalid filter selections: {'; '.join(errors)}")

        with self.transaction():
            self.service_repository.update(service.id, filter_selections=filter_selections)

        if self.cache_service:
            self._invalidate_instructor_caches(instructor_id)

        instructor_service_module = get_instructor_service_module()
        instructor_service_module.invalidate_on_service_change(service.id, "update")

        service.catalog_entry = catalog_service
        return self._instructor_service_to_dict(service)

    @BaseService.measure_operation("validate_filter_selections")
    def validate_filter_selections_for_service(
        self,
        service_catalog_id: str,
        selections: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        catalog_service = self.catalog_repository.get_by_id(service_catalog_id)
        if not catalog_service:
            raise NotFoundException("Catalog service not found")

        is_valid, errors = self.taxonomy_filter_repository.validate_filter_selections(
            subcategory_id=catalog_service.subcategory_id,
            selections=selections,
        )
        return {"valid": is_valid, "errors": errors}

    @BaseService.measure_operation("get_service_filter_context")
    def get_service_filter_context(self, service_id: str) -> Dict[str, Any]:
        service = self.catalog_repository.get_service_with_subcategory(service_id)
        if not service:
            raise NotFoundException("Service not found")

        filters = self.taxonomy_filter_repository.get_filters_for_subcategory(
            service.subcategory_id
        )
        return {
            "available_filters": filters,
            "current_selections": {},
        }
