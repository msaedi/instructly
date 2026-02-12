"""Integration tests for LOCK cancellations (credit-only for student)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_transfer import BookingTransfer
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent, PlatformCredit, StripeConnectedAccount
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.services.booking_service import BookingService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _get_service(db: Session, instructor: User) -> InstructorService:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    if not profile:
        raise RuntimeError("Instructor profile not found")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active.is_(True),
        )
        .first()
    )
    if not service:
        raise RuntimeError("Instructor service not found")
    return service


def _safe_start_window(hours_from_now: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    if end_dt.date() != start_dt.date():
        start_dt = (start_dt - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def _ensure_connected_account(db: Session, instructor_profile_id: str) -> StripeConnectedAccount:
    account = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == instructor_profile_id)
        .first()
    )
    if account:
        return account
    account = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=instructor_profile_id,
        stripe_account_id=f"acct_{ulid.ULID()}",
        onboarding_completed=True,
    )
    db.add(account)
    db.flush()
    return account


def _create_locked_booking(
    db: Session,
    *,
    student: User,
    instructor: User,
) -> Booking:
    service = _get_service(db, instructor)
    start_dt, end_dt = _safe_start_window(30)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Locked Cancellation",
        hourly_rate=120.0,
        total_price=120.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.LOCKED.value,
        payment_intent_id="pi_locked",
        locked_amount_cents=13440,
        locked_at=datetime.now(timezone.utc),
    )
    payment_record = PaymentIntent(
        id=str(ulid.ULID()),
        booking_id=booking.id,
        stripe_payment_intent_id="pi_locked",
        amount=13440,
        application_fee=0,
        status="succeeded",
        instructor_payout_cents=10560,
    )
    db.add(payment_record)

    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    )
    if profile:
        _ensure_connected_account(db, profile.id)

    db.commit()
    return booking


def _get_transfer(db: Session, booking_id: str) -> BookingTransfer | None:
    return (
        db.query(BookingTransfer)
        .filter(BookingTransfer.booking_id == booking_id)
        .first()
    )


def test_student_locked_cancel_ge12_gets_credit_not_refund(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_locked_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.create_manual_transfer = MagicMock()
        stripe_instance.refund_payment = MagicMock()

        booking_service.resolve_lock_for_booking(booking.id, "new_lesson_cancelled_ge12")

        stripe_instance.refund_payment.assert_not_called()

    db.refresh(booking)
    credit = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.source_booking_id == booking.id)
        .first()
    )
    assert credit is not None
    assert credit.amount_cents == 12000
    assert booking.settlement_outcome == "locked_cancel_ge12_full_credit"
    assert booking.refunded_to_card_amount == 0
    assert booking.payment_status == PaymentStatus.SETTLED.value


def test_student_locked_cancel_lt12_gets_50_credit_not_refund(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_locked_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.create_manual_transfer.return_value = {"transfer_id": "tr_payout"}
        stripe_instance.refund_payment = MagicMock()

        booking_service.resolve_lock_for_booking(booking.id, "new_lesson_cancelled_lt12")

        stripe_instance.refund_payment.assert_not_called()

    db.refresh(booking)
    credit = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.source_booking_id == booking.id)
        .first()
    )
    assert credit is not None
    assert credit.amount_cents == 6000
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.payout_transfer_id == "tr_payout"
    assert booking.settlement_outcome == "locked_cancel_lt12_split_50_50"
    assert booking.refunded_to_card_amount == 0
    assert booking.payment_status == PaymentStatus.SETTLED.value


def test_instructor_locked_cancel_gets_full_refund(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_locked_booking(db, student=test_student, instructor=test_instructor)
    booking_service = BookingService(db)

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.refund_payment.return_value = {
            "refund_id": "re_locked",
            "amount_refunded": 13440,
        }

        booking_service.resolve_lock_for_booking(booking.id, "instructor_cancelled")

        stripe_instance.refund_payment.assert_called_once()

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.refund_id == "re_locked"
    assert booking.settlement_outcome == "instructor_cancel_full_refund"
    assert booking.payment_status == PaymentStatus.SETTLED.value
