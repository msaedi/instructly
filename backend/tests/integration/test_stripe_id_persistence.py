"""Integration tests for Stripe ID persistence on bookings."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_transfer import BookingTransfer
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent, StripeConnectedAccount
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.services.booking_service import BookingService
from app.tasks.payment_tasks import _escalate_capture_failure, _process_capture_for_booking

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


def _get_transfer(db: Session, booking_id: str) -> BookingTransfer | None:
    return (
        db.query(BookingTransfer).filter(BookingTransfer.booking_id == booking_id).one_or_none()
    )


def _create_completed_booking(
    db: Session, *, student: User, instructor: User
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
        service_name="Stripe IDs",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_capture",
    )
    payment_record = PaymentIntent(
        id=str(ulid.ULID()),
        booking_id=booking.id,
        stripe_payment_intent_id="pi_capture",
        amount=10000,
        application_fee=0,
        status="requires_capture",
        instructor_payout_cents=8800,
    )
    db.add(payment_record)
    db.commit()
    return booking


def test_transfer_id_stored_on_capture(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_completed_booking(db, student=test_student, instructor=test_instructor)

    capture_payload = {
        "payment_intent": MagicMock(amount_received=10000),
        "amount_received": 10000,
        "transfer_id": "tr_capture",
    }

    with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.capture_booking_payment_intent.return_value = capture_payload
        _process_capture_for_booking(booking.id, "auto_completed")

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.stripe_transfer_id == "tr_capture"


def test_transfer_reversal_id_stored_on_12_24h_cancel(
    db: Session, test_student: User, test_instructor: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor)
    start_dt, end_dt = _safe_start_window(30)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Stripe IDs",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_cancel",
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 18.0,
    )

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.capture_payment_intent.return_value = {
            "transfer_id": "tr_cancel",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        stripe_instance.reverse_transfer.return_value = {"reversal": {"id": "trr_cancel"}}
        stripe_instance.create_manual_transfer.return_value = {"transfer_id": "tr_unused"}
        stripe_instance.cancel_payment_intent.return_value = {"payment_intent": MagicMock()}

        booking_service.cancel_booking(booking.id, test_student, "test cancel")

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.transfer_reversal_id == "trr_cancel"


def test_refund_id_stored_on_instructor_cancel(
    db: Session, test_student: User, test_instructor: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor)
    start_dt, end_dt = _safe_start_window(30)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Stripe IDs",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.SETTLED.value,
        payment_intent_id="pi_refund",
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 30.0,
    )

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.refund_payment.return_value = {
            "refund_id": "re_refund",
            "amount_refunded": 13440,
        }
        stripe_instance.cancel_payment_intent.return_value = {"payment_intent": MagicMock()}

        booking_service.cancel_booking(booking.id, test_instructor, "instructor cancel")

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.refund_id == "re_refund"


def test_payout_transfer_id_stored_on_manual_payout(
    db: Session, test_student: User, test_instructor: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor)
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    )
    if profile:
        _ensure_connected_account(db, profile.id)
    start_dt, end_dt = _safe_start_window(30)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Stripe IDs",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_payout",
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 6.0,
    )

    with patch("app.services.booking_service.StripeService") as mock_stripe_service:
        stripe_instance = mock_stripe_service.return_value
        stripe_instance.capture_payment_intent.return_value = {
            "transfer_id": "tr_payout",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        stripe_instance.reverse_transfer.return_value = {"reversal": {"id": "trr_payout"}}
        stripe_instance.create_manual_transfer.return_value = {"transfer_id": "tr_manual"}

        booking_service.cancel_booking(booking.id, test_student, "late cancel")

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.payout_transfer_id == "tr_manual"


def test_advanced_payout_transfer_id_stored_on_capture_escalation(
    db: Session, test_student: User, test_instructor: User
) -> None:
    service = _get_service(db, test_instructor)
    start_dt, end_dt = _safe_start_window(30)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Stripe IDs",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id="pi_fail",
        capture_failed_at=datetime.now(timezone.utc) - timedelta(hours=80),
    )
    payment_record = PaymentIntent(
        id=str(ulid.ULID()),
        booking_id=booking.id,
        stripe_payment_intent_id="pi_fail",
        amount=10000,
        application_fee=0,
        status="requires_capture",
        instructor_payout_cents=8800,
    )
    db.add(payment_record)

    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    )
    if profile:
        _ensure_connected_account(db, profile.id)

    db.commit()

    with patch(
        "app.tasks.payment_tasks.StripeService.create_manual_transfer",
        return_value={"transfer_id": "tr_advanced"},
    ):
        _escalate_capture_failure(booking.id, datetime.now(timezone.utc))

    db.refresh(booking)
    transfer = _get_transfer(db, booking.id)
    assert transfer is not None
    assert transfer.advanced_payout_transfer_id == "tr_advanced"
