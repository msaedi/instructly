from datetime import date, datetime, time, timezone
from decimal import Decimal
import logging
from typing import Any, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ...core.config import settings
from ...domain.video_utils import compute_join_closes_at, compute_join_opens_at
from ...models.booking import BookingStatus
from ...utils.privacy import format_last_initial
from ...utils.safe_cast import safe_float as _safe_float, safe_str as _safe_str
from .._strict_base import StrictModel
from ..base import Money, StandardizedModel
from ..common import LocationTypeLiteral

logger = logging.getLogger(__name__)


class RescheduledFromInfo(StandardizedModel):
    """Minimal info about the original booking used for annotation."""

    id: str
    booking_date: date
    start_time: time


class NoShowReportResponse(StrictModel):
    """Response for reporting a no-show."""

    success: bool
    booking_id: str
    no_show_type: str
    payment_status: str
    dispute_window_ends: str


class NoShowDisputeResponse(StrictModel):
    """Response for disputing a no-show report."""

    success: bool
    booking_id: str
    disputed: bool
    requires_platform_review: bool


class RetryPaymentResponse(StrictModel):
    """Response for retrying payment authorization."""

    success: bool
    payment_status: str
    failure_count: int
    error: Optional[str] = None


class BookingBase(StandardizedModel):
    """Base booking information - self-contained record."""

    id: str
    student_id: str
    instructor_id: str
    instructor_service_id: str
    rescheduled_from_booking_id: Optional[str] = None
    rescheduled_to_booking_id: Optional[str] = None
    has_locked_funds: Optional[bool] = None
    booking_date: date
    start_time: time
    end_time: time
    booking_start_utc: Optional[datetime] = None
    booking_end_utc: Optional[datetime] = None
    lesson_timezone: Optional[str] = None
    instructor_timezone: Optional[str] = None
    student_timezone: Optional[str] = None
    service_name: str
    hourly_rate: Money
    total_price: Money
    duration_minutes: int
    status: BookingStatus
    service_area: Optional[str]
    meeting_location: Optional[str]
    location_type: Optional[LocationTypeLiteral]
    location_address: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_place_id: Optional[str] = None
    student_note: Optional[str]
    instructor_note: Optional[str]
    created_at: datetime
    confirmed_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancelled_by_id: Optional[str]
    cancellation_reason: Optional[str]
    no_show_reported_by: Optional[str] = None
    no_show_reported_at: Optional[datetime] = None
    no_show_type: Optional[str] = None
    no_show_disputed: Optional[bool] = None
    no_show_disputed_at: Optional[datetime] = None
    no_show_dispute_reason: Optional[str] = None
    no_show_resolved_at: Optional[datetime] = None
    no_show_resolution: Optional[str] = None
    settlement_outcome: Optional[str] = None
    student_credit_amount: Optional[int] = None
    instructor_payout_amount: Optional[int] = None
    refunded_to_card_amount: Optional[int] = None
    credits_reserved_cents: Optional[int] = None
    auth_scheduled_for: Optional[datetime] = None
    auth_attempted_at: Optional[datetime] = None
    auth_failure_count: Optional[int] = None
    auth_last_error: Optional[str] = None
    locked_at: Optional[datetime] = None
    locked_amount_cents: Optional[int] = None
    lock_resolved_at: Optional[datetime] = None
    lock_resolution: Optional[str] = None
    video_room_id: Optional[str] = None
    video_session_started_at: Optional[datetime] = None
    video_session_ended_at: Optional[datetime] = None
    video_session_duration_seconds: Optional[int] = None
    video_instructor_joined_at: Optional[datetime] = None
    video_student_joined_at: Optional[datetime] = None
    can_join_lesson: Optional[bool] = None
    join_opens_at: Optional[datetime] = None
    join_closes_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("booking_start_utc", "booking_end_utc")
    def serialize_booking_utc(self, value: Optional[datetime]) -> Optional[str]:
        if value is None or not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class StudentInfo(StandardizedModel):
    """Basic student information for booking display."""

    id: str
    first_name: str
    last_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class StudentInfoPublic(StandardizedModel):
    """Public student information for instructor-facing booking responses."""

    id: str
    first_name: str
    last_initial: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: Any) -> "StudentInfoPublic":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=format_last_initial(getattr(user, "last_name", None), with_period=True),
        )


