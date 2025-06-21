"""
Instructor profile schemas for InstaInstru platform.

This module defines Pydantic schemas for instructor-related operations,
including profile management and service offerings.

Note: The old booking-related fields (buffer_time, minimum_advance_hours,
default_session_duration) have been removed as part of the refactoring.
These will be reimplemented differently in the new booking system.
"""

import logging
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.constants import MAX_BIO_LENGTH, MAX_SESSION_DURATION, MIN_BIO_LENGTH, MIN_SESSION_DURATION
from .base import Money, StandardizedModel

logger = logging.getLogger(__name__)


class ServiceBase(StandardizedModel):
    """
    Base schema for instructor services.

    Attributes:
        skill: The skill/service being offered (e.g., "Piano", "Yoga")
        hourly_rate: Rate per hour in USD
        description: Optional description of the service
        duration_override: Optional custom duration for this service
    """

    skill: str = Field(..., min_length=1, max_length=100)
    hourly_rate: Money = Field(..., gt=0, le=1000, description="Hourly rate in USD")  # Changed from float
    description: Optional[str] = Field(None, max_length=500)
    duration_override: Optional[int] = Field(
        None,
        ge=MIN_SESSION_DURATION,
        le=MAX_SESSION_DURATION,
        description="Custom duration for this service in minutes (overrides default)",
    )

    @field_validator("skill")
    def validate_skill(cls, v):
        """Ensure skill name is properly formatted."""
        return v.strip().title()


class ServiceCreate(ServiceBase):
    """Schema for creating a new service."""


class ServiceResponse(ServiceBase):
    """
    Schema for service responses.

    Includes the service ID and computed duration.
    """

    id: int
    duration: int = Field(description="Effective duration in minutes")

    model_config = ConfigDict(from_attributes=True)


class UserBasic(StandardizedModel):
    """Basic user information for embedding in responses."""

    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


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
    min_advance_booking_hours: int = Field(default=2, ge=0, le=168, description="Minimum hours in advance for bookings")
    buffer_time_minutes: int = Field(default=0, ge=0, le=60, description="Buffer time between bookings")

    @field_validator("areas_of_service")
    def validate_areas(cls, v):
        """Ensure areas are properly formatted and no duplicates."""
        # Remove duplicates and format properly
        unique_areas = list(set(area.strip().title() for area in v if area.strip()))
        if not unique_areas:
            raise ValueError("At least one area of service is required")
        return unique_areas

    @field_validator("bio")
    def validate_bio(cls, v):
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
    def validate_unique_services(cls, v):
        """Ensure no duplicate service names."""
        skills = [service.skill.lower() for service in v]
        if len(skills) != len(set(skills)):
            raise ValueError("Duplicate services are not allowed")
        return v


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
    def validate_areas(cls, v):
        """Ensure areas are properly formatted if provided."""
        if v is not None and len(v) > 0:
            unique_areas = list(set(area.strip().title() for area in v if area.strip()))
            return unique_areas if unique_areas else []
        return v

    @field_validator("services")
    def validate_unique_services(cls, v):
        """Ensure no duplicate service names if provided."""
        if v is not None:
            skills = [service.skill.lower() for service in v]
            if len(skills) != len(set(skills)):
                raise ValueError("Duplicate services are not allowed")
        return v


class InstructorProfileResponse(InstructorProfileBase):
    """
    Schema for instructor profile responses.

    Includes all profile data plus relationships and metadata.
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    user: UserBasic
    services: List[ServiceResponse]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("areas_of_service", mode="before")
    def convert_areas_to_list(cls, v):
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
            areas = []
            for area in cleaned.split(","):
                # Remove quotes and whitespace
                area = area.strip().strip('"').strip("'").strip()
                if area and len(area) > 2:
                    areas.append(area.title())

            return areas
        return v

    @field_validator("services")
    def sort_services(cls, v):
        """Sort services by skill name for consistent display."""
        return sorted(v, key=lambda s: s.skill)
