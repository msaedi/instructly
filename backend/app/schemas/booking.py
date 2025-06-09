from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

# Request schemas
class BookingCreateOld(BaseModel):
    """Legacy schema for old booking flow"""
    instructor_id: int
    timeslot_id: int
    service_id: int
    requested_duration: Optional[int] = None


class BookingCreate(BaseModel):
    instructor_id: int
    service_id: int
    start_time: datetime
    duration_minutes: int
    
    @validator('duration_minutes')
    def validate_duration(cls, v):
        allowed_durations = [30, 45, 60, 90, 120]
        if v not in allowed_durations:
            raise ValueError(f'Duration must be one of {allowed_durations}')
        return v

class BookingCancel(BaseModel):
    cancellation_reason: Optional[str] = Field(None, max_length=500)

# Response schemas
class TimeSlotResponse(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    is_available: bool
    
    class Config:
        from_attributes = True

class ServiceResponse(BaseModel):
    id: int
    skill: str
    hourly_rate: float
    description: Optional[str] = None
    
    class Config:
        from_attributes = True

class InstructorSummary(BaseModel):
    id: int
    full_name: str
    email: str
    
    class Config:
        from_attributes = True

class BookingResponse(BaseModel):
    id: int
    student_id: int
    instructor_id: int
    timeslot_id: Optional[int] = None
    service_id: int
    status: BookingStatus
    total_price: float
    cancellation_deadline: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Include related data
    time_slot: TimeSlotResponse
    service: ServiceResponse
    instructor: InstructorSummary

    original_duration: Optional[int] = None
    adjusted_duration: Optional[int] = None
    adjustment_reason: Optional[str] = None
    actual_duration: Optional[int] = Field(None, description="Effective duration considering adjustments")

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    adjusted_total_price: Optional[float] = None
    
    class Config:
        from_attributes = True

class BookingAdjustment(BaseModel):
    adjusted_duration: int = Field(ge=30, le=240)
    adjustment_reason: str = Field(min_length=1, max_length=500)

class BookingListResponse(BaseModel):
    bookings: List[BookingResponse]
    total: int
    
class AvailableSlotResponse(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    service_id: Optional[int] = None
    hourly_rate: Optional[float] = None
    
    class Config:
        from_attributes = True