from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
import stripe

from app.models.booking import BookingStatus, PaymentStatus
from app.tasks import payment_tasks


@contextmanager
def _lock(acquired: bool):
    yield acquired


def _booking(
    booking_id: str,
    *,
    payment_status: BookingStatus | str = PaymentStatus.AUTHORIZED.value,
    payment_intent_id: str | None = "pi_123",
    has_locked_funds: bool = False,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=booking_id,
        status=status,
        student_id="student-1",
        instructor_id="instructor-1",
        has_locked_funds=has_locked_funds,
        rescheduled_from_booking_id=None,
        payment_detail=SimpleNamespace(
            payment_status=payment_status,
            payment_intent_id=payment_intent_id,
        ),
    )


def test_get_booking_start_utc_raises_when_missing():
    booking = SimpleNamespace(id="booking-start-missing", booking_start_utc=None)

    with pytest.raises(ValueError, match="missing booking_start_utc"):
        payment_tasks._get_booking_start_utc(booking)


def test_get_booking_end_utc_raises_when_missing():
    booking = SimpleNamespace(id="booking-end-missing", booking_end_utc=None)

    with pytest.raises(ValueError, match="missing booking_end_utc"):
        payment_tasks._get_booking_end_utc(booking)


def test_retry_failed_captures_counts_retry_without_success():
    now = datetime.now(timezone.utc)
    check_booking = SimpleNamespace(
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            capture_failed_at=now - timedelta(hours=5),
        ),
    )
    db_read = MagicMock()
    db_check = MagicMock()

    def _make_repo(db):
        repo = MagicMock()
        if db is db_read:
            repo.get_failed_capture_booking_ids.return_value = ["booking_id"]
        elif db is db_check:
            repo.get_by_id.return_value = check_booking
        return repo

    with patch("app.database.SessionLocal", side_effect=[db_read, db_check]):
        with patch("app.tasks.payment_tasks.BookingRepository", side_effect=_make_repo):
            with patch("app.tasks.payment_tasks.booking_lock_sync", return_value=_lock(True)):
                with patch(
                    "app.tasks.payment_tasks._process_capture_for_booking",
                    return_value={"success": False},
                ):
                    result = payment_tasks.retry_failed_captures()

    assert result["retried"] == 1
    assert result["succeeded"] == 0
    assert result["skipped"] == 0


def test_capture_completed_lessons_filters_capture_candidates_before_processing():
    now = datetime.now(timezone.utc)
    eligible = SimpleNamespace(
        id="eligible",
        payment_detail=SimpleNamespace(payment_intent_id="pi_eligible"),
        has_locked_funds=False,
    )
    recent = SimpleNamespace(
        id="recent",
        payment_detail=SimpleNamespace(payment_intent_id="pi_recent"),
        has_locked_funds=False,
    )
    missing_intent = SimpleNamespace(
        id="missing-intent",
        payment_detail=SimpleNamespace(payment_intent_id=None),
        has_locked_funds=False,
    )
    locked_funds = SimpleNamespace(
        id="locked-funds",
        payment_detail=SimpleNamespace(payment_intent_id=None),
        has_locked_funds=True,
    )

    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = [
        eligible,
        recent,
        missing_intent,
        locked_funds,
    ]
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = []

    with patch("app.database.SessionLocal", return_value=MagicMock()):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=MagicMock(),
            ):
                with patch(
                    "app.tasks.payment_tasks._get_booking_end_utc",
                    side_effect=[
                        now - timedelta(hours=25),
                        now - timedelta(hours=2),
                        now - timedelta(hours=26),
                        now - timedelta(hours=27),
                    ],
                ):
                    with patch(
                        "app.tasks.payment_tasks.booking_lock_sync",
                        side_effect=lambda *_args, **_kwargs: _lock(True),
                    ):
                        with patch(
                            "app.tasks.payment_tasks._process_capture_for_booking",
                            return_value={"success": True},
                        ) as process_mock:
                            result = payment_tasks.capture_completed_lessons()

    assert result["captured"] == 2
    assert result["failed"] == 0
    assert process_mock.call_args_list == [
        call("eligible", "instructor_completed"),
        call("locked-funds", "instructor_completed"),
    ]


def test_capture_completed_lessons_does_not_count_skipped_capture_as_failure():
    now = datetime.now(timezone.utc)
    booking_capture = SimpleNamespace(
        id="capture-id",
        payment_detail=SimpleNamespace(payment_intent_id="pi_capture"),
        has_locked_funds=False,
    )
    booking_repo = MagicMock()
    booking_repo.get_bookings_for_payment_capture.return_value = [booking_capture]
    booking_repo.get_bookings_for_auto_completion.return_value = []
    booking_repo.get_bookings_with_expired_auth.return_value = []

    with patch("app.database.SessionLocal", return_value=MagicMock()):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=booking_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=MagicMock(),
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
                            return_value={"skipped": True},
                        ):
                            result = payment_tasks.capture_completed_lessons()

    assert result["captured"] == 0
    assert result["failed"] == 0


