from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator, BaseModel

class ServiceBase(BaseModel):
    skill: str
    hourly_rate: float = Field(..., gt=0)
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: int
    
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
