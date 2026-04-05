from datetime import datetime
from typing import Any, List, Optional, Sequence

from pydantic import ConfigDict, Field

from ...utils.privacy import format_last_initial
from ..address import ServiceAreaNeighborhoodOut
from ..base import StandardizedModel
from ..service_pricing import ServiceFormatPriceOut
from .locations import (
    PreferredPublicSpaceOut,
    PreferredTeachingLocationOut,
    PreferredTeachingLocationPublicOut,
)
from .requests import InstructorProfileBase
from .services import ServiceResponse


class UserBasic(StandardizedModel):
    """Basic user information for embedding in responses."""

    first_name: str
    last_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class UserBasicPrivacy(StandardizedModel):
    """
    Basic user information with privacy protection.

    Shows only last initial instead of full last name for privacy.
    Used in student-facing endpoints to protect instructor privacy.
    Email is omitted for privacy protection.
    """

    id: str
    first_name: str
    last_initial: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: Any) -> "UserBasicPrivacy":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=format_last_initial(user.last_name, with_period=True),
        )


class _InstructorProfileResponseCommon(InstructorProfileBase):
    """Shared response fields and serializers for instructor profile payloads."""

    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    non_travel_buffer_minutes: int = Field(default=15)
    travel_buffer_minutes: int = Field(default=60)
    overnight_protection_enabled: bool = Field(default=True)
    calendar_settings_acknowledged_at: Optional[datetime] = Field(default=None)
    user: UserBasicPrivacy
    services: List[ServiceResponse]
    is_favorited: Optional[bool] = Field(
        None, description="Whether the current user has favorited this instructor"
    )
    favorited_count: int = Field(0, description="Number of students who favorited this instructor")
    skills_configured: bool = Field(
        default=False, description="Whether skills/pricing were configured at least once"
    )
    identity_verified_at: Optional[datetime] = Field(default=None)
    onboarding_completed_at: Optional[datetime] = Field(default=None)
    is_live: bool = Field(default=False)
    is_founding_instructor: bool = Field(
        default=False, description="Whether the instructor is a founding instructor"
    )
    preferred_public_spaces: List[PreferredPublicSpaceOut] = Field(default_factory=list)
    service_area_neighborhoods: List[ServiceAreaNeighborhoodOut] = Field(default_factory=list)
    service_area_boroughs: List[str] = Field(default_factory=list)
    service_area_summary: Optional[str] = Field(default=None)

    model_config = ConfigDict(from_attributes=True)

    @staticmethod
    def _serialize_services(instructor_profile: Any) -> List[ServiceResponse]:
        services_source: List[Any] = []
        if hasattr(instructor_profile, "instructor_services"):
            services_source = list(getattr(instructor_profile, "instructor_services", []) or [])
        elif hasattr(instructor_profile, "services"):
            services_source = list(getattr(instructor_profile, "services", []) or [])

        services_data: List[ServiceResponse] = []
        for service in sorted(services_source, key=lambda s: getattr(s, "service_catalog_id", "")):
            catalog_entry = getattr(service, "catalog_entry", None)
            catalog_name = (
                getattr(catalog_entry, "name", None) if catalog_entry is not None else None
            )
            service_payload = ServiceResponse(
                id=getattr(service, "id", None),
                service_catalog_id=getattr(service, "service_catalog_id"),
                service_catalog_name=catalog_name or "Unknown Service",
                min_hourly_rate=getattr(service, "min_hourly_rate", None),
                format_prices=[
                    ServiceFormatPriceOut(
                        format=price_row["format"],
                        hourly_rate=price_row["hourly_rate"],
                    )
                    for price_row in (getattr(service, "serialized_format_prices", None) or [])
                ],
                description=getattr(service, "description", None),
                requirements=getattr(service, "requirements", None),
                age_groups=getattr(service, "age_groups", None),
                equipment_required=getattr(service, "equipment_required", None),
                offers_travel=bool(getattr(service, "offers_travel", False)),
                offers_at_location=bool(getattr(service, "offers_at_location", False)),
                offers_online=bool(getattr(service, "offers_online", False)),
                filter_selections=getattr(service, "filter_selections", None) or {},
                duration_options=getattr(service, "duration_options", None) or [60],
            )
            services_data.append(service_payload)

        return services_data

    @staticmethod
    def _serialize_neighborhoods(
        instructor_profile: Any,
    ) -> tuple[List[ServiceAreaNeighborhoodOut], set[str]]:
        boroughs: set[str] = set()
        neighborhoods_payload: List[ServiceAreaNeighborhoodOut] = []
        neighborhoods_source = getattr(instructor_profile, "service_area_neighborhoods", None)

        if not neighborhoods_source:
            return neighborhoods_payload, boroughs

        for entry in neighborhoods_source:
            if isinstance(entry, dict):
                if entry.get("is_active") is False:
                    continue
            else:
                if getattr(entry, "is_active", True) is False:
                    continue
            if isinstance(entry, dict):
                neighborhood_id = entry.get("neighborhood_id") or entry.get("id")
                ntacode = entry.get("ntacode") or entry.get("region_code")
                name = entry.get("name") or entry.get("region_name")
                borough = entry.get("borough") or entry.get("parent_region")
            else:
                neighborhood_id = getattr(entry, "neighborhood_id", None) or getattr(
                    entry, "id", None
                )
                ntacode = getattr(entry, "ntacode", None) or getattr(entry, "region_code", None)
                name = getattr(entry, "name", None) or getattr(entry, "region_name", None)
                borough = getattr(entry, "borough", None) or getattr(entry, "parent_region", None)

            neighborhoods_payload.append(
                ServiceAreaNeighborhoodOut(
                    neighborhood_id=str(neighborhood_id) if neighborhood_id else "",
                    ntacode=ntacode,
                    name=name,
                    borough=borough,
                )
            )
            if borough:
                boroughs.add(borough)

        return neighborhoods_payload, boroughs

    @staticmethod
    def _serialize_coverage_areas(
        instructor_profile: Any,
        neighborhoods_payload: List[ServiceAreaNeighborhoodOut],
        boroughs: set[str],
    ) -> tuple[List[ServiceAreaNeighborhoodOut], set[str]]:
        if neighborhoods_payload:
            return neighborhoods_payload, boroughs

        user_service_areas: Sequence[Any] = []
        if hasattr(instructor_profile, "user") and instructor_profile.user is not None:
            user_service_areas = getattr(instructor_profile.user, "service_areas", []) or []

        for area in user_service_areas:
            if getattr(area, "is_active", True) is False:
                continue
            neighborhood = getattr(area, "neighborhood", None)
            neighborhood_id = getattr(area, "neighborhood_id", None)
            if neighborhood is None:
                continue

            borough = getattr(neighborhood, "parent_region", None) or getattr(
                neighborhood, "borough", None
            )
            ntacode = getattr(neighborhood, "region_code", None) or getattr(
                neighborhood, "ntacode", None
            )
            name = getattr(neighborhood, "region_name", None) or getattr(neighborhood, "name", None)
            neighborhoods_payload.append(
                ServiceAreaNeighborhoodOut(
                    neighborhood_id=str(getattr(neighborhood, "id", neighborhood_id or "")),
                    ntacode=ntacode,
                    name=name,
                    borough=borough,
                )
            )
            if borough:
                boroughs.add(borough)

        return neighborhoods_payload, boroughs

    @classmethod
    def _preferred_places(cls, instructor_profile: Any) -> list[Any]:
        if hasattr(instructor_profile, "user") and instructor_profile.user is not None:
            return getattr(instructor_profile.user, "preferred_places", []) or []
        return []

    @classmethod
    def _serialize_public_teaching_locations(
        cls, instructor_profile: Any
    ) -> List[PreferredTeachingLocationPublicOut]:
        teaching_locations: List[PreferredTeachingLocationPublicOut] = []
        preferred_places = cls._preferred_places(instructor_profile)
        if not preferred_places:
            return teaching_locations

        teaching_sorted = sorted(
            [p for p in preferred_places if getattr(p, "kind", None) == "teaching_location"],
            key=lambda place: getattr(place, "position", 0),
        )
        for place in teaching_sorted:
            teaching_locations.append(
                PreferredTeachingLocationPublicOut(
                    label=getattr(place, "label", None),
                    approx_lat=getattr(place, "approx_lat", None),
                    approx_lng=getattr(place, "approx_lng", None),
                    neighborhood=getattr(place, "neighborhood", None),
                )
            )
        return teaching_locations

    @classmethod
    def _serialize_public_spaces(cls, instructor_profile: Any) -> List[PreferredPublicSpaceOut]:
        public_spaces: List[PreferredPublicSpaceOut] = []
        preferred_places = cls._preferred_places(instructor_profile)
        if not preferred_places:
            return public_spaces

        public_sorted = sorted(
            [p for p in preferred_places if getattr(p, "kind", None) == "public_space"],
            key=lambda place: getattr(place, "position", 0),
        )
        for place in public_sorted:
            public_spaces.append(
                PreferredPublicSpaceOut(
                    address=getattr(place, "address", ""),
                    label=getattr(place, "label", None),
                )
            )
        return public_spaces

    @classmethod
    def _base_payload(cls, instructor_profile: Any) -> dict[str, Any]:
        services_data = cls._serialize_services(instructor_profile)
        neighborhoods_payload, boroughs = cls._serialize_neighborhoods(instructor_profile)
        neighborhoods_payload, boroughs = cls._serialize_coverage_areas(
            instructor_profile, neighborhoods_payload, boroughs
        )
        sorted_boroughs = sorted(boroughs)
        if sorted_boroughs:
            if len(sorted_boroughs) <= 2:
                service_area_summary = ", ".join(sorted_boroughs)
            else:
                service_area_summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
        else:
            service_area_summary = None
        neighborhoods_output = [entry.model_dump(mode="python") for entry in neighborhoods_payload]
        return {
            "id": instructor_profile.id,
            "user_id": instructor_profile.user_id,
            "created_at": instructor_profile.created_at,
            "updated_at": instructor_profile.updated_at,
            "bio": instructor_profile.bio,
            "years_experience": instructor_profile.years_experience,
            "non_travel_buffer_minutes": getattr(
                instructor_profile, "non_travel_buffer_minutes", 15
            ),
            "travel_buffer_minutes": getattr(instructor_profile, "travel_buffer_minutes", 60),
            "overnight_protection_enabled": getattr(
                instructor_profile, "overnight_protection_enabled", True
            ),
            "calendar_settings_acknowledged_at": getattr(
                instructor_profile, "calendar_settings_acknowledged_at", None
            ),
            "user": UserBasicPrivacy.from_user(instructor_profile.user),
            "services": services_data,
            "is_favorited": getattr(instructor_profile, "is_favorited", None),
            "favorited_count": getattr(instructor_profile, "favorited_count", 0),
            "skills_configured": getattr(instructor_profile, "skills_configured", False),
            "identity_verified_at": getattr(instructor_profile, "identity_verified_at", None),
            "onboarding_completed_at": getattr(instructor_profile, "onboarding_completed_at", None),
            "is_live": getattr(instructor_profile, "is_live", False),
            "is_founding_instructor": getattr(instructor_profile, "is_founding_instructor", False),
            "preferred_public_spaces": cls._serialize_public_spaces(instructor_profile),
            "service_area_neighborhoods": neighborhoods_output,
            "service_area_boroughs": sorted_boroughs,
            "service_area_summary": service_area_summary,
        }


