"""Integration tests for the pricing preview API endpoint."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.booking import Booking, BookingStatus
from tests.helpers.pricing import (
    instructor_commission_cents,
    instructor_tier_pct,
    student_fee_cents,
)


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
    start_time = time(13, 0)
    end_dt = datetime.combine(date.today(), start_time) + timedelta(minutes=duration_minutes)

    booking = Booking(
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=date.today(),
        start_time=start_time,
        end_time=end_dt.time(),
        service_name="API Test Service",
        hourly_rate=hourly_rate_decimal,
        total_price=total_price,
        duration_minutes=duration_minutes,
        status=status.value,
        location_type="student_home",
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
        f"/api/bookings/{booking.id}/pricing",
        params={"applied_credit_cents": 500},
        headers=auth_headers_student,
    )

    assert response.status_code == 200
    payload = response.json()

    base_price_cents = 10000
    expected_student_fee = student_fee_cents(db, base_price_cents)
    expected_instructor_commission = instructor_commission_cents(db, base_price_cents)
    assert payload["base_price_cents"] == base_price_cents
    assert payload["student_fee_cents"] == expected_student_fee
    assert payload["instructor_commission_cents"] == expected_instructor_commission
    assert payload["credit_applied_cents"] == 500
    expected_student_pay = max(0, base_price_cents + expected_student_fee - 500)
    expected_application_fee = max(
        0, expected_student_fee + expected_instructor_commission - 500
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
        f"/api/bookings/{booking.id}/pricing",
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
        f"/api/bookings/{booking.id}/pricing",
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
        "location_type": "remote",
        "meeting_location": "Online",
        "applied_credit_cents": 0,
    }

    response = client.post("/api/pricing/preview", json=payload, headers=auth_headers_student)

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
        "location_type": "remote",
        "meeting_location": "Online",
        "applied_credit_cents": 0,
    }

    response = client.post("/api/pricing/preview", json=payload, headers=auth_headers_student)

    assert response.status_code == 400
    detail = response.json()
    assert detail.get("code") == "INVALID_START_TIME"
    assert detail.get("errors", {}).get("start_time") == "25:00"
