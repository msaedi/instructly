"""Integration tests for the pricing preview API endpoint."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.booking import Booking, BookingStatus
from tests.helpers.pricing import (
    instructor_platform_fee_cents,
    instructor_tier_pct,
    student_fee_cents,
)

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


def _create_booking(
    *,
    db,
    instructor,
    student,
    service,
    hourly_rate: Decimal | float,
    duration_minutes: int = 60,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> Booking:
    """Persist a booking record tailored for API tests."""

    hourly_rate_decimal = Decimal(str(hourly_rate)).quantize(Decimal("0.01"))
    total_price = (
        hourly_rate_decimal * Decimal(duration_minutes) / Decimal(60)
    ).quantize(Decimal("0.01"))
    booking_date = date.today()
    start_time = time(13, 0)
    end_dt = datetime.combine(booking_date, start_time) + timedelta(minutes=duration_minutes)

    booking = Booking(
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_dt.time(),
        **booking_timezone_fields(booking_date, start_time, end_dt.time()),
        service_name="API Test Service",
        hourly_rate=hourly_rate_decimal,
        total_price=total_price,
        duration_minutes=duration_minutes,
        status=status.value,
        location_type="student_location",
    )

    if status is BookingStatus.COMPLETED:
        booking.completed_at = datetime.now(timezone.utc)

    db.add(booking)
    db.flush()
    db.commit()
    db.refresh(booking)
    return booking


@pytest.fixture
def instructor_service(db, test_instructor):
    db.refresh(test_instructor)
    profile = test_instructor.instructor_profile
    assert profile is not None
    db.refresh(profile)
    service = profile.instructor_services[0]
    db.refresh(service)
    return service


def test_pricing_preview_returns_expected_totals(
    client,
    db,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_student,
):
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("100.00"),
    )

    response = client.get(
        f"/api/v1/bookings/{booking.id}/pricing",
        params={"applied_credit_cents": 500},
        headers=auth_headers_student,
    )

    assert response.status_code == 200
    payload = response.json()

    base_price_cents = 10000
    expected_student_fee = student_fee_cents(db, base_price_cents)
    expected_platform_fee = instructor_platform_fee_cents(db, base_price_cents)
    assert payload["base_price_cents"] == base_price_cents
    assert payload["student_fee_cents"] == expected_student_fee
    assert payload["instructor_platform_fee_cents"] == expected_platform_fee
    assert payload["credit_applied_cents"] == 500
    expected_student_pay = max(0, base_price_cents + expected_student_fee - 500)
    expected_application_fee = max(
        0, expected_student_fee + expected_platform_fee - 500
    )
    assert payload["student_pay_cents"] == expected_student_pay
    assert payload["application_fee_cents"] == expected_application_fee
    assert payload["top_up_transfer_cents"] == 0
    tier_pct = instructor_tier_pct(db)
    assert pytest.approx(payload["instructor_tier_pct"], rel=0, abs=1e-6) == float(tier_pct)
    assert any(item["label"].startswith("Booking Protection") for item in payload["line_items"])


def test_pricing_preview_rejects_unauthorized_users(
    client,
    db,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_instructor_2,
):
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("100.00"),
    )

    response = client.get(
        f"/api/v1/bookings/{booking.id}/pricing",
        headers=auth_headers_instructor_2,
    )

    assert response.status_code == 403


def test_pricing_preview_propagates_floor_validation(
    client,
    db,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_student,
    enable_price_floors,
):
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("79.99"),
    )

    response = client.get(
        f"/api/v1/bookings/{booking.id}/pricing",
        headers=auth_headers_student,
    )

    assert response.status_code == 422
    detail = response.json()
    assert detail.get("code") == "PRICE_BELOW_FLOOR"
    message = detail.get("detail")
    if isinstance(message, dict):
        message = message.get("message")
    assert message is not None
    assert "Minimum price for a in-person" in str(message)


def test_quote_preview_rejects_invalid_booking_date(
    client,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_student,
):
    payload = {
        "instructor_id": str(test_instructor.id),
        "instructor_service_id": str(instructor_service.id),
        "booking_date": "2024-13-01",
        "start_time": "10:00",
        "selected_duration": 60,
        "location_type": "online",
        "meeting_location": "Online",
        "applied_credit_cents": 0,
    }

    response = client.post("/api/v1/pricing/preview", json=payload, headers=auth_headers_student)

    assert response.status_code == 400
    detail = response.json()
    assert detail.get("code") == "INVALID_BOOKING_DATE"
    assert detail.get("errors", {}).get("booking_date") == "2024-13-01"


def test_quote_preview_rejects_invalid_start_time(
    client,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_student,
):
    payload = {
        "instructor_id": str(test_instructor.id),
        "instructor_service_id": str(instructor_service.id),
        "booking_date": "2024-05-01",
        "start_time": "25:00",
        "selected_duration": 60,
        "location_type": "online",
        "meeting_location": "Online",
        "applied_credit_cents": 0,
    }

    response = client.post("/api/v1/pricing/preview", json=payload, headers=auth_headers_student)

    assert response.status_code == 400
    detail = response.json()
    assert detail.get("code") == "INVALID_START_TIME"
    assert detail.get("errors", {}).get("start_time") == "25:00"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("booking_date", "2025-13-01", "INVALID_BOOKING_DATE"),
        ("start_time", "25:00", "INVALID_START_TIME"),
    ],
)
def test_quote_rejects_invalid_date_time(
    client,
    test_student,
    test_instructor,
    instructor_service,
    auth_headers_student,
    field,
    value,
    expected_code,
):
    payload = {
        "instructor_id": str(test_instructor.id),
        "instructor_service_id": str(instructor_service.id),
        "booking_date": "2025-05-01",
        "start_time": "11:00",
        "selected_duration": 60,
        "location_type": "student_location",
        "meeting_location": "123 Main St",
        "applied_credit_cents": 0,
    }
    payload[field] = value

    response = client.post("/api/v1/pricing/preview", json=payload, headers=auth_headers_student)

    if response.status_code == 422:
        detail = response.json()
        errors = detail.get("detail", []) if isinstance(detail, dict) else []
        assert any(field in err.get("loc", []) for err in errors), errors
    else:
        assert response.status_code == 400
        detail = response.json()
        assert detail.get("code") == expected_code
        error_details = detail.get("details") or detail.get("errors") or {}
        assert error_details.get(field) == value
