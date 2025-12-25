# backend/app/schemas/booking.py
"""
Booking schemas for InstaInstru platform.

Clean Architecture: Bookings are completely self-contained with their own
date/time information. No references to availability slots. This implements
the "Rug and Person" principle where bookings persist independently of
availability changes.
"""

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..models.booking import BookingStatus
from ..schemas.base import STRICT_SCHEMAS, Money, StandardizedModel
from ._strict_base import StrictModel, StrictRequestModel

DATE_ONLY_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ensure_date_only(value: object, field_name: str) -> object:
    if isinstance(value, str):
        candidate = value.strip()
        if not DATE_ONLY_REGEX.fullmatch(candidate):
            raise ValueError(f"{field_name} must be a YYYY-MM-DD date-only string")
        return candidate
    return value


class RescheduledFromInfo(StandardizedModel):
    """Minimal info about the original booking used for annotation."""

    id: str
    booking_date: date
    start_time: time


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
    start_time: time = Field(..., description="Start time")
    selected_duration: int = Field(
        ...,
        ge=15,
        le=720,
        description="Selected duration in minutes from service's duration_options",
    )
    student_note: Optional[str] = Field(
        None, max_length=1000, description="Optional note from student"
    )
    meeting_location: Optional[str] = Field(
        None, description="Specific meeting location if applicable"
    )
    location_type: Optional[
        Literal["student_home", "instructor_location", "neutral", "remote", "in_person"]
    ] = Field("neutral", description="Type of meeting location")

    # Note: end_time is calculated from start_time + selected_duration
    end_time: Optional[time] = Field(None, description="Calculated end time (set automatically)")

    @field_validator("booking_date", mode="before")
    @classmethod
    def _enforce_date_only(cls, v: object) -> object:
        return _ensure_date_only(v, "booking_date")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time_string(cls, v: object) -> object:
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
    def validate_duration(cls, v: int) -> int:
        """Ensure duration is within reasonable bounds."""
        if v < 15:
            raise ValueError("Duration must be at least 15 minutes")
        if v > 720:  # 12 hours
            raise ValueError("Duration cannot exceed 12 hours")
        return v

    # NOTE: Date validation moved to services to support user timezones
    # @field_validator("booking_date")
    # @classmethod
    # def validate_future_date(cls, v: date) -> date:
    #     """Ensure booking is for future date."""
    #     if v < date.today():
    #         raise ValueError("Cannot book for past dates")
    #     return v

    @field_validator("student_note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        """Clean up the student note."""
        return v.strip() if v else v

    @field_validator("location_type")
    @classmethod
    def validate_location_type(cls, v: Optional[str]) -> str:
        """Ensure location type is valid."""
        valid_types = [
            "student_home",
            "instructor_location",
            "neutral",
            "remote",
            "in_person",
        ]
        if v and v not in valid_types:
            raise ValueError(f"location_type must be one of {valid_types}")
        return v or "neutral"

    @model_validator(mode="after")
    def validate_time_order(self) -> "BookingCreate":
        """Ensure end_time is after start_time and calculate if needed."""
        if self.end_time is None and self.start_time and self.selected_duration:
            # Calculate end_time from start_time + duration
            # Use a reference date for time calculation (this is just for math, not timezone-specific)
            reference_date = date(2024, 1, 1)
            start_datetime = datetime.combine(reference_date, self.start_time, tzinfo=timezone.utc)
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

    Frontend will subsequently create a new booking; this endpoint prepares the system by
    cancelling the old booking according to policy and recording audit events.
    """

    booking_date: date = Field(..., description="New date for the lesson")
    start_time: time = Field(..., description="New start time (HH:MM)")
    selected_duration: int = Field(
        ..., ge=15, le=720, description="New selected duration in minutes"
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
        if v < 15:
            raise ValueError("Duration must be at least 15 minutes")
        if v > 720:
            raise ValueError("Duration cannot exceed 12 hours")
        return v


class BookingConfirmPayment(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Confirm payment method for a booking after SetupIntent completion.

    Used in the two-step booking flow:
    1. Create booking (returns SetupIntent client_secret)
    2. Confirm payment (this schema) after card details collected
    """

    payment_method_id: str = Field(
        ..., description="Stripe payment method ID from completed SetupIntent"
    )
    save_payment_method: bool = Field(
        False, description="Whether to save this payment method for future use"
    )


class BookingUpdate(StrictRequestModel):
    """
    Schema for updating booking details.

    Limited fields can be updated after booking creation.
    """

    instructor_note: Optional[str] = Field(None, max_length=1000)
    meeting_location: Optional[str] = None

    @field_validator("instructor_note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        """Clean up the instructor note."""
        return v.strip() if v else v


class BookingCancel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Schema for cancelling a booking."""

    reason: str = Field(..., min_length=1, max_length=500, description="Cancellation reason")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v: str) -> str:
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
    # If this booking was created by rescheduling another booking
    rescheduled_from_booking_id: Optional[str] = None

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
    def from_user(cls, user: Any) -> "InstructorInfo":
        """
        Factory method to create InstructorInfo from User model.
        Ensures privacy by only exposing last initial.
        """
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else "",
        )


class ServiceInfo(StandardizedModel):
    """Basic service information for booking display."""

    id: str
    name: str  # From catalog
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class PaymentSummary(StandardizedModel):
    """Student-facing payment breakdown for a booking."""

    lesson_amount: Money
    service_fee: Money
    credit_applied: Money
    subtotal: Money
    tip_amount: Money
    tip_paid: Money
    total_paid: Money
    tip_status: Optional[str] = None
    tip_last_updated: Optional[datetime] = None


class BookingResponse(BookingBase):
    """
    Complete booking response with privacy protection.

    Shows instructor as "FirstName L" (last initial only).
    Students see their own full information.
    Clean Architecture: No availability slot references.
    """

    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    student: StudentInfo  # Students see their own full info
    instructor: InstructorInfo  # Privacy-aware: only has last_initial
    instructor_service: ServiceInfo
    # Minimal info to display "Rescheduled from ..." on detail page
    rescheduled_from: Optional["RescheduledFromInfo"] = None
    payment_summary: Optional[PaymentSummary] = None

    @field_validator("payment_summary", mode="before")
    @classmethod
    def _validate_payment_summary(cls, v: Any) -> Any:
        """
        Normalize payment_summary to a dict before Pydantic validates it.

        This is critical for test stability: when test modules reload
        app.schemas.booking, the PaymentSummary class identity changes.
        If we returned PaymentSummary instances here, they might be from
        the OLD module while Pydantic validates against the NEW module's
        PaymentSummary type annotation, causing 422 errors.

        By always returning a dict (for non-None values), we let Pydantic
        handle the dict->PaymentSummary conversion using the correct class.
        """
        if v is None:
            return None
        # Already a dict - return as-is for Pydantic to handle
        if isinstance(v, dict):
            return v
        # Any BaseModel (including PaymentSummary from any module version)
        # -> convert to dict so Pydantic uses the correct class
        if isinstance(v, BaseModel):
            return v.model_dump()
        # Mapping types -> convert to dict
        if isinstance(v, Mapping):
            return dict(v)
        # Unknown type - return as-is and let Pydantic decide
        return v

    @classmethod
    def from_booking(
        cls, booking: Any, payment_summary: Optional[PaymentSummary] = None
    ) -> "BookingResponse":
        """
        Create BookingResponse from Booking ORM model.
        Handles privacy transformation automatically.
        """

        # Build the response with proper privacy protection
        # Defensive getters for possibly mocked attributes in tests
        def _safe_str(value: object) -> Optional[str]:
            return value if isinstance(value, str) else None

        def _safe_location_type(value: object) -> Optional[str]:
            if isinstance(value, str) and value in [
                "student_home",
                "instructor_location",
                "neutral",
            ]:
                return value
            return "neutral"

        rescheduled_from_booking_id_value = getattr(booking, "rescheduled_from_booking_id", None)

        response_data = {
            # Base fields from BookingBase
            "id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "instructor_service_id": booking.instructor_service_id,
            "rescheduled_from_booking_id": rescheduled_from_booking_id_value
            if isinstance(rescheduled_from_booking_id_value, str)
            else None,
            # Booking details
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "service_name": booking.service_name,
            "hourly_rate": booking.hourly_rate,
            "total_price": booking.total_price,
            "duration_minutes": booking.duration_minutes,
            "status": booking.status,
            # Location
            "service_area": _safe_str(getattr(booking, "service_area", None)),
            "meeting_location": _safe_str(getattr(booking, "meeting_location", None)),
            "location_type": _safe_location_type(getattr(booking, "location_type", None)),
            # Notes
            "student_note": _safe_str(getattr(booking, "student_note", None)),
            "instructor_note": _safe_str(getattr(booking, "instructor_note", None)),
            # Timestamps
            "created_at": booking.created_at,
            "confirmed_at": booking.confirmed_at,
            "completed_at": booking.completed_at,
            "cancelled_at": booking.cancelled_at,
            # Cancellation info
            "cancelled_by_id": booking.cancelled_by_id,
            "cancellation_reason": booking.cancellation_reason,
            # Privacy-protected nested objects
            "student": StudentInfo.model_validate(booking.student) if booking.student else None,
            "instructor": InstructorInfo.from_user(booking.instructor)
            if booking.instructor
            else None,
            "instructor_service": ServiceInfo.model_validate(booking.instructor_service)
            if booking.instructor_service
            else None,
            # Nested minimal info for annotation
            "rescheduled_from": None,
        }

        # Safely include minimal reschedule info only when real values are present
        try:
            res_from = getattr(booking, "rescheduled_from", None)
            if (
                res_from is not None
                and isinstance(getattr(res_from, "id", None), str)
                and isinstance(getattr(res_from, "booking_date", None), date)
                and isinstance(getattr(res_from, "start_time", None), time)
            ):
                response_data["rescheduled_from"] = RescheduledFromInfo(
                    id=res_from.id,
                    booking_date=res_from.booking_date,
                    start_time=res_from.start_time,
                )
        except Exception:
            # If anything is off (e.g., mocks), omit the optional annotation
            response_data["rescheduled_from"] = None

        response_data["payment_summary"] = payment_summary

        return cls(**response_data)


class BookingCreateResponse(BookingResponse):
    """
    Response after creating a booking with payment setup.

    Includes SetupIntent client_secret for collecting payment method.
    """

    setup_intent_client_secret: Optional[str] = Field(
        None, description="Stripe SetupIntent client_secret for collecting payment method"
    )
    requires_payment_method: bool = Field(
        True, description="Whether payment method is required before confirmation"
    )

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
    def from_booking(
        cls,
        booking: Any,
        payment_summary: Optional[PaymentSummary] = None,
        setup_intent_client_secret: Optional[str] = None,
    ) -> "BookingCreateResponse":
        """
        Create BookingCreateResponse from Booking ORM model.
        Inherits privacy protection from parent and adds payment setup fields.
        """
        # Use the parent's from_booking method to build base response
        response_data = {
            # Base fields from BookingBase
            "id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "instructor_service_id": booking.instructor_service_id,
            # Booking details
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "service_name": booking.service_name,
            "hourly_rate": booking.hourly_rate,
            "total_price": booking.total_price,
            "duration_minutes": booking.duration_minutes,
            "status": booking.status,
            # Location
            "service_area": booking.service_area,
            "meeting_location": booking.meeting_location,
            "location_type": booking.location_type,
            # Notes
            "student_note": booking.student_note,
            "instructor_note": booking.instructor_note,
            # Timestamps
            "created_at": booking.created_at,
            "confirmed_at": booking.confirmed_at,
            "completed_at": booking.completed_at,
            "cancelled_at": booking.cancelled_at,
            # Cancellation info
            "cancelled_by_id": booking.cancelled_by_id,
            "cancellation_reason": booking.cancellation_reason,
            # Related objects with privacy protection
            "instructor": InstructorInfo.from_user(booking.instructor),
            "student": StudentInfo(
                id=booking.student.id,
                first_name=booking.student.first_name,
                last_name=booking.student.last_name,
                email=booking.student.email,
            ),
            "instructor_service": ServiceInfo(
                id=booking.instructor_service.id
                if booking.instructor_service
                else booking.instructor_service_id,
                name=booking.service_name,  # Use denormalized name
                description=booking.instructor_service.description
                if booking.instructor_service
                else None,
            ),
            # Payment setup fields
            "setup_intent_client_secret": setup_intent_client_secret
            or getattr(booking, "setup_intent_client_secret", None),
            "requires_payment_method": True,
            "payment_summary": payment_summary,
        }

        return cls(**response_data)


class BookingPaymentMethodUpdate(StrictRequestModel):
    """
    Request to update a booking's payment method, with optional default flag.
    """

    payment_method_id: str = Field(..., description="Stripe payment method ID")
    set_as_default: bool = Field(False, description="Whether to save as default for the student")


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


class AvailabilityCheckRequest(StrictRequestModel):
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
    def parse_time_string(cls, v: object) -> object:
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
    def validate_time_order(cls, v: time, info: Any) -> time:
        """Ensure end time is after start time."""
        if (
            isinstance(getattr(info, "data", None), dict)
            and "start_time" in info.data
            and v <= info.data["start_time"]
        ):
            raise ValueError("End time must be after start time")
        return v

    @field_validator("booking_date", mode="before")
    @classmethod
    def _enforce_date_only(cls, v: object) -> object:
        return _ensure_date_only(v, "booking_date")

    # NOTE: Date validation moved to services to support user timezones
    # @field_validator("booking_date")
    # def validate_future_date(cls, v):
    #     """Ensure checking future dates only."""
    #     if v < date.today():
    #         raise ValueError("Cannot check availability for past dates")
    #     return v


class AvailabilityCheckResponse(StrictModel):
    """Response for availability check."""

    available: bool
    reason: Optional[str] = None
    min_advance_hours: Optional[int] = None
    conflicts_with: Optional[List[Dict[str, Any]]] = None  # List of conflicting bookings if any
    # Optional metadata sometimes included by handlers; keep optional to preserve strictness
    time_info: Optional[Dict[str, Any]] = None


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
    instructor_id: str
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    student_first_name: str
    student_last_name: str
    instructor_first_name: str
    instructor_last_name: str  # Last initial for students, full for instructors
    meeting_location: Optional[str]
    total_price: float

    model_config = ConfigDict(from_attributes=True)

    @field_validator("total_price", mode="before")
    @classmethod
    def _coerce_price(cls, v: object) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        # Money-like objects
        if hasattr(v, "amount"):
            try:
                return float(v.amount)
            except Exception:
                pass
        from decimal import Decimal

        try:
            return float(Decimal(str(v)))
        except Exception:
            return 0.0


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


class FindBookingOpportunitiesRequest(StrictRequestModel):
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
    def validate_date_range(cls, v: date, info: Any) -> date:
        """Ensure valid date range."""
        if (
            isinstance(getattr(info, "data", None), dict)
            and info.data.get("date_range_start")
            and v < info.data["date_range_start"]
        ):
            raise ValueError("End date must be after start date")
        # Limit search to reasonable range
        from datetime import timedelta

        if isinstance(getattr(info, "data", None), dict) and info.data.get("date_range_start"):
            max_range = info.data["date_range_start"] + timedelta(days=90)
            if v > max_range:
                raise ValueError("Search range cannot exceed 90 days")
        return v

    if STRICT_SCHEMAS:

        @field_validator("date_range_start", "date_range_end", mode="before")
        @classmethod
        def _strict_date_range_only(cls, v: object) -> object:  # pragma: no cover
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


class FindBookingOpportunitiesResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response with available booking opportunities."""

    opportunities: List[BookingOpportunity]
    total_found: int
    search_parameters: Dict[str, Any]


__all__ = [
    "BookingStatus",
]
