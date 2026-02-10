"""Additional webhook branch coverage for StripeService."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.stripe_service as stripe_mod
from app.services.stripe_service import StripeService


@contextmanager
def _tx_ctx():
    yield None


def _service() -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.logger = MagicMock()
    service.transaction = MagicMock(return_value=_tx_ctx())
    service.payment_repository = MagicMock()
    service.booking_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.cache_service = MagicMock()
    service.stripe_configured = True
    return service


def test_handle_successful_payment_handles_pending_and_missing_bookings():
    service = _service()

    service.booking_repository.get_by_id.return_value = None
    service._handle_successful_payment(SimpleNamespace(booking_id="missing"))

    booking = SimpleNamespace(id="booking-1", status="PENDING")
    service.booking_repository.get_by_id.return_value = booking

    with patch("app.services.booking_service.BookingService") as booking_service_cls:
        booking_service_cls.return_value.invalidate_booking_cache.return_value = None
        service._handle_successful_payment(SimpleNamespace(booking_id="booking-1"))

    assert booking.status == "CONFIRMED"
    service.booking_repository.flush.assert_called()


def test_account_and_transfer_webhook_branches():
    service = _service()

    account_updated = {
        "type": "account.updated",
        "data": {"object": {"id": "acct_1", "charges_enabled": True, "details_submitted": True}},
    }
    assert service._handle_account_webhook(account_updated) is True
    service.payment_repository.update_onboarding_status.assert_called_with("acct_1", True)

    account_deauth = {
        "type": "account.application.deauthorized",
        "data": {"object": {"id": "acct_1"}},
    }
    assert service._handle_account_webhook(account_deauth) is True

    with patch.object(service.logger, "info", side_effect=RuntimeError("log-boom")):
        with patch.object(stripe_mod.logger, "debug") as debug_log:
            reversed_evt = {
                "type": "transfer.reversed",
                "data": {"object": {"id": "tr_1", "amount": 2500}},
            }
            assert service._handle_transfer_webhook(reversed_evt) is True
            debug_log.assert_called()


def test_payout_webhook_created_paid_and_failed_paths():
    service = _service()

    acct = SimpleNamespace(instructor_profile_id="profile-1")
    service.payment_repository.get_connected_account_by_stripe_id.return_value = acct
    service.instructor_repository.get_by_id_join_user.return_value = SimpleNamespace(user_id="user-1")

    created_evt = {
        "type": "payout.created",
        "data": {
            "object": {
                "id": "po_created",
                "amount": 1000,
                "status": "pending",
                "arrival_date": "not-a-date",
                "destination": "acct_1",
            }
        },
    }
    assert service._handle_payout_webhook(created_evt) is True

    paid_evt = {
        "type": "payout.paid",
        "data": {
            "object": {
                "id": "po_paid",
                "amount": 2000,
                "status": "paid",
                "arrival_date": datetime.now(timezone.utc),
                "destination": "acct_1",
            }
        },
    }
    with patch("app.services.notification_service.NotificationService") as notification_cls:
        notification_cls.return_value.send_payout_notification.side_effect = RuntimeError(
            "notify-boom"
        )
        assert service._handle_payout_webhook(paid_evt) is True

    failed_evt = {
        "type": "payout.failed",
        "data": {
            "object": {
                "id": "po_failed",
                "amount": 3000,
                "status": "failed",
                "arrival_date": 1730000000,
                "destination": "acct_1",
                "failure_code": "account_closed",
                "failure_message": "Account closed",
            }
        },
    }
    assert service._handle_payout_webhook(failed_evt) is True


def test_identity_webhook_paths_include_verified_and_terminal_statuses():
    service = _service()

    no_user_evt = {
        "type": "identity.verification_session.verified",
        "data": {"object": {"id": "vs_1", "status": "verified", "metadata": {}}},
    }
    assert service._handle_identity_webhook(no_user_evt) is True

    profile = SimpleNamespace(id="profile-1")
    service.instructor_repository.get_by_user_id.return_value = profile

    verified_evt = {
        "type": "identity.verification_session.verified",
        "data": {
            "object": {
                "id": "vs_2",
                "status": "verified",
                "metadata": {"user_id": "user-1"},
            }
        },
    }
    assert service._handle_identity_webhook(verified_evt) is True
    assert service.instructor_repository.update.called

    terminal_evt = {
        "type": "identity.verification_session.updated",
        "data": {
            "object": {
                "id": "vs_3",
                "status": "processing",
                "metadata": {"user_id": "user-1"},
            }
        },
    }
    assert service._handle_identity_webhook(terminal_evt) is True


def test_identity_webhook_unknown_status_returns_true_without_updates():
    service = _service()
    service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="profile-1")

    unknown_evt = {
        "type": "identity.verification_session.updated",
        "data": {
            "object": {
                "id": "vs_unknown",
                "status": "requires_reverification",
                "metadata": {"user_id": "user-1"},
            }
        },
    }

    assert service._handle_identity_webhook(unknown_evt) is True
    service.instructor_repository.update.assert_not_called()


def test_handle_dispute_closed_won_handles_event_fetch_failure():
    service = _service()
    service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
        booking_id="booking-1"
    )
    booking = SimpleNamespace(id="booking-1", student_id="student-1")
    service.booking_repository.get_by_id.side_effect = [booking, booking]
    service.payment_repository.get_payment_events_for_booking.side_effect = RuntimeError("events failed")

    @contextmanager
    def _lock_ctx():
        yield True

    with patch("app.services.stripe_service.booking_lock_sync", return_value=_lock_ctx()):
        with patch("app.services.credit_service.CreditService") as credit_cls:
            result = service._handle_dispute_closed(
                {
                    "data": {
                        "object": {"id": "dp_1", "payment_intent": "pi_1", "status": "won"}
                    }
                }
            )

    assert result is True
    credit_cls.return_value.unfreeze_credits_for_booking.assert_called_once_with(
        booking_id="booking-1", use_transaction=False
    )
