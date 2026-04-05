from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Literal, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator
import pytz

from ...core.constants import MIN_SESSION_DURATION
from .._strict_base import StrictRequestModel
from ..common import LocationTypeLiteral

DATE_ONLY_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ensure_date_only(value: object, field_name: str) -> object:
    if isinstance(value, str):
        candidate = value.strip()
        if not DATE_ONLY_REGEX.fullmatch(candidate):
            raise ValueError(f"{field_name} must be a YYYY-MM-DD date-only string")
        return candidate
    return value


class BookingCreate(StrictRequestModel):
    """
    Create a booking with self-contained time information.

    Clean Architecture: No slot references - bookings are independent.
    The booking contains all necessary information about when and where
    the lesson will occur.
    """

    instructor_id: str = Field(..., description="Instructor to book")
    instructor_service_id: str = Field(..., description="Instructor service being booked")
    booking_date: date = Field(..., description="Date of the booking")
    start_time: time = Field(..., description="Start time (HH:MM)")
    selected_duration: int = Field(
        ...,
        ge=MIN_SESSION_DURATION,
        le=720,
        description="Selected duration in minutes from service's duration_options",
    )
    student_note: Optional[str] = Field(
        None, max_length=1000, description="Optional note from student"
    )
    meeting_location: Optional[str] = Field(
        None, description="Specific meeting location if applicable"
    )
    location_type: Optional[LocationTypeLiteral] = Field(
        "online",
        description="Type of meeting location",
    )
    location_address: Optional[str] = Field(
        None, description="Structured location address for in-person lessons"
    )
    location_lat: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Latitude for the lesson location"
    )
    location_lng: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Longitude for the lesson location"
    )
    location_place_id: Optional[str] = Field(None, description="Place ID for the lesson location")
    end_time: Optional[time] = Field(
        None, description="Calculated end time (HH:MM, set automatically)"
    )
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone for booking times (defaults to instructor timezone)",
    )

    @field_validator("booking_date", mode="before")
    @classmethod
    def _enforce_date_only(cls, v: object) -> object:
        return _ensure_date_only(v, "booking_date")

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

    @field_validator("selected_duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < MIN_SESSION_DURATION:
            raise ValueError(f"Duration must be at least {MIN_SESSION_DURATION} minutes")
        if v > 720:
            raise ValueError("Duration cannot exceed 12 hours")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                pytz.timezone(v)
            except pytz.UnknownTimeZoneError as exc:
                raise ValueError(f"Invalid timezone: {v}") from exc
        return v

    @field_validator("student_note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v

    @field_validator("location_type")
    @classmethod
    def validate_location_type(cls, v: Optional[str]) -> str:
        valid_types = [
            "student_location",
            "instructor_location",
            "online",
            "neutral_location",
        ]
        if v and v not in valid_types:
            raise ValueError(f"location_type must be one of {valid_types}")
        return v or "online"

    @model_validator(mode="after")
    def validate_location_address(self) -> "BookingCreate":
        valid_types = ("student_location", "instructor_location", "online", "neutral_location")
        if self.location_type not in valid_types:
            return self

        if self.location_type != "online":
            address = (self.location_address or self.meeting_location or "").strip()
            if not address:
                raise ValueError("Address is required for non-online bookings")
            if not self.location_address:
                self.location_address = address
        if self.location_type in ("student_location", "neutral_location"):
            if self.location_lat is None or self.location_lng is None:
                raise ValueError(
                    "Coordinates are required for service area validation. "
                    "Please select an address using the address picker."
                )
        return self

    @model_validator(mode="after")
    def validate_time_order(self) -> "BookingCreate":
        if self.end_time is None and self.start_time and self.selected_duration:
            reference_date = date(2024, 1, 1)
            start_datetime = datetime.combine(  # tz-pattern-ok: duration math only
                reference_date, self.start_time, tzinfo=timezone.utc
            )
            end_datetime = start_datetime + timedelta(minutes=self.selected_duration)
            self.end_time = end_datetime.time()

        if self.start_time and self.end_time:
            midnight = time(0, 0)
            if self.end_time == midnight and self.start_time != midnight:
                return self
            if self.end_time <= self.start_time:
                raise ValueError("End time must be after start time")

        return self


class BookingRescheduleRequest(StrictRequestModel):
    """
    Request to reschedule an existing booking by specifying a new date/time and duration.
    """

    booking_date: date = Field(..., description="New date for the lesson")
    start_time: time = Field(..., description="New start time (HH:MM)")
    selected_duration: int = Field(
        ...,
        ge=MIN_SESSION_DURATION,
        le=720,
        description="New selected duration in minutes",
    )
    instructor_service_id: Optional[str] = Field(
        None, description="Override service if needed (defaults to old)"
    )

    @field_validator("booking_date", mode="before")
    @classmethod
    def _enforce_date_only(cls, v: object) -> object:
        return _ensure_date_only(v, "booking_date")

    @field_validator("start_time", mode="before")
    @classmethod
    def parse_time_string(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                hour, minute = v.split(":")
                return time(int(hour), int(minute))
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {v}. Expected HH:MM format.")
        return v

    @field_validator("selected_duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < MIN_SESSION_DURATION:
            raise ValueError(f"Duration must be at least {MIN_SESSION_DURATION} minutes")
        if v > 720:
            raise ValueError("Duration cannot exceed 12 hours")
        return v


class BookingUpdate(StrictRequestModel):
    """Schema for updating booking details."""

    instructor_note: Optional[str] = Field(None, max_length=1000)
    meeting_location: Optional[str] = None

    @field_validator("instructor_note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class BookingCancel(StrictRequestModel):
    """Schema for cancelling a booking."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    reason: str = Field(..., min_length=1, max_length=500, description="Cancellation reason")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Cancellation reason cannot be empty")
        return v


class NoShowReportRequest(StrictRequestModel):
    """Schema for reporting a no-show."""

    no_show_type: Literal["instructor", "student"]
    reason: Optional[str] = Field(None, max_length=500)


class NoShowDisputeRequest(StrictRequestModel):
    """Schema for disputing a no-show report."""

    reason: str = Field(..., min_length=10, max_length=500)


class BookingPaymentMethodUpdate(StrictRequestModel):
    """
    Request to update a booking's payment method, with optional default flag.
    """

    payment_method_id: str = Field(..., description="Stripe payment method ID")
    set_as_default: bool = Field(False, description="Whether to save as default for the student")
