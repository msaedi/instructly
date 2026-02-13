"""Additional coverage tests for payment_tasks helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from app.models.booking import BookingStatus, PaymentStatus
from app.repositories.base_repository import RepositoryException
from app.tasks import payment_tasks


@contextmanager
def _lock(acquired: bool):
    yield acquired


def test_should_retry_auth_intervals():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    booking = SimpleNamespace(payment_detail=SimpleNamespace(auth_attempted_at=None, auth_failure_count=0))
    assert payment_tasks._should_retry_auth(booking, now) is True

    booking = SimpleNamespace(
        payment_detail=SimpleNamespace(auth_attempted_at=now - timedelta(hours=2), auth_failure_count=1)
    )
    assert payment_tasks._should_retry_auth(booking, now) is True

    booking = SimpleNamespace(
        payment_detail=SimpleNamespace(auth_attempted_at=now - timedelta(hours=2), auth_failure_count=2)
    )
    assert payment_tasks._should_retry_auth(booking, now) is False


def test_should_retry_capture():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    booking = SimpleNamespace(payment_detail=SimpleNamespace(capture_failed_at=None))
    assert payment_tasks._should_retry_capture(booking, now) is False

    booking = SimpleNamespace(payment_detail=SimpleNamespace(capture_failed_at=now - timedelta(hours=5)))
    assert payment_tasks._should_retry_capture(booking, now) is True


def test_has_event_type():
    payment_repo = MagicMock()
    payment_repo.get_payment_events_for_booking.return_value = [
        SimpleNamespace(event_type="foo"),
        SimpleNamespace(event_type="bar"),
    ]

    assert payment_tasks.has_event_type(payment_repo, "booking", "bar") is True
    assert payment_tasks.has_event_type(payment_repo, "booking", "missing") is False


def test_resolve_locked_booking_from_task_commits():
    db = MagicMock()

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.services.booking_service.BookingService") as booking_service:
            booking_service.return_value.resolve_lock_for_booking.return_value = {
                "success": True
            }
            result = payment_tasks._resolve_locked_booking_from_task("lock_id", "resolved")

    assert result["success"] is True


def test_process_scheduled_authorizations_skips_when_not_due():
    now = datetime.now(timezone.utc)
    future_booking = SimpleNamespace(
        id="booking_future",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now + timedelta(hours=1),
        ),
        student_id="student-1",
        booking_start_utc=now + timedelta(hours=24),
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [future_booking]
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._process_authorization_for_booking"
            ) as process_mock:
                result = payment_tasks.process_scheduled_authorizations()

    assert result["success"] == 0
    assert result["failed"] == 0
    process_mock.assert_not_called()


def test_retry_failed_authorizations_cancels_when_due():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=10.0,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            return_value=_lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._cancel_booking_payment_failed",
                                return_value=True,
                            ):
                                result = payment_tasks.retry_failed_authorizations()

    assert result["cancelled"] == 1


def test_check_immediate_auth_timeout_cancelled_status():
    booking = SimpleNamespace(
        status=BookingStatus.CANCELLED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        ),
    )
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"skipped": True, "reason": "cancelled"}


def test_retry_failed_captures_skips_when_not_capture_failure():
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            capture_failed_at=None,
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.retry_failed_captures()

    assert result["skipped"] == 1


def test_escalate_capture_failure_handles_payment_record_error():
    now = datetime.now(timezone.utc)
    booking_read = SimpleNamespace(
        id="booking_id",
        instructor_id="instructor_id",
        student_id="student_id",
    )
    booking_write = SimpleNamespace(
        id="booking_id",
        instructor_id="instructor_id",
        student_id="student_id",
        payout_transfer_retry_count=0,
        transfer_retry_count=0,
        payment_detail=SimpleNamespace(payment_status=None),
    )
    student = SimpleNamespace(account_locked=False)

    db_read = MagicMock()
    db_read.query.return_value.filter.return_value.first.return_value = booking_read
    db_write = MagicMock()

    from app.models.booking_payment import BookingPayment as BP

    def _query_side_effect(model):
        query = MagicMock()
        if model is payment_tasks.Booking:
            query.options.return_value.filter.return_value.first.return_value = booking_write
        elif model is payment_tasks.User:
            query.filter.return_value.first.return_value = student
        elif model is BP:
            query.filter.return_value.one_or_none.return_value = booking_write.payment_detail
        else:
            query.filter.return_value.first.return_value = None
        return query

    db_write.query.side_effect = _query_side_effect

    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.side_effect = RepositoryException("boom")

    instructor_repo = MagicMock()
    instructor_repo.get_by_user_id.return_value = None

    pricing_service = MagicMock()
    pricing_service.compute_booking_pricing.return_value = {
        "target_instructor_payout_cents": 0
    }

    with patch("app.database.SessionLocal", side_effect=[db_read, db_write]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_instructor_profile_repository",
                return_value=instructor_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.PricingService",
                    return_value=pricing_service,
                ):
                    payment_tasks._escalate_capture_failure("booking_id", now)

    assert booking_write.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value


def test_capture_completed_lessons_skips_expired_when_cancelled():
    now = datetime.now(timezone.utc)
    booking_repo = MagicMock()
    payment_repo = MagicMock()

    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = [
        SimpleNamespace(id="booking_id", status=BookingStatus.CONFIRMED)
    ]

    payment_repo.get_payment_events_for_booking.return_value = [
        SimpleNamespace(
            event_type="auth_succeeded",
            created_at=now - timedelta(days=8),
        )
    ]

    db_read = MagicMock()
    db_expired = MagicMock()
    db_expired.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.CANCELLED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.AUTHORIZED.value),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_expired]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.booking_lock_sync",
                    return_value=_lock(True),
                ):
                    result = payment_tasks.capture_completed_lessons()

    assert result["expired_handled"] == 0


def test_attempt_payment_capture_skips_cancelled_already_captured():
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CANCELLED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.SETTLED.value),
    )
    payment_repo = MagicMock()
    stripe_service = MagicMock()

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking=booking,
            payment_repo=payment_repo,
            capture_reason="manual",
            stripe_service=stripe_service,
        )

    assert result == {"success": True, "already_captured": True}


def test_capture_late_cancellation_retries_on_exception():
    task = payment_tasks.capture_late_cancellation

    with patch.object(task, "retry", side_effect=RuntimeError("retry")) as retry_mock:
        with patch(
            "app.tasks.payment_tasks.booking_lock_sync", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError):
                task.run("booking_id")

    retry_mock.assert_called_once()


def test_resolve_undisputed_no_shows_handles_exception():
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_no_show_reports_due_for_resolution.return_value = [booking]

    booking_service = MagicMock()
    booking_service.resolve_no_show.side_effect = RuntimeError("boom")

    db = MagicMock()

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.BookingService",
                return_value=booking_service,
            ):
                with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
                    result = payment_tasks.resolve_undisputed_no_shows()

    assert result["failed"] == 1
    db.close.assert_called_once()


def test_mark_child_booking_settled_updates_status():
    booking = SimpleNamespace(id="booking_id", payment_detail=SimpleNamespace(payment_status=None))
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch(
            "app.repositories.booking_repository.BookingRepository.ensure_payment",
            return_value=booking.payment_detail,
        ):
            payment_tasks._mark_child_booking_settled("booking_id")

    assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_check_immediate_auth_timeout_skip_when_lock_unavailable():
    db = MagicMock()

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(False)):
            result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"skipped": True}
    db.close.assert_called_once()


def test_check_immediate_auth_timeout_retry_window_open():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            auth_attempted_at=now - timedelta(minutes=10),
        ),
    )
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"skipped": True, "reason": "retry_window_open"}


def test_check_immediate_auth_timeout_cancelled():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            auth_attempted_at=now - timedelta(hours=1),
        ),
    )
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._cancel_booking_payment_failed",
                return_value=True,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=1),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=1.0,
                    ):
                        result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"cancelled": True}


def test_process_scheduled_authorizations_sends_first_failure_email():
    now = datetime.now(timezone.utc)
    scheduled_booking = SimpleNamespace(
        id="booking_scheduled",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now - timedelta(minutes=5),
        ),
        student_id="student-1",
    )
    legacy_booking = SimpleNamespace(
        id="booking_legacy",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=None,
        ),
        student_id="student-2",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [
        scheduled_booking,
        legacy_booking,
    ]

    db_read = MagicMock()
    db_notify = MagicMock()
    db_notify.query.return_value.options.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(
            id="booking_id",
            payment_detail=SimpleNamespace(auth_failure_first_email_sent_at=None),
        ),
        SimpleNamespace(
            id="booking_id",
            payment_detail=SimpleNamespace(auth_failure_first_email_sent_at=None),
        ),
    ]
    payment_repo = MagicMock()
    payment_repo.get_payment_events_for_booking.return_value = []

    with patch("app.database.SessionLocal", side_effect=[db_read, db_notify, db_notify]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=24),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        side_effect=[24.0, 24.0],
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            side_effect=lambda *_args, **_kwargs: _lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._process_authorization_for_booking",
                                return_value={"success": False, "error": "boom"},
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.NotificationService"
                                ) as notification_cls:
                                    with patch(
                                        "app.repositories.booking_repository.BookingRepository.ensure_payment",
                                        side_effect=lambda *a, **kw: SimpleNamespace(auth_failure_first_email_sent_at=None),
                                    ):
                                        result = payment_tasks.process_scheduled_authorizations()

    assert result["failed"] == 2
    assert notification_cls.return_value.send_final_payment_warning.call_count == 2
    assert payment_repo.create_payment_event.call_count == 2


def test_process_scheduled_authorizations_skips_duplicate_email():
    now = datetime.now(timezone.utc)
    scheduled_booking = SimpleNamespace(
        id="booking_scheduled",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now - timedelta(minutes=5),
        ),
        student_id="student-1",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [scheduled_booking]

    db_read = MagicMock()
    db_notify = MagicMock()
    db_notify.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id="booking_id",
        payment_detail=SimpleNamespace(auth_failure_first_email_sent_at=now),
    )
    payment_repo = MagicMock()
    payment_repo.get_payment_events_for_booking.return_value = []

    with patch("app.database.SessionLocal", side_effect=[db_read, db_notify]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=24),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=24.0,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            return_value=_lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._process_authorization_for_booking",
                                return_value={"success": False, "error": "boom"},
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.NotificationService"
                                ) as notification_cls:
                                    result = payment_tasks.process_scheduled_authorizations()

    assert result["failed"] == 1
    notification_cls.return_value.send_final_payment_warning.assert_not_called()
    payment_repo.create_payment_event.assert_not_called()


def test_process_scheduled_authorizations_records_failure_on_exception():
    now = datetime.now(timezone.utc)
    scheduled_booking = SimpleNamespace(
        id="booking_scheduled",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now - timedelta(minutes=5),
        ),
        student_id="student-1",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [scheduled_booking]

    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_start_utc",
                return_value=now + timedelta(hours=24),
            ):
                with patch(
                    "app.tasks.payment_tasks.TimezoneService.hours_until",
                    return_value=24.0,
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        return_value=_lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._process_authorization_for_booking",
                            side_effect=RuntimeError("boom"),
                        ):
                            result = payment_tasks.process_scheduled_authorizations()

    assert result["failed"] == 1
    assert result["failures"][0]["error"] == "boom"


def test_process_scheduled_authorizations_skips_email_when_event_already_exists():
    now = datetime.now(timezone.utc)
    scheduled_booking = SimpleNamespace(
        id="booking_scheduled",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now - timedelta(minutes=5),
        ),
        student_id="student-1",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [scheduled_booking]

    db_read = MagicMock()
    db_notify = MagicMock()
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_notify]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=24),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=24.0,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            return_value=_lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._process_authorization_for_booking",
                                return_value={"success": False, "error": "boom"},
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.has_event_type",
                                    return_value=True,
                                ):
                                    with patch(
                                        "app.tasks.payment_tasks.NotificationService"
                                    ) as notification_cls:
                                        result = payment_tasks.process_scheduled_authorizations()

    assert result["failed"] == 1
    notification_cls.return_value.send_final_payment_warning.assert_not_called()


def test_process_scheduled_authorizations_handles_missing_booking_for_email():
    now = datetime.now(timezone.utc)
    scheduled_booking = SimpleNamespace(
        id="booking_scheduled",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            auth_scheduled_for=now - timedelta(minutes=5),
        ),
        student_id="student-1",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [scheduled_booking]

    db_read = MagicMock()
    db_notify = MagicMock()
    db_notify.query.return_value.options.return_value.filter.return_value.first.return_value = None
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_notify]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=24),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=24.0,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            return_value=_lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._process_authorization_for_booking",
                                return_value={"success": False, "error": "boom"},
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.has_event_type",
                                    return_value=False,
                                ):
                                    result = payment_tasks.process_scheduled_authorizations()

    assert result["failed"] == 1


def test_process_authorization_for_booking_phase3_missing():
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SCHEDULED.value,
            payment_method_id="pm_1",
            payment_intent_id=None,
        ),
        student_id="student-1",
        instructor_id="instructor-1",
    )

    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking
    db3 = MagicMock()
    db3.query.return_value.options.return_value.filter.return_value.first.return_value = None

    payment_repo = MagicMock()
    payment_repo.get_customer_by_user_id.return_value = None

    with patch("app.database.SessionLocal", side_effect=[db1, db3]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            result = payment_tasks._process_authorization_for_booking(booking.id, 24.0)

    assert result["error"] == "Booking not found in Phase 3"


def test_retry_failed_authorizations_warn_only_sends_warning():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    db_warn = MagicMock()
    booking_warn = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=None,
            auth_failure_t13_warning_sent_at=None,
        ),
    )
    db_warn.query.return_value.options.return_value.filter.return_value.first.return_value = booking_warn

    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=12.5,
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
                                    with patch(
                                        "app.tasks.payment_tasks.NotificationService"
                                    ) as notification_cls:
                                        with patch(
                                            "app.repositories.booking_repository.BookingRepository.ensure_payment",
                                            return_value=booking_warn.payment_detail,
                                        ):
                                            result = payment_tasks.retry_failed_authorizations()

    assert result["warnings_sent"] == 1
    assert result["retried"] == 0
    notification_cls.return_value.send_final_payment_warning.assert_called_once()


def test_retry_failed_authorizations_warn_only_skips_when_already_sent():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    db_warn = MagicMock()
    db_warn.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=None,
            auth_failure_t13_warning_sent_at=now,
        ),
    )

    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=12.5,
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
                                    with patch(
                                        "app.tasks.payment_tasks.NotificationService"
                                    ) as notification_cls:
                                        result = payment_tasks.retry_failed_authorizations()

    assert result["warnings_sent"] == 0
    notification_cls.return_value.send_final_payment_warning.assert_not_called()


def test_retry_failed_authorizations_retry_with_warning_skipped():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
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
                                        return_value={"skipped": True},
                                    ):
                                        result = payment_tasks.retry_failed_authorizations()

    assert result["retried"] == 0
    assert result["failed"] == 0


def test_retry_failed_authorizations_silent_retry_skipped():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_start_utc",
                return_value=now,
            ):
                with patch(
                    "app.tasks.payment_tasks.TimezoneService.hours_until",
                    return_value=20.0,
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
                                return_value={"skipped": True},
                            ):
                                result = payment_tasks.retry_failed_authorizations()

    assert result["retried"] == 0
    assert result["failed"] == 0


def test_retry_failed_authorizations_handles_exception():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_start_utc",
                return_value=now,
            ):
                with patch(
                    "app.tasks.payment_tasks.TimezoneService.hours_until",
                    return_value=20.0,
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
                                side_effect=RuntimeError("boom"),
                            ):
                                result = payment_tasks.retry_failed_authorizations()

    assert result["failed"] == 1


def test_retry_failed_authorizations_cancel_path_noop_when_cancel_returns_false():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=MagicMock(),
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=11.5,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.booking_lock_sync",
                            return_value=_lock(True),
                        ):
                            with patch(
                                "app.tasks.payment_tasks._cancel_booking_payment_failed",
                                return_value=False,
                            ):
                                result = payment_tasks.retry_failed_authorizations()

    assert result["cancelled"] == 0
    assert result["failed"] == 0


def test_check_immediate_auth_timeout_booking_not_found():
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = None

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"error": "Booking not found"}


def test_check_immediate_auth_timeout_resolved():
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            auth_attempted_at=None,
        ),
    )
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"resolved": True}


def test_check_immediate_auth_timeout_attempted_at_missing():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            auth_attempted_at=None,
        ),
    )
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._cancel_booking_payment_failed",
                return_value=True,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now + timedelta(hours=1),
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=1.0,
                    ):
                        result = payment_tasks.check_immediate_auth_timeout("booking_id")

    assert result == {"cancelled": True}


def test_retry_failed_captures_skips_when_lock_unavailable():
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(False)):
            result = payment_tasks.retry_failed_captures()

    assert result["skipped"] == 1


def test_retry_failed_captures_skips_when_booking_missing():
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = None

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            result = payment_tasks.retry_failed_captures()

    assert result["skipped"] == 1


def test_retry_failed_captures_escalates_after_72_hours():
    now = datetime.now(timezone.utc)
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=80),
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._escalate_capture_failure"
            ) as escalate_mock:
                result = payment_tasks.retry_failed_captures()

    escalate_mock.assert_called_once()
    assert result["escalated"] == 1


def test_retry_failed_captures_skips_when_not_ready():
    now = datetime.now(timezone.utc)
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=1),
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._should_retry_capture",
                return_value=False,
            ):
                result = payment_tasks.retry_failed_captures()

    assert result["skipped"] == 1


def test_retry_failed_captures_processes_success():
    now = datetime.now(timezone.utc)
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=5),
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._process_capture_for_booking",
                return_value={"success": True},
            ):
                result = payment_tasks.retry_failed_captures()

    assert result["retried"] == 1
    assert result["succeeded"] == 1


def test_retry_failed_captures_skips_when_process_capture_skipped():
    now = datetime.now(timezone.utc)
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=5),
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._process_capture_for_booking",
                return_value={"skipped": True},
            ):
                result = payment_tasks.retry_failed_captures()

    assert result["skipped"] == 1


def test_retry_failed_captures_handles_exception():
    now = datetime.now(timezone.utc)
    db_read = MagicMock()
    db_read.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id="booking_id")
    ]
    db_check = MagicMock()
    db_check.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=5),
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks._process_capture_for_booking",
                side_effect=RuntimeError("boom"),
            ):
                result = payment_tasks.retry_failed_captures()

    assert result["retried"] == 0
    assert result["succeeded"] == 0


def test_escalate_capture_failure_returns_when_booking_missing():
    db_read = MagicMock()
    db_read.query.return_value.filter.return_value.first.return_value = None

    with patch("app.database.SessionLocal", return_value=db_read):
        payment_tasks._escalate_capture_failure("booking_id", datetime.now(timezone.utc))


def test_escalate_capture_failure_transfer_error():
    now = datetime.now(timezone.utc)
    booking_read = SimpleNamespace(
        id="booking_id",
        instructor_id="instructor_id",
        student_id="student_id",
    )
    booking_write = SimpleNamespace(
        id="booking_id",
        instructor_id="instructor_id",
        student_id="student_id",
        payout_transfer_retry_count=0,
        transfer_retry_count=0,
        payment_detail=SimpleNamespace(payment_status=None),
    )
    student = SimpleNamespace(account_locked=False)

    db_read = MagicMock()
    db_read.query.return_value.filter.return_value.first.return_value = booking_read
    db_stripe = MagicMock()
    db_write = MagicMock()

    from app.models.booking_payment import BookingPayment as BP

    def _query_side_effect(model):
        query = MagicMock()
        if model is payment_tasks.Booking:
            query.options.return_value.filter.return_value.first.return_value = booking_write
        elif model is payment_tasks.User:
            query.filter.return_value.first.return_value = student
        elif model is BP:
            query.filter.return_value.one_or_none.return_value = booking_write.payment_detail
        else:
            query.filter.return_value.first.return_value = None
        return query

    db_write.query.side_effect = _query_side_effect

    payment_record = SimpleNamespace(instructor_payout_cents="invalid")
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = payment_record
    payment_repo.get_connected_account_by_instructor_id.return_value = SimpleNamespace(
        stripe_account_id="acct_123"
    )

    instructor_repo = MagicMock()
    instructor_repo.get_by_user_id.return_value = SimpleNamespace(id="profile_id")

    pricing_service = MagicMock()
    pricing_service.compute_booking_pricing.return_value = {
        "target_instructor_payout_cents": 500
    }

    stripe_service = MagicMock()
    stripe_service.create_manual_transfer.side_effect = RuntimeError("transfer failed")

    with patch("app.database.SessionLocal", side_effect=[db_read, db_stripe, db_write]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_instructor_profile_repository",
                return_value=instructor_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.PricingService",
                    return_value=pricing_service,
                ):
                    with patch(
                        "app.tasks.payment_tasks.StripeService",
                        return_value=stripe_service,
                    ):
                        with patch("app.tasks.payment_tasks.ConfigService"):
                            payment_tasks._escalate_capture_failure("booking_id", now)

    assert booking_write.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert student.account_locked is True


def test_handle_authorization_failure_sets_status():
    booking = SimpleNamespace(id="booking_id", payment_detail=SimpleNamespace(payment_status=None))
    payment_repo = MagicMock()

    with patch("sqlalchemy.orm.object_session", return_value=MagicMock()):
        with patch(
            "app.repositories.booking_repository.BookingRepository.ensure_payment",
            return_value=booking.payment_detail,
        ):
            payment_tasks.handle_authorization_failure(
                booking=booking,
                payment_repo=payment_repo,
                error="boom",
                error_type="card_declined",
                hours_until_lesson=12.0,
            )

    assert booking.payment_detail.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    payment_repo.create_payment_event.assert_called_once()


def test_process_capture_for_booking_locked_funds():
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.AUTHORIZED.value),
        rescheduled_from_booking_id="locked_parent",
        has_locked_funds=True,
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db1):
        with patch(
            "app.tasks.payment_tasks._resolve_locked_booking_from_task",
            return_value={"success": True},
        ):
            with patch(
                "app.tasks.payment_tasks._mark_child_booking_settled"
            ) as mark_mock:
                result = payment_tasks._process_capture_for_booking(
                    booking.id,
                    "instructor_completed",
                )

    assert result["reason"] == "locked_funds"
    mark_mock.assert_called_once_with(booking.id)


def test_process_capture_for_booking_locked_funds_without_settle_when_resolution_fails():
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.AUTHORIZED.value),
        rescheduled_from_booking_id="locked_parent",
        has_locked_funds=True,
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    with patch("app.database.SessionLocal", return_value=db1):
        with patch(
            "app.tasks.payment_tasks._resolve_locked_booking_from_task",
            return_value={"success": False, "skipped": False},
        ):
            with patch("app.tasks.payment_tasks._mark_child_booking_settled") as mark_mock:
                result = payment_tasks._process_capture_for_booking(
                    booking.id,
                    "instructor_completed",
                )

    assert result["reason"] == "locked_funds"
    mark_mock.assert_not_called()


def test_process_capture_for_booking_already_captured():
    booking_phase1 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        rescheduled_from_booking_id=None,
        has_locked_funds=False,
    )
    booking_phase3 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
            credits_reserved_cents=100,
        ),
    )

    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase1
    db_stripe = MagicMock()
    db3 = MagicMock()
    db3.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase3

    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="Already been captured",
        param="payment_intent",
    )

    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.side_effect = RepositoryException("boom")

    with patch("app.database.SessionLocal", side_effect=[db1, db_stripe, db3]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.StripeService",
                return_value=stripe_service,
            ):
                with patch("app.tasks.payment_tasks.ConfigService"):
                    with patch("app.tasks.payment_tasks.PricingService"):
                        with patch(
                            "app.services.credit_service.CreditService"
                        ) as credit_cls:
                            credit_cls.return_value.forfeit_credits_for_booking.side_effect = (
                                RuntimeError("boom")
                            )
                            with patch(
                                "app.repositories.booking_repository.BookingRepository.ensure_payment",
                                return_value=booking_phase3.payment_detail,
                            ):
                                result = payment_tasks._process_capture_for_booking(
                                    "booking_id",
                                    "instructor_completed",
                                )

    assert result.get("already_captured") is True
    assert booking_phase3.payment_detail.payment_status == PaymentStatus.SETTLED.value
    payment_repo.create_payment_event.assert_called_once()


def test_process_capture_for_booking_phase3_missing():
    booking_phase1 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        rescheduled_from_booking_id=None,
        has_locked_funds=False,
    )

    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase1
    db_stripe = MagicMock()
    db3 = MagicMock()
    db3.query.return_value.options.return_value.filter.return_value.first.return_value = None

    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.return_value = {
        "payment_intent": SimpleNamespace(amount_received=100),
        "amount_received": 100,
    }

    with patch("app.database.SessionLocal", side_effect=[db1, db_stripe, db3]):
        with patch(
            "app.tasks.payment_tasks.StripeService",
            return_value=stripe_service,
        ):
            with patch("app.tasks.payment_tasks.ConfigService"):
                with patch("app.tasks.payment_tasks.PricingService"):
                    result = payment_tasks._process_capture_for_booking(
                        "booking_id",
                        "instructor_completed",
                    )

    assert result["error"] == "Booking not found in Phase 3"


def test_auto_complete_booking_locked_funds():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        has_locked_funds=True,
        rescheduled_from_booking_id="parent_id",
        instructor_id="instructor_id",
        student_id="student_id",
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=db1):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_end_utc",
                return_value=now,
            ):
                with patch(
                    "app.tasks.payment_tasks._resolve_locked_booking_from_task",
                    return_value={"success": True},
                ):
                    with patch(
                        "app.tasks.payment_tasks._mark_child_booking_settled"
                    ) as mark_mock:
                        with patch(
                            "app.tasks.payment_tasks.StudentCreditService"
                        ) as credit_cls:
                            credit_cls.return_value.maybe_issue_milestone_credit = MagicMock()
                            with patch(
                                "app.services.referral_service.ReferralService"
                            ) as referral_cls:
                                referral_cls.return_value.on_instructor_lesson_completed = (
                                    MagicMock()
                                )
                                result = payment_tasks._auto_complete_booking(
                                    "booking_id",
                                    now,
                                )

    assert result["captured"] is True
    mark_mock.assert_called_once_with("booking_id")


def test_auto_complete_booking_locked_funds_resolution_failure_keeps_uncaptured():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        has_locked_funds=True,
        rescheduled_from_booking_id="parent_id",
        instructor_id="instructor_id",
        student_id="student_id",
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=db1):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_end_utc",
                return_value=now,
            ):
                with patch(
                    "app.tasks.payment_tasks._resolve_locked_booking_from_task",
                    return_value={"success": False, "skipped": False},
                ):
                    with patch(
                        "app.tasks.payment_tasks._mark_child_booking_settled"
                    ) as mark_mock:
                        with patch(
                            "app.tasks.payment_tasks.StudentCreditService"
                        ) as credit_cls:
                            credit_cls.return_value.maybe_issue_milestone_credit = MagicMock()
                            with patch(
                                "app.services.referral_service.ReferralService"
                            ) as referral_cls:
                                referral_cls.return_value.on_instructor_lesson_completed = (
                                    MagicMock()
                                )
                                result = payment_tasks._auto_complete_booking(
                                    "booking_id",
                                    now,
                                )

    assert result["captured"] is False
    mark_mock.assert_not_called()


def test_auto_complete_booking_no_payment_intent():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id=None,
        ),
        has_locked_funds=False,
        rescheduled_from_booking_id=None,
        instructor_id="instructor_id",
        student_id="student_id",
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking

    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=db1):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks._get_booking_end_utc",
                return_value=now,
            ):
                with patch(
                    "app.tasks.payment_tasks.StudentCreditService"
                ) as credit_cls:
                    credit_cls.return_value.maybe_issue_milestone_credit = MagicMock()
                    with patch(
                        "app.services.referral_service.ReferralService"
                    ) as referral_cls:
                        referral_cls.return_value.on_instructor_lesson_completed = MagicMock()
                        result = payment_tasks._auto_complete_booking(
                            "booking_id",
                            now,
                        )

    assert result["capture_attempted"] is False


def test_capture_completed_lessons_handles_capture_and_auto_complete_failures():
    now = datetime.now(timezone.utc)
    booking_capture = SimpleNamespace(
        id="capture_id",
        payment_detail=SimpleNamespace(payment_intent_id="pi_123"),
        has_locked_funds=False,
    )
    booking_auto = SimpleNamespace(id="auto_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = [booking_capture]
    booking_repo.get_bookings_for_auto_completion.return_value = [booking_auto]
    booking_repo.get_bookings_with_expired_auth.return_value = []

    payment_repo = MagicMock()
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    side_effect=[now - timedelta(hours=25), now - timedelta(hours=25)],
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        side_effect=lambda *_args, **_kwargs: _lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._process_capture_for_booking",
                            return_value={"success": False, "skipped": False},
                        ):
                            with patch(
                                "app.tasks.payment_tasks._auto_complete_booking",
                                return_value={
                                    "auto_completed": True,
                                    "captured": False,
                                    "capture_attempted": True,
                                },
                            ):
                                result = payment_tasks.capture_completed_lessons()

    assert result["failed"] == 2
    assert result["auto_completed"] == 1


def test_capture_completed_lessons_auto_loop_skips_when_lock_unavailable():
    now = datetime.now(timezone.utc)
    booking_auto = SimpleNamespace(id="auto_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = [booking_auto]
    booking_repo.get_bookings_with_expired_auth.return_value = []

    payment_repo = MagicMock()
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    return_value=now - timedelta(hours=25),
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        return_value=_lock(False),
                    ):
                        result = payment_tasks.capture_completed_lessons()

    assert result["captured"] == 0
    assert result["auto_completed"] == 0
    assert result["failed"] == 0


def test_capture_completed_lessons_auto_loop_counts_capture_without_auto_completed():
    now = datetime.now(timezone.utc)
    booking_auto = SimpleNamespace(id="auto_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = [booking_auto]
    booking_repo.get_bookings_with_expired_auth.return_value = []

    payment_repo = MagicMock()
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    return_value=now - timedelta(hours=25),
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        return_value=_lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._auto_complete_booking",
                            return_value={
                                "auto_completed": False,
                                "captured": True,
                                "capture_attempted": True,
                            },
                        ):
                            result = payment_tasks.capture_completed_lessons()

    assert result["captured"] == 1
    assert result["auto_completed"] == 0
    assert result["failed"] == 0


def test_capture_completed_lessons_marks_expired_auth():
    now = datetime.now(timezone.utc)
    booking_expired = SimpleNamespace(
        id="expired_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
            capture_retry_count=0,
        ),
    )
    auth_event = SimpleNamespace(
        event_type="auth_succeeded",
        created_at=now - timedelta(days=8),
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = [booking_expired]

    payment_repo = MagicMock()
    payment_repo.get_payment_events_for_booking.return_value = [auth_event]

    db_read = MagicMock()
    db_expired = MagicMock()
    db_expired.query.return_value.options.return_value.filter.return_value.first.return_value = booking_expired

    with patch("app.database.SessionLocal", side_effect=[db_read, db_expired]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.booking_lock_sync",
                    return_value=_lock(True),
                ):
                    with patch(
                        "app.repositories.booking_repository.BookingRepository.ensure_payment",
                        return_value=booking_expired.payment_detail,
                    ):
                        result = payment_tasks.capture_completed_lessons()

    assert result["expired_handled"] == 1
    assert booking_expired.payment_detail.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert booking_expired.payment_detail.capture_retry_count == 1
    payment_repo.create_payment_event.assert_called_once()


def test_attempt_payment_capture_skips_cancelled_settled():
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CANCELLED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.SETTLED.value,
            payment_intent_id="pi_123",
        ),
    )
    payment_repo = MagicMock()
    stripe_service = MagicMock()

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking,
            payment_repo,
            "test_reason",
            stripe_service,
        )

    assert result == {"success": True, "already_captured": True}


def test_create_new_authorization_and_capture_commit_error():
    """Pre-capture commit failure now returns early instead of proceeding to Stripe."""
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_intent_id="pi_old",
            payment_method_id="pm_1",
            payment_status=PaymentStatus.AUTHORIZED.value,
            credits_reserved_cents=100,
        ),
    )
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = SimpleNamespace(
        instructor_payout_cents="500"
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("boom")

    db_stripe = MagicMock()
    stripe_service = MagicMock()
    stripe_service.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
        id="pi_new"
    )
    stripe_service.capture_booking_payment_intent.return_value = {
        "amount_received": 100,
        "top_up_transfer_cents": 0,
    }

    with patch("app.database.SessionLocal", return_value=db_stripe):
        with patch(
            "app.tasks.payment_tasks.StripeService",
            return_value=stripe_service,
        ):
            with patch("app.tasks.payment_tasks.ConfigService"):
                with patch("app.tasks.payment_tasks.PricingService"):
                    with patch(
                        "app.services.credit_service.CreditService"
                    ) as credit_cls:
                        credit_cls.return_value.forfeit_credits_for_booking.side_effect = (
                            RuntimeError("boom")
                        )
                        with patch(
                            "app.repositories.booking_repository.BookingRepository.ensure_payment",
                            return_value=booking.payment_detail,
                        ):
                            result = payment_tasks.create_new_authorization_and_capture(
                                booking,
                                payment_repo,
                                db,
                                lock_acquired=True,
                            )

    assert result["success"] is False
    assert result["error"] == "pre_capture_commit_failed"
    # Stripe should NOT have been called since commit failed
    stripe_service.capture_booking_payment_intent.assert_not_called()


def test_resolve_undisputed_no_shows_skips_and_fails():
    booking_one = SimpleNamespace(id="booking_one")
    booking_two = SimpleNamespace(id="booking_two")

    booking_repo = MagicMock()
    booking_repo.get_no_show_reports_due_for_resolution.return_value = [
        booking_one,
        booking_two,
    ]
    booking_service = MagicMock()
    booking_service.resolve_no_show.return_value = {"success": False}

    db = MagicMock()
    lock_iter = iter([False, True])

    def _lock_side_effect(*_args, **_kwargs):
        return _lock(next(lock_iter))

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.BookingService",
                return_value=booking_service,
            ):
                with patch(
                    "app.tasks.payment_tasks.booking_lock_sync",
                    side_effect=_lock_side_effect,
                ):
                    result = payment_tasks.resolve_undisputed_no_shows()

    assert result["skipped"] == 1
    assert result["failed"] == 1


def test_check_authorization_health_flags_overdue():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [booking]
    payment_repo = MagicMock()
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value = query

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=booking_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=10.0,
                    ):
                        result = payment_tasks.check_authorization_health()

    assert result["overdue_count"] == 1


def test_audit_and_fix_payout_schedules_retries_on_error():
    db = MagicMock()
    with patch("app.database.SessionLocal", return_value=db):
        with patch(
            "app.tasks.payment_tasks.StripeService",
            side_effect=RuntimeError("boom"),
        ):
            with patch("app.tasks.payment_tasks.ConfigService"):
                with patch("app.tasks.payment_tasks.PricingService"):
                    with patch(
                        "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository"
                    ):
                        with patch.object(
                            payment_tasks.audit_and_fix_payout_schedules,
                            "retry",
                            side_effect=RuntimeError("retry"),
                        ):
                            with pytest.raises(RuntimeError):
                                payment_tasks.audit_and_fix_payout_schedules()


def test_capture_late_cancellation_already_captured():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
            settlement_outcome=None,
        ),
    )

    booking_repo = MagicMock()
    booking_repo.get_by_id.return_value = booking
    payment_repo = MagicMock()
    db = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="Already been captured",
        param="payment_intent",
    )

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                    return_value=booking_repo,
                ):
                    with patch(
                        "app.tasks.payment_tasks._get_booking_start_utc",
                        return_value=now,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.TimezoneService.hours_until",
                            return_value=5.0,
                        ):
                            with patch(
                                "app.tasks.payment_tasks.StripeService",
                                return_value=stripe_service,
                            ):
                                with patch("app.tasks.payment_tasks.ConfigService"):
                                    with patch("app.tasks.payment_tasks.PricingService"):
                                        result = payment_tasks.capture_late_cancellation(
                                            booking.id,
                                        )

    assert result["already_captured"] is True


def test_capture_late_cancellation_credit_service_failure():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
            settlement_outcome=None,
            credits_reserved_cents=100,
        ),
    )

    booking_repo = MagicMock()
    booking_repo.get_by_id.return_value = booking
    payment_repo = MagicMock()
    db = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.return_value = SimpleNamespace(
        amount_received=100
    )

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                    return_value=booking_repo,
                ):
                    with patch(
                        "app.tasks.payment_tasks._get_booking_start_utc",
                        return_value=now,
                    ):
                        with patch(
                            "app.tasks.payment_tasks.TimezoneService.hours_until",
                            return_value=5.0,
                        ):
                            with patch(
                                "app.tasks.payment_tasks.StripeService",
                                return_value=stripe_service,
                            ):
                                with patch("app.tasks.payment_tasks.ConfigService"):
                                    with patch("app.tasks.payment_tasks.PricingService"):
                                        with patch(
                                            "app.services.credit_service.CreditService"
                                        ) as credit_cls:
                                            credit_cls.return_value.forfeit_credits_for_booking.side_effect = (
                                                RuntimeError("boom")
                                            )
                                            result = payment_tasks.capture_late_cancellation(
                                                booking.id,
                                            )

    assert result["success"] is True


def test_capture_completed_lessons_capture_loop_exception_counts_failed():
    now = datetime.now(timezone.utc)
    booking_capture = SimpleNamespace(
        id="capture_id",
        payment_detail=SimpleNamespace(payment_intent_id="pi_capture"),
        has_locked_funds=False,
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = [booking_capture]
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = []

    payment_repo = MagicMock()
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    return_value=now - timedelta(hours=25),
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        return_value=_lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._process_capture_for_booking",
                            side_effect=RuntimeError("boom"),
                        ):
                            result = payment_tasks.capture_completed_lessons()

    assert result["captured"] == 0
    assert result["failed"] == 1


def test_capture_completed_lessons_auto_complete_loop_exception_counts_failed():
    now = datetime.now(timezone.utc)
    booking_auto = SimpleNamespace(id="auto_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = [booking_auto]
    booking_repo.get_bookings_with_expired_auth.return_value = []

    payment_repo = MagicMock()
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    return_value=now - timedelta(hours=25),
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        return_value=_lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._auto_complete_booking",
                            side_effect=RuntimeError("boom"),
                        ):
                            result = payment_tasks.capture_completed_lessons()

    assert result["auto_completed"] == 0
    assert result["failed"] == 1


def test_capture_completed_lessons_expired_auth_skip_paths_and_error_branch():
    now = datetime.now(timezone.utc)
    old_auth_event = SimpleNamespace(
        event_type="auth_succeeded",
        created_at=now - timedelta(days=8),
    )
    expired_candidates = [
        SimpleNamespace(id="b-lock", status=BookingStatus.CONFIRMED),
        SimpleNamespace(id="b-missing", status=BookingStatus.CONFIRMED),
        SimpleNamespace(id="b-manual", status=BookingStatus.CONFIRMED),
        SimpleNamespace(id="b-not-auth", status=BookingStatus.CONFIRMED),
        SimpleNamespace(id="b-error", status=BookingStatus.COMPLETED),
    ]

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = []
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = expired_candidates

    payment_repo = MagicMock()
    payment_repo.get_payment_events_for_booking.return_value = [old_auth_event]

    db_read = MagicMock()
    db_missing = MagicMock()
    db_missing.query.return_value.options.return_value.filter.return_value.first.return_value = None
    db_manual = MagicMock()
    db_manual.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.MANUAL_REVIEW.value),
    )
    db_not_auth = MagicMock()
    db_not_auth.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value),
    )
    db_error = MagicMock()
    db_error.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
    )

    lock_iter = iter([False, True, True, True, True])

    def _lock_side_effect(*_args, **_kwargs):
        return _lock(next(lock_iter))

    with patch(
        "app.database.SessionLocal",
        side_effect=[db_read, db_missing, db_manual, db_not_auth, db_error],
    ):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks.booking_lock_sync",
                    side_effect=_lock_side_effect,
                ):
                    with patch(
                        "app.tasks.payment_tasks._process_capture_for_booking",
                        side_effect=RuntimeError("capture failed"),
                    ):
                        result = payment_tasks.capture_completed_lessons()

    assert result["expired_handled"] == 0
    assert result["failed"] == 1


@pytest.mark.parametrize("payout_value", [None, "not-a-number"])
def test_process_capture_for_booking_already_captured_sets_completed_fields(payout_value):
    booking_phase1 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        rescheduled_from_booking_id=None,
        has_locked_funds=False,
    )
    booking_phase3 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
            credits_reserved_cents=120,
            capture_retry_count=0,
        ),
    )

    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase1
    db_stripe = MagicMock()
    db3 = MagicMock()
    db3.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase3

    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="already been captured",
        param="payment_intent",
    )

    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = SimpleNamespace(
        instructor_payout_cents=payout_value
    )

    with patch("app.database.SessionLocal", side_effect=[db1, db_stripe, db3]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch("app.tasks.payment_tasks.StripeService", return_value=stripe_service):
                with patch("app.tasks.payment_tasks.ConfigService"):
                    with patch("app.tasks.payment_tasks.PricingService"):
                        with patch("app.services.credit_service.CreditService") as credit_cls:
                            credit_cls.return_value.forfeit_credits_for_booking = MagicMock()
                            with patch(
                                "app.repositories.booking_repository.BookingRepository.ensure_payment",
                                return_value=booking_phase3.payment_detail,
                            ):
                                result = payment_tasks._process_capture_for_booking(
                                    "booking_id",
                                    "instructor_completed",
                                )

    assert result.get("already_captured") is True
    assert booking_phase3.payment_detail.payment_status == PaymentStatus.SETTLED.value
    assert booking_phase3.payment_detail.credits_reserved_cents == 0
    assert booking_phase3.payment_detail.settlement_outcome == "lesson_completed_full_payout"
    assert booking_phase3.payment_detail.instructor_payout_amount is None
    payment_repo.create_payment_event.assert_called_once()


@pytest.mark.parametrize(
    "payment_lookup_result",
    [
        RepositoryException("lookup failed"),
        SimpleNamespace(instructor_payout_cents="bad-int"),
        SimpleNamespace(instructor_payout_cents=None),
    ],
)
def test_create_new_authorization_and_capture_handles_payout_lookup_issues(payment_lookup_result):
    booking = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.COMPLETED,
        payment_detail=SimpleNamespace(
            payment_intent_id="pi_old",
            payment_method_id="pm_123",
            payment_status=PaymentStatus.AUTHORIZED.value,
            credits_reserved_cents=100,
        ),
    )
    payment_repo = MagicMock()
    if isinstance(payment_lookup_result, Exception):
        payment_repo.get_payment_by_booking_id.side_effect = payment_lookup_result
    else:
        payment_repo.get_payment_by_booking_id.return_value = payment_lookup_result

    db = MagicMock()
    db_stripe = MagicMock()
    stripe_service = MagicMock()
    stripe_service.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(id="pi_new")
    stripe_service.capture_booking_payment_intent.return_value = {
        "amount_received": 2500,
        "top_up_transfer_cents": 0,
    }

    with patch("app.database.SessionLocal", return_value=db_stripe):
        with patch("app.tasks.payment_tasks.StripeService", return_value=stripe_service):
            with patch("app.tasks.payment_tasks.ConfigService"):
                with patch("app.tasks.payment_tasks.PricingService"):
                    with patch("app.services.credit_service.CreditService") as credit_cls:
                        credit_cls.return_value.forfeit_credits_for_booking = MagicMock()
                        with patch(
                            "app.repositories.booking_repository.BookingRepository.ensure_payment",
                            return_value=booking.payment_detail,
                        ):
                            result = payment_tasks.create_new_authorization_and_capture(
                                booking,
                                payment_repo,
                                db,
                                lock_acquired=True,
                            )

    assert result["success"] is True
    assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
    assert booking.payment_detail.instructor_payout_amount is None
    payment_repo.create_payment_event.assert_called_once()


def test_check_authorization_health_booking_not_overdue_branch():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [booking]
    payment_repo = MagicMock()
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(
        created_at=now - timedelta(minutes=5)
    )
    db.query.return_value = query

    with patch("app.tasks.payment_tasks.get_db", return_value=iter([db])):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=booking_repo,
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_start_utc",
                    return_value=now,
                ):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=30.0,
                    ):
                        result = payment_tasks.check_authorization_health()

    assert result["overdue_count"] == 0
    assert result["healthy"] is True


def test_process_scheduled_authorizations_ignores_non_scheduled_bookings():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        id="booking_id",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            auth_scheduled_for=now - timedelta(hours=1),
        ),
        student_id="student-1",
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_authorization.return_value = [booking]
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=MagicMock(),
            ):
                with patch("app.tasks.payment_tasks._get_booking_start_utc", return_value=now):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=24.0,
                    ):
                        with patch(
                            "app.tasks.payment_tasks._process_authorization_for_booking"
                        ) as process_mock:
                            result = payment_tasks.process_scheduled_authorizations()

    assert result["success"] == 0
    assert result["failed"] == 0
    process_mock.assert_not_called()


def test_retry_failed_authorizations_warn_only_skips_when_booking_no_longer_eligible():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    db_warn = MagicMock()
    db_warn.query.return_value.options.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status=BookingStatus.CANCELLED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=None,
            auth_failure_t13_warning_sent_at=None,
        ),
    )

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=MagicMock(),
            ):
                with patch("app.tasks.payment_tasks._get_booking_start_utc", return_value=now):
                    with patch(
                        "app.tasks.payment_tasks.TimezoneService.hours_until",
                        return_value=12.5,
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


def test_retry_failed_authorizations_warn_only_then_retry_success():
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(id="booking_id")

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_retry.return_value = [booking]

    db_read = MagicMock()
    db_warn = MagicMock()
    booking_warn = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=None,
            auth_failure_t13_warning_sent_at=None,
        ),
    )
    db_warn.query.return_value.options.return_value.filter.return_value.first.return_value = booking_warn
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
                return_value=payment_repo,
            ):
                with patch("app.tasks.payment_tasks._get_booking_start_utc", return_value=now):
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
                                return_value=False,
                            ):
                                with patch(
                                    "app.tasks.payment_tasks.booking_lock_sync",
                                    side_effect=[_lock(True), _lock(True)],
                                ):
                                    with patch(
                                        "app.tasks.payment_tasks._process_retry_authorization",
                                        return_value={"success": True},
                                    ):
                                        with patch(
                                            "app.tasks.payment_tasks.NotificationService"
                                        ) as notification_cls:
                                            with patch(
                                                "app.repositories.booking_repository.BookingRepository.ensure_payment",
                                                return_value=booking_warn.payment_detail,
                                            ):
                                                result = payment_tasks.retry_failed_authorizations()

    assert result["warnings_sent"] == 1
    assert result["retried"] == 1
    assert result["success"] == 1
    assert result["failed"] == 0
    notification_cls.return_value.send_final_payment_warning.assert_called_once()


def test_process_retry_authorization_returns_phase3_missing():
    booking_phase1 = SimpleNamespace(
        id="booking_id",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            payment_method_id="pm_123",
            payment_intent_id=None,
        ),
        student_id="student-1",
        instructor_id="instructor-1",
    )
    db1 = MagicMock()
    db1.query.return_value.options.return_value.filter.return_value.first.return_value = booking_phase1

    db_stripe = MagicMock()
    db3 = MagicMock()
    db3.query.return_value.options.return_value.filter.return_value.first.return_value = None

    payment_repo = MagicMock()
    payment_repo.get_customer_by_user_id.return_value = SimpleNamespace(id="cus_123")
    payment_repo.get_connected_account_by_instructor_id.return_value = SimpleNamespace(
        stripe_account_id="acct_123"
    )

    stripe_service = MagicMock()
    stripe_service.build_charge_context.return_value = SimpleNamespace(
        student_pay_cents=500,
        application_fee_cents=50,
        applied_credit_cents=0,
    )
    stripe_service.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
        id="pi_new"
    )

    with patch("app.database.SessionLocal", side_effect=[db1, db_stripe, db3]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo,
        ):
            with patch(
                "app.repositories.instructor_profile_repository.InstructorProfileRepository"
            ) as instructor_repo_cls:
                instructor_repo_cls.return_value.get_by_user_id.return_value = SimpleNamespace(
                    id="profile_1"
                )
                with patch("app.tasks.payment_tasks.StripeService", return_value=stripe_service):
                    with patch("app.tasks.payment_tasks.ConfigService"):
                        with patch("app.tasks.payment_tasks.PricingService"):
                            result = payment_tasks._process_retry_authorization(
                                "booking_id",
                                18.0,
                            )

    assert result == {"success": False, "error": "Booking not found in Phase 3"}


def test_escalate_capture_failure_returns_when_booking_missing_in_phase3():
    now = datetime.now(timezone.utc)
    booking_read = SimpleNamespace(id="booking_id", instructor_id="instructor-1")
    db_read = MagicMock()
    db_read.query.return_value.filter.return_value.first.return_value = booking_read

    payment_repo_read = MagicMock()
    payment_repo_read.get_payment_by_booking_id.return_value = SimpleNamespace(
        instructor_payout_cents=900
    )
    payment_repo_read.get_connected_account_by_instructor_id.return_value = None
    instructor_repo = MagicMock()
    instructor_repo.get_by_user_id.return_value = None

    db_write = MagicMock()
    db_write.query.return_value.options.return_value.filter.return_value.first.return_value = None

    with patch("app.database.SessionLocal", side_effect=[db_read, db_write]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=payment_repo_read,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_instructor_profile_repository",
                return_value=instructor_repo,
            ):
                payment_tasks._escalate_capture_failure("booking_id", now)

    db_write.commit.assert_not_called()


def test_escalate_capture_failure_commits_without_student_record():
    now = datetime.now(timezone.utc)
    booking_read = SimpleNamespace(id="booking_id", instructor_id="instructor-1")
    booking_write = SimpleNamespace(
        id="booking_id",
        student_id="student-1",
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_retry_count=2,
        ),
        transfer_retry_count=0,
        payout_transfer_retry_count=0,
    )

    db_read = MagicMock()
    db_read.query.return_value.filter.return_value.first.return_value = booking_read

    payment_repo_read = MagicMock()
    payment_repo_read.get_payment_by_booking_id.return_value = SimpleNamespace(
        instructor_payout_cents=900
    )
    payment_repo_read.get_connected_account_by_instructor_id.return_value = None
    instructor_repo = MagicMock()
    instructor_repo.get_by_user_id.return_value = None

    db_write = MagicMock()

    from app.models.booking_payment import BookingPayment as BP

    def _query_side_effect_no_student(model):
        query = MagicMock()
        if model is payment_tasks.Booking:
            query.options.return_value.filter.return_value.first.return_value = booking_write
        elif model is payment_tasks.User:
            query.filter.return_value.first.return_value = None
        elif model is BP:
            query.filter.return_value.one_or_none.return_value = booking_write.payment_detail
        else:
            query.filter.return_value.first.return_value = None
        return query

    db_write.query.side_effect = _query_side_effect_no_student
    payment_repo_write = MagicMock()

    with patch("app.database.SessionLocal", side_effect=[db_read, db_write]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            side_effect=[payment_repo_read, payment_repo_write],
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_instructor_profile_repository",
                return_value=instructor_repo,
            ):
                payment_tasks._escalate_capture_failure("booking_id", now)

    db_write.commit.assert_called_once()
    payment_repo_write.create_payment_event.assert_called_once()
