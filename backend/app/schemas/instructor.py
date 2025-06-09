from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator, BaseModel

class ServiceBase(BaseModel):
    skill: str
    hourly_rate: float = Field(..., gt=0)
    description: Optional[str] = None
    duration_override: Optional[int] = Field(None, ge=30, le=240, description="Override instructor's default duration (minutes)")

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
    bio: str = Field(..., min_length=10, max_length=1000)
    areas_of_service: List[str] = Field(..., min_items=1)
    years_experience: int = Field(..., gt=-1)
    default_session_duration: int = Field(default=60, ge=30, le=240, description="Default session duration in minutes")
    buffer_time: int = Field(default=0, ge=0, le=120, description="Buffer time between sessions in minutes")
    minimum_advance_hours: int = Field(default=2, ge=0, le=168, description="Minimum hours in advance to book")


class InstructorProfileCreate(InstructorProfileBase):
    services: List[ServiceCreate] = Field(..., min_items=1)

class InstructorProfileUpdate(BaseModel):
    bio: Optional[str] = Field(None, min_length=10, max_length=1000)
    areas_of_service: Optional[List[str]] = Field(None, min_items=1)
    years_experience: Optional[int] = Field(None, ge=0)
    services: Optional[List[ServiceCreate]] = Field(None, min_items=1)

class InstructorProfileResponse(InstructorProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    user: UserBasic
    services: List[ServiceResponse] 

    class Config:
        from_attributes = True
