"""
Integration tests for LOCK activation on scheduled bookings (v2.1.1).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.core.exceptions import BusinessRuleException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.services.booking_service import BookingService


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

    svc_cat = ServiceCatalog(
        id=str(ulid.ULID()), category_id=cat.id, name="Svc", slug=f"svc-{ulid.ULID()}"
    )
    db.add(svc_cat)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=svc_cat.id,
        hourly_rate=120.00,
        duration_options=[60],
        is_active=True,
    )
    db.add(svc)
    db.flush()

    connected = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        stripe_account_id="acct_test",
        onboarding_completed=True,
    )
    db.add(connected)
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


def _create_stripe_customer(db: Session, user_id: str) -> None:
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(user_id, f"cus_{ulid.ULID()}")


def _create_booking(
    db: Session,
    student: User,
    instructor: User,
    svc: InstructorService,
    when: datetime,
    *,
    payment_status: str = "scheduled",
    payment_intent_id: str | None = None,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> Booking:
    start_at = when.astimezone(timezone.utc)
    end_at = start_at + timedelta(hours=1)
    if end_at.date() != start_at.date():
        start_at = start_at - timedelta(hours=1)
        end_at = start_at + timedelta(hours=1)
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=start_at.date(),
        start_time=start_at.time().replace(tzinfo=None),
        end_time=end_at.time().replace(tzinfo=None),
        booking_start_utc=start_at,
        booking_end_utc=end_at,
        lesson_timezone="UTC",
        instructor_tz_at_booking="UTC",
        student_tz_at_booking="UTC",
        service_name="Svc",
        hourly_rate=svc.hourly_rate,
        total_price=svc.hourly_rate,
        duration_minutes=60,
        status=status,
        meeting_location="Test",
        location_type="neutral",
        payment_method_id="pm_test",
        payment_intent_id=payment_intent_id,
        payment_status=payment_status,
    )
    db.add(booking)
    db.flush()
    return booking


def _mock_charge_context() -> SimpleNamespace:
    return SimpleNamespace(
        student_pay_cents=13440,
        application_fee_cents=2880,
        applied_credit_cents=0,
        base_price_cents=12000,
    )


def test_scheduled_booking_in_12_24h_triggers_lock(db: Session) -> None:
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=18)
    booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="scheduled",
        payment_intent_id=None,
    )
    _create_stripe_customer(db, student.id)

    service = BookingService(db)

    with patch(
        "app.services.stripe_service.StripeService.build_charge_context",
        return_value=_mock_charge_context(),
    ), patch(
        "app.services.stripe_service.StripeService.create_or_retry_booking_payment_intent",
        return_value=SimpleNamespace(id="pi_auth"),
    ), patch(
        "app.services.stripe_service.StripeService.capture_payment_intent",
        return_value={
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        },
    ) as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer",
        return_value={"reversal": {"id": "trr_test"}},
    ) as mock_reverse:
        service.activate_lock_for_reschedule(booking.id)

    db.refresh(booking)
    assert booking.payment_status == "locked"
    assert booking.payment_intent_id == "pi_auth"
    assert booking.locked_at is not None
    assert booking.locked_amount_cents == 13440
    assert booking.late_reschedule_used is True
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()


def test_scheduled_booking_auth_failure_blocks_lock(db: Session) -> None:
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=18)
    booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="scheduled",
        payment_intent_id=None,
    )
    _create_stripe_customer(db, student.id)

    service = BookingService(db)

    with patch(
        "app.services.stripe_service.StripeService.build_charge_context",
        return_value=_mock_charge_context(),
    ), patch(
        "app.services.stripe_service.StripeService.create_or_retry_booking_payment_intent",
        side_effect=Exception("auth_failed"),
    ), patch(
        "app.tasks.payment_tasks.check_immediate_auth_timeout.apply_async"
    ) as mock_retry, patch(
        "app.services.stripe_service.StripeService.capture_payment_intent"
    ) as mock_capture:
        with pytest.raises(BusinessRuleException):
            service.activate_lock_for_reschedule(booking.id)

    db.refresh(booking)
    assert booking.payment_status == "payment_method_required"
    mock_capture.assert_not_called()
    mock_retry.assert_called()


def test_authorized_booking_in_12_24h_still_triggers_lock(db: Session) -> None:
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=18)
    booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="authorized",
        payment_intent_id="pi_auth",
    )

    service = BookingService(db)

    with patch(
        "app.services.stripe_service.StripeService.capture_payment_intent",
        return_value={
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        },
    ) as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer",
        return_value={"reversal": {"id": "trr_test"}},
    ) as mock_reverse:
        service.activate_lock_for_reschedule(booking.id)

    db.refresh(booking)
    assert booking.payment_status == "locked"
    assert booking.locked_at is not None
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()
