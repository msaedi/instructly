"""
Availability window schemas for InstaInstru platform.

This module contains schemas specifically for the availability windows API endpoints.
It handles the week-based availability management interface.

Note: References to RecurringAvailability have been removed as part of the
refactoring to use only date-specific availability.
"""

import datetime
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import StandardizedModel

# Type aliases for annotations
DateType = datetime.date
TimeType = datetime.time
DateTimeType = datetime.datetime

# Type definitions
WeekSchedule = Dict[str, List["TimeSlot"]]  # Maps date strings to lists of time slots


class TimeSlot(BaseModel):
    """Time slot for availability"""

    start_time: TimeType
    end_time: TimeType
    is_available: bool = True


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

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data and "start_time" in info.data and info.data["start_time"] and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


# REMOVED: RecurringAvailabilityCreate - no longer needed


class SpecificDateAvailabilityCreate(AvailabilityWindowBase):
    """Schema for creating availability on a specific date."""

    specific_date: DateType

    @field_validator("specific_date")
    def validate_future_date(cls, v):
        """Prevent setting availability for past dates."""
        if v < date.today():
            raise ValueError("Cannot set availability for past dates")
        return v


class AvailabilityWindowUpdate(BaseModel):
    """Schema for updating an availability window."""

    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    is_available: Optional[TimeType] = None

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time if both provided."""
        if v and info.data and "start_time" in info.data and info.data["start_time"] and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class AvailabilityWindowResponse(StandardizedModel):
    """Response schema for availability windows."""

    id: int
    instructor_id: int
    day_of_week: Optional[DayOfWeekEnum] = None  # Always None now
    specific_date: Optional[DateType] = None
    is_recurring: bool  # Always False now
    start_time: TimeType  # Add these from base
    end_time: TimeType
    is_available: bool = True

    model_config = ConfigDict(from_attributes=True)


# REMOVED: WeeklyScheduleCreate - no longer needed
# REMOVED: WeeklyScheduleResponse - no longer needed


# Blackout dates
class BlackoutDateCreate(BaseModel):
    """Schema for creating a blackout date."""

    date: DateType
    reason: Optional[str] = Field(None, max_length=255)

    @field_validator("date")
    def validate_future_date(cls, v):
        """Prevent creating blackout dates in the past."""
        if v < date.today():
            raise ValueError("Cannot create blackout date in the past")
        return v


class BlackoutDateResponse(StandardizedModel):  # Changed from BaseModel
    """Response schema for blackout dates."""

    id: int
    instructor_id: int
    date: DateType
    reason: Optional[str] = None
    created_at: DateTimeType  # Changed from str to datetime

    model_config = ConfigDict(from_attributes=True)


# Week-specific operations
class DateTimeSlot(BaseModel):
    """Schema for a time slot on a specific date."""

    date: DateType
    start_time: TimeType
    end_time: TimeType
    is_available: bool = True

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data and "start_time" in info.data and info.data["start_time"] and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v

    @field_validator("date")
    def validate_not_past(cls, v):
        """Prevent creating slots for past dates."""
        if v < date.today():
            raise ValueError("Cannot create availability for past dates")
        return v


class WeekSpecificScheduleCreate(BaseModel):
    """Schema for creating schedule for specific dates."""

    schedule: List[DateTimeSlot]
    clear_existing: bool = Field(
        default=True,
        description="Whether to clear existing entries for the week before saving",
    )
    week_start: Optional[DateType] = Field(
        None,
        description="Optional Monday date. If not provided, inferred from schedule dates",
    )

    @field_validator("week_start")
    def validate_monday(cls, v):
        """Ensure week start is a Monday if provided."""
        if v and v.weekday() != 0:
            raise ValueError("Week start must be a Monday")
        return v


class CopyWeekRequest(BaseModel):
    """Schema for copying availability between weeks."""

    from_week_start: DateType
    to_week_start: DateType

    @field_validator("from_week_start")
    @classmethod
    def validate_from_monday(cls, v):
        """Ensure from_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError(f"{v} is not a Monday (weekday={v.weekday()})")
        return v

    @field_validator("to_week_start")
    @classmethod
    def validate_to_monday(cls, v):
        """Ensure to_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError(f"{v} is not a Monday (weekday={v.weekday()})")
        return v

    @field_validator("to_week_start")
    def validate_different_weeks(cls, v, info):
        """Ensure we're not copying to the same week."""
        if info.data and "from_week_start" in info.data and v == info.data["from_week_start"]:
            raise ValueError("Cannot copy to the same week")
        return v


class ApplyToDateRangeRequest(BaseModel):
    """Schema for applying a week pattern to a date range."""

    from_week_start: DateType
    start_date: DateType
    end_date: DateType

    @field_validator("from_week_start")
    def validate_monday(cls, v):
        """Ensure source week starts on Monday."""
        if v.weekday() != 0:
            raise ValueError("Source week must start on a Monday")
        return v

    @field_validator("end_date")
    def validate_date_range(cls, v, info):
        """Validate the date range."""
        if info.data and "start_date" in info.data:
            if v < info.data["start_date"]:
                raise ValueError("End date must be after start date")
            # Enforce 1-year maximum range
            from datetime import timedelta

            max_end = info.data["start_date"] + timedelta(days=365)
            if v > max_end:
                raise ValueError("Date range cannot exceed 1 year (365 days)")
        return v

    @field_validator("start_date")
    def validate_future_date(cls, v):
        """Ensure we're not applying to past dates."""
        if v < date.today():
            raise ValueError("Cannot apply schedule to past dates")
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

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time for add/update."""
        if v and info.data and "start_time" in info.data and info.data["start_time"] and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v

    @field_validator("date")
    def validate_required_for_add(cls, v, info):
        if info.data.get("action") == "add" and not v:
            raise ValueError("date is required for add operations")
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


# Validation schemas
class ValidationSlotDetail(BaseModel):
    """Details about a slot operation in validation"""

    operation_index: int
    action: str
    date: Optional[DateType] = None
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    slot_id: Optional[int] = None
    reason: Optional[str] = None
    conflicts_with: Optional[List[Dict[str, Any]]] = None


class ValidationSummary(BaseModel):
    """Summary of validation results"""

    total_operations: int
    valid_operations: int
    invalid_operations: int
    operations_by_type: Dict[str, int]  # e.g., {"add": 3, "remove": 2}
    has_conflicts: bool
    estimated_changes: Dict[str, int]  # e.g., {"slots_added": 3, "slots_removed": 2}


class WeekValidationResponse(BaseModel):
    """Response for week schedule validation"""

    valid: bool
    summary: ValidationSummary
    details: List[ValidationSlotDetail]
    warnings: List[str] = []  # e.g., ["3 operations affect booked dates"]


class ValidateWeekRequest(BaseModel):
    """Request to validate week changes"""

    current_week: WeekSchedule  # What's currently shown in UI
    saved_week: WeekSchedule  # What's saved in database
    week_start: DateType
