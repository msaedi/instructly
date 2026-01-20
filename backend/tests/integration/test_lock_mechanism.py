"""
Integration tests for Phase 2 LOCK anti-gaming mechanism (v2.1.1).
"""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.booking import BookingCreate
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
        offers_travel=True,
        offers_at_location=True,
        offers_online=True,
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


def _create_booking(
    db: Session,
    student: User,
    instructor: User,
    svc: InstructorService,
    when: datetime,
    *,
    payment_status: str = "authorized",
    payment_intent_id: str | None = "pi_test",
    has_locked_funds: bool = False,
    rescheduled_from_id: str | None = None,
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
        location_type="neutral_location",
        payment_method_id="pm_test",
        payment_intent_id=payment_intent_id,
        payment_status=payment_status,
        has_locked_funds=has_locked_funds,
        rescheduled_from_booking_id=rescheduled_from_id,
    )
    db.add(booking)
    db.flush()
    return booking


@pytest.mark.parametrize(
    "hours_until,initiated_by,payment_status,expected",
    [
        (18, "student", "authorized", True),
        (30, "student", "authorized", False),
        (8, "student", "authorized", False),
        (18, "instructor", "authorized", False),
        (18, "student", "scheduled", True),
    ],
)
def test_should_trigger_lock(hours_until, initiated_by, payment_status, expected, db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=hours_until)
    booking = _create_booking(db, student, instructor, svc, when, payment_status=payment_status)

    service = BookingService(db)
    assert service.should_trigger_lock(booking, initiated_by) is expected


def test_lock_activation_captures_and_reverses(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=18)
    booking = _create_booking(db, student, instructor, svc, when, payment_status="authorized")

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ) as mock_reverse:
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        service.activate_lock_for_reschedule(booking.id)

    db.refresh(booking)
    assert booking.payment_status == "locked"
    assert booking.locked_at is not None
    assert booking.locked_amount_cents == 13440
    mock_reverse.assert_called_once()


def test_lock_activation_idempotent_when_already_locked(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=18)
    booking = _create_booking(db, student, instructor, svc, when, payment_status="locked")

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture:
        result = service.activate_lock_for_reschedule(booking.id)

    assert result.get("already_locked") is True
    mock_capture.assert_not_called()


def test_resolve_lock_new_lesson_completed(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    locked_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="locked",
        payment_intent_id="pi_locked",
    )
    locked_booking.locked_amount_cents = 13440

    service = BookingService(db)

    with patch(
        "app.repositories.payment_repository.PaymentRepository.get_payment_by_booking_id",
        return_value=SimpleNamespace(instructor_payout_cents=10560),
    ), patch("app.services.stripe_service.StripeService.create_manual_transfer") as mock_transfer:
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        result = service.resolve_lock_for_booking(locked_booking.id, "new_lesson_completed")

    assert result.get("success") is True
    db.refresh(locked_booking)
    assert locked_booking.settlement_outcome == "lesson_completed_full_payout"
    assert locked_booking.instructor_payout_amount == 10560
    assert locked_booking.payment_status == "settled"
    assert locked_booking.lock_resolution == "new_lesson_completed"


def test_resolve_lock_new_lesson_cancelled_ge12(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    locked_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="locked",
        payment_intent_id="pi_locked",
    )

    service = BookingService(db)

    with patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit:
        result = service.resolve_lock_for_booking(locked_booking.id, "new_lesson_cancelled_ge12")

    assert result.get("success") is True
    db.refresh(locked_booking)
    assert locked_booking.settlement_outcome == "locked_cancel_ge12_full_credit"
    assert locked_booking.student_credit_amount == 12000
    mock_credit.assert_called_once()


def test_resolve_lock_new_lesson_cancelled_lt12(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    locked_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="locked",
        payment_intent_id="pi_locked",
    )

    service = BookingService(db)

    with patch(
        "app.repositories.payment_repository.PaymentRepository.get_payment_by_booking_id",
        return_value=SimpleNamespace(instructor_payout_cents=10560),
    ), patch("app.services.stripe_service.StripeService.create_manual_transfer") as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_transfer.return_value = {"transfer_id": "tr_split"}
        result = service.resolve_lock_for_booking(locked_booking.id, "new_lesson_cancelled_lt12")

    assert result.get("success") is True
    db.refresh(locked_booking)
    assert locked_booking.settlement_outcome == "locked_cancel_lt12_split_50_50"
    assert locked_booking.student_credit_amount == 6000
    assert locked_booking.instructor_payout_amount == 5280
    mock_transfer.assert_called_once()
    mock_credit.assert_called_once()


def test_resolve_lock_instructor_cancelled(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    locked_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="locked",
        payment_intent_id="pi_locked",
    )
    locked_booking.locked_amount_cents = 13440

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.refund_payment") as mock_refund:
        mock_refund.return_value = {"refund_id": "re_test", "amount_refunded": 13440}
        result = service.resolve_lock_for_booking(locked_booking.id, "instructor_cancelled")

    assert result.get("success") is True
    db.refresh(locked_booking)
    assert locked_booking.settlement_outcome == "instructor_cancel_full_refund"
    assert locked_booking.refunded_to_card_amount == 13440
    assert locked_booking.payment_status == "settled"


def test_resolve_lock_skips_if_not_locked(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="authorized",
        payment_intent_id="pi_test",
    )

    service = BookingService(db)
    result = service.resolve_lock_for_booking(booking.id, "new_lesson_completed")
    assert result.get("skipped") is True


def test_create_rescheduled_booking_with_locked_funds_links_chain(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    original = _create_booking(db, student, instructor, svc, when, payment_status="authorized")

    booking_data = BookingCreate(
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=(when + timedelta(days=7)).date(),
        start_time=time(10, 0),
        selected_duration=60,
        student_note=None,
        meeting_location="Test",
        location_type="neutral_location",
        location_lat=40.758,
        location_lng=-73.985,
    )

    service = BookingService(db)

    with patch.object(service, "_validate_booking_prerequisites", return_value=(svc, profile)), patch.object(
        service, "_validate_against_availability_bits"
    ), patch.object(service, "_check_conflicts_and_rules"):
        new_booking = service.create_rescheduled_booking_with_locked_funds(
            student, booking_data, 60, original.id
        )

    db.refresh(original)
    assert new_booking.rescheduled_from_booking_id == original.id
    assert original.rescheduled_to_booking_id == new_booking.id
    assert new_booking.has_locked_funds is True
    assert new_booking.payment_status == "locked"


def test_cancel_new_booking_resolves_lock(db: Session):
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now(timezone.utc) + timedelta(hours=15)

    locked_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when,
        payment_status="locked",
        payment_intent_id="pi_locked",
    )

    new_booking = _create_booking(
        db,
        student,
        instructor,
        svc,
        when + timedelta(days=7),
        payment_status="locked",
        payment_intent_id=None,
        has_locked_funds=True,
        rescheduled_from_id=locked_booking.id,
    )

    service = BookingService(db)

    with patch.object(service, "resolve_lock_for_booking", return_value={"success": True}) as mock_resolve:
        service.cancel_booking(new_booking.id, user=student, reason="test")

    mock_resolve.assert_called_once_with(locked_booking.id, "new_lesson_cancelled_ge12")
