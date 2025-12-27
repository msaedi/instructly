"""
Integration tests for booking mutex on Celery tasks.

These tests verify that payment tasks skip bookings when the lock is unavailable.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models.booking import BookingStatus
from app.tasks.payment_tasks import (
    capture_completed_lessons,
    capture_late_cancellation,
    create_new_authorization_and_capture,
    process_scheduled_authorizations,
    retry_failed_authorizations,
)


def _lock_unavailable_factory(calls):
    @contextmanager
    def _lock(booking_id, *args, **kwargs):
        calls.append(str(booking_id))
        yield False

    return _lock


def _update_booking(db, booking, **updates):
    for key, value in updates.items():
        setattr(booking, key, value)
    db.commit()
    return booking


def test_process_scheduled_authorizations_skips_locked_booking(db, test_booking):
    now = datetime.now(timezone.utc)
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CONFIRMED,
        payment_status="scheduled",
        payment_method_id="pm_test",
        booking_start_utc=now + timedelta(hours=24),
    )

    calls = []
    with patch(
        "app.tasks.payment_tasks.booking_lock_sync", _lock_unavailable_factory(calls)
    ), patch(
        "app.tasks.payment_tasks._process_authorization_for_booking"
    ) as mock_process:
        result = process_scheduled_authorizations()

    assert test_booking.id in calls
    mock_process.assert_not_called()
    assert result["failed"] == 0


def test_retry_failed_authorizations_skips_locked_booking(db, test_booking):
    now = datetime.now(timezone.utc)
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CONFIRMED,
        payment_status="auth_failed",
        payment_method_id="pm_test",
        booking_start_utc=now + timedelta(hours=10),
    )

    calls = []
    with patch(
        "app.tasks.payment_tasks.booking_lock_sync", _lock_unavailable_factory(calls)
    ), patch(
        "app.tasks.payment_tasks._process_retry_authorization"
    ) as mock_retry, patch(
        "app.tasks.payment_tasks._cancel_booking_payment_failed"
    ) as mock_cancel:
        result = retry_failed_authorizations()

    assert test_booking.id in calls
    mock_retry.assert_not_called()
    mock_cancel.assert_not_called()
    assert result["failed"] == 0


def test_capture_completed_lessons_skips_locked_booking(db, test_booking):
    now = datetime.now(timezone.utc)
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.COMPLETED,
        payment_status="authorized",
        payment_intent_id="pi_test",
        completed_at=now - timedelta(hours=25),
        booking_end_utc=now - timedelta(hours=25),
    )

    calls = []
    with patch(
        "app.tasks.payment_tasks.booking_lock_sync", _lock_unavailable_factory(calls)
    ), patch(
        "app.tasks.payment_tasks._process_capture_for_booking"
    ) as mock_capture:
        result = capture_completed_lessons()

    assert test_booking.id in calls
    mock_capture.assert_not_called()
    assert result["failed"] == 0


def test_capture_late_cancellation_skips_when_locked():
    calls = []
    with patch(
        "app.tasks.payment_tasks.booking_lock_sync", _lock_unavailable_factory(calls)
    ):
        result = capture_late_cancellation("booking_123")

    assert "booking_123" in calls
    assert result["skipped"] is True
    assert result["error"] == "lock_unavailable"


def test_create_new_authorization_and_capture_skips_when_locked():
    booking = MagicMock()
    booking.id = "booking_456"
    payment_repo = MagicMock()
    db = MagicMock()
    calls = []

    with patch(
        "app.tasks.payment_tasks.booking_lock_sync", _lock_unavailable_factory(calls)
    ):
        result = create_new_authorization_and_capture(booking, payment_repo, db)

    assert "booking_456" in calls
    assert result["skipped"] is True
    assert result["error"] == "lock_unavailable"
