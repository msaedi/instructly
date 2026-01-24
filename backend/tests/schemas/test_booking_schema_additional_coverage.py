"""Additional schema coverage for booking DTOs and validators."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import MappingProxyType, SimpleNamespace

from pydantic import ValidationError
import pytest

from app.models.booking import BookingStatus
from app.schemas.booking import (
    AvailabilityCheckRequest,
    BookingCancel,
    BookingCreate,
    BookingCreateResponse,
    BookingListResponse,
    BookingRescheduleRequest,
    BookingResponse,
    FindBookingOpportunitiesRequest,
    PaymentSummary,
    UpcomingBookingResponse,
    UpcomingBookingsListResponse,
)


def _base_booking_payload() -> dict:
    return {
        "id": "booking-1",
        "student_id": "student-1",
        "instructor_id": "inst-1",
        "instructor_service_id": "service-1",
        "rescheduled_from_booking_id": None,
        "rescheduled_to_booking_id": None,
        "has_locked_funds": None,
        "booking_date": date(2024, 1, 1),
        "start_time": time(9, 0),
        "end_time": time(10, 0),
        "booking_start_utc": datetime(2024, 1, 1, 14, 0, 0),
        "booking_end_utc": datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
        "lesson_timezone": None,
        "instructor_timezone": None,
        "student_timezone": None,
        "service_name": "Guitar",
        "hourly_rate": 40,
        "total_price": 80,
        "duration_minutes": 120,
        "status": BookingStatus.CONFIRMED,
        "service_area": None,
        "meeting_location": None,
        "location_type": "neutral_location",
        "student_note": None,
        "instructor_note": None,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "confirmed_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "cancelled_by_id": None,
        "cancellation_reason": None,
        "no_show_reported_by": None,
        "no_show_reported_at": None,
        "no_show_type": None,
        "no_show_disputed": None,
        "no_show_disputed_at": None,
        "no_show_dispute_reason": None,
        "no_show_resolved_at": None,
        "no_show_resolution": None,
        "settlement_outcome": None,
        "student_credit_amount": True,
        "instructor_payout_amount": None,
        "refunded_to_card_amount": None,
        "credits_reserved_cents": True,
        "auth_scheduled_for": None,
        "auth_attempted_at": None,
        "auth_failure_count": None,
        "auth_last_error": None,
        "locked_at": None,
        "locked_amount_cents": None,
        "lock_resolved_at": None,
        "lock_resolution": None,
        "student": {
            "id": "student-1",
            "first_name": "Ava",
            "last_name": "Taylor",
            "email": "ava@example.com",
        },
        "instructor": {"id": "inst-1", "first_name": "Sam", "last_initial": "L"},
        "instructor_service": {"id": "service-1", "name": "Guitar", "description": None},
        "payment_summary": None,
    }


def test_booking_create_invalid_time_format() -> None:
    with pytest.raises(ValueError, match="Invalid time format"):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="bad",
            selected_duration=60,
        )


def test_booking_create_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=10,
        )

    with pytest.raises(ValidationError):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=721,
        )


def test_booking_create_invalid_timezone() -> None:
    with pytest.raises(ValueError, match="Invalid timezone"):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=60,
            timezone="Mars/Phobos",
        )


def test_booking_create_invalid_location_type() -> None:
    with pytest.raises(ValidationError):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=60,
            location_type="unknown",
        )


def test_booking_create_time_order_validation() -> None:
    with pytest.raises(ValueError, match="End time must be after start time"):
        BookingCreate(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            end_time="09:00",
            selected_duration=60,
        )


def test_booking_create_allows_midnight_end_time() -> None:
    booking = BookingCreate(
        instructor_id="inst",
        instructor_service_id="svc",
        booking_date="2024-01-01",
        start_time="23:00",
        end_time="00:00",
        selected_duration=60,
    )

    assert booking.end_time == time(0, 0)


def test_booking_reschedule_invalid_time_format() -> None:
    with pytest.raises(ValueError, match="Invalid time format"):
        BookingRescheduleRequest(
            booking_date="2024-01-01",
            start_time="bad",
            selected_duration=60,
        )


def test_booking_reschedule_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        BookingRescheduleRequest(
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=5,
        )

    with pytest.raises(ValidationError):
        BookingRescheduleRequest(
            booking_date="2024-01-01",
            start_time="10:00",
            selected_duration=900,
        )


def test_booking_cancel_reason_empty() -> None:
    with pytest.raises(ValueError, match="Cancellation reason cannot be empty"):
        BookingCancel(reason="   ")


def test_booking_response_serializes_naive_utc_and_rescheduled() -> None:
    payload = _base_booking_payload()
    rescheduled_from = SimpleNamespace(
        id="booking-0", booking_date=date(2023, 12, 1), start_time=time(8, 0)
    )
    payload["student"] = SimpleNamespace(
        id="student-1",
        first_name="Ava",
        last_name="Taylor",
        email="ava@example.com",
    )
    payload["instructor"] = SimpleNamespace(
        id="inst-1",
        first_name="Sam",
        last_name="Lee",
    )
    payload["instructor_service"] = SimpleNamespace(
        id="service-1",
        name="Guitar",
        description=None,
    )
    booking = SimpleNamespace(**payload, rescheduled_from=rescheduled_from)
    response = BookingResponse.from_booking(booking)

    dumped = response.model_dump()

    assert dumped["booking_start_utc"].endswith("Z")
    assert response.rescheduled_from is not None
    assert response.credits_reserved_cents is None


def test_booking_response_payment_summary_mapping() -> None:
    payload = _base_booking_payload()
    payment = PaymentSummary(
        lesson_amount=10,
        service_fee=2,
        credit_applied=0,
        subtotal=12,
        tip_amount=0,
        tip_paid=0,
        total_paid=12,
    )
    payload["payment_summary"] = MappingProxyType(payment.model_dump())

    response = BookingResponse(**payload)

    assert response.payment_summary is not None


def test_booking_create_response_properties() -> None:
    payload = _base_booking_payload()
    response = BookingCreateResponse(**payload)

    assert response.is_cancellable is True
    assert response.is_upcoming(date(2023, 12, 31)) is True


def test_booking_list_response_total_pages() -> None:
    response = BookingListResponse(bookings=[], total=10, page=1, per_page=3)
    assert response.total_pages == 4


def test_availability_check_request_time_validation() -> None:
    with pytest.raises(ValueError, match="Invalid time format"):
        AvailabilityCheckRequest(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="bad",
            end_time="10:00",
        )

    with pytest.raises(ValueError, match="End time must be after start time"):
        AvailabilityCheckRequest(
            instructor_id="inst",
            instructor_service_id="svc",
            booking_date="2024-01-01",
            start_time="10:00",
            end_time="09:00",
        )


def test_upcoming_booking_response_coerce_price() -> None:
    class BadAmount:
        def __init__(self) -> None:
            self.amount = "bad"

    response = UpcomingBookingResponse(
        id="booking-1",
        instructor_id="inst",
        booking_date=date(2024, 1, 1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Guitar",
        student_first_name="Ava",
        student_last_name="Taylor",
        instructor_first_name="Sam",
        instructor_last_name="L",
        meeting_location=None,
        total_price=BadAmount(),
    )

    assert response.total_price == 0.0


def test_upcoming_bookings_list_total_pages() -> None:
    response = UpcomingBookingsListResponse(bookings=[], total=11, page=1, per_page=5)
    assert response.total_pages == 3


def test_find_booking_opportunities_date_range_validation() -> None:
    with pytest.raises(ValueError, match="End date must be after start date"):
        FindBookingOpportunitiesRequest(
            instructor_id="inst",
            instructor_service_id="svc",
            date_range_start=date(2024, 1, 10),
            date_range_end=date(2024, 1, 9),
        )

    with pytest.raises(ValueError, match="cannot exceed 90 days"):
        FindBookingOpportunitiesRequest(
            instructor_id="inst",
            instructor_service_id="svc",
            date_range_start=date(2024, 1, 1),
            date_range_end=date(2024, 4, 15),
        )
