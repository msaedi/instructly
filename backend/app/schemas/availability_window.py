# backend/app/schemas/availability_window.py
"""
Availability window schemas for InstaInstru platform.

Clean Architecture: Focused on date-specific availability management.
No recurring patterns, no is_available fields, no legacy enums.
Slots exist = available. That's it.
"""

import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import StandardizedModel

# Type aliases for clarity
DateType = datetime.date
TimeType = datetime.time
DateTimeType = datetime.datetime


class TimeSlot(BaseModel):
    """Time slot for availability - simplified without is_available."""

    start_time: TimeType
    end_time: TimeType


class AvailabilityWindowBase(BaseModel):
    """Base schema for availability windows."""

    start_time: TimeType
    end_time: TimeType

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class SpecificDateAvailabilityCreate(AvailabilityWindowBase):
    """Schema for creating availability on a specific date."""

    specific_date: DateType

    # Date validation removed - handled in service layer with user timezone context
    # Past date validation requires knowing the user's timezone


class AvailabilityWindowUpdate(BaseModel):
    """Schema for updating an availability window."""

    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time if both provided."""
        if v and info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class AvailabilityWindowResponse(StandardizedModel):
    """
    Response schema for availability windows.
    Clean Architecture: Only meaningful fields for single-table design.
    """

    id: str
    instructor_id: str
    specific_date: DateType
    start_time: TimeType
    end_time: TimeType

    model_config = ConfigDict(from_attributes=True)


class BlackoutDateCreate(BaseModel):
    """Schema for creating a blackout date."""

    date: DateType
    reason: Optional[str] = Field(None, max_length=255)

    # Date validation removed - handled in service layer with user timezone context
    # Past date validation requires knowing the instructor's timezone


class BlackoutDateResponse(StandardizedModel):
    """Response schema for blackout dates."""

    id: str
    instructor_id: str
    date: DateType
    reason: Optional[str] = None
    created_at: DateTimeType

    model_config = ConfigDict(from_attributes=True)


class TimeRange(BaseModel):
    """Simple time range for schedule entries."""

    start_time: TimeType
    end_time: TimeType

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class WeekSpecificScheduleCreate(BaseModel):
    """Schema for creating schedule for specific dates."""

    schedule: List[
        Dict[str, Any]
    ]  # Each item: {"date": "2025-07-15", "start_time": "09:00", "end_time": "10:00"}
    clear_existing: bool = Field(
        default=True,
        description="Whether to clear existing entries for the week before saving",
    )
    week_start: Optional[DateType] = Field(
        None,
        description="Optional Monday date. If not provided, inferred from schedule dates",
    )
    version: Optional[str] = Field(
        None,
        description="Optional optimistic concurrency token (ETag) for this week",
    )

    @field_validator("week_start")
    @classmethod
    def validate_monday(cls, v):
        """Ensure week start is a Monday if provided."""
        if v and v.weekday() != 0:
            raise ValueError("Week start must be a Monday")
        return v

    @field_validator("schedule")
    @classmethod
    def validate_schedule_items(cls, v):
        """Validate each schedule item has required fields."""
        for item in v:
            if not isinstance(item, dict):
                raise ValueError("Schedule items must be dictionaries")
            if "date" not in item or "start_time" not in item or "end_time" not in item:
                raise ValueError("Each schedule item must have date, start_time, and end_time")
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
    @classmethod
    def validate_different_weeks(cls, v, info):
        """Ensure we're not copying to the same week."""
        if info.data.get("from_week_start") and v == info.data["from_week_start"]:
            raise ValueError("Cannot copy to the same week")
        return v


class ApplyToDateRangeRequest(BaseModel):
    """Schema for applying a week pattern to a date range."""

    from_week_start: DateType
    start_date: DateType
    end_date: DateType

    @field_validator("from_week_start")
    @classmethod
    def validate_monday(cls, v):
        """Ensure source week starts on Monday."""
        if v.weekday() != 0:
            raise ValueError("Source week must start on a Monday")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        """Validate the date range."""
        if info.data.get("start_date"):
            if v < info.data["start_date"]:
                raise ValueError("End date must be after start date")
            # Enforce 1-year maximum range
            from datetime import timedelta

            max_end = info.data["start_date"] + timedelta(days=365)
            if v > max_end:
                raise ValueError("Date range cannot exceed 1 year (365 days)")
        return v

    # Date validation removed - handled in service layer with user timezone context
    # Past date validation requires knowing the instructor's timezone


# Bulk update schemas
class SlotOperation(BaseModel):
    """Schema for a single slot operation in bulk update."""

    action: Literal["add", "remove", "update"]
    # For add/update:
    date: Optional[DateType] = None
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    # For remove/update:
    slot_id: Optional[str] = None

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time for add/update."""
        if v and info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v

    @field_validator("date")
    @classmethod
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
    slot_id: Optional[str] = None  # For successful adds


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
    slot_id: Optional[str] = None
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

    current_week: Dict[str, List[TimeSlot]]  # What's currently shown in UI
    saved_week: Dict[str, List[TimeSlot]]  # What's saved in database
    week_start: DateType
