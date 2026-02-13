"""
Integration tests for payment_tasks.py coverage targets.

Uses real DB/repositories and mocks only external services (Stripe, notifications).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session
import stripe

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_payment import BookingPayment
from app.models.payment import PaymentIntent
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.tasks.payment_tasks import (
    _auto_complete_booking,
    _cancel_booking_payment_failed,
    _mark_child_booking_settled,
    _process_authorization_for_booking,
    _process_capture_for_booking,
    _process_retry_authorization,
    _resolve_locked_booking_from_task,
    capture_completed_lessons,
    capture_late_cancellation,
    check_immediate_auth_timeout,
    process_scheduled_authorizations,
    retry_failed_authorizations,
    retry_failed_captures,
)

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _ensure_stripe_customer(db: Session, user_id: str) -> None:
    payment_repo = PaymentRepository(db)
    if payment_repo.get_customer_by_user_id(user_id):
        return
    payment_repo.create_customer_record(user_id=user_id, stripe_customer_id=f"cus_{generate_ulid()}")
    db.commit()


def _ensure_connected_account(db: Session, instructor: User) -> None:
    payment_repo = PaymentRepository(db)
    profile = instructor.instructor_profile
    if payment_repo.get_connected_account_by_instructor_id(profile.id):
        return
    payment_repo.create_connected_account_record(
        instructor_profile_id=profile.id,
        stripe_account_id=f"acct_{generate_ulid()}",
        onboarding_completed=True,
    )
    db.commit()


def _create_booking(
    db: Session,
    *,
    student: User,
    instructor: User,
    start_dt: datetime,
    payment_status: str,
    status: BookingStatus = BookingStatus.CONFIRMED,
    payment_method_id: str | None = "pm_test",
    payment_intent_id: str | None = None,
) -> Booking:
    end_dt = start_dt + timedelta(hours=1)
    safe_start_dt = start_dt
    safe_end_dt = end_dt
    if safe_end_dt.date() != safe_start_dt.date():
        # Avoid invalid local ranges during fixture insert; preserve UTC times after insert.
        safe_start_dt = safe_start_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        safe_end_dt = safe_start_dt + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=safe_start_dt.date(),
        start_time=safe_start_dt.time(),
        end_time=safe_end_dt.time(),
        instructor_timezone="UTC",
        student_timezone="UTC",
        service_name="Payment Tasks",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=status,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=payment_status,
        payment_method_id=payment_method_id,
        payment_intent_id=payment_intent_id,
    )
    booking.booking_start_utc = start_dt
    booking.booking_end_utc = end_dt
    db.commit()
    return booking


def _create_payment_intent(db: Session, booking: Booking, payout_cents: int = 8000) -> None:
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    pi_id = (bp.payment_intent_id if bp else None) or f"pi_{generate_ulid()}"
    payment_intent = PaymentIntent(
        id=generate_ulid(),
        booking_id=booking.id,
        stripe_payment_intent_id=pi_id,
        amount=10000,
        application_fee=1000,
        status="requires_capture",
        instructor_payout_cents=payout_cents,
    )
    db.add(payment_intent)
    db.commit()


def _prepare_capture_booking(
    db: Session,
    *,
    student: User,
    instructor: User,
    payment_intent_id: str,
    capture_retry_count: int = 0,
) -> Booking:
    booking = _create_booking(
        db,
        student=student,
        instructor=instructor,
        start_dt=datetime.now(timezone.utc) - timedelta(hours=26),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id=payment_intent_id,
    )
    booking.status = BookingStatus.COMPLETED
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        bp.capture_retry_count = capture_retry_count
    db.commit()
    return booking


def test_process_scheduled_authorizations_success(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)
    start_dt = now + timedelta(hours=24)

    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=start_dt,
        payment_status=PaymentStatus.SCHEDULED.value,
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.auth_scheduled_for = now - timedelta(minutes=5)
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
        id="pi_auth_success"
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        results = process_scheduled_authorizations()

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert results["success"] == 1
    assert bp.payment_status == PaymentStatus.AUTHORIZED.value
    assert bp.payment_intent_id == "pi_auth_success"


def test_retry_failed_authorizations_cancels_and_retries(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)

    booking_cancel = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_method_id="pm_cancel",
    )
    bp_cancel = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_cancel.id).first()
    assert bp_cancel is not None
    bp_cancel.auth_attempted_at = now - timedelta(hours=2)
    bp_cancel.auth_failure_count = 2

    booking_retry = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_method_id="pm_retry",
    )
    bp_retry = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_retry.id).first()
    assert bp_retry is not None
    bp_retry.auth_attempted_at = now - timedelta(hours=2)
    bp_retry.auth_failure_count = 1
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
        id="pi_retry_success"
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_booking_cancelled_payment_failed"
    ):
        results = retry_failed_authorizations()

    db.refresh(booking_cancel)
    db.refresh(booking_retry)
    bp_cancel = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_cancel.id).first()
    bp_retry = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_retry.id).first()
    assert results["cancelled"] == 1
    assert results["retried"] == 1
    assert booking_cancel.status == BookingStatus.CANCELLED
    assert bp_cancel is not None
    assert bp_cancel.payment_status == PaymentStatus.SETTLED.value
    assert bp_retry is not None
    assert bp_retry.payment_status == PaymentStatus.AUTHORIZED.value
    assert bp_retry.payment_intent_id == "pi_retry_success"


def test_retry_failed_authorizations_warn_only_sends_warning(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """T-13 warning path should send a warning without retrying."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=12, minutes=30),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_method_id="pm_warn_only",
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.auth_attempted_at = now - timedelta(minutes=30)
    bp.auth_failure_count = 1
    db.commit()

    with patch("app.tasks.payment_tasks.NotificationService.send_final_payment_warning") as mock_warning:
        results = retry_failed_authorizations()

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert results["warnings_sent"] >= 1
    assert bp.auth_failure_t13_warning_sent_at is not None
    mock_warning.assert_called()


