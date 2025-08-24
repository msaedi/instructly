"""Response models for availability endpoints."""

from datetime import date, time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .availability_window import AvailabilityWindowResponse, BlackoutDateResponse


class WeekAvailabilityUpdateResponse(BaseModel):
    """Response for updating weekly availability."""

    message: str
    week_start: date
    week_end: date
    windows_created: int
    windows_updated: int
    windows_deleted: int


class CopyWeekResponse(BaseModel):
    """Response for copying week availability."""

    message: str
    source_week_start: date
    target_week_start: date
    windows_copied: int


class ApplyToDateRangeResponse(BaseModel):
    """Response for applying availability to date range."""

    message: str
    start_date: date
    end_date: date
    weeks_applied: int
    windows_created: int


class DeleteWindowResponse(BaseModel):
    """Response for deleting an availability window."""

    message: str = "Availability window deleted successfully"
    window_id: str


class BookedSlotsResponse(BaseModel):
    """Response for getting booked slots in a week."""

    week_start: date
    week_end: date
    booked_slots: List[Dict[str, Any]] = Field(description="List of booked slots with booking details")


class DeleteBlackoutResponse(BaseModel):
    """Response for deleting a blackout date."""

    message: str = "Blackout date removed successfully"
    blackout_id: str
