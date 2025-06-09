# backend/app/schemas/availability.py
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional

class TimeSlotBase(BaseModel):
    start_time: datetime
    end_time: datetime
    is_available: bool = True

class TimeSlotCreate(TimeSlotBase):
    pass

class TimeSlotUpdate(BaseModel):
    is_available: Optional[bool] = None

class TimeSlotOption(BaseModel):
    start_time: datetime
    end_time: datetime
    available: bool = True
    
    class Config:
        from_attributes = True

class TimeSlotResponse(TimeSlotBase):
    id: int
    instructor_id: int
    is_booked: bool = False
    
    class Config:
        from_attributes = True

class AvailabilityQuery(BaseModel):
    instructor_id: int
    service_id: int
    date: date