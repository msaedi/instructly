# backend/app/schemas/booking.py
"""
Booking schemas for InstaInstru platform.

Clean Architecture: Bookings are completely self-contained with their own
date/time information. No references to availability slots. This implements
the "Rug and Person" principle where bookings persist independently of
availability changes.
"""

from datetime import date, datetime, time, timedelta
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, validator

from ..models.booking import BookingStatus
from ..schemas.base import Money, StandardizedModel


class BookingCreate(BaseModel):
    """
    Create a booking with self-contained time information.

    Clean Architecture: No slot references - bookings are independent.
    The booking contains all necessary information about when and where
    the lesson will occur.
    """

    instructor_id: str = Field(..., description="Instructor to book")
    instructor_service_id: str = Field(..., description="Instructor service being booked")
    booking_date: date = Field(..., description="Date of the booking")
    start_time: time = Field(..., description="Start time")
    selected_duration: int = Field(..., description="Selected duration in minutes from service's duration_options")
    student_note: Optional[str] = Field(None, max_length=1000, description="Optional note from student")
    meeting_location: Optional[str] = Field(None, description="Specific meeting location if applicable")
    location_type: Optional[Literal["student_home", "instructor_location", "neutral"]] = Field(
        "neutral", description="Type of meeting location"
    )

    # Note: end_time is calculated from start_time + selected_duration
    end_time: Optional[time] = Field(None, description="Calculated end time (set automatically)")

    # Forbid extra fields to enforce clean architecture
    model_config = ConfigDict(extra="forbid")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_string(cls, v):
        """Convert time strings to time objects."""
        if isinstance(v, str):
            try:
                # Parse HH:MM format
                hour, minute = v.split(":")
                return time(int(hour), int(minute))
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {v}. Expected HH:MM format.")
        return v

    @field_validator("selected_duration")
    @classmethod
    def validate_duration(cls, v):
        """Ensure duration is within reasonable bounds."""
        if v < 15:
            raise ValueError("Duration must be at least 15 minutes")
        if v > 720:  # 12 hours
            raise ValueError("Duration cannot exceed 12 hours")
        return v

    # NOTE: Date validation moved to services to support user timezones
    # @field_validator("booking_date")
    # @classmethod
    # def validate_future_date(cls, v):
    #     """Ensure booking is for future date."""
    #     if v < date.today():
    #         raise ValueError("Cannot book for past dates")
    #     return v

    @field_validator("student_note")
    @classmethod
    def clean_note(cls, v):
        """Clean up the student note."""
        return v.strip() if v else v

    @field_validator("location_type")
    @classmethod
    def validate_location_type(cls, v):
        """Ensure location type is valid."""
        valid_types = ["student_home", "instructor_location", "neutral"]
        if v and v not in valid_types:
            raise ValueError(f"location_type must be one of {valid_types}")
        return v or "neutral"

    @model_validator(mode="after")
    def validate_time_order(self):
        """Ensure end_time is after start_time and calculate if needed."""
        if self.end_time is None and self.start_time and self.selected_duration:
            # Calculate end_time from start_time + duration
            # Use a reference date for time calculation (this is just for math, not timezone-specific)
            reference_date = date(2024, 1, 1)
            start_datetime = datetime.combine(reference_date, self.start_time)
            end_datetime = start_datetime + timedelta(minutes=self.selected_duration)
            self.end_time = end_datetime.time()

        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValueError("End time must be after start time")

        return self


class BookingUpdate(BaseModel):
    """
    Schema for updating booking details.

    Limited fields can be updated after booking creation.
    """

    instructor_note: Optional[str] = Field(None, max_length=1000)
    meeting_location: Optional[str] = None

    @field_validator("instructor_note")
    @classmethod
    def clean_note(cls, v):
        """Clean up the instructor note."""
        return v.strip() if v else v


