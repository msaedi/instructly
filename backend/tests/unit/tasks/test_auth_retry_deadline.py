"""
Unit tests for authorization retry deadline (T-12h).
"""

from contextlib import contextmanager
from datetime import date, time
from unittest.mock import MagicMock, patch

import ulid

from app.models.booking import Booking, BookingStatus
from app.tasks.payment_tasks import retry_failed_authorizations


@contextmanager
def _always_acquire_lock(*_args, **_kwargs):
    yield True


def _make_booking() -> Booking:
    booking = MagicMock(spec=Booking)
    booking.id = str(ulid.ULID())
    booking.status = BookingStatus.CONFIRMED
    booking.payment_status = "auth_failed"
    booking.payment_method_id = "pm_deadline"
    booking.student_id = "student_deadline"
    booking.instructor_id = "instructor_deadline"
    booking.booking_date = date.today()
    booking.start_time = time(10, 0)
    booking.lesson_timezone = "America/New_York"
    return booking


def test_cancels_at_12h_deadline():
    booking = _make_booking()

    mock_payment_repo = MagicMock()
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    with patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
        return_value=mock_payment_repo,
    ), patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
        return_value=mock_booking_repo,
    ), patch(
        "app.database.SessionLocal",
        return_value=MagicMock(),
    ), patch(
        "app.tasks.payment_tasks.booking_lock_sync",
        _always_acquire_lock,
    ), patch(
        "app.tasks.payment_tasks.TimezoneService.hours_until",
        return_value=11.0,
    ), patch(
        "app.tasks.payment_tasks._cancel_booking_payment_failed",
        return_value=True,
    ) as mock_cancel, patch(
        "app.tasks.payment_tasks._process_retry_authorization"
    ) as mock_retry:
        result = retry_failed_authorizations()

    assert result["cancelled"] == 1
    assert result["retried"] == 0
    mock_cancel.assert_called_once()
    mock_retry.assert_not_called()


def test_retries_before_12h_deadline():
    booking = _make_booking()

    mock_payment_repo = MagicMock()
    mock_payment_repo.get_payment_events_for_booking.return_value = []
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    with patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
        return_value=mock_payment_repo,
    ), patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
        return_value=mock_booking_repo,
    ), patch(
        "app.database.SessionLocal",
        return_value=MagicMock(),
    ), patch(
        "app.tasks.payment_tasks.booking_lock_sync",
        _always_acquire_lock,
    ), patch(
        "app.tasks.payment_tasks.TimezoneService.hours_until",
        return_value=14.0,
    ), patch(
        "app.tasks.payment_tasks._process_retry_authorization",
        return_value={"success": True},
    ) as mock_retry:
        result = retry_failed_authorizations()

    assert result["cancelled"] == 0
    assert result["retried"] == 1
    assert result["success"] == 1
    mock_retry.assert_called_once()


def test_exactly_12h_triggers_cancel():
    booking = _make_booking()

    mock_payment_repo = MagicMock()
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    with patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
        return_value=mock_payment_repo,
    ), patch(
        "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
        return_value=mock_booking_repo,
    ), patch(
        "app.database.SessionLocal",
        return_value=MagicMock(),
    ), patch(
        "app.tasks.payment_tasks.booking_lock_sync",
        _always_acquire_lock,
    ), patch(
        "app.tasks.payment_tasks.TimezoneService.hours_until",
        return_value=12.0,
    ), patch(
        "app.tasks.payment_tasks._cancel_booking_payment_failed",
        return_value=True,
    ) as mock_cancel:
        result = retry_failed_authorizations()

    assert result["cancelled"] == 1
    mock_cancel.assert_called_once()
