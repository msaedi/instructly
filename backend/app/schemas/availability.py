# backend/app/schemas/availability.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TimeSlotBase(BaseModel):
    start_time: datetime
    end_time: datetime
    is_available: bool = True

class TimeSlotCreate(TimeSlotBase):
    pass

class TimeSlotUpdate(BaseModel):
    is_available: Optional[bool] = None

class TimeSlotResponse(TimeSlotBase):
    id: int
    instructor_id: int
    is_booked: bool = False
    
    class Config:
        from_attributes = True