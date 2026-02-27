"""Additional retry-flow branch coverage for payment tasks."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.booking import BookingStatus, PaymentStatus
from app.tasks import payment_tasks


@contextmanager
def _lock(acquired: bool = True):
    yield acquired


def test_retry_failed_authorizations_warn_only_skips_if_warning_already_sent():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking-warn-only")

    db_read = MagicMock()
    db_warn = MagicMock()

    warned_booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        capture_failed_at=None,
        auth_failure_t13_warning_sent_at=now,
    )
    db_warn.query.return_value.filter.return_value.first.return_value = warned_booking

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    payment_repo_read = MagicMock()

    def _payment_repo_for(db):
        return payment_repo_read if db is db_read else MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                side_effect=_payment_repo_for,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=12, minutes=45),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=12.75,
                    ):
                        with patch(
                            "app.tasks.payment_tasks._should_retry_auth",
                            return_value=False,
                        ):
                            with patch(
                                "app.tasks.payment_tasks.has_event_type",
                                return_value=False,
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.booking_lock_sync",
                                    return_value=_lock(True),
                                ):
                                    result = payment_tasks.retry_failed_authorizations()

    assert result["warnings_sent"] == 0
    assert result["retried"] == 0
    db_warn.commit.assert_called()


def test_retry_failed_authorizations_retries_in_t13_window_without_warning_branch():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking-retry")

    db_read = MagicMock()
    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]
    payment_repo_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=payment_repo_read,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=12, minutes=30),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=12.5,
                    ):
                        with patch(
                            "app.tasks.payment_tasks._should_retry_auth",
                            return_value=True,
                        ):
                            with patch(
                                "app.tasks.payment_tasks.has_event_type",
                                return_value=True,
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.booking_lock_sync",
                                    return_value=_lock(True),
                                ):
                                    with patch(
                                        "app.tasks.payment_tasks._process_retry_authorization",
                                        return_value={"success": True},
                                    ):
                                        result = payment_tasks.retry_failed_authorizations()

    assert result["retried"] == 1
    assert result["success"] == 1
    assert result["failed"] == 0


def test_retry_failed_authorizations_counts_processing_exceptions_as_failed():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking-error")

    db_read = MagicMock()
    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]
    payment_repo_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=payment_repo_read,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=20),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=20,
                    ):
                        with patch(
                            "app.tasks.payment_tasks._should_retry_auth",
                            return_value=True,
                        ):
                            with patch(
                                "app.tasks.payment_tasks.booking_lock_sync",
                                return_value=_lock(True),
                            ):
                                with patch(
                                    "app.tasks.payment_tasks._process_retry_authorization",
                                    side_effect=RuntimeError("retry-boom"),
                                ):
                                    result = payment_tasks.retry_failed_authorizations()

    assert result["retried"] == 0
    assert result["failed"] == 1
