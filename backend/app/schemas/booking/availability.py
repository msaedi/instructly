from datetime import date, datetime, time, timedelta
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.constants import MIN_SESSION_DURATION
from .._strict_base import StrictModel, StrictRequestModel
from ..base import STRICT_SCHEMAS
from ..common import LocationTypeLiteral


class ConflictingBookingInfo(StrictModel):
    """Information about a conflicting booking."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    booking_id: Optional[str] = Field(default=None, description="ID of the conflicting booking")
    start_time: Optional[str] = Field(default=None, description="Start time of conflict (HH:MM:SS)")
    end_time: Optional[str] = Field(default=None, description="End time of conflict (HH:MM:SS)")


class TimeSlotInfo(StrictModel):
    """Time slot information for availability checks."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    date: str = Field(description="ISO date string (YYYY-MM-DD)")
    start_time: str = Field(description="ISO time string (HH:MM:SS)")
    end_time: str = Field(description="ISO time string (HH:MM:SS)")
    instructor_id: str = Field(description="Instructor ID")


class AvailabilityWarningInfo(StrictModel):
    """Advisory availability warning details."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    type: Literal["proximity"] = Field(description="Warning type")
    message: str = Field(description="Human-readable advisory warning")
    conflicting_booking_id: str = Field(description="Related booking ID")
    conflicting_service: str = Field(description="Related service name")
    gap_minutes: int = Field(description="Gap in minutes between bookings")


class AvailabilityCheckRequest(StrictRequestModel):
    """
    Check if a specific time is available for booking.
    """

    instructor_id: str = Field(..., description="Instructor to check")
    instructor_service_id: str = Field(..., description="Service to book")
    exclude_booking_id: Optional[str] = Field(
        None,
        description="Optional booking ID to exclude during conflict checks",
    )
    booking_date: date = Field(..., description="Date to check")
    start_time: time = Field(..., description="Start time to check (HH:MM)")
    end_time: time = Field(..., description="End time to check (HH:MM)")
    location_type: LocationTypeLiteral = Field(..., description="Requested booking format")
    selected_duration: Optional[int] = Field(
        None,
        ge=MIN_SESSION_DURATION,
        le=720,
        description="Optional duration in minutes for parity with booking validation",
    )
    location_address: Optional[str] = Field(
        None,
        description="Optional address for preflight location comparison",
    )
    location_place_id: Optional[str] = Field(
        None,
        description="Optional place ID for preflight location comparison",
    )
    location_lat: Optional[float] = Field(
        None,
        ge=-90.0,
        le=90.0,
        description="Optional latitude for service-area validation",
    )
    location_lng: Optional[float] = Field(
        None,
        ge=-180.0,
        le=180.0,
        description="Optional longitude for service-area validation",
    )

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_string(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                hour, minute = v.split(":")
                return time(int(hour), int(minute))
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {v}. Expected HH:MM format.")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: time, info: Any) -> time:
        start_time_value = None
        if isinstance(getattr(info, "data", None), dict):
            start_time_value = info.data.get("start_time")

        if start_time_value is None:
            return v

        if v == time(0, 0) and start_time_value != time(0, 0):
            return v

        if v <= start_time_value:
            raise ValueError("End time must be after start time")
        return v

    @field_validator("booking_date", mode="before")
    @classmethod
    def _enforce_date_only(cls, v: object) -> object:
        from .requests import _ensure_date_only

        return _ensure_date_only(v, "booking_date")


class AvailabilityCheckResponse(StrictModel):
    """Response for availability check."""

    available: bool
    reason: Optional[str] = None
    warnings: Optional[List[AvailabilityWarningInfo]] = Field(
        default=None,
        description="Advisory warnings that do not block booking",
    )
    min_advance_minutes: Optional[int] = None
    conflicts_with: Optional[List[ConflictingBookingInfo]] = Field(
        default=None, description="List of conflicting bookings if any"
    )
    time_info: Optional[TimeSlotInfo] = Field(
        default=None, description="Time slot information for the availability check"
    )


class FindBookingOpportunitiesRequest(StrictRequestModel):
    """
    Request to find available booking opportunities.
    """

    instructor_id: str = Field(..., description="Instructor to search")
    instructor_service_id: str = Field(..., description="Service to book")
    date_range_start: date = Field(..., description="Start of search range")
    date_range_end: date = Field(..., description="End of search range")
    preferred_times: Optional[List[time]] = Field(None, description="Preferred start times (HH:MM)")

    @field_validator("date_range_end")
    @classmethod
    def validate_date_range(cls, v: date, info: Any) -> date:
        if (
            isinstance(getattr(info, "data", None), dict)
            and info.data.get("date_range_start")
            and v < info.data["date_range_start"]
        ):
            raise ValueError("End date must be after start date")

        if isinstance(getattr(info, "data", None), dict) and info.data.get("date_range_start"):
            max_range = info.data["date_range_start"] + timedelta(days=90)
            if v > max_range:
                raise ValueError("Search range cannot exceed 90 days")
        return v

    if STRICT_SCHEMAS:

        @field_validator("date_range_start", "date_range_end", mode="before")
        @classmethod
        def _strict_date_range_only(cls, v: object) -> object:
            if isinstance(v, str):
                datetime.strptime(v, "%Y-%m-%d")
                return v
            return v


class BookingOpportunity(BaseModel):
    """A single booking opportunity."""

    date: date
    start_time: time
    end_time: time
    available: bool = True


class BookingSearchParameters(StrictModel):
    """Search parameters used to find booking opportunities."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    instructor_id: str = Field(description="Instructor searched")
    instructor_service_id: str = Field(description="Service to book")
    date_range_start: str = Field(description="Start of search range (YYYY-MM-DD)")
    date_range_end: str = Field(description="End of search range (YYYY-MM-DD)")
    preferred_times: Optional[List[str]] = Field(
        default=None, description="Preferred start times (HH:MM)"
    )


class FindBookingOpportunitiesResponse(StrictModel):
    """Response with available booking opportunities."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    opportunities: List[BookingOpportunity]
    total_found: int
    search_parameters: BookingSearchParameters = Field(description="Parameters used for the search")
