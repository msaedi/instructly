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
from typing import Optional, List
from pydantic import BaseModel, Field, validator

from ..models.user import UserRole
from ..core.constants import (
    MIN_BIO_LENGTH, MAX_BIO_LENGTH,
    MIN_SESSION_DURATION, MAX_SESSION_DURATION
)

logger = logging.getLogger(__name__)


class ServiceBase(BaseModel):
    """
    Base schema for instructor services.
    
    Attributes:
        skill: The skill/service being offered (e.g., "Piano", "Yoga")
        hourly_rate: Rate per hour in USD
        description: Optional description of the service
        duration_override: Optional custom duration for this service
    """
    skill: str = Field(..., min_length=1, max_length=100)
    hourly_rate: float = Field(..., gt=0, le=1000, description="Hourly rate in USD")
    description: Optional[str] = Field(None, max_length=500)
    duration_override: Optional[int] = Field(
        None, 
        ge=MIN_SESSION_DURATION, 
        le=MAX_SESSION_DURATION, 
        description="Custom duration for this service in minutes (overrides default)"
    )
    
    @validator('skill')
    def validate_skill(cls, v):
        """Ensure skill name is properly formatted."""
        return v.strip().title()


class ServiceCreate(ServiceBase):
    """Schema for creating a new service."""
    pass


class ServiceResponse(ServiceBase):
    """
    Schema for service responses.
    
    Includes the service ID and computed duration.
    """
    id: int
    duration: int = Field(description="Effective duration in minutes")
    
    class Config:
        from_attributes = True


class UserBasic(BaseModel):
    """Basic user information for embedding in responses."""
    full_name: str
    email: str

    class Config:
        from_attributes = True


class InstructorProfileBase(BaseModel):
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
        description="Instructor biography/description"
    )
    areas_of_service: List[str] = Field(
        ..., 
        min_items=1,
        max_items=10,
        description="NYC areas where instructor provides services"
    )
    years_experience: int = Field(
        ..., 
        ge=0,
        le=50,
        description="Years of teaching experience"
    )
    
    @validator('areas_of_service')
    def validate_areas(cls, v):
        """Ensure areas are properly formatted and no duplicates."""
        # Remove duplicates and format properly
        unique_areas = list(set(area.strip().title() for area in v if area.strip()))
        if not unique_areas:
            raise ValueError("At least one area of service is required")
        return unique_areas
    
    @validator('bio')
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
        min_items=1,
        max_items=20,
        description="Services offered by the instructor"
    )
    
    @validator('services')
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
    bio: Optional[str] = Field(
        None, 
        min_length=MIN_BIO_LENGTH, 
        max_length=MAX_BIO_LENGTH
    )
    areas_of_service: Optional[List[str]] = Field(
        None, 
        min_items=1,
        max_items=10
    )
    years_experience: Optional[int] = Field(
        None, 
        ge=0,
        le=50
    )
    services: Optional[List[ServiceCreate]] = Field(
        None, 
        min_items=1,
        max_items=20
    )
    
    @validator('areas_of_service')
    def validate_areas(cls, v):
        """Ensure areas are properly formatted if provided."""
        if v is not None:
            unique_areas = list(set(area.strip().title() for area in v if area.strip()))
            if not unique_areas:
                raise ValueError("At least one area of service is required")
            return unique_areas
        return v
    
    @validator('services')
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
    
    class Config:
        from_attributes = True
        
    @validator('services')
    def sort_services(cls, v):
        """Sort services by skill name for consistent display."""
        return sorted(v, key=lambda s: s.skill)