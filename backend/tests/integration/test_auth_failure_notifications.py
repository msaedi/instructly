"""Integration tests for auth failure notifications (T-24 and T-13)."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.user import User
from app.tasks.payment_tasks import process_scheduled_authorizations, retry_failed_authorizations

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@contextmanager
def _always_acquire_lock(*_args, **_kwargs):
    yield True


def _create_scheduled_booking(
    db: Session, *, student: User, instructor: User, hours_from_now: float
) -> Booking:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(
        minute=0, second=0, microsecond=0
    )
    end_dt = start_dt + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        instructor_timezone="UTC",
        student_timezone="UTC",
        service_name="Auth Notification",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_test",
    )
    booking.auth_scheduled_for = now - timedelta(minutes=5)
    db.commit()
    return booking


def _create_failed_auth_booking(
    db: Session, *, student: User, instructor: User, hours_from_now: float
) -> Booking:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(
        minute=0, second=0, microsecond=0
    )
    hours_until = (start_dt - now).total_seconds() / 3600
    if hours_until <= 12:
        start_dt = start_dt + timedelta(hours=1)
    elif hours_until > 13:
        start_dt = start_dt - timedelta(hours=1)
    end_dt = start_dt + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        instructor_timezone="UTC",
        student_timezone="UTC",
        service_name="Auth Notification",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_method_id="pm_test",
    )
    booking.auth_attempted_at = now - timedelta(hours=2)
    booking.auth_failure_count = 1
    db.commit()
    return booking


def test_first_auth_failure_sends_email(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_scheduled_booking(
        db, student=test_student, instructor=test_instructor, hours_from_now=24
    )

    with patch(
        "app.tasks.payment_tasks._process_authorization_for_booking",
        return_value={"success": False, "error": "declined", "error_type": "card_declined"},
    ), patch(
        "app.tasks.payment_tasks.NotificationService.send_final_payment_warning"
    ) as mock_warn, patch(
        "app.tasks.payment_tasks.booking_lock_sync", _always_acquire_lock
    ):
        process_scheduled_authorizations()

    db.refresh(booking)
    assert booking.auth_failure_first_email_sent_at is not None
    assert mock_warn.called is True


def test_t13_warning_sent(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_failed_auth_booking(
        db, student=test_student, instructor=test_instructor, hours_from_now=12.5
    )

    with patch(
        "app.tasks.payment_tasks._process_retry_authorization",
        return_value={"success": False, "error": "declined"},
    ), patch(
        "app.tasks.payment_tasks.NotificationService.send_final_payment_warning"
    ) as mock_warn, patch(
        "app.tasks.payment_tasks.booking_lock_sync", _always_acquire_lock
    ):
        retry_failed_authorizations()

    db.refresh(booking)
    assert booking.auth_failure_t13_warning_sent_at is not None
    assert mock_warn.called is True