class BookingCancel(BaseModel):
    """Schema for cancelling a booking."""

    reason: str = Field(..., min_length=1, max_length=500, description="Cancellation reason")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v):
        """Ensure reason is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("Cancellation reason cannot be empty")
        return v


class BookingBase(StandardizedModel):
    """Base booking information - self-contained record."""

    id: str
    student_id: str
    instructor_id: str
    instructor_service_id: str

    # Self-contained booking details
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    hourly_rate: Money
    total_price: Money
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
    cancelled_by_id: Optional[str]
    cancellation_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class StudentInfo(StandardizedModel):
    """Basic student information for booking display."""

    id: str
    first_name: str
    last_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class InstructorInfo(StandardizedModel):
    """
    Instructor information for booking display.

    Privacy-aware: Only shows last initial for privacy protection.
    Full last name never exposed to students.
    """

    id: str
    first_name: str
    last_initial: str  # Only last initial (e.g., "S") - NO PERIOD
    # Note: email excluded for student privacy

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user) -> "InstructorInfo":
        """
        Factory method to create InstructorInfo from User model.
        Ensures privacy by only exposing last initial.
        """
        return cls(id=user.id, first_name=user.first_name, last_initial=user.last_name[0] if user.last_name else "")


class ServiceInfo(StandardizedModel):
    """Basic service information for booking display."""

    id: str
    name: str  # From catalog
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class BookingResponse(BookingBase):
    """
    Complete booking response with privacy protection.

    Shows instructor as "FirstName L" (last initial only).
    Students see their own full information.
    Clean Architecture: No availability slot references.
    """

    student: StudentInfo  # Students see their own full info
    instructor: InstructorInfo  # Privacy-aware: only has last_initial
    instructor_service: ServiceInfo

    @property
    def is_cancellable(self) -> bool:
        """Check if booking can be cancelled."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    def is_upcoming(self, user_today: date) -> bool:
        """
        Check if booking is in the future.

        Args:
            user_today: Today's date in user's timezone (required)
        """
        return self.booking_date > user_today and self.status == BookingStatus.CONFIRMED

    @classmethod
    def from_orm(cls, booking) -> "BookingResponse":
        """
        Create BookingResponse from Booking ORM model.
        Handles privacy transformation automatically.
        """
        # Build the response with proper privacy protection
        return cls(
            # Base fields from BookingBase
            id=booking.id,
            student_id=booking.student_id,
            instructor_id=booking.instructor_id,
            instructor_service_id=booking.instructor_service_id,
            # Booking details
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            service_name=booking.service_name,
            hourly_rate=booking.hourly_rate,
            total_price=booking.total_price,
            duration_minutes=booking.duration_minutes,
            status=booking.status,
            # Location
            service_area=booking.service_area,
            meeting_location=booking.meeting_location,
            location_type=booking.location_type,
            # Notes
            student_note=booking.student_note,
            instructor_note=booking.instructor_note,
            # Timestamps
            created_at=booking.created_at,
            confirmed_at=booking.confirmed_at,
            completed_at=booking.completed_at,
            cancelled_at=booking.cancelled_at,
            # Cancellation info
            cancelled_by_id=booking.cancelled_by_id,
            cancellation_reason=booking.cancellation_reason,
            # Related objects with privacy protection
            instructor=InstructorInfo.from_user(booking.instructor),
            student=StudentInfo(
                id=booking.student.id,
                first_name=booking.student.first_name,
                last_name=booking.student.last_name,
                email=booking.student.email,
            ),
            instructor_service=ServiceInfo(
                id=booking.instructor_service.id if booking.instructor_service else booking.instructor_service_id,
                name=booking.service_name,  # Use denormalized name
                description=booking.instructor_service.description if booking.instructor_service else None,
            ),
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
    """
    Check if a specific time is available for booking.

    Clean Architecture: Uses instructor, date, and time directly.
    No slot references needed.
    """

    instructor_id: str = Field(..., description="Instructor to check")
    instructor_service_id: str = Field(..., description="Service to book")
    booking_date: date = Field(..., description="Date to check")
    start_time: time = Field(..., description="Start time to check")
    end_time: time = Field(..., description="End time to check")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_string(cls, v):
        """Convert time strings to time objects."""
        if isinstance(v, str):
            try:
                # Parse HH:MM format
                hour, minute = v.split(":")
                return time(int(hour), int(minute))
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {v}. Expected HH:MM format.")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data and "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v

    # NOTE: Date validation moved to services to support user timezones
    # @field_validator("booking_date")
    # def validate_future_date(cls, v):
    #     """Ensure checking future dates only."""
    #     if v < date.today():
    #         raise ValueError("Cannot check availability for past dates")
    #     return v


class AvailabilityCheckResponse(BaseModel):
    """Response for availability check."""

    available: bool
    reason: Optional[str] = None
    min_advance_hours: Optional[int] = None
    conflicts_with: Optional[List[dict]] = None  # List of conflicting bookings if any


class BookingStatsResponse(StandardizedModel):
    """Booking statistics for instructors."""

    total_bookings: int
    upcoming_bookings: int
    completed_bookings: int
    cancelled_bookings: int
    total_earnings: Money
    this_month_earnings: Money
    average_rating: Optional[float] = None  # For future use


class UpcomingBookingResponse(StandardizedModel):
    """
    Simplified response for upcoming bookings widget.

    Privacy-aware: instructor_last_name shows last initial for students,
    full last name for instructors viewing their own bookings.
    """

    id: str
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    student_first_name: str
    student_last_name: str
    instructor_first_name: str
    instructor_last_name: str  # Last initial for students, full for instructors
    meeting_location: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class UpcomingBookingsListResponse(StandardizedModel):
    """Response for upcoming bookings endpoint - consistent paginated format."""

    bookings: List[UpcomingBookingResponse]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.per_page - 1) // self.per_page


class FindBookingOpportunitiesRequest(BaseModel):
    """
    Request to find available booking opportunities.

    New pattern: Let BookingService find available times based on
    instructor availability and existing bookings.
    """

    instructor_id: str = Field(..., description="Instructor to search")
    instructor_service_id: str = Field(..., description="Service to book")
    date_range_start: date = Field(..., description="Start of search range")
    date_range_end: date = Field(..., description="End of search range")
    preferred_times: Optional[List[time]] = Field(None, description="Preferred start times")

    @field_validator("date_range_end")
    @classmethod
    def validate_date_range(cls, v, info):
        """Ensure valid date range."""
        if info.data.get("date_range_start") and v < info.data["date_range_start"]:
            raise ValueError("End date must be after start date")
        # Limit search to reasonable range
        from datetime import timedelta

        if info.data.get("date_range_start"):
            max_range = info.data["date_range_start"] + timedelta(days=90)
            if v > max_range:
                raise ValueError("Search range cannot exceed 90 days")
        return v


class BookingOpportunity(BaseModel):
    """A single booking opportunity."""

    date: date
    start_time: time
    end_time: time
    available: bool = True


class FindBookingOpportunitiesResponse(BaseModel):
    """Response with available booking opportunities."""

    opportunities: List[BookingOpportunity]
    total_found: int
    search_parameters: dict  # Echo back search params for context
