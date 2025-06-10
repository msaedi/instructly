from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

from ..models.user import UserRole
from ..core.constants import (
    MIN_SESSION_DURATION, MAX_SESSION_DURATION, DEFAULT_SESSION_DURATION,
    MIN_BUFFER_TIME, MAX_BUFFER_TIME, DEFAULT_BUFFER_TIME,
    MIN_ADVANCE_BOOKING, MAX_ADVANCE_BOOKING, DEFAULT_ADVANCE_BOOKING,
    MIN_BIO_LENGTH, MAX_BIO_LENGTH
)

class ServiceBase(BaseModel):
    skill: str
    hourly_rate: float = Field(..., gt=0)
    description: Optional[str] = None
    duration_override: Optional[int] = Field(
        None, 
        ge=MIN_SESSION_DURATION, 
        le=MAX_SESSION_DURATION, 
        description="Override instructor's default duration (minutes)"
    )

class ServiceCreate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: int
    duration: int = Field(description="Effective duration in minutes")  # Will use the @property from model
    
    class Config:
        from_attributes = True

class UserBasic(BaseModel):
    full_name: str
    email: str

    class Config:
        from_attributes = True

class InstructorProfileBase(BaseModel):
    bio: str = Field(..., min_length=MIN_BIO_LENGTH, max_length=MAX_BIO_LENGTH)
    areas_of_service: List[str] = Field(..., min_items=1)  # Keep as List[str]
    years_experience: int = Field(..., gt=-1)  # Allow -1 as per original
    default_session_duration: int = Field(
        default=DEFAULT_SESSION_DURATION, 
        ge=MIN_SESSION_DURATION, 
        le=MAX_SESSION_DURATION, 
        description="Default session duration in minutes"
    )
    buffer_time: int = Field(
        default=DEFAULT_BUFFER_TIME, 
        ge=MIN_BUFFER_TIME, 
        le=MAX_BUFFER_TIME, 
        description="Buffer time between sessions in minutes"
    )
    minimum_advance_hours: int = Field(
        default=DEFAULT_ADVANCE_BOOKING, 
        ge=MIN_ADVANCE_BOOKING, 
        le=MAX_ADVANCE_BOOKING, 
        description="Minimum hours in advance to book"
    )

class InstructorProfileCreate(InstructorProfileBase):
    services: List[ServiceCreate] = Field(..., min_items=1)

class InstructorProfileUpdate(BaseModel):
    bio: Optional[str] = Field(None, min_length=MIN_BIO_LENGTH, max_length=MAX_BIO_LENGTH)
    areas_of_service: Optional[List[str]] = Field(None, min_items=1)
    years_experience: Optional[int] = Field(None, ge=0)
    services: Optional[List[ServiceCreate]] = Field(None, min_items=1)
    default_session_duration: Optional[int] = Field(
        None, 
        ge=MIN_SESSION_DURATION, 
        le=MAX_SESSION_DURATION
    )
    buffer_time: Optional[int] = Field(
        None, 
        ge=MIN_BUFFER_TIME, 
        le=MAX_BUFFER_TIME
    )
    minimum_advance_hours: Optional[int] = Field(
        None, 
        ge=MIN_ADVANCE_BOOKING, 
        le=MAX_ADVANCE_BOOKING
    )

class InstructorProfileResponse(InstructorProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    user: UserBasic
    services: List[ServiceResponse] 

    class Config:
        from_attributes = True