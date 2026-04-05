from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.constants import MAX_BIO_LENGTH, MIN_BIO_LENGTH
from .._strict_base import StrictModel, StrictRequestModel
from ..base import StandardizedModel
from .locations import PreferredPublicSpaceIn, PreferredTeachingLocationIn
from .services import ServiceCreate


class InstructorFilterParams(BaseModel):
    """
    Query parameters for filtering instructors.

    All fields are optional for flexible filtering.
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
        if v is None or v == "":
            return None
        vv = str(v).strip().lower()
        if vv == "" or vv == "both":
            return None
        if vv not in {"kids", "adults"}:
            raise ValueError("age_group must be one of: 'kids', 'adults'")
        return vv

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InstructorProfileBase(StandardizedModel):
    """
    Base schema for instructor profiles.

    Booking settings are updated through dedicated calendar-settings endpoints.
    """

    bio: str = Field(
        ...,
        min_length=MIN_BIO_LENGTH,
        max_length=MAX_BIO_LENGTH,
        description="Instructor biography/description",
    )
    years_experience: int = Field(..., ge=1, le=50, description="Years of teaching experience")

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

    model_config = ConfigDict(
        **InstructorProfileBase.model_config,
        **StrictRequestModel.model_config,
    )


class GenerateBioResponse(BaseModel):
    """Response schema for AI-generated instructor bio."""

    bio: str


class InstructorProfileUpdate(StrictRequestModel):
    """
    Schema for updating an instructor profile.

    All fields are optional for partial updates.
    """

    bio: Optional[str] = Field(None, min_length=MIN_BIO_LENGTH, max_length=MAX_BIO_LENGTH)
    years_experience: Optional[int] = Field(None, ge=1, le=50)
    services: Optional[List[ServiceCreate]] = Field(None, min_length=0, max_length=20)
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


class UpdateCalendarSettings(StrictRequestModel):
    """Editable instructor calendar settings surfaced on the availability page."""

    non_travel_buffer_minutes: Optional[int] = Field(None, ge=10, le=120)
    travel_buffer_minutes: Optional[int] = Field(None, ge=30, le=120)
    overnight_protection_enabled: Optional[bool] = None


class CalendarSettingsResponse(StrictModel):
    """Focused calendar settings payload for availability-page updates."""

    non_travel_buffer_minutes: int = Field(default=15)
    travel_buffer_minutes: int = Field(default=60)
    overnight_protection_enabled: bool = Field(default=True)


class CalendarSettingsAcknowledgeResponse(StrictModel):
    """Acknowledgement timestamp returned after the first-save popup is dismissed."""

    calendar_settings_acknowledged_at: datetime | None = None
