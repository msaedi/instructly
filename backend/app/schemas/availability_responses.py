from ._strict_base import StrictModel

"""Response models for availability endpoints."""

from datetime import date
from typing import Any, Dict, List

from pydantic import ConfigDict, Field, RootModel

from .availability_window import TimeRange


class WeekAvailabilityUpdateResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for updating weekly availability."""

    message: str
    week_start: date
    week_end: date
    windows_created: int
    windows_updated: int
    windows_deleted: int
    days_written: int = 0
    weeks_affected: int = 0
    edited_dates: List[str] = Field(default_factory=list)
    skipped_dates: List[str] = Field(default_factory=list)
    skipped_past_window: int = 0
    version: str | None = None
    week_version: str | None = None


class CopyWeekResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for copying week availability."""

    message: str
    source_week_start: date
    target_week_start: date
    windows_copied: int


class ApplyToDateRangeResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for applying availability to date range."""

    message: str
    start_date: date
    end_date: date
    weeks_applied: int
    windows_created: int
    weeks_affected: int
    days_written: int
    skipped_past_targets: int = 0
    edited_dates: List[str] = Field(default_factory=list)


class DeleteWindowResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for deleting an availability window."""

    message: str = "Availability window deleted successfully"
    window_id: str


class BookedSlotsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for getting booked slots in a week."""

    week_start: date
    week_end: date
    booked_slots: List[Dict[str, Any]] = Field(
        description="List of booked slots with booking details"
    )


class DeleteBlackoutResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for deleting a blackout date."""

    message: str = "Blackout date removed successfully"
    blackout_id: str


class WeekAvailabilityResponse(RootModel[Dict[str, List[TimeRange]]]):
    """Week availability mapping keyed by ISO date string."""
