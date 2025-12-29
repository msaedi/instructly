"""Integration tests for UTC boundary handling in cancellation logic."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.booking import BookingStatus, PaymentStatus
from app.models.user import User
from app.services.booking_service import BookingService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_booking(db: Session, *, student: User, instructor: User) -> str:
    start_dt = datetime.now(timezone.utc) + timedelta(days=2)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=(start_dt + timedelta(hours=1)).time(),
        service_name="Boundary Test",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_boundary",
    )
    db.commit()
    return booking.id


def _scenario_for_hours(
    db: Session,
    booking_service: BookingService,
    booking_id: str,
    student: User,
    monkeypatch: pytest.MonkeyPatch,
    hours_until: float,
) -> str:
    from app.services.timezone_service import TimezoneService

    monkeypatch.setattr(TimezoneService, "hours_until", lambda _dt: hours_until)
    booking = booking_service.repository.get_by_id(booking_id)
    assert booking is not None
    ctx = booking_service._build_cancellation_context(booking, student)
    return ctx["scenario"]


def test_exactly_24h_is_gte24h_bucket(
    db: Session, test_student: User, test_instructor: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)
    scenario = _scenario_for_hours(
        db, booking_service, booking_id, test_student, monkeypatch, 24.0
    )
    assert scenario == "over_24h_regular"


def test_23h59m_is_12_to_24h_bucket(
    db: Session, test_student: User, test_instructor: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)
    scenario = _scenario_for_hours(
        db, booking_service, booking_id, test_student, monkeypatch, 23.99
    )
    assert scenario == "between_12_24h"


def test_exactly_12h_is_12_to_24h_bucket(
    db: Session, test_student: User, test_instructor: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)
    scenario = _scenario_for_hours(
        db, booking_service, booking_id, test_student, monkeypatch, 12.0
    )
    assert scenario == "between_12_24h"


def test_11h59m_is_lt12h_bucket(
    db: Session, test_student: User, test_instructor: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)
    scenario = _scenario_for_hours(
        db, booking_service, booking_id, test_student, monkeypatch, 11.99
    )
    assert scenario == "under_12h"
