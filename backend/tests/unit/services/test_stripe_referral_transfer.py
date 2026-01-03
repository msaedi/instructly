"""Tests for Stripe referral bonus transfer."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
import stripe

from app.core.exceptions import ServiceException
from app.services.stripe_service import StripeService


class TestCreateReferralBonusTransfer:
    """Tests for the create_referral_bonus_transfer method."""

    @patch("stripe.Transfer.create")
    def test_creates_transfer_with_correct_amount(self, mock_stripe_create, db):
        mock_stripe_create.return_value = MagicMock(id="tr_test123")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())
        service.create_referral_bonus_transfer(
            payout_id="payout_123",
            destination_account_id="acct_456",
            amount_cents=7500,
            referrer_user_id="referrer_789",
            referred_instructor_id="referred_012",
            was_founding_bonus=True,
        )

        call_kwargs = mock_stripe_create.call_args.kwargs
        assert call_kwargs["amount"] == 7500
        assert call_kwargs["currency"] == "usd"

    @patch("stripe.Transfer.create")
    def test_uses_correct_destination_account(self, mock_stripe_create, db):
        mock_stripe_create.return_value = MagicMock(id="tr_test123")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())
        service.create_referral_bonus_transfer(
            payout_id="payout_123",
            destination_account_id="acct_referrer",
            amount_cents=5000,
            referrer_user_id="referrer_789",
            referred_instructor_id="referred_012",
            was_founding_bonus=False,
        )

        call_kwargs = mock_stripe_create.call_args.kwargs
        assert call_kwargs["destination"] == "acct_referrer"

    @patch("stripe.Transfer.create")
    def test_idempotency_key_includes_payout_id(self, mock_stripe_create, db):
        mock_stripe_create.return_value = MagicMock(id="tr_test123")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())
        service.create_referral_bonus_transfer(
            payout_id="payout_unique_123",
            destination_account_id="acct_456",
            amount_cents=7500,
            referrer_user_id="referrer_789",
            referred_instructor_id="referred_012",
            was_founding_bonus=True,
        )

        call_kwargs = mock_stripe_create.call_args.kwargs
        assert "payout_unique_123" in call_kwargs["idempotency_key"]

    @patch("stripe.Transfer.create")
    def test_metadata_includes_all_fields(self, mock_stripe_create, db):
        mock_stripe_create.return_value = MagicMock(id="tr_test123")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())
        service.create_referral_bonus_transfer(
            payout_id="payout_123",
            destination_account_id="acct_456",
            amount_cents=7500,
            referrer_user_id="referrer_789",
            referred_instructor_id="referred_012",
            was_founding_bonus=True,
        )

        metadata = mock_stripe_create.call_args.kwargs["metadata"]
        assert metadata["type"] == "instructor_referral_bonus"
        assert metadata["payout_id"] == "payout_123"
        assert metadata["referrer_user_id"] == "referrer_789"
        assert metadata["referred_instructor_id"] == "referred_012"
        assert metadata["was_founding_bonus"] == "true"

    @patch("stripe.Transfer.create")
    def test_handles_stripe_error(self, mock_stripe_create, db):
        mock_stripe_create.side_effect = stripe.error.StripeError("Test error")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())

        with pytest.raises(ServiceException, match="Failed to create referral bonus transfer"):
            service.create_referral_bonus_transfer(
                payout_id="payout_123",
                destination_account_id="acct_456",
                amount_cents=7500,
                referrer_user_id="referrer_789",
                referred_instructor_id="referred_012",
                was_founding_bonus=True,
            )

    @patch("stripe.Transfer.create")
    def test_founding_bonus_description(self, mock_stripe_create, db):
        mock_stripe_create.return_value = MagicMock(id="tr_test123")

        service = StripeService(db, config_service=Mock(), pricing_service=Mock())
        service.create_referral_bonus_transfer(
            payout_id="payout_1",
            destination_account_id="acct_456",
            amount_cents=7500,
            referrer_user_id="referrer_789",
            referred_instructor_id="referred_012",
            was_founding_bonus=True,
        )

        description = mock_stripe_create.call_args.kwargs["description"]
        assert "Founding" in description
        assert "$75" in description
