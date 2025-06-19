"""
Availability schemas for InstaInstru platform.

This module defines Pydantic schemas for availability-related operations.
These schemas handle data validation and serialization for the availability
management system.

Note: Schema names have been updated to match the new model names after
the table renaming refactoring.
"""

from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AvailabilitySlotBase(BaseModel):
    """Base schema for availability time slots."""

    start_time: time
    end_time: time

    @field_validator("end_time")
    def validate_time_order(cls, v, values):
        """Ensure end time is after start time."""
        if "start_time" in values and v <= values["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class AvailabilitySlotCreate(AvailabilitySlotBase):
    """Schema for creating a new availability slot."""


class AvailabilitySlot(AvailabilitySlotBase):
    """Schema for returning availability slot data."""

    id: int
    availability_id: int  # Changed from date_override_id

    model_config = ConfigDict(from_attributes=True)


class InstructorAvailabilityBase(BaseModel):
    """Base schema for instructor availability entries."""

    date: date
    is_cleared: bool = False


class InstructorAvailabilityCreate(InstructorAvailabilityBase):
    """Schema for creating instructor availability."""

    time_slots: List[AvailabilitySlotCreate] = []

    @field_validator("date")
    def validate_not_past(cls, v):
        """Prevent creating availability for past dates."""
        if v < date.today():
            raise ValueError("Cannot create availability for past dates")
        return v


class InstructorAvailabilityUpdate(BaseModel):
    """Schema for updating instructor availability."""

    is_cleared: Optional[bool] = None
    time_slots: Optional[List[AvailabilitySlotCreate]] = None


class InstructorAvailability(InstructorAvailabilityBase):
    """Schema for returning instructor availability data."""

    id: int
    instructor_id: int
    time_slots: List[AvailabilitySlot] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Legacy schemas for backward compatibility during migration
class DateTimeSlot(BaseModel):
    """
    Legacy schema maintained for API compatibility.
    Maps to the new AvailabilitySlot in the backend.
    """

    date: date
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format
    is_available: bool = True


class WeekScheduleCreate(BaseModel):
    """Schema for creating a week's schedule."""

    schedule: List[DateTimeSlot]
    clear_existing: bool = True


class CopyWeekRequest(BaseModel):
    """Schema for copying availability between weeks."""

    from_week_start: date
    to_week_start: date

    @field_validator("from_week_start")
    @classmethod
    def validate_from_monday(cls, v):
        """Ensure from_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError("Week start dates must be Mondays")
        return v

    @field_validator("to_week_start")
    @classmethod
    def validate_to_monday(cls, v):
        """Ensure to_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError("Week start dates must be Mondays")
        return v

    @field_validator("to_week_start")
    def validate_different_weeks(cls, v, values):
        """Ensure we're not copying to the same week."""
        if "from_week_start" in values and v == values["from_week_start"]:
            raise ValueError("Cannot copy to the same week")
        return v


class ApplyToDateRangeRequest(BaseModel):
    """Schema for applying a pattern to a date range."""

    from_week_start: date
    start_date: date
    end_date: date

    @field_validator("from_week_start")
    def validate_monday(cls, v):
        """Ensure week start is a Monday."""
        if v.weekday() != 0:
            raise ValueError("Week start date must be a Monday")
        return v

    @field_validator("end_date")
    def validate_date_range(cls, v, values):
        """Ensure valid date range."""
        if "start_date" in values and v < values["start_date"]:
            raise ValueError("End date must be after start date")
        # Check for 1-year limit
        if "start_date" in values:
            from datetime import timedelta

            max_end = values["start_date"] + timedelta(days=365)
            if v > max_end:
                raise ValueError("Date range cannot exceed 1 year")
        return v


class AvailabilityQuery(BaseModel):
    """Schema for querying availability."""

    instructor_id: int
    service_id: int
    date: date

    @field_validator("date")
    def validate_future_date(cls, v):
        """Ensure querying for future dates only."""
        if v < date.today():
            raise ValueError("Cannot query availability for past dates")
        return v
