"""
Booking schemas for InstaInstru platform.

This module defines Pydantic schemas for booking-related operations,
including instant booking creation, booking management, and status updates.
"""

from datetime import date, datetime, time
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.booking import BookingStatus
from ..schemas.base import Money, StandardizedModel


class BookingCreate(BaseModel):
    """
    Schema for creating a new instant booking.

    The student provides the slot they want to book, and the system
    handles all the calculations and confirmations.
    """

    availability_slot_id: int = Field(
        ..., description="ID of the availability slot to book"
    )
    service_id: int = Field(..., description="ID of the service being booked")
    student_note: Optional[str] = Field(
        None, max_length=1000, description="Optional note from student"
    )
    meeting_location: Optional[str] = Field(
        None, description="Specific meeting location if applicable"
    )
    location_type: Optional[
        Literal["student_home", "instructor_location", "neutral"]
    ] = Field("neutral", description="Type of meeting location")

    @field_validator("student_note")
    def clean_note(cls, v):
        """Clean up the student note."""
        return v.strip() if v else v

    @field_validator("location_type")
    def validate_location_type(cls, v):
        """Ensure location type is valid."""
        valid_types = ["student_home", "instructor_location", "neutral"]
        if v and v not in valid_types:
            raise ValueError(f"location_type must be one of {valid_types}")
        return v or "neutral"


class BookingUpdate(BaseModel):
    """
    Schema for updating booking details.

    Limited fields can be updated after booking creation.
    """

    instructor_note: Optional[str] = Field(None, max_length=1000)
    meeting_location: Optional[str] = None

    @field_validator("instructor_note")
    def clean_note(cls, v):
        """Clean up the instructor note."""
        return v.strip() if v else v


class BookingCancel(BaseModel):
    """Schema for cancelling a booking."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="Cancellation reason"
    )

    @field_validator("reason")
    def clean_reason(cls, v):
        """Ensure reason is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("Cancellation reason cannot be empty")
        return v


class BookingBase(StandardizedModel):
    """Base booking information."""

    id: int
    student_id: int
    instructor_id: int
    service_id: int
    availability_slot_id: Optional[int]

    # Booking details
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    hourly_rate: Money  # Changed from Decimal
    total_price: Money  # Changed from Decimal
    duration_minutes: int
    status: BookingStatus

    # Location
    service_area: Optional[str]
    meeting_location: Optional[str]
    location_type: Optional[str]

    # Notes
    student_note: Optional[str]
    instructor_note: Optional[str]

    # Timestamps
    created_at: datetime
    confirmed_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]

    # Cancellation info
    cancelled_by_id: Optional[int]
    cancellation_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class StudentInfo(StandardizedModel):
    """Basic student information for booking display."""

    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class InstructorInfo(StandardizedModel):
    """Basic instructor information for booking display."""

    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class ServiceInfo(StandardizedModel):
    """Basic service information for booking display."""

    id: int
    skill: str
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class BookingResponse(BookingBase):
    """
    Complete booking response with related information.

    Includes student, instructor, and service details.
    """

    student: StudentInfo
    instructor: InstructorInfo
    service: ServiceInfo

    @property
    def is_cancellable(self) -> bool:
        """Check if booking can be cancelled."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    @property
    def is_upcoming(self) -> bool:
        """Check if booking is in the future."""
        from datetime import date as dt_date

        return (
            self.booking_date > dt_date.today()
            and self.status == BookingStatus.CONFIRMED
        )


class BookingListResponse(StandardizedModel):
    """Response for booking list endpoints."""

    bookings: List[BookingResponse]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.per_page - 1) // self.per_page


class AvailabilityCheckRequest(BaseModel):
    """Request to check if a slot is available for booking."""

    availability_slot_id: int
    service_id: int


class AvailabilityCheckResponse(BaseModel):
    """Response for availability check."""

    available: bool
    reason: Optional[str] = None
    min_advance_hours: Optional[int] = None
    slot_info: Optional[dict] = None


class BookingStatsResponse(StandardizedModel):
    """Booking statistics for instructors."""

    total_bookings: int
    upcoming_bookings: int
    completed_bookings: int
    cancelled_bookings: int
    total_earnings: Money  # Changed from Decimal
    this_month_earnings: Money  # Changed from Decimal
    average_rating: Optional[float] = None  # For future use


class UpcomingBookingResponse(StandardizedModel):
    """Simplified response for upcoming bookings widget."""

    id: int
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    student_name: str
    instructor_name: str
    meeting_location: Optional[str]

    model_config = ConfigDict(from_attributes=True)
