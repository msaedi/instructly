"""Unit tests for `app.services.stripe.payment_flow`.

Covers Stripe 15 expand-parameter requirements on PaymentIntent refresh.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_service_with_payment_flow() -> Any:
    """Build a minimal object exposing `_refresh_captured_payment_intent`."""
    from app.services.stripe_service import StripeService

    svc = StripeService.__new__(StripeService)
    svc.stripe_configured = True
    svc.logger = MagicMock()
    return svc


@pytest.mark.unit
class TestRefreshCapturedPaymentIntent:
    """Verify Stripe 15 migration invariant: PaymentIntent.retrieve must expand latest_charge."""

    @patch("app.services.stripe_service.stripe")
    def test_refresh_captured_payment_intent_expands_latest_charge(self, mock_stripe: Any) -> None:
        svc = _make_service_with_payment_flow()
        mock_stripe.PaymentIntent.retrieve.return_value = MagicMock()

        svc._refresh_captured_payment_intent(
            payment_intent_id="pi_test_123",
            payment_intent=MagicMock(),
        )

        mock_stripe.PaymentIntent.retrieve.assert_called_once()
        call_kwargs = mock_stripe.PaymentIntent.retrieve.call_args.kwargs
        assert call_kwargs.get("expand") == ["latest_charge"], (
            "PaymentIntent.retrieve must pass expand=['latest_charge'] so downstream "
            "code can access charge fields as an expanded object (Stripe 15 requirement)"
        )

    @patch("app.services.stripe_service.stripe")
    def test_refresh_skipped_when_stripe_not_configured(self, mock_stripe: Any) -> None:
        svc = _make_service_with_payment_flow()
        svc.stripe_configured = False
        original_pi = MagicMock(name="original_pi")

        result = svc._refresh_captured_payment_intent(
            payment_intent_id="pi_test_123",
            payment_intent=original_pi,
        )

        mock_stripe.PaymentIntent.retrieve.assert_not_called()
        assert result is original_pi