class InstructorInfo(StandardizedModel):
    """
    Instructor information for booking display.

    Privacy-aware: Only shows last initial for privacy protection.
    """

    id: str
    first_name: str
    last_initial: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: Any) -> "InstructorInfo":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=format_last_initial(getattr(user, "last_name", None), with_period=True),
        )


class BookingServiceInfo(StandardizedModel):
    """Basic service information for booking display."""

    model_config = ConfigDict(from_attributes=True, title="BookingServiceInfo")

    id: str
    name: str
    description: Optional[str]


def _safe_location_type(value: object) -> Optional[str]:
    if isinstance(value, str) and value in (
        "student_location",
        "instructor_location",
        "online",
        "neutral_location",
    ):
        return value
    return "online"


def _safe_datetime(value: object) -> Optional[datetime]:
    return value if isinstance(value, datetime) else None


def _safe_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _safe_bool(value: object) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _extract_satellite_fields(booking: Any) -> dict[str, Any]:
    no_show_detail = getattr(booking, "no_show_detail", None)
    lock_detail = getattr(booking, "lock_detail", None)
    payment_detail = getattr(booking, "payment_detail", None)
    reschedule_detail = getattr(booking, "reschedule_detail", None)
    video_session = getattr(booking, "video_session", None)

    def _payment_value(field_name: str) -> object:
        if payment_detail is not None:
            return getattr(payment_detail, field_name, None)
        return None

    _can_join: bool | None = False if not settings.hundredms_enabled else None
    _opens_at: datetime | None = None
    _closes_at: datetime | None = None
    _location = getattr(booking, "location_type", None)
    _status = getattr(booking, "status", None)
    _start = getattr(booking, "booking_start_utc", None)
    _end = getattr(booking, "booking_end_utc", None)
    _duration = getattr(booking, "duration_minutes", None)
    if settings.hundredms_enabled and (
        _location == "online"
        and _status == BookingStatus.CONFIRMED.value
        and isinstance(_start, datetime)
        and isinstance(_duration, (int, float))
    ):
        _opens_at = compute_join_opens_at(_start)
        _closes_at = compute_join_closes_at(
            _start,
            int(_duration),
            _end if isinstance(_end, datetime) else None,
        )
        _now = datetime.now(timezone.utc)
        _can_join = _opens_at <= _now <= _closes_at

    rescheduled_from_booking_id_raw = getattr(booking, "rescheduled_from_booking_id", None)

    return {
        "rescheduled_from_booking_id": rescheduled_from_booking_id_raw
        if isinstance(rescheduled_from_booking_id_raw, str)
        else None,
        "rescheduled_to_booking_id": _safe_str(
            getattr(reschedule_detail, "rescheduled_to_booking_id", None)
        ),
        "has_locked_funds": _safe_bool(getattr(booking, "has_locked_funds", None)),
        "booking_start_utc": _safe_datetime(getattr(booking, "booking_start_utc", None)),
        "booking_end_utc": _safe_datetime(getattr(booking, "booking_end_utc", None)),
        "lesson_timezone": _safe_str(getattr(booking, "lesson_timezone", None)),
        "instructor_timezone": _safe_str(getattr(booking, "instructor_tz_at_booking", None)),
        "student_timezone": _safe_str(getattr(booking, "student_tz_at_booking", None)),
        "service_area": _safe_str(getattr(booking, "service_area", None)),
        "meeting_location": _safe_str(getattr(booking, "meeting_location", None)),
        "location_type": _safe_location_type(getattr(booking, "location_type", None)),
        "location_address": _safe_str(getattr(booking, "location_address", None)),
        "location_lat": _safe_float(getattr(booking, "location_lat", None)),
        "location_lng": _safe_float(getattr(booking, "location_lng", None)),
        "location_place_id": _safe_str(getattr(booking, "location_place_id", None)),
        "student_note": _safe_str(getattr(booking, "student_note", None)),
        "instructor_note": _safe_str(getattr(booking, "instructor_note", None)),
        "no_show_reported_by": _safe_str(getattr(no_show_detail, "no_show_reported_by", None)),
        "no_show_reported_at": _safe_datetime(getattr(no_show_detail, "no_show_reported_at", None)),
        "no_show_type": _safe_str(getattr(no_show_detail, "no_show_type", None)),
        "no_show_disputed": _safe_bool(getattr(no_show_detail, "no_show_disputed", None)),
        "no_show_disputed_at": _safe_datetime(getattr(no_show_detail, "no_show_disputed_at", None)),
        "no_show_dispute_reason": _safe_str(
            getattr(no_show_detail, "no_show_dispute_reason", None)
        ),
        "no_show_resolved_at": _safe_datetime(getattr(no_show_detail, "no_show_resolved_at", None)),
        "no_show_resolution": _safe_str(getattr(no_show_detail, "no_show_resolution", None)),
        "settlement_outcome": _safe_str(_payment_value("settlement_outcome")),
        "student_credit_amount": _safe_int(getattr(booking, "student_credit_amount", None)),
        "instructor_payout_amount": _safe_int(_payment_value("instructor_payout_amount")),
        "refunded_to_card_amount": _safe_int(getattr(booking, "refunded_to_card_amount", None)),
        "credits_reserved_cents": _safe_int(_payment_value("credits_reserved_cents")),
        "auth_scheduled_for": _safe_datetime(_payment_value("auth_scheduled_for")),
        "auth_attempted_at": _safe_datetime(_payment_value("auth_attempted_at")),
        "auth_failure_count": _safe_int(_payment_value("auth_failure_count")),
        "auth_last_error": _safe_str(_payment_value("auth_last_error")),
        "locked_at": _safe_datetime(getattr(lock_detail, "locked_at", None)),
        "locked_amount_cents": _safe_int(getattr(lock_detail, "locked_amount_cents", None)),
        "lock_resolved_at": _safe_datetime(getattr(lock_detail, "lock_resolved_at", None)),
        "lock_resolution": _safe_str(getattr(lock_detail, "lock_resolution", None)),
        "video_room_id": _safe_str(getattr(video_session, "room_id", None)),
        "video_session_started_at": _safe_datetime(
            getattr(video_session, "session_started_at", None)
        ),
        "video_session_ended_at": _safe_datetime(getattr(video_session, "session_ended_at", None)),
        "video_session_duration_seconds": _safe_int(
            getattr(video_session, "session_duration_seconds", None)
        ),
        "video_instructor_joined_at": _safe_datetime(
            getattr(video_session, "instructor_joined_at", None)
        ),
        "video_student_joined_at": _safe_datetime(
            getattr(video_session, "student_joined_at", None)
        ),
        "can_join_lesson": _can_join,
        "join_opens_at": _opens_at,
        "join_closes_at": _closes_at,
    }


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


