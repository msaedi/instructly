"""Profile mutation flows for InstructorService."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Sequence, cast

from ...core.enums import RoleName
from ...core.exceptions import BusinessRuleException, NotFoundException
from ...models.user import User
from ...schemas.instructor import (
    CalendarSettingsAcknowledgeResponse,
    CalendarSettingsResponse,
    InstructorProfileCreate,
    InstructorProfileUpdate,
    ServiceCreate,
    UpdateCalendarSettings,
)
from ..base import BaseService
from .mixin_base import (
    InstructorMixinBase,
    PreparedProfileUpdateContext,
    PreparedTeachingLocationGeocode,
    get_instructor_service_module,
)

logger = logging.getLogger(__name__)


class InstructorProfileMutationsMixin(InstructorMixinBase):
    """Profile create/update/delete, calendar settings, cache invalidation."""

    @BaseService.measure_operation("create_instructor_profile")
    def create_instructor_profile(
        self, user: User, profile_data: InstructorProfileCreate
    ) -> Dict[str, Any]:
        """Create a new instructor profile."""
        if self.profile_repository.exists(user_id=user.id):
            raise BusinessRuleException(
                "Instructor profile already exists",
                code="instructor_profile_exists",
            )

        with self.transaction():
            if profile_data.services:
                catalog_ids = [service.service_catalog_id for service in profile_data.services]
                self._validate_catalog_ids(catalog_ids)

            profile_dict = profile_data.model_dump(exclude={"services"})
            profile_dict["user_id"] = user.id
            profile = self.profile_repository.create(**profile_dict)

            for service_data in profile_data.services:
                service_dict = service_data.model_dump()
                catalog_service = self.catalog_repository.get_by_id(service_data.service_catalog_id)
                if not catalog_service:
                    raise NotFoundException("Catalog service not found")
                self._validate_age_groups_subset(catalog_service, service_dict.get("age_groups"))
                normalized_prices = self._normalize_format_prices(service_dict.pop("format_prices"))
                self.validate_service_format_prices(
                    instructor_id=user.id,
                    catalog_service=catalog_service,
                    format_prices=normalized_prices,
                )
                service_dict["instructor_profile_id"] = profile.id
                service = self.service_repository.create(**service_dict)
                service.format_prices = self.service_format_pricing_repository.sync_format_prices(
                    service.id,
                    normalized_prices,
                )

            from app.services.permission_service import PermissionService

            permission_service = PermissionService(self.db)
            permission_service.assign_role(user.id, RoleName.INSTRUCTOR)

            refreshed_user = self.user_repository.get_by_id(user.id)
            profile.user = refreshed_user or user
            self.db.expire(profile, ["instructor_services"])

        logger.info("Created instructor profile for user %s", user.id)
        return self._profile_to_dict(profile)

    @staticmethod
    def _extract_profile_basic_updates(update_data: InstructorProfileUpdate) -> dict[str, Any]:
        """Return profile fields persisted directly on the instructor profile row."""
        return update_data.model_dump(
            exclude={"services", "preferred_teaching_locations", "preferred_public_spaces"},
            exclude_unset=True,
        )

    @staticmethod
    def _oxford_join(items: List[str]) -> str:
        """Join display strings using an Oxford comma."""
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"

    def _build_auto_bio(
        self,
        user_id: str,
        services: Sequence[ServiceCreate],
        *,
        user_record: User | None = None,
        city: str | None = None,
    ) -> str:
        """Generate a default bio for instructors completing their profile."""
        try:
            resolved_user = user_record or cast(
                "User | None", self.user_repository.get_by_id(user_id)
            )
            first_name = getattr(resolved_user, "first_name", "") or "This instructor"
            resolved_city = city or "New York"
            skill_names: List[str] = []
            try:
                for service in services:
                    catalog_entry = self.catalog_repository.get_by_id(service.service_catalog_id)
                    if catalog_entry and getattr(catalog_entry, "name", None):
                        skill_names.append(str(catalog_entry.name).strip().lower())
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)

            skills_phrase = self._oxford_join(skill_names)
            if skills_phrase:
                return f"{first_name} is a {resolved_city}-based {skills_phrase} instructor."
            return f"{first_name} is a {resolved_city}-based instructor."
        except Exception as exc:
            logger.warning(
                "bio_generation_fallback",
                extra={"user_id": user_id, "error": str(exc)},
                exc_info=True,
            )
            return "Experienced instructor"

    async def _prepare_profile_update_context(
        self, user_id: str, update_data: InstructorProfileUpdate
    ) -> PreparedProfileUpdateContext:
        """Prepare async geocoding work before the sync persistence path runs."""
        context = PreparedProfileUpdateContext()
        provider: Any | None = None
        instructor_service_module = get_instructor_service_module()

        def _get_provider() -> Any:
            nonlocal provider
            if provider is None:
                provider = instructor_service_module.create_geocoding_provider()
            return provider

        basic_updates = self._extract_profile_basic_updates(update_data)
        if update_data.services is not None and "bio" not in basic_updates:
            profile = await asyncio.to_thread(self.profile_repository.find_one_by, user_id=user_id)
            missing_bio = not getattr(profile, "bio", None) or not str(profile.bio).strip()
            try:
                context.user_record = await asyncio.to_thread(
                    self.user_repository.get_by_id, user_id
                )
            except Exception:
                logger.debug("Non-fatal error loading user for bio generation", exc_info=True)
            if missing_bio:
                try:
                    user_record = context.user_record
                    if user_record and getattr(user_record, "zip_code", None):
                        geocoded = await _get_provider().geocode(user_record.zip_code)
                        if geocoded and getattr(geocoded, "city", None):
                            context.bio_city = geocoded.city
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)

        if update_data.preferred_teaching_locations is None:
            return context

        existing_places_by_address: dict[str, dict[str, Any | None]] = {}
        try:
            existing_places = await asyncio.to_thread(
                self.preferred_place_repository.list_for_instructor_and_kind,
                user_id,
                "teaching_location",
            )
            for place in existing_places:
                address_key = str(place.address or "").strip().lower()
                if address_key:
                    existing_places_by_address[address_key] = {
                        "lat": getattr(place, "lat", None),
                        "lng": getattr(place, "lng", None),
                        "approx_lat": getattr(place, "approx_lat", None),
                        "approx_lng": getattr(place, "approx_lng", None),
                    }
        except Exception:
            logger.debug("Non-fatal error loading existing teaching locations", exc_info=True)

        for item in update_data.preferred_teaching_locations:
            address = item.address.strip()
            address_key = address.lower()
            if not address or address_key in context.teaching_location_geocodes:
                continue

            existing_place = existing_places_by_address.get(address_key, {})
            has_existing_geo = (
                existing_place.get("approx_lat") is not None
                and existing_place.get("approx_lng") is not None
            ) or (existing_place.get("lat") is not None and existing_place.get("lng") is not None)
            if has_existing_geo:
                continue

            try:
                geocoded = await _get_provider().geocode(address)
                if geocoded:
                    context.teaching_location_geocodes[
                        address_key
                    ] = PreparedTeachingLocationGeocode(
                        lat=getattr(geocoded, "latitude", None),
                        lng=getattr(geocoded, "longitude", None),
                        place_id=getattr(geocoded, "provider_id", None),
                        neighborhood=getattr(geocoded, "neighborhood", None),
                        city=getattr(geocoded, "city", None),
                        state=getattr(geocoded, "state", None),
                    )
            except Exception:
                logger.debug(
                    "Non-fatal geocoding error for teaching location",
                    extra={"address": address},
                    exc_info=True,
                )

        return context

    @BaseService.measure_operation("update_instructor_profile_async")
    async def update_instructor_profile_async(
        self, user_id: str, update_data: InstructorProfileUpdate
    ) -> Dict[str, Any]:
        """Prepare async geocoding work, then persist the update on a worker thread."""
        prepared_context = await self._prepare_profile_update_context(user_id, update_data)
        return await asyncio.to_thread(
            self.update_instructor_profile,
            user_id,
            update_data,
            prepared_context,
        )

    @BaseService.measure_operation("update_instructor_profile")
    def update_instructor_profile(
        self,
        user_id: str,
        update_data: InstructorProfileUpdate,
        prepared_context: PreparedProfileUpdateContext | None = None,
    ) -> Dict[str, Any]:
        """Update instructor profile with proper soft delete handling."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        instructor_service_module = get_instructor_service_module()
        with self.transaction():
            basic_updates = self._extract_profile_basic_updates(update_data)
            if update_data.services is not None:
                missing_bio = not getattr(profile, "bio", None) or not str(profile.bio).strip()
                if "bio" not in basic_updates and missing_bio:
                    basic_updates["bio"] = self._build_auto_bio(
                        user_id,
                        update_data.services,
                        user_record=prepared_context.user_record if prepared_context else None,
                        city=prepared_context.bio_city if prepared_context else None,
                    )

            if basic_updates:
                self.profile_repository.update(profile.id, **basic_updates)

            resolved_bio = basic_updates.get("bio", profile.bio)
            resolved_years = basic_updates.get("years_experience", profile.years_experience)
            if update_data.preferred_teaching_locations is not None:
                self._replace_preferred_places(
                    instructor_id=user_id,
                    kind="teaching_location",
                    items=update_data.preferred_teaching_locations,
                    geocoded_locations=(
                        prepared_context.teaching_location_geocodes if prepared_context else None
                    ),
                )
            if update_data.preferred_public_spaces is not None:
                self._replace_preferred_places(
                    instructor_id=user_id,
                    kind="public_space",
                    items=update_data.preferred_public_spaces,
                )

            services_configured_now = False
            if update_data.services is not None:
                services_configured_now = self._update_services(
                    profile.id, user_id, update_data.services
                )

            bio_value = str(resolved_bio or "").strip()
            if bio_value and resolved_years is not None:
                instructor_service_module.InstructorLifecycleService(
                    self.db
                ).record_profile_submitted(profile.user_id)
            if services_configured_now:
                instructor_service_module.InstructorLifecycleService(
                    self.db
                ).record_services_configured(profile.user_id)

        if self.cache_service:
            self._invalidate_instructor_caches(user_id)
        instructor_service_module.invalidate_on_instructor_profile_change(user_id)
        return self.get_instructor_profile(user_id)

    @BaseService.measure_operation("update_calendar_settings")
    def update_calendar_settings(
        self, user_id: str, update_data: UpdateCalendarSettings
    ) -> Dict[str, Any]:
        """Update instructor calendar settings independently from the profile form."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        updates = update_data.model_dump(exclude_unset=True)
        with self.transaction():
            updated_profile = self.profile_repository.update(profile.id, **updates)

        if self.cache_service:
            self._invalidate_instructor_caches(user_id)
        get_instructor_service_module().invalidate_on_instructor_profile_change(user_id)

        effective = updated_profile or profile
        return CalendarSettingsResponse(
            non_travel_buffer_minutes=getattr(effective, "non_travel_buffer_minutes", 15),
            travel_buffer_minutes=getattr(effective, "travel_buffer_minutes", 60),
            overnight_protection_enabled=getattr(effective, "overnight_protection_enabled", True),
        ).model_dump(mode="python")

    @BaseService.measure_operation("acknowledge_calendar_settings")
    def acknowledge_calendar_settings(self, user_id: str) -> Dict[str, Any]:
        """Persist the first-save acknowledgement timestamp for calendar settings."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        acknowledged_at = getattr(profile, "calendar_settings_acknowledged_at", None)
        if acknowledged_at is None:
            acknowledged_at = datetime.now(timezone.utc)
            with self.transaction():
                updated_profile = self.profile_repository.update(
                    profile.id,
                    calendar_settings_acknowledged_at=acknowledged_at,
                )
                acknowledged_at = getattr(
                    updated_profile,
                    "calendar_settings_acknowledged_at",
                    acknowledged_at,
                )

            if self.cache_service:
                self._invalidate_instructor_caches(user_id)
            get_instructor_service_module().invalidate_on_instructor_profile_change(user_id)

        return CalendarSettingsAcknowledgeResponse(
            calendar_settings_acknowledged_at=acknowledged_at
        ).model_dump(mode="python")

    @BaseService.measure_operation("delete_instructor_profile")
    def delete_instructor_profile(self, user_id: str) -> None:
        """Delete instructor profile and revert to student role."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        with self.transaction():
            services = self.service_repository.find_by(instructor_profile_id=profile.id)
            for service in services:
                if service.is_active:
                    self.service_repository.update(service.id, is_active=False)

            self.service_repository.flush()
            self.profile_repository.delete(profile.id)

            from app.services.permission_service import PermissionService

            permission_service = PermissionService(self.db)
            permission_service.remove_role(user_id, RoleName.INSTRUCTOR)
            permission_service.assign_role(user_id, RoleName.STUDENT)

        if self.cache_service:
            self._invalidate_instructor_caches(user_id)
        get_instructor_service_module().invalidate_on_instructor_profile_change(user_id)

        logger.info("Deleted instructor profile for user %s", user_id)
        try:
            from ..availability_service import AvailabilityService

            availability_service = AvailabilityService(self.db)
            purged = availability_service.delete_orphan_availability_for_instructor(
                user_id,
                keep_days_with_bookings=True,
            )
            logger.info(
                "instructor_delete: purged_orphan_days=%s instructor_id=%s", purged, user_id
            )
        except Exception as cleanup_error:
            logger.warning(
                "instructor_delete: failed to purge orphan availability for %s (%s)",
                user_id,
                cleanup_error,
            )

    def _invalidate_instructor_caches(self, user_id: str) -> None:
        """Invalidate all caches related to an instructor."""
        if not self.cache_service:
            return

        self.cache_service.delete(f"instructor:public:{user_id}")
        self.cache_service.invalidate_instructor_availability(user_id)
        self.cache_service.delete_pattern("instructors:list:*")
        self.cache_service.clear_prefix("catalog:services:")
        self.cache_service.clear_prefix("catalog:top-services:")
        self.cache_service.clear_prefix("catalog:all-services")
        self.cache_service.clear_prefix("catalog:kids-available")
        self.cache_service.clear_prefix("service_catalog:list")
        self.cache_service.clear_prefix("service_catalog:search")
        self.cache_service.clear_prefix("service_catalog:trending")
        logger.debug("Invalidated caches for instructor %s", user_id)
