from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

# Request schemas
class BookingCreate(BaseModel):
    instructor_id: int
    timeslot_id: int
    service_id: int

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
    timeslot_id: int
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
    
    class Config:
        from_attributes = True

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