"""
Integration tests that simulate booking race conditions using deterministic locks.

These tests avoid real concurrency by forcing lock outcomes.
"""

from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import status
import pytest

from app.api.dependencies.services import get_booking_service
from app.main import fastapi_app as app
from app.models.booking import BookingStatus
from app.models.booking_payment import BookingPayment
from app.services.booking_service import BookingService
from app.tasks.payment_tasks import capture_completed_lessons, process_scheduled_authorizations


@pytest.fixture
def mock_booking_service():
    service = MagicMock(spec=BookingService)
    service.db = MagicMock()
    service.cancel_booking = MagicMock()
    return service


@pytest.fixture
def client_with_mock_booking_service(client, mock_booking_service):
    app.dependency_overrides[get_booking_service] = lambda: mock_booking_service
    yield client
    app.dependency_overrides.clear()


_PAYMENT_FIELDS = {
    "payment_status", "payment_intent_id", "payment_method_id",
    "auth_scheduled_for", "auth_attempted_at", "auth_failure_count",
    "auth_last_error", "auth_failure_first_email_sent_at",
    "auth_failure_t13_warning_sent_at", "credits_reserved_cents",
    "settlement_outcome", "instructor_payout_amount",
    "capture_failed_at", "capture_escalated_at", "capture_retry_count",
    "capture_error",
}


def _update_booking(db, booking, **updates):
    from app.core.ulid_helper import generate_ulid

    payment_updates = {k: v for k, v in updates.items() if k in _PAYMENT_FIELDS}
    booking_updates = {k: v for k, v in updates.items() if k not in _PAYMENT_FIELDS}
    for key, value in booking_updates.items():
        setattr(booking, key, value)
    if payment_updates:
        bp = db.query(BookingPayment).filter_by(booking_id=booking.id).first()
        if bp is None:
            bp = BookingPayment(id=generate_ulid(), booking_id=booking.id)
            db.add(bp)
        for key, value in payment_updates.items():
            setattr(bp, key, value)
        db.flush()
        booking.payment_detail = bp
    db.commit()
    return booking


def _lock_unavailable_factory(calls):
    @contextmanager
    def _lock(booking_id, *args, **kwargs):
        calls.append(str(booking_id))
        yield False

    return _lock


def test_cancel_vs_capture_lock_blocks_capture(db, test_booking):
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


def test_double_cancel_second_request_gets_429(
    client_with_mock_booking_service, auth_headers_student, mock_booking_service, test_booking
):
    mock_booking_service.cancel_booking.return_value = test_booking
    call_state = {"count": 0}

    @asynccontextmanager
    async def _lock_sequence(*_args, **_kwargs):
        call_state["count"] += 1
        yield call_state["count"] == 1

    with patch("app.routes.v1.bookings.booking_lock", _lock_sequence):
        first = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            json={"reason": "Race test"},
            headers=auth_headers_student,
        )
        second = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            json={"reason": "Race test"},
            headers=auth_headers_student,
        )

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"] == "Operation in progress"
    assert mock_booking_service.cancel_booking.call_count == 1


def test_auth_job_skips_cancelled_after_read(db, test_booking):
    now = datetime.now(timezone.utc)
    _update_booking(
        db,
        test_booking,
        status=BookingStatus.CONFIRMED,
        payment_status="scheduled",
        payment_method_id="pm_test",
        booking_start_utc=now + timedelta(hours=24),
    )

    @contextmanager
    def _lock_and_cancel(booking_id, *args, **kwargs):
        if str(booking_id) == test_booking.id:
            test_booking.status = BookingStatus.CANCELLED
            test_booking.cancelled_at = datetime.now(timezone.utc)
            db.commit()
        yield True

    with patch("app.tasks.payment_tasks.booking_lock_sync", _lock_and_cancel):
        result = process_scheduled_authorizations()

    assert result["success"] == 0
    assert result["failed"] == 0
    assert test_booking.status == BookingStatus.CANCELLED
