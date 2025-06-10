# backend/app/schemas/availability.py
from datetime import date
from pydantic import BaseModel
from typing import List

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

class AvailabilityQuery(BaseModel):
    instructor_id: int
    service_id: int
    date: date