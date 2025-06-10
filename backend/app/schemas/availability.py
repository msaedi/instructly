# backend/app/schemas/availability.py
from datetime import date
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

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

class DateTimeSlot(BaseModel):
    date: date
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    is_available: bool = True

class WeekScheduleCreate(BaseModel):
    schedule: List[DateTimeSlot]
    clear_existing: bool = True

class CopyWeekRequest(BaseModel):
    from_week_start: date
    to_week_start: date

class ApplyToDateRangeRequest(BaseModel):
    from_week_start: date
    start_date: date
    end_date: date