class InstructorProfilePublic(_InstructorProfileResponseCommon):
    """
    Public/student-facing instructor profile response.

    Excludes internal verification session IDs and private teaching addresses.
    """

    preferred_teaching_locations: List[PreferredTeachingLocationPublicOut] = Field(
        default_factory=list
    )

    @classmethod
    def from_orm(cls, instructor_profile: Any) -> "InstructorProfilePublic":
        payload = cls._base_payload(instructor_profile)
        payload["preferred_teaching_locations"] = cls._serialize_public_teaching_locations(
            instructor_profile
        )
        return cls(**payload)


class InstructorProfileResponse(_InstructorProfileResponseCommon):
    """Private/self instructor profile response with internal identifiers."""

    preferred_teaching_locations: List[PreferredTeachingLocationOut] = Field(default_factory=list)
    identity_name_mismatch: bool = Field(default=False)
    bgc_name_mismatch: bool = Field(default=False)
    background_check_uploaded_at: Optional[datetime] = Field(default=None)
    bgc_status: Optional[str] = Field(default=None)
    identity_verification_session_id: Optional[str] = Field(default=None)
    background_check_object_key: Optional[str] = Field(default=None)

    @classmethod
    def _serialize_private_teaching_locations(
        cls, instructor_profile: Any
    ) -> List[PreferredTeachingLocationOut]:
        teaching_locations: List[PreferredTeachingLocationOut] = []
        preferred_places = cls._preferred_places(instructor_profile)
        if not preferred_places:
            return teaching_locations

        teaching_sorted = sorted(
            [p for p in preferred_places if getattr(p, "kind", None) == "teaching_location"],
            key=lambda place: getattr(place, "position", 0),
        )
        for place in teaching_sorted:
            teaching_locations.append(
                PreferredTeachingLocationOut(
                    address=getattr(place, "address", None),
                    label=getattr(place, "label", None),
                    approx_lat=getattr(place, "approx_lat", None),
                    approx_lng=getattr(place, "approx_lng", None),
                    neighborhood=getattr(place, "neighborhood", None),
                )
            )
        return teaching_locations

    @classmethod
    def from_orm(cls, instructor_profile: Any) -> "InstructorProfileResponse":
        payload = cls._base_payload(instructor_profile)
        bgc_status_raw = getattr(instructor_profile, "bgc_status", None)
        payload["preferred_teaching_locations"] = cls._serialize_private_teaching_locations(
            instructor_profile
        )
        payload["identity_name_mismatch"] = getattr(
            instructor_profile, "identity_name_mismatch", False
        )
        payload["bgc_name_mismatch"] = getattr(instructor_profile, "bgc_name_mismatch", False)
        payload["background_check_uploaded_at"] = getattr(
            instructor_profile, "background_check_uploaded_at", None
        )
        payload["bgc_status"] = bgc_status_raw if isinstance(bgc_status_raw, str) else None
        payload["identity_verification_session_id"] = getattr(
            instructor_profile, "identity_verification_session_id", None
        )
        payload["background_check_object_key"] = getattr(
            instructor_profile, "background_check_object_key", None
        )
        return cls(**payload)