def test_check_immediate_auth_timeout_cancels_after_window(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.auth_attempted_at = now - timedelta(minutes=31)
    db.commit()

    with patch(
        "app.tasks.payment_tasks.NotificationService.send_booking_cancelled_payment_failed"
    ):
        result = check_immediate_auth_timeout(booking.id)

    db.refresh(booking)
    assert result.get("cancelled") is True
    assert booking.status == BookingStatus.CANCELLED


def test_retry_failed_captures_escalates_after_72h(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)
    payment_intent_id = f"pi_{generate_ulid()}"

    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id=payment_intent_id,
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.capture_failed_at = now - timedelta(hours=80)
    db.commit()

    _ensure_connected_account(db, test_instructor_with_availability)
    _create_payment_intent(db, booking, payout_cents=8000)

    mock_stripe = MagicMock()
    mock_stripe.create_manual_transfer.return_value = {"transfer_id": "tr_escalated"}

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        results = retry_failed_captures()

    db.refresh(booking)
    db.refresh(test_student)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert results["escalated"] == 1
    assert bp.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert bp.capture_escalated_at is not None
    assert test_student.account_locked is True


def test_capture_completed_lessons_captures_and_auto_completes(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)
    base_dt = (now - timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )

    completed_booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=base_dt,
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_completed_capture",
    )
    completed_booking.status = BookingStatus.COMPLETED
    completed_booking.completed_at = completed_booking.booking_end_utc
    db.commit()

    auto_booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=base_dt + timedelta(hours=2),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_auto_capture",
    )
    db.commit()

    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.return_value = {
        "payment_intent": SimpleNamespace(id="pi_capture", status="succeeded"),
        "amount_received": 10000,
        "transfer_id": "tr_capture",
    }

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = capture_completed_lessons()

    db.refresh(completed_booking)
    db.refresh(auto_booking)
    bp_completed = db.query(BookingPayment).filter(BookingPayment.booking_id == completed_booking.id).first()
    assert result["captured"] >= 1
    assert result["auto_completed"] >= 1
    assert bp_completed is not None
    assert bp_completed.payment_status == PaymentStatus.SETTLED.value
    assert auto_booking.status == BookingStatus.COMPLETED