def _build_booking_response_data(
    booking: Any,
    *,
    student_info: StudentInfo | StudentInfoPublic | None,
    payment_summary: Optional[PaymentSummary] = None,
    instructor_service_info: Optional["BookingServiceInfo"] = None,
) -> dict[str, Any]:
    satellite = _extract_satellite_fields(booking)
    response_data = {
        "id": booking.id,
        "student_id": booking.student_id,
        "instructor_id": booking.instructor_id,
        "instructor_service_id": booking.instructor_service_id,
        "booking_date": booking.booking_date,
        "start_time": booking.start_time,
        "end_time": booking.end_time,
        "service_name": booking.service_name,
        "hourly_rate": booking.hourly_rate,
        "total_price": booking.total_price,
        "duration_minutes": booking.duration_minutes,
        "status": booking.status,
        "created_at": booking.created_at,
        "confirmed_at": booking.confirmed_at,
        "completed_at": booking.completed_at,
        "cancelled_at": booking.cancelled_at,
        "cancelled_by_id": booking.cancelled_by_id,
        "cancellation_reason": booking.cancellation_reason,
        "student": student_info,
        "instructor": InstructorInfo.from_user(booking.instructor) if booking.instructor else None,
        "instructor_service": instructor_service_info
        or (
            BookingServiceInfo.model_validate(booking.instructor_service)
            if booking.instructor_service
            else None
        ),
        "rescheduled_from": None,
        **satellite,
    }

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
        response_data["rescheduled_from"] = None

    response_data["payment_summary"] = payment_summary
    return response_data


