"""
Tests that immediate auth (<24h) defers to background and emits events.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.booking_service import BookingService


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield


def _bootstrap_instructor_and_service(db: Session) -> tuple[User, InstructorProfile, InstructorService]:
    instructor = User(
        id=str(ulid.ULID()),
        email=f"instructor_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="I",
        last_name="N",
        is_active=True,
        zip_code="10001",
        timezone="UTC",
    )
    db.add(instructor)
    db.flush()

    profile = InstructorProfile(id=str(ulid.ULID()), user_id=instructor.id, years_experience=3)
    db.add(profile)
    db.flush()

    cat = ServiceCategory(id=str(ulid.ULID()), name="Cat", slug=f"cat-{ulid.ULID()}")
    db.add(cat)
    db.flush()

    catalog = ServiceCatalog(id=str(ulid.ULID()), category_id=cat.id, name="Svc", slug=f"svc-{ulid.ULID()}")
    db.add(catalog)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=100.00,
        is_active=True,
        duration_options=[60],
    )
    db.add(svc)
    db.flush()
    return instructor, profile, svc


def _create_student(db: Session) -> User:
    student = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="S",
        last_name="T",
        is_active=True,
        zip_code="10001",
        timezone="UTC",
    )
    db.add(student)
    db.flush()
    return student


def test_confirm_payment_immediate_defers_and_emits_event(db: Session):
    instructor, profile, svc = _bootstrap_instructor_and_service(db)
    student = _create_student(db)

    # Create a PENDING booking within 24h (tomorrow earlier than now's time)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    lesson_utc = now_utc + timedelta(hours=23)
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=lesson_utc.date(),
        start_time=lesson_utc.time().replace(tzinfo=None),
        end_time=(lesson_utc + timedelta(hours=1)).time().replace(tzinfo=None),
        booking_start_utc=lesson_utc,
        booking_end_utc=lesson_utc + timedelta(hours=1),
        lesson_timezone="UTC",
        instructor_tz_at_booking="UTC",
        student_tz_at_booking="UTC",
        service_name="Svc",
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()

    service = BookingService(db)

    def _authorize_now(booking_id: str, _hours_until: float):
        target = db.query(Booking).filter(Booking.id == booking_id).first()
        assert target is not None
        target.payment_status = "authorized"
        target.payment_intent_id = "pi_test"
        db.flush()
        return {"success": True}

    with patch("app.repositories.payment_repository.PaymentRepository.create_payment_event") as mock_event, patch(
        "app.tasks.payment_tasks._process_authorization_for_booking",
        side_effect=_authorize_now,
    ) as mock_authorize:
        updated = service.confirm_booking_payment(booking.id, student=student, payment_method_id="pm_x")

    # Booking moves to CONFIRMED and is authorized immediately
    assert updated.status == BookingStatus.CONFIRMED
    assert updated.payment_status == "authorized"
    mock_authorize.assert_called_once()
    # Event emitted
    mock_event.assert_called()
