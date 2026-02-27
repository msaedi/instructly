# backend/app/schemas/availability_window.py
"""
Availability window schemas for InstaInstru platform.

Clean Architecture: Focused on date-specific availability management.
No recurring patterns, no is_available fields, no legacy enums.
Slots exist = available. That's it.
"""

import datetime
import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._strict_base import StrictModel, StrictRequestModel
from .base import StandardizedModel

logger = logging.getLogger(__name__)


class ScheduleItem(StrictModel):
    """Individual schedule item for availability creation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    date: str = Field(description="ISO date string (YYYY-MM-DD)")
    start_time: str = Field(description="Start time (HH:MM or HH:MM:SS)")
    end_time: str = Field(description="End time (HH:MM or HH:MM:SS)")


class AvailabilityConflictInfo(StrictModel):
    """Information about a booking that conflicts with an availability operation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    booking_id: Optional[str] = Field(default=None, description="ID of conflicting booking")
    start_time: Optional[str] = Field(default=None, description="Start time of conflict")
    end_time: Optional[str] = Field(default=None, description="End time of conflict")


# Type aliases for clarity
DateType = datetime.date
TimeType = datetime.time
DateTimeType = datetime.datetime

_MIDNIGHT = datetime.time(0, 0)


def _is_half_open_interval(start: TimeType | None, end: TimeType | None) -> bool:
    """Allow [start, end) intervals with midnight treated as 24:00."""
    if start is None or end is None:
        return True
    if end > start:
        return True
    return end == _MIDNIGHT and start != _MIDNIGHT


class TimeSlot(BaseModel):
    """Time slot for availability."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    start_time: TimeType
    end_time: TimeType


class AvailabilityWindowBase(StrictRequestModel):
    """Base schema for availability windows."""

    model_config = StrictRequestModel.model_config

    start_time: TimeType
    end_time: TimeType

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: TimeType, info: Any) -> TimeType:
        """Ensure end time is after start time."""
        data = getattr(info, "data", None)
        start = data.get("start_time") if isinstance(data, dict) else None
        if not _is_half_open_interval(start, v):
            raise ValueError("End time must be after start time")
        return v


class SpecificDateAvailabilityCreate(StrictRequestModel):
    """Schema for creating availability on a specific date."""

    model_config = StrictRequestModel.model_config

    start_time: TimeType
    end_time: TimeType
    specific_date: DateType

    # Date validation removed - handled in service layer with user timezone context
    # Past date validation requires knowing the user's timezone

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: TimeType, info: Any) -> TimeType:
        """Ensure end time is after start time."""
        data = getattr(info, "data", None)
        start = data.get("start_time") if isinstance(data, dict) else None
        if not _is_half_open_interval(start, v):
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


class BlackoutDateCreate(StrictRequestModel):
    """Schema for creating a blackout date."""

    model_config = StrictRequestModel.model_config

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

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    start_time: TimeType
    end_time: TimeType

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: TimeType, info: Any) -> TimeType:
        """Ensure end time is after start time."""
        data = getattr(info, "data", None)
        start = data.get("start_time") if isinstance(data, dict) else None
        if not _is_half_open_interval(start, v):
            raise ValueError("End time must be after start time")
        return v


class WeekSpecificScheduleCreate(StrictRequestModel):
    """Schema for creating schedule for specific dates."""

    model_config = StrictRequestModel.model_config

    schedule: List[ScheduleItem] = Field(
        description="List of schedule items with date, start_time, and end_time"
    )
    clear_existing: bool = Field(
        default=True,
        description="Whether to clear existing entries for the week before saving",
    )
    week_start: Optional[DateType] = Field(
        None,
        description="Optional Monday date. If not provided, inferred from schedule dates",
    )
    base_version: Optional[str] = Field(
        None,
        description="Client's baseline week version when saving (If-Match fallback)",
    )
    version: Optional[str] = Field(  # Back-compat alias; prefer base_version
        None,
        description="Deprecated alias for base_version (optimistic concurrency token)",
    )
    override: bool = Field(
        default=False,
        description="If true, bypass server-side version checks when saving",
    )

    @field_validator("week_start")
    @classmethod
    def validate_monday(cls, v: Optional[DateType]) -> Optional[DateType]:
        """Ensure week start is a Monday if provided."""
        if v and v.weekday() != 0:
            raise ValueError("Week start must be a Monday")
        return v


class CopyWeekRequest(StrictRequestModel):
    """Schema for copying availability between weeks."""

    model_config = StrictRequestModel.model_config

    from_week_start: DateType
    to_week_start: DateType

    @field_validator("from_week_start")
    @classmethod
    def validate_from_monday(cls, v: DateType) -> DateType:
        """Ensure from_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError(f"{v} is not a Monday (weekday={v.weekday()})")
        return v

    @field_validator("to_week_start")
    @classmethod
    def validate_to_monday(cls, v: DateType) -> DateType:
        """Ensure to_week_start is a Monday."""
        if v.weekday() != 0:
            raise ValueError(f"{v} is not a Monday (weekday={v.weekday()})")
        return v

    @field_validator("to_week_start")
    @classmethod
    def validate_different_weeks(cls, v: DateType, info: Any) -> DateType:
        """Ensure we're not copying to the same week."""
        if (
            getattr(info, "data", None)
            and info.data.get("from_week_start")
            and v == info.data["from_week_start"]
        ):
            raise ValueError("Cannot copy to the same week")
        return v


