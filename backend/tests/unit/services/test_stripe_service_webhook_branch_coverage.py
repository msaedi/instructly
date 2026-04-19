"""Additional webhook branch coverage for StripeService."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.booking import BookingStatus
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


_TEST_SENTINEL = object()


def _attach_mark_confirmed(booking: SimpleNamespace) -> None:
    def _mark_confirmed(*, confirmed_at: datetime | object = _TEST_SENTINEL) -> None:
        booking.status = BookingStatus.CONFIRMED
        if confirmed_at is _TEST_SENTINEL:
            if booking.confirmed_at is None:
                booking.confirmed_at = datetime.now(timezone.utc)
        else:
            booking.confirmed_at = confirmed_at

    booking.mark_confirmed = _mark_confirmed


def test_handle_successful_payment_handles_pending_and_missing_bookings():
    service = _service()

    service.booking_repository.get_by_id.return_value = None
    service._handle_successful_payment(SimpleNamespace(booking_id="missing"))

    booking = SimpleNamespace(id="booking-1", status="PENDING", confirmed_at=None)
    _attach_mark_confirmed(booking)
    service.booking_repository.get_by_id.return_value = booking

    with patch("app.services.booking_service.BookingService") as booking_service_cls:
        booking_service_cls.return_value.invalidate_booking_cache.return_value = None
        service._handle_successful_payment(SimpleNamespace(booking_id="booking-1"))

    assert booking.status == BookingStatus.CONFIRMED
    assert booking.confirmed_at is not None
    service.booking_repository.flush.assert_called()


def test_account_webhook_branches_use_event_shape_aware_account_ids():
    service = _service()
    # QF1: no-op guard needs a stale False record for the write to fire.
    service.payment_repository.get_connected_account_by_stripe_id.return_value = (
        SimpleNamespace(stripe_account_id="acct_1", onboarding_completed=False)
    )

    account_updated = {
        "type": "account.updated",
        "data": {"object": {"id": "acct_1", "charges_enabled": True, "details_submitted": True}},
    }
    assert service._handle_account_webhook(account_updated) is True
    service.payment_repository.update_onboarding_status.assert_called_with("acct_1", True)

    external_account_event = {
        "type": "account.external_account.deleted",
        "account": "acct_platform",
        "data": {"object": {"id": "ba_123"}},
    }
    assert service._handle_account_webhook(external_account_event) is True
    service.logger.warning.assert_called_with(
        "External account deleted for %s: %s",
        "acct_platform",
        "ba_123",
    )

    capability_event = {
        "type": "capability.updated",
        "account": "acct_platform",
        "data": {"object": {"id": "transfers", "status": "active"}},
    }
    assert service._handle_account_webhook(capability_event) is True
    service.logger.info.assert_any_call(
        "Capability updated for %s: capability=%s, status=%s",
        "acct_platform",
        "transfers",
        "active",
    )

    account_deauth = {
        "type": "account.application.deauthorized",
        "data": {"object": {"id": "acct_1"}},
    }
    assert service._handle_account_webhook(account_deauth) is False


def test_transfer_webhook_dead_subtypes_return_false_and_reversed_warning_fallback():
    service = _service()

    assert (
        service._handle_transfer_webhook(
            {"type": "transfer.paid", "data": {"object": {"id": "tr_paid"}}}
        )
        is False
    )
    assert (
        service._handle_transfer_webhook(
            {"type": "transfer.failed", "data": {"object": {"id": "tr_failed"}}}
        )
        is False
    )

    with patch.object(service.logger, "info", side_effect=RuntimeError("log-boom")):
        with patch.object(stripe_mod.logger, "warning") as warning_log:
            reversed_evt = {
                "type": "transfer.reversed",
                "data": {"object": {"id": "tr_1", "amount": 2500}},
            }
            assert service._handle_transfer_webhook(reversed_evt) is True
            warning_log.assert_called()


def test_customer_payment_method_and_fraud_webhook_branches():
    service = _service()

    customer_created = {
        "type": "customer.created",
        "data": {"object": {"id": "cus_1", "email": "student@example.com"}},
    }
    assert service._handle_customer_webhook(customer_created) is True
    service.logger.info.assert_any_call(
        "Customer created: %s, email=%s",
        "cus_1",
        "student@example.com",
    )
    assert (
        service._handle_customer_webhook(
            {"type": "customer.deleted", "data": {"object": {"id": "cus_1"}}}
        )
        is False
    )

    pm_attached = {
        "type": "payment_method.attached",
        "data": {"object": {"id": "pm_1", "type": "card", "customer": "cus_1"}},
    }
    assert service._handle_payment_method_webhook(pm_attached) is True
    service.logger.info.assert_any_call(
        "Payment method attached: %s, type=%s, customer=%s",
        "pm_1",
        "card",
        "cus_1",
    )
    assert (
        service._handle_payment_method_webhook(
            {"type": "payment_method.updated", "data": {"object": {"id": "pm_1"}}}
        )
        is False
    )

    review_opened = {
        "type": "review.opened",
        "data": {"object": {"id": "prv_1", "charge": "ch_1", "reason": "rule"}},
    }
    assert service._handle_fraud_webhook(review_opened) is True
    service.logger.warning.assert_any_call(
        "Payment review opened: %s, charge=%s, reason=%s",
        "prv_1",
        "ch_1",
        "rule",
    )
    assert (
        service._handle_fraud_webhook(
            {"type": "radar.value_list.created", "data": {"object": {"id": "rvl_1"}}}
        )
        is False
    )


def test_payout_webhook_created_paid_and_failed_paths():
    service = _service()

    acct = SimpleNamespace(instructor_profile_id="profile-1")
    service.payment_repository.get_connected_account_by_stripe_id.return_value = acct
    service.instructor_repository.get_by_id_join_user.return_value = SimpleNamespace(
        user_id="user-1"
    )

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


def test_identity_webhook_canceled_preserves_session_id():
    """canceled should preserve the session ID for later replacement decisions."""
    service = _service()
    service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="profile-1")

    canceled_evt = {
        "type": "identity.verification_session.canceled",
        "data": {
            "object": {
                "id": "vs_cancel",
                "status": "canceled",
                "metadata": {"user_id": "user-1"},
            }
        },
    }
    assert service._handle_identity_webhook(canceled_evt) is True
    service.instructor_repository.update.assert_called_with(
        "profile-1", identity_verification_session_id="vs_cancel"
    )


def test_identity_webhook_requires_input_preserves_session_id():
    """requires_input should preserve the session ID for reuse."""
    service = _service()
    service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="profile-1")

    requires_input_evt = {
        "type": "identity.verification_session.requires_input",
        "data": {
            "object": {
                "id": "vs_ri",
                "status": "requires_input",
                "metadata": {"user_id": "user-1"},
            }
        },
    }
    assert service._handle_identity_webhook(requires_input_evt) is True
    service.instructor_repository.update.assert_called_with(
        "profile-1", identity_verification_session_id="vs_ri"
    )


def test_identity_webhook_processing_keeps_session_id():
    """processing means Stripe is reviewing — session_id should be preserved."""
    service = _service()
    service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="profile-1")

    processing_evt = {
        "type": "identity.verification_session.processing",
        "data": {
            "object": {
                "id": "vs_proc",
                "status": "processing",
                "metadata": {"user_id": "user-1"},
            }
        },
    }
    assert service._handle_identity_webhook(processing_evt) is True
    service.instructor_repository.update.assert_called_with(
        "profile-1", identity_verification_session_id="vs_proc"
    )


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
    service.payment_repository.get_payment_events_for_booking.side_effect = RuntimeError(
        "events failed"
    )

    @contextmanager
    def _lock_ctx():
        yield True

    with patch("app.services.stripe_service.booking_lock_sync", return_value=_lock_ctx()):
        with patch("app.services.credit_service.CreditService") as credit_cls:
            result = service._handle_dispute_closed(
                {"data": {"object": {"id": "dp_1", "payment_intent": "pi_1", "status": "won"}}}
            )

    assert result is True
    credit_cls.return_value.unfreeze_credits_for_booking.assert_called_once_with(
        booking_id="booking-1", use_transaction=False
    )
