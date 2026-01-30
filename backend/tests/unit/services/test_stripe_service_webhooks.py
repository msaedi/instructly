"""Unit tests for StripeService webhook handling."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from app.core.exceptions import ServiceException
from app.models.booking import PaymentStatus
import app.services.stripe_service as stripe_service
from app.services.stripe_service import StripeService


@contextmanager
def _noop_txn():
    yield None


def _make_service() -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.db.commit = MagicMock()
    service.db.rollback = MagicMock()
    service.logger = MagicMock()
    service.cache_service = None
    service.stripe_configured = True
    service.payment_repository = MagicMock()
    service.payment_repository.transaction = _noop_txn
    service.booking_repository = MagicMock()
    service.user_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.config_service = MagicMock()
    service.pricing_service = MagicMock()
    return service


class TestWebhookSignatureAndRouting:
    def test_handle_webhook_invalid_signature(self, monkeypatch):
        service = _make_service()
        secret = SimpleNamespace(get_secret_value=lambda: "whsec_123")
        monkeypatch.setattr(stripe_service, "settings", SimpleNamespace(stripe_webhook_secret=secret))

        with patch.object(
            stripe_service.stripe.Webhook,
            "construct_event",
            side_effect=stripe.SignatureVerificationError("bad", "sig"),
        ):
            with pytest.raises(ServiceException, match="Invalid webhook signature"):
                StripeService.handle_webhook(service, "payload", "sig")

    def test_handle_webhook_invalid_payload(self, monkeypatch):
        service = _make_service()
        secret = SimpleNamespace(get_secret_value=lambda: "whsec_456")
        monkeypatch.setattr(stripe_service, "settings", SimpleNamespace(stripe_webhook_secret=secret))

        with patch.object(
            stripe_service.stripe.Webhook,
            "construct_event",
            side_effect=Exception("boom"),
        ):
            with pytest.raises(ServiceException, match="Invalid webhook payload"):
                StripeService.handle_webhook(service, "payload", "sig")


class TestPaymentIntentWebhooks:
    def test_handle_payment_intent_webhook_succeeded(self):
        service = _make_service()
        payment_record = SimpleNamespace(booking_id="booking_1")
        service.payment_repository.update_payment_status.return_value = payment_record
        service._handle_successful_payment = MagicMock()

        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_1", "status": "succeeded"}},
        }

        result = StripeService.handle_payment_intent_webhook(service, event)

        assert result is True
        service._handle_successful_payment.assert_called_once_with(payment_record)

    def test_handle_payment_intent_webhook_missing_record(self):
        service = _make_service()
        service.payment_repository.update_payment_status.return_value = None

        event = {
            "type": "payment_intent.processing",
            "data": {"object": {"id": "pi_2", "status": "processing"}},
        }

        result = StripeService.handle_payment_intent_webhook(service, event)

        assert result is False


class TestChargeAndPayoutWebhooks:
    def test_handle_charge_refunded_calls_credit_hooks(self):
        service = _make_service()
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_2"
        )
        service.booking_repository.get_by_id.return_value = SimpleNamespace(id="booking_2")

        credit_service = MagicMock()
        with patch.object(stripe_service, "StudentCreditService", return_value=credit_service):
            event = {
                "type": "charge.refunded",
                "data": {
                    "object": {"id": "ch_1", "payment_intent": "pi_3"}
                },
            }
            result = StripeService._handle_charge_webhook(service, event)

        assert result is True
        service.payment_repository.update_payment_status.assert_called_once_with("pi_3", "refunded")
        credit_service.process_refund_hooks.assert_called_once()

    def test_handle_charge_refunded_credit_hook_error(self):
        service = _make_service()
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_3"
        )
        service.booking_repository.get_by_id.return_value = SimpleNamespace(id="booking_3")

        credit_service = MagicMock()
        credit_service.process_refund_hooks.side_effect = Exception("boom")
        with patch.object(stripe_service, "StudentCreditService", return_value=credit_service):
            event = {
                "type": "charge.refunded",
                "data": {
                    "object": {"id": "ch_2", "payment_intent": "pi_4"}
                },
            }
            result = StripeService._handle_charge_webhook(service, event)

        assert result is True

    def test_handle_payout_webhook_paid_sends_notification(self):
        service = _make_service()
        acct = SimpleNamespace(instructor_profile_id="prof_1")
        service.payment_repository.get_connected_account_by_stripe_id.return_value = acct
        service.instructor_repository.get_by_id_join_user.return_value = SimpleNamespace(
            user_id="user_1"
        )

        notification_service = MagicMock()
        with patch(
            "app.services.notification_service.NotificationService",
            return_value=notification_service,
        ):
            event = {
                "type": "payout.paid",
                "data": {
                    "object": {
                        "id": "po_1",
                        "amount": 1234,
                        "status": "paid",
                        "arrival_date": 1700000000,
                        "destination": "acct_1",
                    }
                },
            }
            result = StripeService._handle_payout_webhook(service, event)

        assert result is True
        notification_service.send_payout_notification.assert_called_once()


class TestIdentityAndDisputes:
    def test_handle_identity_webhook_verified_updates_profile(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_2")
        service.instructor_repository.get_by_user_id.return_value = profile

        event = {
            "type": "identity.verification_session.verified",
            "data": {
                "object": {
                    "id": "vs_1",
                    "status": "verified",
                    "metadata": {"user_id": "user_2"},
                }
            },
        }

        result = StripeService._handle_identity_webhook(service, event)

        assert result is True
        service.instructor_repository.update.assert_called_once()

    def test_handle_dispute_closed_lost_applies_negative_balance(self):
        service = _make_service()
        service.stripe_configured = True
        payment_record = SimpleNamespace(booking_id="booking_4")
        booking = SimpleNamespace(
            id="booking_4",
            student_id="student_1",
            payment_status=PaymentStatus.SETTLED.value,
        )
        service.payment_repository.get_payment_by_intent_id.return_value = payment_record
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.payment_repository.get_payment_events_for_booking.return_value = []

        @contextmanager
        def _lock(_booking_id):
            yield True

        credit_service = MagicMock()
        credit_service.get_spent_credits_for_booking.return_value = 500

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = SimpleNamespace(account_restricted=False)

        event = {
            "type": "charge.dispute.closed",
            "data": {
                "object": {
                    "id": "dp_1",
                    "payment_intent": "pi_999",
                    "status": "lost",
                    "amount": 500,
                }
            },
        }

        with patch.object(stripe_service, "booking_lock_sync", _lock):
            with patch("app.services.credit_service.CreditService", return_value=credit_service):
                with patch.object(
                    stripe_service.RepositoryFactory,
                    "create_base_repository",
                    return_value=user_repo,
                ):
                    result = StripeService._handle_dispute_closed(service, event)

        assert result is True
        credit_service.apply_negative_balance.assert_called_once()
        service.payment_repository.create_payment_event.assert_called()