class ApplyToDateRangeRequest(StrictRequestModel):
    """Schema for applying a week pattern to a date range."""

    model_config = StrictRequestModel.model_config

    from_week_start: DateType
    start_date: DateType
    end_date: DateType

    @field_validator("from_week_start")
    @classmethod
    def validate_monday(cls, v: DateType) -> DateType:
        """Ensure source week starts on Monday."""
        if v.weekday() != 0:
            raise ValueError("Source week must start on a Monday")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: DateType, info: Any) -> DateType:
        """Validate the date range."""
        if getattr(info, "data", None) and info.data.get("start_date"):
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

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action: Literal["add", "remove", "update"]
    # For add/update:
    date: Optional[DateType] = None
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    # For remove/update:
    slot_id: Optional[str] = None

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: Optional[TimeType], info: Any) -> Optional[TimeType]:
        """Ensure end time is after start time for add/update."""
        if not v:
            return v
        data = getattr(info, "data", None)
        start = data.get("start_time") if isinstance(data, dict) else None
        if not _is_half_open_interval(start, v):
            raise ValueError("End time must be after start time")
        return v

    @field_validator("date")
    @classmethod
    def validate_required_for_add(cls, v: Optional[DateType], info: Any) -> Optional[DateType]:
        if (
            isinstance(getattr(info, "data", None), dict)
            and info.data.get("action") == "add"
            and not v
        ):
            raise ValueError("date is required for add operations")
        return v


class OperationResult(BaseModel):
    """Result of a single operation in bulk update."""

    operation_index: int
    action: str
    status: Literal["success", "failed", "skipped"]
    reason: Optional[str] = None
    slot_id: Optional[str] = None  # For successful adds


# Validation schemas
class ValidationSlotDetail(BaseModel):
    """Details about a slot operation in validation"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    operation_index: int
    action: str
    date: Optional[DateType] = None
    start_time: Optional[TimeType] = None
    end_time: Optional[TimeType] = None
    slot_id: Optional[str] = None
    reason: Optional[str] = None
    conflicts_with: Optional[List[AvailabilityConflictInfo]] = Field(
        default=None, description="Bookings that conflict with this operation"
    )


class ValidationSummary(BaseModel):
    """Summary of validation results"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    total_operations: int
    valid_operations: int
    invalid_operations: int
    operations_by_type: Dict[str, int]  # e.g., {"add": 3, "remove": 2}
    has_conflicts: bool
    estimated_changes: Dict[str, int]  # e.g., {"slots_added": 3, "slots_removed": 2}


class WeekValidationResponse(StrictModel):
    """Response for week schedule validation"""

    valid: bool
    summary: ValidationSummary
    details: List[ValidationSlotDetail]
    warnings: List[str] = []  # e.g., ["3 operations affect booked dates"]


class ValidateWeekRequest(StrictRequestModel):
    """Request to validate week changes"""

    model_config = StrictRequestModel.model_config

    current_week: Dict[str, List[TimeSlot]]  # What's currently shown in UI
    saved_week: Dict[str, List[TimeSlot]]  # What's saved in database
    week_start: DateType


try:
    WeekSpecificScheduleCreate.model_rebuild(force=True)
    ValidateWeekRequest.model_rebuild(force=True)
except Exception:  # pragma: no cover - defensive initialization
    logger.debug("Failed to rebuild availability schemas", exc_info=True)