class BookingResponseBase(BookingBase):
    """
    Shared booking response fields for audience-specific DTOs.
    """

    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    instructor: InstructorInfo
    instructor_service: BookingServiceInfo
    rescheduled_from: Optional["RescheduledFromInfo"] = None
    payment_summary: Optional[PaymentSummary] = None

    @field_validator("rescheduled_from", mode="before")
    @classmethod
    def _validate_rescheduled_from(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        return v

    @field_validator("payment_summary", mode="before")
    @classmethod
    def _validate_payment_summary(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        return v


class BookingResponse(BookingResponseBase):
    """Complete booking response with privacy protection."""

    student: StudentInfo

    @classmethod
    def from_booking(
        cls, booking: Any, payment_summary: Optional[PaymentSummary] = None
    ) -> "BookingResponse":
        return cls(
            **_build_booking_response_data(
                booking,
                student_info=StudentInfo.model_validate(booking.student)
                if booking.student
                else None,
                payment_summary=payment_summary,
            )
        )


class InstructorBookingResponse(BookingResponseBase):
    """Instructor-facing booking response with public student identity only."""

    student: StudentInfoPublic

    @classmethod
    def from_booking(
        cls, booking: Any, payment_summary: Optional[PaymentSummary] = None
    ) -> "InstructorBookingResponse":
        return cls(
            **_build_booking_response_data(
                booking,
                student_info=StudentInfoPublic.from_user(booking.student)
                if booking.student
                else None,
                payment_summary=payment_summary,
            )
        )


class BookingCreateResponse(BookingResponse):
    """
    Response after creating a booking with payment setup.
    """

    setup_intent_client_secret: Optional[str] = Field(
        None, description="Stripe SetupIntent client_secret for collecting payment method"
    )
    requires_payment_method: bool = Field(
        True, description="Whether payment method is required before confirmation"
    )

    @property
    def is_cancellable(self) -> bool:
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    def is_upcoming(self, user_today: date) -> bool:
        return self.booking_date > user_today and self.status == BookingStatus.CONFIRMED

    @classmethod
    def from_booking(
        cls,
        booking: Any,
        payment_summary: Optional[PaymentSummary] = None,
        setup_intent_client_secret: Optional[str] = None,
    ) -> "BookingCreateResponse":
        response_data = _build_booking_response_data(
            booking,
            student_info=StudentInfo.model_validate(booking.student) if booking.student else None,
            payment_summary=payment_summary,
            instructor_service_info=BookingServiceInfo(
                id=booking.instructor_service.id
                if booking.instructor_service
                else booking.instructor_service_id,
                name=booking.service_name,
                description=booking.instructor_service.description
                if booking.instructor_service
                else None,
            ),
        )
        response_data["setup_intent_client_secret"] = setup_intent_client_secret or getattr(
            booking,
            "setup_intent_client_secret",
            None,
        )
        response_data["requires_payment_method"] = True
        return cls(**response_data)


class BookingListResponse(StandardizedModel):
    """Response for booking list endpoints."""

    bookings: List[BookingResponse]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page


class BookingStatsResponse(StandardizedModel):
    """Booking statistics for instructors."""

    total_bookings: int
    upcoming_bookings: int
    completed_bookings: int
    cancelled_bookings: int
    total_earnings: Money
    this_month_earnings: Money
    average_rating: Optional[float] = None


class UpcomingBookingResponse(StandardizedModel):
    """
    Simplified response for upcoming bookings widget.
    """

    id: str
    instructor_id: str
    booking_date: date
    start_time: time
    end_time: time
    service_name: str
    student_first_name: str
    student_last_initial: str
    instructor_first_name: str
    instructor_last_name: str
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
        if hasattr(v, "amount"):
            try:
                return float(v.amount)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)

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
        return (self.total + self.per_page - 1) // self.per_page
