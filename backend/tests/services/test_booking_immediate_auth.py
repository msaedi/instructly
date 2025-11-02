"""
Tests that immediate auth (<24h) defers to background and emits events.
"""

from datetime import datetime, timedelta
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
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
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
    )
    db.add(student)
    db.flush()
    return student


@pytest.mark.asyncio
async def test_confirm_payment_immediate_defers_and_emits_event(db: Session):
    instructor, profile, svc = _bootstrap_instructor_and_service(db)
    student = _create_student(db)

    # Create a PENDING booking within 24h (tomorrow earlier than now's time)
    now = datetime.now()
    lesson = (now + timedelta(days=1)).replace(hour=max(0, now.hour - 2), minute=0, second=0, microsecond=0)
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=lesson.date(),
        start_time=lesson.time(),
        end_time=(lesson + timedelta(hours=1)).time(),
        service_name="Svc",
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()

    service = BookingService(db)

    with patch("app.repositories.payment_repository.PaymentRepository.create_payment_event") as mock_event:
        updated = await service.confirm_booking_payment(booking.id, student=student, payment_method_id="pm_x")

    # Booking moves to CONFIRMED and payment_status authorizing
    assert updated.status == BookingStatus.CONFIRMED
    assert updated.payment_status == "authorizing"
    # Event emitted
    mock_event.assert_called()
