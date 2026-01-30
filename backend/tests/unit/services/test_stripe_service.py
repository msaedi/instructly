"""Unit tests for StripeService core payment flows."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from app.core.exceptions import ServiceException
import app.services.stripe_service as stripe_service
from app.services.stripe_service import ChargeContext, StripeService


@contextmanager
def _noop_txn():
    yield None


def _make_service(*, stripe_configured: bool = True) -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.db.commit = MagicMock()
    service.db.rollback = MagicMock()
    service.logger = MagicMock()
    service.cache_service = None
    service.stripe_configured = stripe_configured
    service.platform_fee_percentage = 0.15
    service.payment_repository = MagicMock()
    service.payment_repository.transaction = _noop_txn
    service.booking_repository = MagicMock()
    service.user_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.config_service = MagicMock()
    service.pricing_service = MagicMock()
    return service


class TestCustomerManagement:
    def test_create_customer_returns_existing(self):
        service = _make_service()
        existing = SimpleNamespace(id="cust_local", stripe_customer_id="cus_123")
        service.payment_repository.get_customer_by_user_id.return_value = existing

        with patch.object(stripe_service.stripe.Customer, "create") as create_mock:
            result = StripeService.create_customer(
                service, "user_1", "user@example.com", "User One"
            )

        assert result is existing
        create_mock.assert_not_called()

    def test_create_customer_mock_on_auth_error_when_unconfigured(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.get_customer_by_user_id.return_value = None
        service.payment_repository.create_customer_record.return_value = SimpleNamespace(
            id="cust_db", stripe_customer_id="mock_cust_user_2"
        )

        auth_error = stripe.error.AuthenticationError("No API key provided")
        with patch.object(stripe_service.stripe.Customer, "create", side_effect=auth_error):
            result = StripeService.create_customer(
                service, "user_2", "user2@example.com", "User Two"
            )

        service.payment_repository.create_customer_record.assert_called_once_with(
            user_id="user_2", stripe_customer_id="mock_cust_user_2"
        )
        assert result == service.payment_repository.create_customer_record.return_value

    def test_create_customer_unconfigured_non_auth_error_raises(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.get_customer_by_user_id.return_value = None

        api_error = stripe.error.APIError("boom")
        with patch.object(stripe_service.stripe.Customer, "create", side_effect=api_error):
            with pytest.raises(ServiceException, match="Failed to create Stripe customer"):
                StripeService.create_customer(
                    service, "user_3", "user3@example.com", "User Three"
                )

    def test_get_or_create_customer_missing_user(self):
        service = _make_service()
        service.payment_repository.get_customer_by_user_id.return_value = None
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ServiceException, match="not found"):
            StripeService.get_or_create_customer(service, "user_missing")


class TestPaymentIntents:
    def test_create_payment_intent_requires_amount_when_no_context(self):
        service = _make_service()

        with pytest.raises(ServiceException, match="amount_cents is required"):
            StripeService.create_payment_intent(
                service,
                booking_id="booking_1",
                customer_id="cus_1",
                destination_account_id="acct_1",
            )

    def test_create_payment_intent_fallback_mock_when_unconfigured(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.create_payment_record.return_value = SimpleNamespace(
            id="pay_1", stripe_payment_intent_id="mock_pi_booking_1"
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", side_effect=Exception("boom")
        ):
            result = StripeService.create_payment_intent(
                service,
                booking_id="booking_1",
                customer_id="cus_1",
                destination_account_id="acct_1",
                amount_cents=5000,
            )

        assert result == service.payment_repository.create_payment_record.return_value
        call_kwargs = service.payment_repository.create_payment_record.call_args.kwargs
        assert call_kwargs["payment_intent_id"] == "mock_pi_booking_1"
        assert call_kwargs["status"] == "requires_payment_method"

    def test_create_payment_intent_platform_fee_rounds_up(self):
        service = _make_service(stripe_configured=False)
        service.platform_fee_percentage = 0.15
        service.payment_repository.create_payment_record.return_value = SimpleNamespace(
            id="pay_2", stripe_payment_intent_id="mock_pi_booking_2"
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", side_effect=Exception("boom")
        ):
            StripeService.create_payment_intent(
                service,
                booking_id="booking_2",
                customer_id="cus_2",
                destination_account_id="acct_2",
                amount_cents=101,
            )

        call_kwargs = service.payment_repository.create_payment_record.call_args.kwargs
        assert call_kwargs["application_fee"] == 16

    def test_create_and_confirm_manual_authorization_requires_action(self):
        service = _make_service()
        service.payment_repository.upsert_payment_record = None
        service.payment_repository.get_payment_by_intent_id.return_value = None

        pi = SimpleNamespace(id="pi_123", status="requires_action", client_secret="secret_123")

        with patch.object(stripe_service.stripe.PaymentIntent, "create", return_value=pi):
            result = StripeService.create_and_confirm_manual_authorization(
                service,
                booking_id="booking_3",
                customer_id="cus_3",
                destination_account_id="acct_3",
                payment_method_id="pm_1",
                amount_cents=2000,
                idempotency_key="auth_1",
            )

        assert result["requires_action"] is True
        assert result["client_secret"] == "secret_123"
        service.payment_repository.create_payment_record.assert_called_once()

    def test_create_and_confirm_manual_authorization_rounds_fee_up(self):
        service = _make_service()
        service.platform_fee_percentage = 0.15
        service.payment_repository.upsert_payment_record = None
        service.payment_repository.get_payment_by_intent_id.return_value = None

        pi = SimpleNamespace(id="pi_round", status="requires_capture", client_secret=None)

        with patch.object(stripe_service.stripe.PaymentIntent, "create", return_value=pi) as create:
            StripeService.create_and_confirm_manual_authorization(
                service,
                booking_id="booking_round",
                customer_id="cus_round",
                destination_account_id="acct_round",
                payment_method_id="pm_round",
                amount_cents=101,
                idempotency_key="auth_round",
            )

        create_kwargs = create.call_args.kwargs
        assert create_kwargs["transfer_data"]["amount"] == 85

    def test_capture_payment_intent_uses_metadata_fallback(self):
        service = _make_service()
        service.payment_repository.update_payment_status = MagicMock()

        class AttrDict(dict):
            __getattr__ = dict.get

        pi_payload = AttrDict({
            "id": "pi_123",
            "status": "succeeded",
            "amount_received": 4200,
            "charges": {"data": [{"id": "ch_1", "amount": 4200, "transfer": "tr_1"}]},
            "metadata": {"target_instructor_payout_cents": "4200"},
        })

        with patch.object(stripe_service.stripe.PaymentIntent, "capture", return_value=pi_payload):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", side_effect=Exception("boom")
            ):
                result = StripeService.capture_payment_intent(
                    service, "pi_123", idempotency_key="cap_1"
                )

        assert result["transfer_amount"] == 4200
        assert result["charge_id"] == "ch_1"
        service.payment_repository.update_payment_status.assert_called_once_with(
            "pi_123", "succeeded"
        )

    def test_capture_booking_payment_intent_computes_top_up(self):
        service = _make_service()
        service.stripe_configured = True
        service.capture_payment_intent = MagicMock(
            return_value={"payment_intent": SimpleNamespace(amount=3000, metadata=None)}
        )
        service._top_up_from_pi_metadata = MagicMock(return_value=None)
        service.build_charge_context = MagicMock(
            return_value=ChargeContext(
                booking_id="booking_4",
                applied_credit_cents=0,
                base_price_cents=5000,
                student_fee_cents=0,
                instructor_platform_fee_cents=0,
                target_instructor_payout_cents=5000,
                student_pay_cents=3000,
                application_fee_cents=0,
                top_up_transfer_cents=0,
                instructor_tier_pct=0,
            )
        )
        service.ensure_top_up_transfer = MagicMock()
        service.booking_repository.get_by_id.return_value = SimpleNamespace(
            id="booking_4", instructor_id="inst_user"
        )
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_1")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_1")
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", side_effect=Exception("nope")
        ):
            result = StripeService.capture_booking_payment_intent(
                service,
                booking_id="booking_4",
                payment_intent_id="pi_456",
                idempotency_key="cap_2",
            )

        assert result["top_up_transfer_cents"] == 2000
        service.ensure_top_up_transfer.assert_called_once()


class TestRefundsAndVoids:
    def test_refund_payment_omits_invalid_reason(self):
        service = _make_service()
        refund_obj = SimpleNamespace(id="re_1", status="succeeded", amount=500)

        with patch.object(stripe_service.StripeRefund, "create", return_value=refund_obj) as create:
            result = StripeService.refund_payment(
                service,
                "pi_999",
                amount_cents=500,
                reason="other",
                idempotency_key="refund_1",
            )

        call_kwargs = create.call_args.kwargs
        assert "reason" not in call_kwargs
        assert call_kwargs["idempotency_key"] == "refund_1"
        assert result["refund_id"] == "re_1"

    def test_refund_payment_includes_valid_reason(self):
        service = _make_service()
        refund_obj = SimpleNamespace(id="re_2", status="succeeded", amount=800)

        with patch.object(stripe_service.StripeRefund, "create", return_value=refund_obj) as create:
            StripeService.refund_payment(
                service,
                "pi_100",
                amount_cents=800,
                reason="duplicate",
                idempotency_key="refund_2",
                refund_application_fee=True,
            )

        call_kwargs = create.call_args.kwargs
        assert call_kwargs["reason"] == "duplicate"
        assert call_kwargs["refund_application_fee"] is True
        assert call_kwargs["idempotency_key"] == "refund_2"

    def test_void_or_refund_payment_requires_capture(self):
        service = _make_service()
        service.stripe_configured = True
        service.cancel_payment_intent = MagicMock()
        service.refund_payment = MagicMock()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            return_value=SimpleNamespace(status="requires_capture"),
        ):
            StripeService._void_or_refund_payment(service, "pi_123")

        service.cancel_payment_intent.assert_called_once_with(
            "pi_123", idempotency_key="void_pi_123"
        )
        service.refund_payment.assert_not_called()

    def test_void_or_refund_payment_succeeded(self):
        service = _make_service()
        service.stripe_configured = True
        service.cancel_payment_intent = MagicMock()
        service.refund_payment = MagicMock()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            return_value=SimpleNamespace(status="succeeded"),
        ):
            StripeService._void_or_refund_payment(service, "pi_456")

        service.refund_payment.assert_called_once_with(
            "pi_456",
            reverse_transfer=True,
            refund_application_fee=True,
            idempotency_key="refund_pi_456",
        )
        service.cancel_payment_intent.assert_not_called()