def test_auto_complete_booking_referral_failure_still_auto_completes():
    now = datetime.now(timezone.utc)
    booking = _booking("booking-id")
    booking_repo = MagicMock()
    booking_repo.get_by_id.return_value = booking
    payment_repo = MagicMock()

    with patch("app.database.SessionLocal", return_value=MagicMock()):
        with patch("app.tasks.payment_tasks.BookingRepository", return_value=booking_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=payment_repo,
            ):
                with patch("app.tasks.payment_tasks._get_booking_end_utc", return_value=now):
                    with patch("app.tasks.payment_tasks.StudentCreditService") as credit_cls:
                        credit_cls.return_value.maybe_issue_milestone_credit = MagicMock()
                        with patch("app.services.referral_service.ReferralService") as referral_cls:
                            referral_cls.return_value.on_instructor_lesson_completed.side_effect = RuntimeError(
                                "referral down"
                            )
                            with patch(
                                "app.tasks.payment_tasks._process_capture_for_booking",
                                return_value={"success": True},
                            ):
                                with patch("app.tasks.payment_tasks.PricingService") as pricing_cls:
                                    pricing_cls.return_value.evaluate_and_persist_instructor_tier = (
                                        MagicMock()
                                    )
                                    result = payment_tasks._auto_complete_booking("booking-id", now)

    assert result["auto_completed"] is True
    assert result["captured"] is True
    assert booking.status == BookingStatus.COMPLETED
    assert booking.completed_at == now
    payment_repo.create_payment_event.assert_called_once()


def test_attempt_payment_capture_success_updates_session_backed_payment():
    booking = _booking("booking-id")
    payment_record = SimpleNamespace(
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_123",
        capture_failed_at=datetime.now(timezone.utc),
        capture_retry_count=2,
    )
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.return_value = {"amount_received": 2500}

    with patch("sqlalchemy.orm.object_session", return_value=MagicMock()):
        with patch(
            "app.repositories.booking_repository.BookingRepository.ensure_payment",
            return_value=payment_record,
        ):
            result = payment_tasks.attempt_payment_capture(
                booking,
                payment_repo,
                "instructor_completed",
                stripe_service,
            )

    assert result == {"success": True}
    assert payment_record.payment_status == PaymentStatus.SETTLED.value
    assert payment_repo.create_payment_event.call_args.kwargs["event_type"] == "payment_captured"


def test_attempt_payment_capture_already_captured_resets_session_retry_state():
    payment_record = SimpleNamespace(
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_123",
        capture_failed_at=datetime.now(timezone.utc),
        capture_retry_count=3,
    )
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="already been captured",
        param="payment_intent",
    )

    with patch("sqlalchemy.orm.object_session", return_value=MagicMock()):
        with patch(
            "app.repositories.booking_repository.BookingRepository.ensure_payment",
            return_value=payment_record,
        ):
            result = payment_tasks.attempt_payment_capture(
                _booking("booking-id"),
                payment_repo,
                "instructor_completed",
                stripe_service,
            )

    assert result == {"success": True, "already_captured": True}
    assert payment_record.payment_status == PaymentStatus.SETTLED.value
    assert payment_record.capture_failed_at is None
    assert payment_record.capture_retry_count == 0


def test_attempt_payment_capture_expired_without_session_keeps_booking_state_unchanged():
    booking = _booking("booking-id")
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="PaymentIntent has expired",
        param=None,
        code="payment_intent_unexpected_state",
        http_body=None,
        http_status=None,
        json_body=None,
        headers=None,
    )

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking,
            payment_repo,
            "expired_auth",
            stripe_service,
        )

    assert result == {"success": False, "expired": True}
    assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
    assert payment_repo.create_payment_event.call_args.kwargs["event_type"] == "capture_failed_expired"


def test_attempt_payment_capture_generic_exception_marks_session_backed_retry_state():
    payment_record = SimpleNamespace(
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_123",
        capture_failed_at=None,
        capture_retry_count=0,
    )
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = RuntimeError("capture boom")

    with patch("sqlalchemy.orm.object_session", return_value=MagicMock()):
        with patch(
            "app.repositories.booking_repository.BookingRepository.ensure_payment",
            return_value=payment_record,
        ):
            result = payment_tasks.attempt_payment_capture(
                _booking("booking-id"),
                payment_repo,
                "instructor_completed",
                stripe_service,
            )

    assert result == {"success": False, "error": "capture boom"}
    assert payment_record.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert payment_record.capture_failed_at is not None
    assert payment_record.capture_retry_count == 1


