"""Profile reads and profile serialization helpers for InstructorService."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, cast

from ...core.exceptions import NotFoundException
from ...models.instructor import InstructorPreferredPlace, InstructorProfile
from ...models.user import User
from ...utils.privacy import format_last_initial
from ..base import BaseService
from .mixin_base import InstructorMixinBase, JsonDict


class InstructorProfileReadsMixin(InstructorMixinBase):
    """Profile reads, public profile, and profile serialization."""

    @BaseService.measure_operation("get_instructor_profile")
    def get_instructor_profile(
        self, user_id: str, include_inactive_services: bool = False
    ) -> Dict[str, Any]:
        """Get instructor profile with proper service filtering."""
        profile = self.profile_repository.get_by_user_id_with_details(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")
        return self._profile_to_dict(profile, include_inactive_services)

    @BaseService.measure_operation("get_instructor_user")
    def get_instructor_user(self, user_id: str) -> User:
        """Get the User object for an instructor, validating they have a profile."""
        user = self.user_repository.get_by_id(user_id)
        if user:
            profile = self.profile_repository.get_by_user_id(user.id)
            if not profile:
                raise NotFoundException("Instructor not found")
            return cast(User, user)

        profile = self.profile_repository.get_by_id(user_id)
        if not profile:
            raise NotFoundException("Instructor not found")

        resolved_user = self.user_repository.get_by_id(profile.user_id)
        if not resolved_user:
            raise NotFoundException("Instructor not found")
        return cast(User, resolved_user)

    @BaseService.measure_operation("get_all_instructors")
    def get_all_instructors(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all instructor profiles with active services only."""
        profiles = self.profile_repository.get_all_with_details(skip=skip, limit=limit)
        return [self._profile_to_dict(profile) for profile in profiles]

    @BaseService.measure_operation("get_public_instructor_profile")
    def get_public_instructor_profile(self, instructor_id: str) -> Dict[str, Any] | None:
        """Return a public-facing instructor profile when visible."""
        cache_key = f"instructor:public:{instructor_id}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached:
                return cast(JsonDict, cached)

        profile = self.profile_repository.get_public_by_id(instructor_id)
        if not profile:
            return None

        result = self._public_profile_to_dict(profile)
        if self.cache_service:
            self.cache_service.set(cache_key, result, ttl=300)
        return result

    def _build_services_dict(
        self,
        profile: InstructorProfile,
        include_inactive_services: bool,
    ) -> List[Dict[str, Any]]:
        """Serialize instructor services and attach format pricing."""
        svcs_source = getattr(profile, "services", None)
        if svcs_source is None:
            svcs_source = getattr(profile, "instructor_services", []) or []

        try:
            services = list(svcs_source or [])
        except TypeError:
            services = []

        if not include_inactive_services:
            services = [service for service in services if getattr(service, "is_active", True)]

        if services:
            service_ids = [service.id for service in services if getattr(service, "id", None)]
            prices_by_service = self.service_format_pricing_repository.get_prices_for_services(
                service_ids
            )
            for service in services:
                service.format_prices = prices_by_service.get(service.id, [])

        return [
            {
                "id": service.id,
                "service_catalog_id": service.service_catalog_id,
                "service_catalog_name": service.catalog_entry.name
                if service.catalog_entry
                else "Unknown Service",
                "name": service.catalog_entry.name if service.catalog_entry else "Unknown Service",
                "min_hourly_rate": service.min_hourly_rate,
                "format_prices": service.serialized_format_prices,
                "description": service.description,
                "age_groups": service.age_groups,
                "filter_selections": service.filter_selections or {},
                "equipment_required": service.equipment_required,
                "offers_travel": getattr(service, "offers_travel", False),
                "offers_at_location": getattr(service, "offers_at_location", False),
                "offers_online": getattr(service, "offers_online", False),
                "duration_options": service.duration_options,
                "is_active": service.is_active,
            }
            for service in sorted(services, key=lambda item: item.service_catalog_id)
        ]

    def _build_preferred_places_dict(
        self, profile: InstructorProfile
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Serialize preferred teaching locations and public spaces."""
        user = getattr(profile, "user", None)
        preferred_places: Sequence[InstructorPreferredPlace]
        if user is not None and hasattr(user, "preferred_places"):
            raw_places = getattr(user, "preferred_places", None)
            try:
                preferred_places = list(raw_places or [])
            except TypeError:
                preferred_places = []
        else:
            preferred_places = self.preferred_place_repository.list_for_instructor(profile.user_id)

        teaching_locations: List[Dict[str, Any]] = []
        public_spaces: List[Dict[str, Any]] = []
        if not preferred_places:
            return teaching_locations, public_spaces

        teaching_places = sorted(
            [place for place in preferred_places if place.kind == "teaching_location"],
            key=lambda place: place.position,
        )
        public_places = sorted(
            [place for place in preferred_places if place.kind == "public_space"],
            key=lambda place: place.position,
        )

        for place in teaching_places:
            teaching_entry: Dict[str, Any] = {"address": place.address}
            if place.label:
                teaching_entry["label"] = place.label
            if getattr(place, "approx_lat", None) is not None:
                teaching_entry["approx_lat"] = place.approx_lat
            if getattr(place, "approx_lng", None) is not None:
                teaching_entry["approx_lng"] = place.approx_lng
            if getattr(place, "neighborhood", None):
                teaching_entry["neighborhood"] = place.neighborhood
            teaching_locations.append(teaching_entry)

        for place in public_places:
            public_entry: Dict[str, Any] = {"address": place.address}
            if place.label:
                public_entry["label"] = place.label
            public_spaces.append(public_entry)

        return teaching_locations, public_spaces

    def _build_service_areas_dict(
        self, profile: InstructorProfile
    ) -> tuple[List[Dict[str, Any]], List[str], str]:
        """Serialize service area neighborhoods and summary text."""
        if profile.user and hasattr(profile.user, "service_areas"):
            service_area_records = list(profile.user.service_areas)
        else:
            service_area_records = self.service_area_repository.list_for_instructor(profile.user_id)

        service_area_records = [
            area for area in service_area_records if getattr(area, "is_active", True)
        ]
        service_area_neighborhoods: List[Dict[str, Any]] = []
        boroughs: set[str] = set()

        for area in service_area_records:
            region = getattr(area, "neighborhood", None)
            region_code = getattr(region, "region_code", None) if region is not None else None
            region_name = getattr(region, "region_name", None) if region is not None else None
            borough = getattr(region, "parent_region", None) if region is not None else None
            region_meta = getattr(region, "region_metadata", None) if region is not None else None
            if isinstance(region_meta, dict):
                region_code = (
                    region_code or region_meta.get("nta_code") or region_meta.get("ntacode")
                )
                region_name = region_name or region_meta.get("nta_name") or region_meta.get("name")
                borough = borough or region_meta.get("borough")

            if borough:
                boroughs.add(borough)

            service_area_neighborhoods.append(
                {
                    "neighborhood_id": area.neighborhood_id,
                    "ntacode": region_code,
                    "name": region_name,
                    "borough": borough,
                }
            )

        sorted_boroughs = sorted(boroughs)
        if not sorted_boroughs:
            service_area_summary = ""
        elif len(sorted_boroughs) <= 2:
            service_area_summary = ", ".join(sorted_boroughs)
        else:
            service_area_summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"

        return service_area_neighborhoods, sorted_boroughs, service_area_summary

    @staticmethod
    def _build_user_summary(profile: InstructorProfile) -> Dict[str, Any] | None:
        """Serialize the public user summary for an instructor profile."""
        if not hasattr(profile, "user") or not profile.user:
            return None

        return {
            "id": profile.user.id,
            "first_name": profile.user.first_name,
            "last_initial": format_last_initial(profile.user.last_name, with_period=True),
        }

    def _profile_to_dict(
        self,
        profile: InstructorProfile,
        include_inactive_services: bool = False,
    ) -> Dict[str, Any]:
        """Convert instructor profile to dictionary."""
        services = self._build_services_dict(profile, include_inactive_services)
        teaching_locations, public_spaces = self._build_preferred_places_dict(profile)
        (
            service_area_neighborhoods,
            service_area_boroughs,
            service_area_summary,
        ) = self._build_service_areas_dict(profile)

        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "bio": profile.bio,
            "years_experience": profile.years_experience,
            "non_travel_buffer_minutes": getattr(profile, "non_travel_buffer_minutes", 15),
            "travel_buffer_minutes": getattr(profile, "travel_buffer_minutes", 60),
            "overnight_protection_enabled": getattr(profile, "overnight_protection_enabled", True),
            "calendar_settings_acknowledged_at": getattr(
                profile, "calendar_settings_acknowledged_at", None
            ),
            "preferred_teaching_locations": teaching_locations,
            "preferred_public_spaces": public_spaces,
            "service_area_neighborhoods": service_area_neighborhoods,
            "service_area_boroughs": service_area_boroughs,
            "service_area_summary": service_area_summary,
            "skills_configured": getattr(profile, "skills_configured", False),
            "identity_verified_at": profile.identity_verified_at,
            "identity_name_mismatch": getattr(profile, "identity_name_mismatch", False),
            "bgc_name_mismatch": getattr(profile, "bgc_name_mismatch", False),
            "identity_verification_session_id": getattr(
                profile, "identity_verification_session_id", None
            ),
            "background_check_object_key": getattr(profile, "background_check_object_key", None),
            "background_check_uploaded_at": getattr(profile, "background_check_uploaded_at", None),
            "onboarding_completed_at": getattr(profile, "onboarding_completed_at", None),
            "is_live": getattr(profile, "is_live", False),
            "is_founding_instructor": getattr(profile, "is_founding_instructor", False),
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "user": self._build_user_summary(profile),
            "services": services,
        }

    def _public_profile_to_dict(
        self,
        profile: InstructorProfile,
        include_inactive_services: bool = False,
    ) -> Dict[str, Any]:
        """Convert an instructor profile into the public/student-facing response shape."""
        profile_data = self._profile_to_dict(
            profile,
            include_inactive_services=include_inactive_services,
        )
        profile_data.pop("identity_verification_session_id", None)
        profile_data.pop("background_check_object_key", None)
        for location in profile_data.get("preferred_teaching_locations", []):
            if isinstance(location, dict):
                location.pop("address", None)
        return profile_data
