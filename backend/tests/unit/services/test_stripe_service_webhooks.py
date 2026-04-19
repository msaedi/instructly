"""Unit tests for StripeService webhook handling."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from app.models.booking import PaymentStatus
from app.services.stripe.exceptions import (
    WebhookPermanentError,
    WebhookRetryableError,
)
import app.services.stripe_service as stripe_service
from app.services.stripe_service import StripeService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.stripe_fixtures import make_charge
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.stripe_fixtures import make_charge


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
    def test_resolve_payment_intent_from_charge_uses_real_fixture(self):
        service = _make_service()
        service.stripe_configured = True

        with patch.object(
            stripe_service.stripe.Charge,
            "retrieve",
            return_value=make_charge(payment_intent="pi_fixture"),
        ):
            result = StripeService._resolve_payment_intent_id_from_charge(service, "ch_fixture")

        assert result == "pi_fixture"

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
        service.payment_repository.update_payment_status_for_update.assert_called_once_with(
            "pi_3", "refunded"
        )
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


class TestHandleWebhookEventTypedExceptionReraise:
    """C2: typed exceptions (WebhookRetryableError, WebhookPermanentError,
    OperationalError) must propagate through both handle_webhook_event and
    handle_payment_intent_webhook unchanged — wrapping them in ServiceException
    collapses them to the generic Exception branch and defeats H2."""

    def test_operational_error_propagates_from_payment_intent_handler(self):
        from sqlalchemy.exc import OperationalError

        service = _make_service()
        service.payment_repository.update_payment_status.side_effect = OperationalError(
            "SELECT FOR UPDATE", {}, Exception("lock not available")
        )
        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_op", "status": "succeeded"}},
        }

        with pytest.raises(OperationalError):
            StripeService.handle_webhook_event(service, event)

    def test_webhook_retryable_error_propagates_through_outer_handler(self):
        """Inner handlers that raise a typed error must not be re-wrapped."""
        service = _make_service()
        service.handle_payment_intent_webhook = MagicMock(
            side_effect=WebhookRetryableError("inner transient")
        )
        event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_r"}}}

        with pytest.raises(WebhookRetryableError):
            service.handle_webhook_event(event)


class TestHandleWebhookEventErrorMapping:
    """H2: transient Stripe errors must be re-raised as WebhookRetryableError;
    permanent ones as WebhookPermanentError."""

    def test_api_connection_error_becomes_retryable(self):
        service = _make_service()
        service.handle_payment_intent_webhook = MagicMock(
            side_effect=stripe.error.APIConnectionError("network down")
        )
        event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_x"}}}

        with pytest.raises(WebhookRetryableError):
            service.handle_webhook_event(event)

    def test_rate_limit_error_becomes_retryable(self):
        service = _make_service()
        service.handle_payment_intent_webhook = MagicMock(
            side_effect=stripe.error.RateLimitError("too many requests")
        )
        event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_x"}}}

        with pytest.raises(WebhookRetryableError):
            service.handle_webhook_event(event)

    def test_invalid_request_error_becomes_permanent(self):
        service = _make_service()
        service.handle_payment_intent_webhook = MagicMock(
            side_effect=stripe.error.InvalidRequestError("bad param", param="x")
        )
        event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_x"}}}

        with pytest.raises(WebhookPermanentError):
            service.handle_webhook_event(event)


class TestHandleSuccessfulPaymentPropagates:
    """C3: transfer or side-effect failures must propagate (not be swallowed)."""

    def test_booking_repo_error_propagates(self):
        service = _make_service()
        service.booking_repository.get_by_id.side_effect = stripe.error.APIConnectionError(
            "network"
        )
        payment_record = SimpleNamespace(booking_id="booking_1")

        with pytest.raises(stripe.error.APIConnectionError):
            service._handle_successful_payment(payment_record)


class TestDisputeAlreadyReversed:
    """H1: if a transfer was already reversed (e.g. by a refund), the dispute
    handler must treat the InvalidRequestError as a success no-op."""

    def _make_transfer_stub(self):
        return SimpleNamespace(
            stripe_transfer_id="tr_test",
            transfer_reversed=False,
        )

    def test_transfer_reversal_amount_exceeded_returns_noop(self):
        service = _make_service()
        service.booking_repository.get_transfer_by_booking_id.return_value = (
            self._make_transfer_stub()
        )
        err = stripe.error.InvalidRequestError(
            "Transfer has already been reversed",
            param=None,
            code="transfer_reversal_amount_exceeded",
        )
        service.reverse_transfer = MagicMock(side_effect=err)

        reversal_id, reversal_error = service._attempt_dispute_transfer_reversal(
            booking_id="bk_1", dispute_id="dp_1"
        )

        assert reversal_id is None
        assert reversal_error is None

    def test_message_already_fully_reversed_returns_noop(self):
        """QF2: only the exact 'already been fully reversed' phrase no-ops."""
        service = _make_service()
        service.booking_repository.get_transfer_by_booking_id.return_value = (
            self._make_transfer_stub()
        )
        service.reverse_transfer = MagicMock(
            side_effect=Exception(
                "This transfer has already been fully reversed"
            )
        )

        reversal_id, reversal_error = service._attempt_dispute_transfer_reversal(
            booking_id="bk_2", dispute_id="dp_2"
        )

        assert reversal_id is None
        assert reversal_error is None

    def test_partial_reversal_message_propagates(self):
        """QF2: 'already been reversed' without 'fully' must no longer no-op.

        Previously the loose marker matched partial-reversal-in-flight errors,
        hiding a real integration bug where the dispute handler tried to reverse
        an already-partially-reversed transfer.
        """
        service = _make_service()
        service.booking_repository.get_transfer_by_booking_id.return_value = (
            self._make_transfer_stub()
        )
        service.reverse_transfer = MagicMock(
            side_effect=Exception(
                "Transfer has already been reversed partially; reversal in flight"
            )
        )

        reversal_id, reversal_error = service._attempt_dispute_transfer_reversal(
            booking_id="bk_partial", dispute_id="dp_partial"
        )

        assert reversal_id is None
        assert reversal_error is not None
        assert "partially" in reversal_error

    def test_no_such_transfer_reversal_propagates(self):
        """QF2: 'No such transfer reversal' now surfaces as a failure.

        Previously the loose message marker silently swallowed ``resource_missing``
        errors raised for a bogus reversal ID, masking a real integration bug.
        """
        service = _make_service()
        service.booking_repository.get_transfer_by_booking_id.return_value = (
            self._make_transfer_stub()
        )
        err = stripe.error.InvalidRequestError(
            "No such transfer reversal: trr_missing",
            param=None,
            code="resource_missing",
        )
        service.reverse_transfer = MagicMock(side_effect=err)

        reversal_id, reversal_error = service._attempt_dispute_transfer_reversal(
            booking_id="bk_missing", dispute_id="dp_missing"
        )

        assert reversal_id is None
        assert reversal_error is not None
        assert "trr_missing" in reversal_error

    def test_unrelated_invalid_request_preserves_failure(self):
        service = _make_service()
        service.booking_repository.get_transfer_by_booking_id.return_value = (
            self._make_transfer_stub()
        )
        err = stripe.error.InvalidRequestError(
            "No such transfer: tr_bogus",
            param=None,
            code="resource_missing",
        )
        service.reverse_transfer = MagicMock(side_effect=err)

        reversal_id, reversal_error = service._attempt_dispute_transfer_reversal(
            booking_id="bk_3", dispute_id="dp_3"
        )

        assert reversal_id is None
        assert reversal_error is not None
        assert "tr_bogus" in reversal_error


class TestAccountUpdatedFlipBack:
    """C6: account.updated must flip onboarding_completed back to False on regression."""

    def _base_event(self, **overrides):
        obj = {
            "id": "acct_test",
            "charges_enabled": True,
            "details_submitted": True,
            "requirements": {},
        }
        obj.update(overrides)
        return {
            "type": "account.updated",
            "account": "acct_test",
            "data": {"object": obj},
        }

    def test_charges_disabled_flips_to_false(self):
        service = _make_service()
        # QF1: ensure the no-op guard sees a stale-True record so the write still fires.
        service.payment_repository.get_connected_account_by_stripe_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_test", onboarding_completed=True)
        )
        event = self._base_event(charges_enabled=False)

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_test", False
        )

    def test_account_updated_skips_write_when_status_unchanged(self):
        """QF1: a heartbeat event carrying the same state should not touch the DB."""
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_test", onboarding_completed=True)
        )
        event = self._base_event()  # fully onboarded

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_not_called()

    def test_account_updated_skips_when_record_missing(self):
        """Fix 4: an unknown account_id must not trigger a misleading
        ``onboarding_completed=<x>`` log for a write that didn't happen.
        Skip the write and log a clear "not found in DB" message instead."""
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = None
        event = self._base_event()

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_not_called()

    def test_details_not_submitted_flips_to_false(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_test", onboarding_completed=True)
        )
        event = self._base_event(details_submitted=False)

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_test", False
        )

    def test_disabled_reason_flips_to_false(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_test", onboarding_completed=True)
        )
        event = self._base_event(requirements={"disabled_reason": "listed_as_high_risk"})

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_test", False
        )

    def test_account_handler_reraises_operational_error(self):
        """Fix 1: OperationalError inside a sub-handler must propagate so the
        outer handle_webhook_event can map it to WebhookRetryableError → 503.
        Previously the broad ``except Exception: return False`` swallowed it
        and the endpoint silently returned 200 on transient DB failures."""
        from sqlalchemy.exc import OperationalError

        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.side_effect = (
            OperationalError("SELECT", {}, Exception("lock not available"))
        )
        event = self._base_event()

        with pytest.raises(OperationalError):
            service._handle_account_webhook(event)

    def test_unhandled_account_subtype_returns_true(self):
        """Fix 2: an unrecognized account.* subtype must ack (True) so Stripe
        stops retrying an event we deterministically don't handle."""
        service = _make_service()
        event = {
            "type": "account.application.authorized",
            "data": {"object": {"id": "acct_unhandled"}},
        }

        result = service._handle_account_webhook(event)

        assert result is True

    def test_fully_onboarded_sets_true(self):
        service = _make_service()
        # Stub a stale False record so the no-op guard does not short-circuit.
        service.payment_repository.get_connected_account_by_stripe_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_test", onboarding_completed=False)
        )
        event = self._base_event()

        result = service._handle_account_webhook(event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_test", True
        )