def test_capture_late_cancellation_success(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_late_cancel",
    )
    booking.status = BookingStatus.CANCELLED
    db.commit()

    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.return_value = SimpleNamespace(
        amount_received=10000
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = capture_late_cancellation(booking.id)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert result["success"] is True
    assert bp is not None
    assert bp.payment_status == PaymentStatus.SETTLED.value


def test_process_capture_already_captured(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_already_captured",
    )

    error = stripe.error.InvalidRequestError(
        message="Already been captured",
        param="payment_intent",
        code="already_captured",
    )
    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.side_effect = error

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert result.get("already_captured") is True
    assert bp is not None
    assert bp.payment_status == PaymentStatus.SETTLED.value


def test_process_capture_expired_marks_failed(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_expired_auth",
        capture_retry_count=1,
    )

    error = stripe.error.InvalidRequestError(
        message="Authorization expired",
        param="payment_intent",
        code="payment_intent_unexpected_state",
    )
    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.side_effect = error

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("expired") is True
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert bp.capture_failed_at is not None


def test_process_capture_card_error_marks_failed(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_card_error",
        capture_retry_count=1,
    )

    error = stripe.error.CardError(
        message="Card declined",
        param="card",
        code="card_declined",
    )
    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.side_effect = error

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("card_error") is True
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert bp.capture_error == "Card declined"


def test_process_capture_generic_error_marks_failed(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_generic_error",
        capture_retry_count=1,
    )

    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.side_effect = Exception("capture boom")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is False
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


def test_process_capture_booking_not_found() -> None:
    """Missing bookings should return a not found error."""
    result = _process_capture_for_booking(generate_ulid(), "instructor_completed")
    assert result.get("success") is False
    assert result.get("error") == "Booking not found"


def test_process_capture_cancelled_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Cancelled bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_cancelled_capture",
    )
    booking.status = BookingStatus.CANCELLED
    db.commit()

    result = _process_capture_for_booking(booking.id, "instructor_completed")

    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_process_capture_missing_payment_intent(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Bookings without payment intents should return an error."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id=None,
    )
    db.commit()

    result = _process_capture_for_booking(booking.id, "instructor_completed")

    assert result.get("success") is False
    assert result.get("error") == "No payment_intent_id"


def test_process_capture_manual_review_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Manual review bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
        payment_intent_id="pi_manual_review",
    )
    db.commit()

    result = _process_capture_for_booking(booking.id, "instructor_completed")

    assert result.get("skipped") is True
    assert result.get("reason") == "disputed"


def test_process_capture_settled_already_captured(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Settled bookings should be treated as already captured."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.SETTLED.value,
        payment_intent_id="pi_settled",
    )
    db.commit()

    result = _process_capture_for_booking(booking.id, "instructor_completed")

    assert result.get("already_captured") is True


def test_process_capture_not_eligible_status_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Non-eligible statuses should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id="pi_not_eligible",
    )
    db.commit()

    result = _process_capture_for_booking(booking.id, "instructor_completed")

    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_process_capture_not_capture_failure_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Retry captures should skip when capture_failed_at is missing."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id="pi_retry_capture",
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        bp.capture_failed_at = None
    db.commit()

    result = _process_capture_for_booking(booking.id, "retry_failed_capture")

    assert result.get("skipped") is True
    assert result.get("reason") == "not_capture_failure"


def test_process_capture_locked_funds_skips_and_settles_child(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Locked funds capture path resolves and settles the child booking."""
    base_dt = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    locked_booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=base_dt,
        payment_status=PaymentStatus.SETTLED.value,
        payment_intent_id="pi_locked_parent",
    )
    child_booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=base_dt + timedelta(hours=1),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_locked_child",
    )
    child_booking.has_locked_funds = True
    child_booking.rescheduled_from_booking_id = locked_booking.id
    db.commit()

    result = _process_capture_for_booking(child_booking.id, "instructor_completed")

    db.refresh(child_booking)
    bp_child = db.query(BookingPayment).filter(BookingPayment.booking_id == child_booking.id).first()
    assert result.get("skipped") is True
    assert result.get("reason") == "locked_funds"
    assert bp_child is not None
    assert bp_child.payment_status == PaymentStatus.SETTLED.value


def test_process_capture_success_uses_amount_field(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Capture should fall back to payment_intent.amount when amount_received is missing."""
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_amount_only",
    )
    _create_payment_intent(db, booking, payout_cents=8000)

    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.return_value = SimpleNamespace(amount=10000)

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is True
    assert bp.payment_status == PaymentStatus.SETTLED.value