def test_retry_failed_authorizations_warn_only_skips_duplicate_notification():
    booking = _booking(
        "booking-warn",
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )
    payment_state = SimpleNamespace(
        auth_failure_t13_warning_sent_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    repo_read = MagicMock()
    repo_read.get_bookings_for_payment_retry.return_value = [booking]
    repo_warn = MagicMock()
    repo_warn.get_by_id.return_value = booking
    repo_warn.ensure_payment.return_value = payment_state
    db_read = MagicMock()
    db_warn = MagicMock()
    payment_repo_read = MagicMock()
    payment_repo_warn = MagicMock()

    def _payment_repo_for_db(db):
        if db is db_read:
            return payment_repo_read
        if db is db_warn:
            return payment_repo_warn
        raise AssertionError("unexpected db")

    def _booking_repo_for_db(db):
        if db is db_warn:
            return repo_warn
        raise AssertionError("unexpected db")

    with patch("app.database.SessionLocal", side_effect=[db_read, db_warn]):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=repo_read,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                side_effect=_payment_repo_for_db,
            ):
                with patch("app.tasks.payment_tasks.BookingRepository", side_effect=_booking_repo_for_db):
                    with patch("app.tasks.payment_tasks._get_booking_start_utc", return_value=datetime.now(timezone.utc)):
                        with patch("app.tasks.payment_tasks.TimezoneService.hours_until", return_value=12.5):
                            with patch("app.tasks.payment_tasks._should_retry_auth", return_value=False):
                                with patch("app.tasks.payment_tasks.has_event_type", return_value=False):
                                    with patch(
                                        "app.tasks.payment_tasks.booking_lock_sync",
                                        return_value=_lock(True),
                                    ):
                                        with patch("app.tasks.payment_tasks.NotificationService") as notification_cls:
                                            result = payment_tasks.retry_failed_authorizations()

    assert result["warnings_sent"] == 0
    assert result["retried"] == 0
    notification_cls.assert_not_called()
    payment_repo_warn.create_payment_event.assert_not_called()
    db_warn.commit.assert_called_once()


def test_retry_failed_authorizations_silent_retry_skipped_does_not_increment_counts():
    booking = _booking(
        "booking-retry",
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
    )
    repo_read = MagicMock()
    repo_read.get_bookings_for_payment_retry.return_value = [booking]
    db_read = MagicMock()

    with patch("app.database.SessionLocal", return_value=db_read):
        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.create_booking_repository",
            return_value=repo_read,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.create_payment_repository",
                return_value=MagicMock(),
            ):
                with patch("app.tasks.payment_tasks._get_booking_start_utc", return_value=datetime.now(timezone.utc)):
                    with patch("app.tasks.payment_tasks.TimezoneService.hours_until", return_value=24):
                        with patch("app.tasks.payment_tasks._should_retry_auth", return_value=True):
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
    assert result["success"] == 0
    assert result["failed"] == 0


def test_attempt_payment_capture_missing_payment_intent_short_circuits_without_event():
    booking = _booking("booking-missing-intent", payment_intent_id=None)
    payment_repo = MagicMock()
    stripe_service = MagicMock()

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

    assert result == {"success": False, "error": "missing_payment_intent"}
    stripe_service.capture_booking_payment_intent.assert_not_called()
    payment_repo.create_payment_event.assert_not_called()


def test_attempt_payment_capture_already_captured_without_session_records_event_only():
    booking = _booking("booking-already-captured")
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
        message="already been captured",
        param="payment_intent",
    )

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

    assert result == {"success": True, "already_captured": True}
    assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
    assert payment_repo.create_payment_event.call_args.kwargs["event_type"] == "capture_already_done"


def test_attempt_payment_capture_card_error_without_session_records_event_only():
    booking = _booking("booking-card-error")
    payment_repo = MagicMock()
    stripe_service = MagicMock()
    stripe_service.capture_booking_payment_intent.side_effect = stripe.error.CardError(
        message="Insufficient funds",
        param=None,
        code="card_declined",
        http_body=None,
        http_status=402,
        json_body=None,
        headers=None,
    )

    with patch("sqlalchemy.orm.object_session", return_value=None):
        result = payment_tasks.attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

    assert result == {"success": False, "card_error": True}
    assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
    assert payment_repo.create_payment_event.call_args.kwargs["event_type"] == "capture_failed_card"
