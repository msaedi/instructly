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
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.constants import (
    MAX_BIO_LENGTH,
    MAX_SESSION_DURATION,
    MIN_BIO_LENGTH,
    MIN_SESSION_DURATION,
)
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
        if v is None:
            return v
        vv = str(v).strip().lower()
        if vv == "both":
            # Treat 'both' as no filter
            return None
        if vv not in {"kids", "adults"}:
            raise ValueError("age_group must be one of: 'kids', 'adults'")
        return vv

    # Enforce strictness for query param schema when instantiated explicitly
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


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


class ServiceCreate(ServiceBase):
    """Schema for creating a new service."""

    # Harden nested service creation payloads
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ServiceResponse(ServiceBase):
    """
    Schema for service responses.

    Includes the service ID and catalog information.
    """

    id: str

    model_config = ConfigDict(from_attributes=True)


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
    areas_of_service: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="NYC areas where instructor provides services",
    )
    years_experience: int = Field(..., ge=0, le=50, description="Years of teaching experience")
    min_advance_booking_hours: int = Field(
        default=2, ge=0, le=168, description="Minimum hours in advance for bookings"
    )
    buffer_time_minutes: int = Field(
        default=0, ge=0, le=60, description="Buffer time between bookings"
    )

    @field_validator("areas_of_service")
    def validate_areas(cls, v: List[str]) -> List[str]:
        """Ensure areas are properly formatted and no duplicates."""
        # Remove duplicates and format properly
        unique_areas = list(set(area.strip().title() for area in v if area.strip()))
        if not unique_areas:
            raise ValueError("At least one area of service is required")
        return unique_areas

    @field_validator("bio")
    def validate_bio(cls, v: str) -> str:
        """Ensure bio is not just whitespace."""
        if not v.strip():
            raise ValueError("Bio cannot be empty")
        return v.strip()


class InstructorProfileCreate(InstructorProfileBase):
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

    # Forbid unexpected fields in profile creation
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InstructorProfileUpdate(BaseModel):
    """
    Schema for updating an instructor profile.

    All fields are optional for partial updates.
    """

    bio: Optional[str] = Field(None, min_length=MIN_BIO_LENGTH, max_length=MAX_BIO_LENGTH)
    areas_of_service: Optional[List[str]] = Field(None, min_length=0, max_length=10)
    years_experience: Optional[int] = Field(None, ge=0, le=50)
    services: Optional[List[ServiceCreate]] = Field(None, min_length=0, max_length=20)

    @field_validator("areas_of_service")
    def validate_areas(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Ensure areas are properly formatted if provided."""
        if v is not None and len(v) > 0:
            unique_areas = list(set(area.strip().title() for area in v if area.strip()))
            return unique_areas if unique_areas else []
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

    # Forbid unexpected fields in profile update
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


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
        return cls(
            id=instructor_profile.id,
            user_id=instructor_profile.user_id,
            created_at=instructor_profile.created_at,
            updated_at=instructor_profile.updated_at,
            bio=instructor_profile.bio,
            areas_of_service=instructor_profile.areas_of_service,
            years_experience=instructor_profile.years_experience,
            min_advance_booking_hours=instructor_profile.min_advance_booking_hours,
            buffer_time_minutes=instructor_profile.buffer_time_minutes,
            user=UserBasicPrivacy.from_user(instructor_profile.user),
            services=instructor_profile.services if hasattr(instructor_profile, "services") else [],
            is_favorited=getattr(instructor_profile, "is_favorited", None),
            favorited_count=getattr(instructor_profile, "favorited_count", 0),
            skills_configured=getattr(instructor_profile, "skills_configured", False),
            identity_verified_at=getattr(instructor_profile, "identity_verified_at", None),
            background_check_uploaded_at=getattr(
                instructor_profile, "background_check_uploaded_at", None
            ),
            onboarding_completed_at=getattr(instructor_profile, "onboarding_completed_at", None),
            is_live=getattr(instructor_profile, "is_live", False),
        )

    @field_validator("areas_of_service", mode="before")
    def convert_areas_to_list(cls, v: object) -> object:
        """Convert comma-separated string to list if needed."""
        if isinstance(v, str):
            # Clean up any corrupted data
            cleaned = v
            # Remove excessive escaping
            while '\\"' in cleaned or "\\\\" in cleaned:
                cleaned = cleaned.replace('\\"', '"')
                cleaned = cleaned.replace("\\'", "'")
                cleaned = cleaned.replace("\\\\", "\\")

            # Remove any curly braces
            cleaned = cleaned.replace("{", "").replace("}", "")

            # Split by comma and clean up each area
            areas: List[str] = []
            for area in cleaned.split(","):
                # Remove quotes and whitespace
                area = area.strip().strip('"').strip("'").strip()
                if area and len(area) > 2:
                    areas.append(area.title())

            return areas
        return v

    @field_validator("services")
    def sort_services(cls, v: List[ServiceResponse]) -> List[ServiceResponse]:
        """Sort services by catalog ID for consistent display."""
        return sorted(v, key=lambda s: s.service_catalog_id)