def test_process_capture_invalid_request_notifies_failure(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """InvalidRequest errors should mark failure and attempt notification."""
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_invalid_request",
        capture_retry_count=0,
    )

    error = stripe.error.InvalidRequestError(
        message="Invalid request",
        param="payment_intent",
        code="invalid_request",
    )
    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.side_effect = error

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_payment_failed_notification",
        side_effect=Exception("notify failed"),
    ):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is False
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


def test_process_capture_credit_forfeit_failure_logs(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Capture success should tolerate credit forfeit errors."""
    booking = _prepare_capture_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        payment_intent_id="pi_forfeit_fail",
    )
    _create_payment_intent(db, booking, payout_cents=8000)

    mock_stripe = MagicMock()
    mock_stripe.capture_booking_payment_intent.return_value = SimpleNamespace(
        amount_received=10000
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.services.credit_service.CreditService.forfeit_credits_for_booking",
        side_effect=Exception("forfeit failed"),
    ):
        result = _process_capture_for_booking(booking.id, "instructor_completed")

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is True
    assert bp.payment_status == PaymentStatus.SETTLED.value


def test_mark_child_booking_settled_updates_status(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Child bookings should be marked settled."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_child",
    )
    db.commit()

    _mark_child_booking_settled(booking.id)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert bp.payment_status == PaymentStatus.SETTLED.value


def test_mark_child_booking_settled_missing_booking() -> None:
    """Missing child bookings should be ignored."""
    _mark_child_booking_settled(generate_ulid())


def test_resolve_locked_booking_from_task_not_locked(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Non-locked bookings should return a skipped result."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=6),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_not_locked",
    )
    db.commit()

    result = _resolve_locked_booking_from_task(booking.id, "new_lesson_completed")

    assert result.get("skipped") is True
    assert result.get("reason") == "not_locked"


def test_auto_complete_booking_missing() -> None:
    """Missing bookings should return a not found error."""
    result = _auto_complete_booking(generate_ulid(), datetime.now(timezone.utc))
    assert result.get("success") is False
    assert result.get("error") == "Booking not found"


def test_auto_complete_booking_cancelled_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Cancelled bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now - timedelta(hours=2),
        payment_status=PaymentStatus.AUTHORIZED.value,
        status=BookingStatus.CANCELLED,
    )
    db.commit()

    result = _auto_complete_booking(booking.id, now)

    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_auto_complete_booking_manual_review_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Disputed bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now - timedelta(hours=2),
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
        status=BookingStatus.CONFIRMED,
    )
    db.commit()

    result = _auto_complete_booking(booking.id, now)

    assert result.get("skipped") is True
    assert result.get("reason") == "disputed"


def test_auto_complete_booking_not_eligible_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Non-eligible bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now - timedelta(hours=2),
        payment_status=PaymentStatus.SCHEDULED.value,
        status=BookingStatus.PENDING,
    )
    db.commit()

    result = _auto_complete_booking(booking.id, now)

    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_process_authorization_existing_payment_intent_confirms(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Existing PaymentIntent is confirmed and booking is authorized."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=30),
        payment_status=PaymentStatus.SCHEDULED.value,
        status=BookingStatus.PENDING,
        payment_method_id="pm_existing",
        payment_intent_id="pi_existing",
    )

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
        base_price_cents=10000,
    )
    mock_stripe.confirm_payment_intent.return_value = SimpleNamespace(status="requires_capture")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.services.booking_service.BookingService.send_booking_notifications_after_confirmation"
    ):
        result = _process_authorization_for_booking(booking.id, 30.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is True
    assert bp.payment_status == PaymentStatus.AUTHORIZED.value
    assert bp.payment_intent_id == "pi_existing"
    assert booking.status == BookingStatus.CONFIRMED


def test_process_authorization_existing_intent_unexpected_status_marks_failed(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Unexpected PaymentIntent status triggers authorization failure."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=30),
        payment_status=PaymentStatus.SCHEDULED.value,
        status=BookingStatus.PENDING,
        payment_method_id="pm_existing_bad",
        payment_intent_id="pi_existing_bad",
    )

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
        base_price_cents=10000,
    )
    mock_stripe.confirm_payment_intent.return_value = SimpleNamespace(status="processing")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_payment_failed_notification"
    ):
        result = _process_authorization_for_booking(booking.id, 30.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is False
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


def test_process_authorization_credits_only_handles_notification_error(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Credits-only authorization confirms booking and swallows notification errors."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=30),
        payment_status=PaymentStatus.SCHEDULED.value,
        status=BookingStatus.PENDING,
        payment_method_id="pm_credits_only",
    )

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=0,
        application_fee_cents=0,
        applied_credit_cents=10000,
        base_price_cents=10000,
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.services.booking_service.BookingService.send_booking_notifications_after_confirmation",
        side_effect=Exception("notification failure"),
    ):
        result = _process_authorization_for_booking(booking.id, 30.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is True
    assert bp.payment_status == PaymentStatus.AUTHORIZED.value
    assert booking.status == BookingStatus.CONFIRMED


def test_process_authorization_missing_payment_method_marks_failed(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Missing payment method triggers failure handling and timeout scheduling."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id=None,
    )

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
        base_price_cents=10000,
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_payment_failed_notification",
        side_effect=Exception("notify failed"),
    ), patch(
        "app.tasks.payment_tasks.check_immediate_auth_timeout.apply_async",
        side_effect=Exception("enqueue failed"),
    ):
        result = _process_authorization_for_booking(booking.id, 10.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is False
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert bp.auth_failure_count == 1


def test_process_authorization_not_eligible_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Non-scheduled bookings should be skipped in Phase 1."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=30),
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    result = _process_authorization_for_booking(booking.id, 30.0)

    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_process_authorization_cancelled_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Cancelled bookings should be skipped in Phase 1."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=30),
        payment_status=PaymentStatus.SCHEDULED.value,
        status=BookingStatus.CANCELLED,
    )

    result = _process_authorization_for_booking(booking.id, 30.0)

    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_process_retry_authorization_failure_updates_booking(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Retry failures increment auth counters and keep payment required."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.auth_failure_count = 1
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.side_effect = Exception("retry failed")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_retry_authorization(booking.id, 20.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is False
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert bp.auth_failure_count == 2


def test_process_retry_authorization_booking_not_found(db: Session) -> None:
    """Missing bookings return a not found error."""
    result = _process_retry_authorization(generate_ulid(), 20.0)
    assert result.get("success") is False
    assert result.get("error") == "Booking not found"


def test_process_retry_authorization_cancelled_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Cancelled bookings should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        status=BookingStatus.CANCELLED,
    )

    result = _process_retry_authorization(booking.id, 20.0)

    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_process_retry_authorization_not_eligible_skipped(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Non-eligible status should be skipped."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    result = _process_retry_authorization(booking.id, 20.0)

    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_process_retry_authorization_missing_customer(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Retry should fail when student lacks a Stripe customer."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )

    payment_repo = PaymentRepository(db)
    existing = payment_repo.get_customer_by_user_id(test_student.id)
    if existing:
        db.delete(existing)
        db.commit()

    result = _process_retry_authorization(booking.id, 20.0)

    assert result.get("success") is False
    assert "No Stripe customer" in result.get("error", "")


def test_process_retry_authorization_missing_instructor_profile(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Retry should fail when instructor profile is missing."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )

    _ensure_stripe_customer(db, test_student.id)
    booking.instructor_id = test_student.id
    db.commit()

    result = _process_retry_authorization(booking.id, 20.0)

    assert result.get("success") is False
    assert "No instructor profile" in result.get("error", "")


def test_process_retry_authorization_missing_connected_account(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Retry should fail when instructor lacks a Stripe account."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )

    _ensure_stripe_customer(db, test_student.id)

    payment_repo = PaymentRepository(db)
    account = payment_repo.get_connected_account_by_instructor_id(
        test_instructor_with_availability.instructor_profile.id
    )
    if account:
        db.delete(account)
        db.commit()

    result = _process_retry_authorization(booking.id, 20.0)

    assert result.get("success") is False
    assert "No Stripe account" in result.get("error", "")


def test_process_retry_authorization_credits_only(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Credits-only retry authorizes without Stripe capture."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=20),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=0,
        application_fee_cents=0,
        applied_credit_cents=10000,
    )

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
        result = _process_retry_authorization(booking.id, 20.0)

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert result.get("success") is True
    assert bp.payment_status == PaymentStatus.AUTHORIZED.value


def test_process_scheduled_authorizations_sends_t24_warning(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Scheduled auth failure triggers the T-24 warning path."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=24),
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_warn",
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    bp.auth_scheduled_for = now - timedelta(minutes=1)
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.side_effect = Exception("stripe fail")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_final_payment_warning"
    ) as mock_warning:
        results = process_scheduled_authorizations()

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert results["failed"] >= 1
    assert bp.auth_failure_first_email_sent_at is not None
    mock_warning.assert_called()


def test_process_scheduled_authorizations_legacy_window_sends_t24_warning(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Legacy window path should send warning and create event."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=24),
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_warn_legacy",
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        bp.auth_scheduled_for = None
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.side_effect = Exception("stripe fail")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_final_payment_warning"
    ) as mock_warning:
        results = process_scheduled_authorizations()

    db.refresh(booking)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    payment_repo = PaymentRepository(db)
    events = payment_repo.get_payment_events_for_booking(booking.id)

    assert results["failed"] >= 1
    assert bp.auth_failure_first_email_sent_at is not None
    assert "t24_first_failure_email_sent" in {event.event_type for event in events}
    mock_warning.assert_called()


def test_process_scheduled_authorizations_t24_email_failure_logs(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Failures sending T-24 warnings should not crash the task."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=24),
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_warn_fail",
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        bp.auth_scheduled_for = None
    db.commit()

    _ensure_stripe_customer(db, test_student.id)
    _ensure_connected_account(db, test_instructor_with_availability)

    mock_stripe = MagicMock()
    mock_stripe.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=10000,
        application_fee_cents=1000,
        applied_credit_cents=0,
    )
    mock_stripe.create_or_retry_booking_payment_intent.side_effect = Exception("stripe fail")

    with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe), patch(
        "app.tasks.payment_tasks.NotificationService.send_final_payment_warning",
        side_effect=Exception("email error"),
    ):
        results = process_scheduled_authorizations()

    assert results["failed"] >= 1


def test_cancel_booking_payment_failed_missing_booking(db: Session) -> None:
    """Missing booking returns False."""
    now = datetime.now(timezone.utc)
    assert _cancel_booking_payment_failed(generate_ulid(), 8.0, now) is False


def test_cancel_booking_payment_failed_already_cancelled(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Already cancelled bookings are ignored."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        status=BookingStatus.CANCELLED,
    )

    assert _cancel_booking_payment_failed(booking.id, 8.0, now) is False


def test_cancel_booking_payment_failed_credit_release_failure(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Credit release failures should not block cancellation."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        bp.credits_reserved_cents = 1000
    db.commit()

    with patch(
        "app.services.credit_service.CreditService.release_credits_for_booking",
        side_effect=Exception("release failed"),
    ), patch(
        "app.tasks.payment_tasks.NotificationService.send_booking_cancelled_payment_failed"
    ):
        result = _cancel_booking_payment_failed(booking.id, 8.0, now)

    db.refresh(booking)
    assert result is True
    assert booking.status == BookingStatus.CANCELLED


def test_cancel_booking_payment_failed_notification_failure_returns_false(
    db: Session, test_student: User, test_instructor_with_availability: User
) -> None:
    """Notification failures should return False after rollback."""
    now = datetime.now(timezone.utc)
    booking = _create_booking(
        db,
        student=test_student,
        instructor=test_instructor_with_availability,
        start_dt=now + timedelta(hours=10),
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )

    with patch(
        "app.tasks.payment_tasks.NotificationService.send_booking_cancelled_payment_failed",
        side_effect=Exception("notify failed"),
    ):
        result = _cancel_booking_payment_failed(booking.id, 8.0, now)

    assert result is False
