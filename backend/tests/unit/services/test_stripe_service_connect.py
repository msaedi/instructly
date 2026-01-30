"""Unit tests for StripeService connect/account management."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ServiceException
import app.services.stripe_service as stripe_service
from app.services.stripe_service import StripeService


@contextmanager
def _noop_repo_txn():
    yield None


def _make_service(*, stripe_configured: bool = True) -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.db.commit = MagicMock()
    service.db.rollback = MagicMock()
    service.logger = MagicMock()
    service.cache_service = None
    service.stripe_configured = stripe_configured
    service.payment_repository = MagicMock()
    service.payment_repository.transaction = _noop_repo_txn
    service.booking_repository = MagicMock()
    service.user_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.config_service = MagicMock()
    service.pricing_service = MagicMock()
    return service


class TestConnectAccounts:
    def test_create_connected_account_returns_existing(self):
        service = _make_service()
        existing = SimpleNamespace(stripe_account_id="acct_existing")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = existing

        with patch.object(stripe_service.stripe.Account, "create") as create_mock:
            result = StripeService.create_connected_account(
                service, "profile_1", "inst@example.com"
            )

        assert result is existing
        create_mock.assert_not_called()

    def test_create_connected_account_unconfigured_fallback(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.get_connected_account_by_instructor_id.return_value = None
        service.payment_repository.create_connected_account_record.return_value = SimpleNamespace(
            stripe_account_id="mock_acct_profile_2"
        )

        with patch.object(
            stripe_service.stripe.Account, "create", side_effect=Exception("boom")
        ):
            result = StripeService.create_connected_account(
                service, "profile_2", "inst2@example.com"
            )

        assert result.stripe_account_id == "mock_acct_profile_2"
        service.payment_repository.create_connected_account_record.assert_called_once_with(
            instructor_profile_id="profile_2",
            stripe_account_id="mock_acct_profile_2",
            onboarding_completed=False,
        )

    def test_create_connected_account_integrity_race_returns_existing(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_instructor_id.return_value = None
        existing = SimpleNamespace(stripe_account_id="acct_existing")
        service.payment_repository.get_connected_account_by_instructor_id.side_effect = [
            None,
            existing,
        ]
        service.payment_repository.create_connected_account_record.side_effect = IntegrityError(
            "statement", "params", "orig"
        )

        with patch.object(
            stripe_service.stripe.Account, "create", return_value=SimpleNamespace(id="acct_new")
        ):
            result = StripeService.create_connected_account(
                service, "profile_3", "inst3@example.com"
            )

        assert result is existing

    def test_create_account_link_missing_account_raises(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_instructor_id.return_value = None

        with pytest.raises(ServiceException, match="No connected account found"):
            StripeService.create_account_link(
                service,
                instructor_profile_id="profile_missing",
                refresh_url="https://example.com/refresh",
                return_url="https://example.com/return",
            )


class TestAccountStatusAndPayouts:
    def test_check_account_status_updates_onboarding(self):
        service = _make_service()
        account_record = SimpleNamespace(
            stripe_account_id="acct_1", onboarding_completed=False
        )
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            account_record
        )

        requirements = SimpleNamespace(
            currently_due=["field_1"], past_due=None, pending_verification=["field_2", 123]
        )
        stripe_account = SimpleNamespace(
            charges_enabled=True,
            payouts_enabled=False,
            details_submitted=True,
            requirements=requirements,
        )

        with patch.object(stripe_service.stripe.Account, "retrieve", return_value=stripe_account):
            result = StripeService.check_account_status(service, "profile_4")

        assert result["onboarding_completed"] is True
        assert result["charges_enabled"] is True
        assert "field_1" in result["requirements"]
        assert "field_2" in result["requirements"]
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_1", True
        )

    def test_set_payout_schedule_for_account_missing_account_raises(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_instructor_id.return_value = None

        with pytest.raises(ServiceException, match="Connected account not found"):
            StripeService.set_payout_schedule_for_account(service, instructor_profile_id="x")

    def test_set_payout_schedule_for_account_success(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_sched")
        )
        updated = SimpleNamespace(settings={"payouts": {"schedule": {"interval": "weekly"}}})

        with patch.object(stripe_service.stripe.Account, "modify", return_value=updated):
            result = StripeService.set_payout_schedule_for_account(
                service, instructor_profile_id="profile_5", interval="weekly", weekly_anchor="fri"
            )

        assert result["account_id"] == "acct_sched"
        assert "settings" in result
