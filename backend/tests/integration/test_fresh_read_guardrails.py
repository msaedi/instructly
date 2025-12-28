"""
Integration tests for fresh-read guardrails in payment tasks and cancel flow.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.models.booking import BookingStatus, PaymentStatus
from app.tasks.payment_tasks import (
    _process_authorization_for_booking,
    _process_capture_for_booking,
)


@asynccontextmanager
async def _lock_available(*_args, **_kwargs):
    yield True


def _update_booking(db, booking, **updates):
    for key, value in updates.items():
        setattr(booking, key, value)
    db.commit()
    return booking


def test_auth_task_skips_cancelled_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CANCELLED,
        cancelled_at=datetime.now(timezone.utc),
    )
    result = _process_authorization_for_booking(test_booking.id, hours_until_lesson=24.0)
    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_auth_task_skips_not_eligible_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CONFIRMED,
        payment_status="authorized",
    )
    result = _process_authorization_for_booking(test_booking.id, hours_until_lesson=24.0)
    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_capture_task_skips_cancelled_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CANCELLED,
        payment_status="authorized",
        payment_intent_id="pi_test",
        cancelled_at=datetime.now(timezone.utc),
    )
    result = _process_capture_for_booking(test_booking.id, "test")
    assert result.get("skipped") is True
    assert result.get("reason") == "cancelled"


def test_capture_task_skips_disputed_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.COMPLETED,
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
        payment_intent_id="pi_test",
    )
    result = _process_capture_for_booking(test_booking.id, "test")
    assert result.get("skipped") is True
    assert result.get("reason") == "disputed"


def test_capture_task_skips_already_captured_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.COMPLETED,
        payment_status = "settled",
        payment_intent_id="pi_test",
    )
    result = _process_capture_for_booking(test_booking.id, "test")
    assert result.get("already_captured") is True


def test_capture_task_skips_not_authorized_booking(db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.COMPLETED,
        payment_status="scheduled",
        payment_intent_id="pi_test",
    )
    result = _process_capture_for_booking(test_booking.id, "test")
    assert result.get("skipped") is True
    assert result.get("reason") == "not_eligible"


def test_cancel_idempotent_for_already_cancelled(client, auth_headers_student, db, test_booking):
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CANCELLED,
        cancelled_at=datetime.now(timezone.utc),
    )

    from unittest.mock import patch

    with patch("app.routes.v1.bookings.booking_lock", _lock_available):
        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            json={"reason": "Double cancel attempt"},
            headers=auth_headers_student,
        )

    assert response.status_code == 200
