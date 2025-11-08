"""
Tests for BookingService cancellation policy branches (>24h, 12–24h, <12h).
"""

from datetime import date, datetime, time, timedelta
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


def _create_instructor_with_service(db: Session) -> tuple[User, InstructorProfile, InstructorService]:
    instructor = User(
        id=str(ulid.ULID()),
        email=f"inst_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Inst",
        last_name="Ructor",
        is_active=True,
        zip_code="10001",
    )
    db.add(instructor)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor.id,
        bio="bio",
        years_experience=3,
    )
    db.add(profile)
    db.flush()

    cat = ServiceCategory(id=str(ulid.ULID()), name="Cat", slug=f"cat-{ulid.ULID()}")
    db.add(cat)
    db.flush()

    svc_cat = ServiceCatalog(id=str(ulid.ULID()), category_id=cat.id, name="Svc", slug=f"svc-{ulid.ULID()}")
    db.add(svc_cat)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=svc_cat.id,
        hourly_rate=100.00,
        duration_options=[60],
        is_active=True,
    )
    db.add(svc)
    db.flush()

    return instructor, profile, svc


def _create_student(db: Session) -> User:
    student = User(
        id=str(ulid.ULID()),
        email=f"stud_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Stu",
        last_name="Dent",
        is_active=True,
        zip_code="10001",
    )
    db.add(student)
    db.flush()
    return student


def _create_booking(db: Session, student: User, instructor: User, svc: InstructorService, when: datetime) -> Booking:
    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=when.date(),
        start_time=when.time(),
        end_time=(when + timedelta(hours=1)).time(),
        service_name="Svc",
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        payment_method_id="pm_x",
        payment_intent_id="pi_x",
    )
    db.add(bk)
    db.flush()
    return bk


@pytest.mark.asyncio
async def test_cancel_over_24h_releases_auth(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking 2 days out (>24h)
    when = datetime.combine(date.today() + timedelta(days=2), time(14, 0))
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, patch(
        "app.repositories.payment_repository.PaymentRepository.create_payment_event"
    ) as mock_event:
        result = await service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "released"
    mock_cancel.assert_called_once()
    mock_event.assert_called()


@pytest.mark.asyncio
async def test_cancel_12_24h_capture_reverse_credit(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking ~18 hours out. Avoid crossing midnight which would wrap end_time to 00:00
    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ) as mock_reverse, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_capture.return_value = {"transfer_id": "tr_x", "amount_received": 10000}
        result = await service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "credit_issued"
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()
    mock_credit.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_under_12h_capture_only(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking ~3 hours out. Avoid crossing midnight which would make end_time wrap to 00:00
    # on the same booking_date and violate the DB constraint (start_time < end_time).
    when = datetime.now() + timedelta(hours=3)
    when = when.replace(minute=0, second=0, microsecond=0)
    # If adding one hour crosses the date boundary, push start into next day (01:00)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"amount_received": 10000}
        result = await service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "captured"
    mock_capture.assert_called_once()
