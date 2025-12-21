"""
Instructor profile schemas for InstaInstru platform.

This module defines Pydantic schemas for instructor-related operations,
including profile management and service offerings.

Note: The old booking-related fields (buffer_time, minimum_advance_hours,
default_session_duration) have been removed as part of the refactoring.
These will be reimplemented differently in the new booking system.
"""

from datetime import datetime
import logging
from typing import Any, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from ..core.constants import (
    MAX_BIO_LENGTH,
    MAX_SESSION_DURATION,
    MIN_BIO_LENGTH,
    MIN_SESSION_DURATION,
)
from ._strict_base import StrictRequestModel
from .address import ServiceAreaNeighborhoodOut
from .base import Money, StandardizedModel

logger = logging.getLogger(__name__)


class InstructorFilterParams(BaseModel):
    """
    Query parameters for filtering instructors.

    All fields are optional to maintain backward compatibility.
    Supports text search, skill filtering, and price range filtering.
    """

    search: Optional[str] = Field(
        None,
        description="Text search across instructor name, bio, and services",
        min_length=1,
        max_length=100,
    )
    service_catalog_id: Optional[str] = Field(
        None, description="Filter by specific service catalog ID"
    )
    min_price: Optional[float] = Field(
        None, ge=0, le=1000, description="Minimum hourly rate filter"
    )
    max_price: Optional[float] = Field(
        None, ge=0, le=1000, description="Maximum hourly rate filter"
    )
    age_group: Optional[str] = Field(
        None,
        description="Age group filter. Allowed: 'kids' or 'adults'. If omitted, no age filter is applied.",
    )

    @field_validator("max_price")
    def validate_price_range(cls, v: Optional[float], info: Any) -> Optional[float]:
        """Ensure max_price >= min_price if both are provided."""
        if v is not None and hasattr(info, "data") and "min_price" in info.data:
            min_price = info.data["min_price"]
            if min_price is not None and v < min_price:
                raise ValueError("max_price must be greater than or equal to min_price")
        return v

    @field_validator("search")
    def clean_string_fields(cls, v: Optional[str]) -> Optional[str]:
        """Clean and normalize string fields."""
        if v is not None:
            return v.strip()
        return v

    @field_validator("age_group")
    def validate_age_group(cls, v: Optional[str]) -> Optional[str]:
        # Treat None or empty string as "no filter"
        if v is None or v == "":
            return None
        vv = str(v).strip().lower()
        # Also treat stripped empty or 'both' as no filter
        if vv == "" or vv == "both":
            return None
        if vv not in {"kids", "adults"}:
            raise ValueError("age_group must be one of: 'kids', 'adults'")
        return vv

    # Enforce strictness for query param schema when instantiated explicitly
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PreferredTeachingLocationIn(BaseModel):
    """Preferred teaching location input payload."""

    address: str = Field(..., min_length=1, max_length=512)
    label: str | None = Field(default=None, min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PreferredPublicSpaceIn(BaseModel):
    """Preferred public space input payload."""

    address: str = Field(..., min_length=1, max_length=512)
    label: str | None = Field(default=None, min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PreferredTeachingLocationOut(PreferredTeachingLocationIn):
    """Preferred teaching location response payload."""

    model_config = ConfigDict(from_attributes=True)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {"address": self.address}
        if self.label is not None:
            data["label"] = self.label
        return data


class PreferredPublicSpaceOut(PreferredPublicSpaceIn):
    """Preferred public space response payload."""

    model_config = ConfigDict(from_attributes=True)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {"address": self.address}
        if self.label is not None:
            data["label"] = self.label
        return data


class ServiceBase(StandardizedModel):
    """
    Base schema for instructor services.

    Attributes:
        service_catalog_id: ID of the service from the catalog
        hourly_rate: Rate per hour in USD
        description: Optional description of the service
        duration_options: Available duration options for this service in minutes
    """

    service_catalog_id: str = Field(..., description="ID of the service from catalog")
    hourly_rate: Money = Field(
        ..., gt=0, le=1000, description="Hourly rate in USD"
    )  # Changed from float
    description: Optional[str] = Field(None, max_length=500)
    requirements: Optional[str] = Field(None, max_length=500)
    age_groups: Optional[List[str]] = Field(
        default=None,
        description="Age groups this service is offered to. Allowed: 'kids', 'adults'. Use both for both.",
    )
    levels_taught: Optional[List[str]] = Field(
        default=None,
        description="Levels taught. Allowed: 'beginner', 'intermediate', 'advanced'",
    )
    equipment_required: Optional[List[str]] = Field(
        default=None,
        description="List of equipment required (strings)",
    )
    location_types: Optional[List[str]] = Field(
        default=None,
        description="Where lessons are offered. Allowed: 'in-person', 'online'",
    )
    duration_options: List[int] = Field(
        default=[60],
        description="Available duration options for this service in minutes",
        min_length=1,
    )

    @field_validator("duration_options")
    def validate_duration_range(cls, v: List[int]) -> List[int]:
        """Ensure each duration is within valid range."""
        if not v:
            raise ValueError("At least one duration option is required")
        for duration in v:
            if not MIN_SESSION_DURATION <= duration <= MAX_SESSION_DURATION:
                raise ValueError(
                    f"Duration must be between {MIN_SESSION_DURATION} and {MAX_SESSION_DURATION} minutes"
                )
        return v

    @field_validator("age_groups")
    def validate_age_groups(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize and validate age groups.

        Accepts ['kids'], ['adults'], or ['kids','adults'].
        Collapses duplicates and ignores casing. Raises if unknown values provided.
        """
        if v is None:
            return v
        allowed = {"kids", "adults"}
        normalized: List[str] = []
        for item in v:
            value = str(item).strip().lower()
            if value == "both":
                normalized.extend(["kids", "adults"])
            elif value in allowed:
                normalized.append(value)
            else:
                raise ValueError("age_groups must be one or more of: 'kids', 'adults'")
        # De-duplicate while preserving order
        seen: set[str] = set()
        deduped: List[str] = []
        for item in normalized:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    @field_validator("levels_taught")
    def validate_levels_taught(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize and validate levels_taught.

        Allowed values: beginner, intermediate, advanced.
        """
        if v is None:
            return v
        allowed = {"beginner", "intermediate", "advanced"}
        normalized: List[str] = []
        for item in v:
            value = str(item).strip().lower()
            if value not in allowed:
                raise ValueError(
                    "levels_taught must be any of: 'beginner', 'intermediate', 'advanced'"
                )
            if value not in normalized:
                normalized.append(value)
        return normalized

    @field_validator("location_types")
    def validate_location_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize and validate location types.

        Allowed values: in-person, online.
        """
        if v is None:
            return v
        allowed = {"in-person", "online"}
        normalized: List[str] = []
        for item in v:
            value = str(item).strip().lower()
            if value not in allowed:
                raise ValueError("location_types must be one or more of: 'in-person', 'online'")
            if value not in normalized:
                normalized.append(value)
        return normalized


class ServiceCreate(StrictRequestModel, ServiceBase):
    """Schema for creating a new service."""

    # Preserve existing response config (use_enum_values/populate_by_name) while forbidding extras
    model_config = ConfigDict(
        **ServiceBase.model_config,
        **StrictRequestModel.model_config,
    )


class ServiceResponse(ServiceBase):
    """
    Schema for service responses.

    Includes the service ID and catalog information.
    """

    id: str
    name: str | None = Field(
        default=None,
        description="Resolved name of the service from the catalog",
    )
    service_catalog_name: str = Field(
        ...,
        max_length=255,
        description="Human-readable name of the catalog service",
    )
    display_order: int | None = Field(
        default=None,
        description="Display order hint from the catalog (nullable)",
    )
    online_capable: bool | None = Field(
        default=None,
        description="Whether the catalog service supports online delivery",
    )
    requires_certification: bool | None = Field(
        default=None,
        description="Whether the catalog service requires certification",
    )
    is_active: bool | None = Field(
        default=None,
        description="Whether this service is currently active for the instructor",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


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
    last_initial: str  # Only last initial, not full last_name
    # No email field for privacy protection

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: Any) -> "UserBasicPrivacy":
        """
        Create UserBasicPrivacy from User model.
        Ensures privacy by only exposing last initial and no email.

        Args:
            user: User model object

        Returns:
            UserBasicPrivacy instance with protected data
        """
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else "",
            # No email for privacy protection
        )


class InstructorProfileBase(StandardizedModel):
    """
    Base schema for instructor profiles.

    Note: Removed fields from old booking system:
        - default_session_duration (moved to service level)
        - buffer_time (will be in booking settings)
        - minimum_advance_hours (will be in booking settings)
    """

    bio: str = Field(
        ...,
        min_length=MIN_BIO_LENGTH,
        max_length=MAX_BIO_LENGTH,
        description="Instructor biography/description",
    )
    years_experience: int = Field(..., ge=0, le=50, description="Years of teaching experience")
    min_advance_booking_hours: int = Field(
        default=2, ge=0, le=168, description="Minimum hours in advance for bookings"
    )
    buffer_time_minutes: int = Field(
        default=0, ge=0, le=60, description="Buffer time between bookings"
    )

    @field_validator("bio")
    def validate_bio(cls, v: str) -> str:
        """Ensure bio is not just whitespace."""
        if not v.strip():
            raise ValueError("Bio cannot be empty")
        return v.strip()


class InstructorProfileCreate(StrictRequestModel, InstructorProfileBase):
    """
    Schema for creating an instructor profile.

    Requires at least one service to be defined.
    """

    services: List[ServiceCreate] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Services offered by the instructor",
    )

    @field_validator("services")
    def validate_unique_services(cls, v: List[ServiceCreate]) -> List[ServiceCreate]:
        """Ensure no duplicate service catalog IDs."""
        catalog_ids = [service.service_catalog_id for service in v]
        if len(catalog_ids) != len(set(catalog_ids)):
            raise ValueError("Duplicate services are not allowed")
        return v

    # Maintain populate_by_name/use_enum_values from base while enforcing strict requests
    model_config = ConfigDict(
        **InstructorProfileBase.model_config,
        **StrictRequestModel.model_config,
    )


class InstructorProfileUpdate(StrictRequestModel):
    """
    Schema for updating an instructor profile.

    All fields are optional for partial updates.
    """

    bio: Optional[str] = Field(None, min_length=MIN_BIO_LENGTH, max_length=MAX_BIO_LENGTH)
    years_experience: Optional[int] = Field(None, ge=0, le=50)
    services: Optional[List[ServiceCreate]] = Field(None, min_length=0, max_length=20)
    min_advance_booking_hours: Optional[int] = Field(
        None, ge=0, le=168, description="Minimum hours in advance for bookings"
    )
    buffer_time_minutes: Optional[int] = Field(
        None, ge=0, le=60, description="Buffer time between bookings"
    )
    preferred_teaching_locations: Optional[List[PreferredTeachingLocationIn]] = Field(default=None)
    preferred_public_spaces: Optional[List[PreferredPublicSpaceIn]] = Field(default=None)

    @field_validator("preferred_teaching_locations")
    def validate_preferred_teaching_locations(
        cls, v: Optional[List[PreferredTeachingLocationIn]]
    ) -> Optional[List[PreferredTeachingLocationIn]]:
        if v is not None and len(v) > 2:
            raise ValueError("preferred_teaching_locations must contain at most two entries")
        return v

    @field_validator("preferred_public_spaces")
    def validate_preferred_public_spaces(
        cls, v: Optional[List[PreferredPublicSpaceIn]]
    ) -> Optional[List[PreferredPublicSpaceIn]]:
        if v is not None and len(v) > 2:
            raise ValueError("preferred_public_spaces must contain at most two entries")
        return v

    @field_validator("services")
    def validate_unique_services(
        cls, v: Optional[List[ServiceCreate]]
    ) -> Optional[List[ServiceCreate]]:
        """Ensure no duplicate service catalog IDs if provided."""
        if v is not None:
            catalog_ids = [service.service_catalog_id for service in v]
            if len(catalog_ids) != len(set(catalog_ids)):
                raise ValueError("Duplicate services are not allowed")
        return v


class InstructorProfileResponse(InstructorProfileBase):
    """
    Schema for instructor profile responses with privacy protection.

    Includes all profile data plus relationships and metadata.
    Student-facing endpoints will show only instructor last initial.
    """

    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    user: UserBasicPrivacy  # Changed from UserBasic to protect privacy
    services: List[ServiceResponse]
    is_favorited: Optional[bool] = Field(
        None, description="Whether the current user has favorited this instructor"
    )
    favorited_count: int = Field(0, description="Number of students who favorited this instructor")
    # Onboarding status fields
    skills_configured: bool = Field(
        default=False, description="Whether skills/pricing were configured at least once"
    )
    identity_verified_at: Optional[datetime] = Field(default=None)
    identity_verification_session_id: Optional[str] = Field(default=None)
    background_check_object_key: Optional[str] = Field(default=None)
    background_check_uploaded_at: Optional[datetime] = Field(default=None)
    onboarding_completed_at: Optional[datetime] = Field(default=None)
    is_live: bool = Field(default=False)
    is_founding_instructor: bool = Field(
        default=False, description="Whether the instructor is a founding instructor"
    )
    preferred_teaching_locations: List[PreferredTeachingLocationOut] = Field(default_factory=list)
    preferred_public_spaces: List[PreferredPublicSpaceOut] = Field(default_factory=list)
    service_area_neighborhoods: List[ServiceAreaNeighborhoodOut] = Field(default_factory=list)
    service_area_boroughs: List[str] = Field(default_factory=list)
    service_area_summary: Optional[str] = Field(default=None)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, instructor_profile: Any) -> "InstructorProfileResponse":
        """
        Create InstructorProfileResponse from ORM model with privacy protection.

        Args:
            instructor_profile: InstructorProfile ORM object with user relationship

        Returns:
            InstructorProfileResponse with privacy-protected user data
        """
        preferred_places: list[Any] = []
        if hasattr(instructor_profile, "user") and instructor_profile.user is not None:
            preferred_places = getattr(instructor_profile.user, "preferred_places", []) or []

        teaching_locations: List[PreferredTeachingLocationOut] = []
        public_spaces: List[PreferredPublicSpaceOut] = []

        if preferred_places:
            teaching_sorted = sorted(
                [p for p in preferred_places if getattr(p, "kind", None) == "teaching_location"],
                key=lambda place: getattr(place, "position", 0),
            )
            public_sorted = sorted(
                [p for p in preferred_places if getattr(p, "kind", None) == "public_space"],
                key=lambda place: getattr(place, "position", 0),
            )

            for place in teaching_sorted:
                teaching_locations.append(
                    PreferredTeachingLocationOut(
                        address=getattr(place, "address", ""),
                        label=getattr(place, "label", None),
                    )
                )

            for place in public_sorted:
                public_spaces.append(
                    PreferredPublicSpaceOut(
                        address=getattr(place, "address", ""),
                    )
                )

        # Normalize instructor services with catalog names eagerly resolved
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
                id=getattr(service, "id"),
                service_catalog_id=getattr(service, "service_catalog_id"),
                service_catalog_name=catalog_name or "Unknown Service",
                hourly_rate=getattr(service, "hourly_rate"),
                description=getattr(service, "description", None),
                requirements=getattr(service, "requirements", None),
                age_groups=getattr(service, "age_groups", None),
                levels_taught=getattr(service, "levels_taught", None),
                equipment_required=getattr(service, "equipment_required", None),
                location_types=getattr(service, "location_types", None),
                duration_options=getattr(service, "duration_options", None) or [60],
            )
            services_data.append(service_payload)

        boroughs: set[str] = set()
        neighborhoods_payload: List[ServiceAreaNeighborhoodOut] = []

        neighborhoods_source = getattr(instructor_profile, "service_area_neighborhoods", None)

        if neighborhoods_source:
            for entry in neighborhoods_source:
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
                    borough = getattr(entry, "borough", None) or getattr(
                        entry, "parent_region", None
                    )

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
        else:
            user_service_areas: Sequence[Any] = []
            if hasattr(instructor_profile, "user") and instructor_profile.user is not None:
                user_service_areas = getattr(instructor_profile.user, "service_areas", []) or []

            for area in user_service_areas:
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
                name = getattr(neighborhood, "region_name", None) or getattr(
                    neighborhood, "name", None
                )
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

        sorted_boroughs = sorted(boroughs)
        if sorted_boroughs:
            if len(sorted_boroughs) <= 2:
                service_area_summary = ", ".join(sorted_boroughs)
            else:
                service_area_summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
        else:
            service_area_summary = None

        neighborhoods_output = [entry.model_dump(mode="python") for entry in neighborhoods_payload]

        return cls(
            id=instructor_profile.id,
            user_id=instructor_profile.user_id,
            created_at=instructor_profile.created_at,
            updated_at=instructor_profile.updated_at,
            bio=instructor_profile.bio,
            years_experience=instructor_profile.years_experience,
            min_advance_booking_hours=instructor_profile.min_advance_booking_hours,
            buffer_time_minutes=instructor_profile.buffer_time_minutes,
            user=UserBasicPrivacy.from_user(instructor_profile.user),
            services=services_data,
            is_favorited=getattr(instructor_profile, "is_favorited", None),
            favorited_count=getattr(instructor_profile, "favorited_count", 0),
            skills_configured=getattr(instructor_profile, "skills_configured", False),
            identity_verified_at=getattr(instructor_profile, "identity_verified_at", None),
            background_check_uploaded_at=getattr(
                instructor_profile, "background_check_uploaded_at", None
            ),
            onboarding_completed_at=getattr(instructor_profile, "onboarding_completed_at", None),
            is_live=getattr(instructor_profile, "is_live", False),
            is_founding_instructor=getattr(instructor_profile, "is_founding_instructor", False),
            preferred_teaching_locations=teaching_locations,
            preferred_public_spaces=public_spaces,
            service_area_neighborhoods=neighborhoods_output,
            service_area_boroughs=sorted_boroughs,
            service_area_summary=service_area_summary,
        )

    @field_validator("services")
    def sort_services(cls, v: List[ServiceResponse]) -> List[ServiceResponse]:
        """Sort services by catalog ID for consistent display."""
        return sorted(v, key=lambda s: s.service_catalog_id)
