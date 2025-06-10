# Create this file: app/schemas/availability_window.py

from pydantic import BaseModel, Field, validator
from datetime import date, time
from typing import Optional, List
from enum import Enum

class DayOfWeekEnum(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

# Base schemas
class AvailabilityWindowBase(BaseModel):
    start_time: time
    end_time: time
    is_available: bool = True
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v

class RecurringAvailabilityCreate(AvailabilityWindowBase):
    day_of_week: DayOfWeekEnum
    
class SpecificDateAvailabilityCreate(AvailabilityWindowBase):
    specific_date: date
    
    @validator('specific_date')
    def validate_future_date(cls, v):
        if v < date.today():
            raise ValueError('Cannot set availability for past dates')
        return v

class AvailabilityWindowUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_available: Optional[bool] = None

class AvailabilityWindowResponse(AvailabilityWindowBase):
    id: int
    instructor_id: int
    day_of_week: Optional[DayOfWeekEnum] = None
    specific_date: Optional[date] = None
    is_recurring: bool
    
    class Config:
        from_attributes = True

# Bulk operations
class WeeklyScheduleCreate(BaseModel):
    """Create a full week schedule at once"""
    schedule: List[RecurringAvailabilityCreate]
    clear_existing: bool = Field(default=True, description="Clear existing recurring availability before creating new")

class WeeklyScheduleResponse(BaseModel):
    """Response for weekly schedule"""
    monday: List[AvailabilityWindowResponse] = []
    tuesday: List[AvailabilityWindowResponse] = []
    wednesday: List[AvailabilityWindowResponse] = []
    thursday: List[AvailabilityWindowResponse] = []
    friday: List[AvailabilityWindowResponse] = []
    saturday: List[AvailabilityWindowResponse] = []
    sunday: List[AvailabilityWindowResponse] = []

# Blackout dates
class BlackoutDateCreate(BaseModel):
    date: date
    reason: Optional[str] = Field(None, max_length=255)
    
    @validator('date')
    def validate_future_date(cls, v):
        if v < date.today():
            raise ValueError('Cannot create blackout date in the past')
        return v

class BlackoutDateResponse(BaseModel):
    id: int
    instructor_id: int
    date: date
    reason: Optional[str] = None
    
    class Config:
        from_attributes = True

# Quick presets
class AvailabilityPreset(str, Enum):
    WEEKDAY_9_TO_5 = "weekday_9_to_5"
    MORNINGS_ONLY = "mornings_only"
    EVENINGS_ONLY = "evenings_only"
    WEEKENDS_ONLY = "weekends_only"
    
class ApplyPresetRequest(BaseModel):
    preset: AvailabilityPreset
    clear_existing: bool = True

# For week-specific operations
class DateTimeSlot(BaseModel):
    date: date
    start_time: time  # Using time type instead of str
    end_time: time
    is_available: bool = True
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v

class WeekSpecificScheduleCreate(BaseModel):
    """Create schedule for specific dates (not recurring)"""
    schedule: List[DateTimeSlot]
    clear_existing: bool = True
    week_start: Optional[date] = None 

class CopyWeekRequest(BaseModel):
    from_week_start: date
    to_week_start: date
    
    @validator('to_week_start')
    def validate_different_weeks(cls, v, values):
        if 'from_week_start' in values and v == values['from_week_start']:
            raise ValueError('Cannot copy to the same week')
        return v

class ApplyToDateRangeRequest(BaseModel):
    from_week_start: date
    start_date: date
    end_date: date
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('End date must be after start date')
        return v