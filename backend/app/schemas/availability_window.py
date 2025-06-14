"""
Availability window schemas for InstaInstru platform.

This module contains schemas specifically for the availability windows API endpoints.
It handles the week-based availability management interface.

Note: References to RecurringAvailability have been removed as part of the
refactoring to use only date-specific availability.
"""

import datetime
from datetime import date, time
from typing import Optional, List, Literal, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator

# Type aliases for annotations
DateType = datetime.date
TimeType = datetime.time

class DayOfWeekEnum(str, Enum):
    """Enumeration for days of the week."""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


# Base schemas
class AvailabilityWindowBase(BaseModel):
    """Base schema for availability windows."""
    start_time: TimeType
    end_time: TimeType
    is_available: bool = True
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        """Ensure end time is after start time."""
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v


# REMOVED: RecurringAvailabilityCreate - no longer needed


class SpecificDateAvailabilityCreate(AvailabilityWindowBase):
    """Schema for creating availability on a specific date."""
    specific_date: DateType
    
    @validator('specific_date')
    def validate_future_date(cls, v):
        """Prevent setting availability for past dates."""
        if v < date.today():
            raise ValueError('Cannot set availability for past dates')
        return v


class AvailabilityWindowUpdate(BaseModel):
    """Schema for updating an availability window."""
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    is_available: Optional[TimeType] = None
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        """Ensure end time is after start time if both provided."""
        if v and 'start_time' in values and values['start_time'] and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v


class AvailabilityWindowResponse(AvailabilityWindowBase):
    """Response schema for availability windows."""
    id: int
    instructor_id: int
    day_of_week: Optional[DayOfWeekEnum] = None  # Always None now
    specific_date: Optional[DateType] = None
    is_recurring: bool  # Always False now
    is_cleared: bool = False
    
    class Config:
        from_attributes = True


# REMOVED: WeeklyScheduleCreate - no longer needed
# REMOVED: WeeklyScheduleResponse - no longer needed


# Blackout dates
class BlackoutDateCreate(BaseModel):
    """Schema for creating a blackout date."""
    date: DateType
    reason: Optional[str] = Field(None, max_length=255)
    
    @validator('date')
    def validate_future_date(cls, v):
        """Prevent creating blackout dates in the past."""
        if v < date.today():
            raise ValueError('Cannot create blackout date in the past')
        return v


class BlackoutDateResponse(BaseModel):
    """Response schema for blackout dates."""
    id: int
    instructor_id: int
    date: DateType
    reason: Optional[str] = None
    created_at: str
    
    class Config:
        from_attributes = True


# Week-specific operations
class DateTimeSlot(BaseModel):
    """Schema for a time slot on a specific date."""
    date: DateType
    start_time: TimeType
    end_time: TimeType
    is_available: bool = True
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        """Ensure end time is after start time."""
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v
    
    @validator('date')
    def validate_not_past(cls, v):
        """Prevent creating slots for past dates."""
        if v < date.today():
            raise ValueError('Cannot create availability for past dates')
        return v


class WeekSpecificScheduleCreate(BaseModel):
    """Schema for creating schedule for specific dates."""
    schedule: List[DateTimeSlot]
    clear_existing: bool = Field(
        default=True,
        description="Whether to clear existing entries for the week before saving"
    )
    week_start: Optional[DateType] = Field(
        None,
        description="Optional Monday date. If not provided, inferred from schedule dates"
    )
    
    @validator('week_start')
    def validate_monday(cls, v):
        """Ensure week start is a Monday if provided."""
        if v and v.weekday() != 0:
            raise ValueError('Week start must be a Monday')
        return v


class CopyWeekRequest(BaseModel):
    """Schema for copying availability between weeks."""
    from_week_start: DateType
    to_week_start: DateType
    
    @validator('from_week_start', 'to_week_start')
    def validate_mondays(cls, v):
        """Ensure both dates are Mondays."""
        if v.weekday() != 0:
            raise ValueError(f'{v} is not a Monday (weekday={v.weekday()})')
        return v
    
    @validator('to_week_start')
    def validate_different_weeks(cls, v, values):
        """Ensure we're not copying to the same week."""
        if 'from_week_start' in values and v == values['from_week_start']:
            raise ValueError('Cannot copy to the same week')
        return v


class ApplyToDateRangeRequest(BaseModel):
    """Schema for applying a week pattern to a date range."""
    from_week_start: DateType
    start_date: DateType
    end_date: DateType
    
    @validator('from_week_start')
    def validate_monday(cls, v):
        """Ensure source week starts on Monday."""
        if v.weekday() != 0:
            raise ValueError('Source week must start on a Monday')
        return v
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate the date range."""
        if 'start_date' in values:
            if v < values['start_date']:
                raise ValueError('End date must be after start date')
            # Enforce 1-year maximum range
            from datetime import timedelta
            max_end = values['start_date'] + timedelta(days=365)
            if v > max_end:
                raise ValueError('Date range cannot exceed 1 year (365 days)')
        return v
    
    @validator('start_date')
    def validate_future_date(cls, v):
        """Ensure we're not applying to past dates."""
        if v < date.today():
            raise ValueError('Cannot apply schedule to past dates')
        return v
    
# Bulk update schemas
class SlotOperation(BaseModel):
    """Schema for a single slot operation in bulk update."""
    action: Literal["add", "remove", "update"]
    # For add/update:
    date: Optional[DateType] = None
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    # For remove/update:
    slot_id: Optional[int] = None
    
    @validator('end_time')
    def validate_time_order(cls, v, values):
        """Ensure end time is after start time for add/update."""
        if v and 'start_time' in values and values['start_time'] and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v
    
    @validator('date')
    def validate_required_for_add(cls, v, values):
        """Ensure required fields for add action."""
        if values.get('action') == 'add' and not v:
            raise ValueError('Date is required for add action')
        return v

class BulkUpdateRequest(BaseModel):
    """Request schema for bulk availability update."""
    operations: List[SlotOperation]
    validate_only: bool = Field(False, description="If true, only validate without making changes")

class OperationResult(BaseModel):
    """Result of a single operation in bulk update."""
    operation_index: int
    action: str
    status: Literal["success", "failed", "skipped"]
    reason: Optional[str] = None
    slot_id: Optional[int] = None  # For successful adds
    
class BulkUpdateResponse(BaseModel):
    """Response schema for bulk availability update."""
    successful: int
    failed: int
    skipped: int
    results: List[OperationResult]