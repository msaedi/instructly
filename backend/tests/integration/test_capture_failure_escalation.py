"""Integration tests for capture failure escalation."""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session
import ulid

from app.models.booking import BookingStatus, PaymentStatus
from app.models.booking_transfer import BookingTransfer
from app.models.payment import PaymentIntent, StripeConnectedAccount
from app.models.user import User
from app.tasks.payment_tasks import _escalate_capture_failure

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def test_escalate_capture_failure_locks_account_and_pays_instructor(
    db: Session,
    test_student: User,
    test_instructor: User,
):
    """Escalation locks the student account and records instructor payout."""
    profile = test_instructor.instructor_profile
    service = next((svc for svc in profile.instructor_services if svc.is_active), None)
    assert service is not None, "Expected active instructor service"

    now = datetime.now(timezone.utc)
    booking_date = date.today() + timedelta(days=1)
    start_time = time(10, 0)
    end_time = time(11, 0)

    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.COMPLETED,
        allow_overlap=True,
        service_name="Capture Failure",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        location_type="neutral_location",
        meeting_location="Test",
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id="pi_capture_fail",
        capture_failed_at=now - timedelta(hours=80),
    )

    payment_record = PaymentIntent(
        id=str(ulid.ULID()),
        booking_id=booking.id,
        stripe_payment_intent_id="pi_capture_fail",
        amount=10000,
        application_fee=0,
        status="requires_capture",
        instructor_payout_cents=8800,
    )
    db.add(payment_record)

    connected_account = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        stripe_account_id="acct_test",
        onboarding_completed=True,
    )
    db.add(connected_account)
    db.commit()

    with patch(
        "app.tasks.payment_tasks.StripeService.create_manual_transfer",
        return_value={"transfer_id": "tr_capture_fail"},
    ):
        _escalate_capture_failure(booking.id, now)

    db.refresh(test_student)
    db.refresh(booking)
    from app.models.booking_payment import BookingPayment as BP
    bp = db.query(BP).filter(BP.booking_id == booking.id).one_or_none()
    student = db.query(User).filter(User.id == test_student.id).first()
    transfer = (
        db.query(BookingTransfer).filter(BookingTransfer.booking_id == booking.id).one_or_none()
    )
    assert student is not None
    assert transfer is not None
    assert bp is not None

    assert bp.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert bp.settlement_outcome == "capture_failure_instructor_paid"
    assert bp.instructor_payout_amount == 8800
    assert transfer.stripe_transfer_id == "tr_capture_fail"

    assert student.account_locked is True
    assert student.account_locked_reason is not None
    assert booking.id in student.account_locked_reason
