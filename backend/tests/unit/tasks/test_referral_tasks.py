"""Tests for instructor referral payout Celery tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.models.referrals import InstructorReferralPayout
from app.tasks.referral_tasks import (
    check_pending_instructor_referral_payouts,
    process_instructor_referral_payout,
    retry_failed_instructor_referral_payouts,
)


class TestProcessInstructorReferralPayout:
    """Tests for the main payout processing task."""

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.StripeService")
    @patch("app.tasks.referral_tasks.InstructorProfileRepository")
    def test_successful_payout(self, mock_instructor_repo, mock_stripe_service, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout = Mock(spec=InstructorReferralPayout)
        mock_payout.id = "payout_123"
        mock_payout.referrer_user_id = "referrer_456"
        mock_payout.referred_instructor_id = "referred_789"
        mock_payout.amount_cents = 7500
        mock_payout.was_founding_bonus = True
        mock_payout.stripe_transfer_status = "pending"

        (
            mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value
        ) = mock_payout

        mock_profile = Mock()
        mock_profile.stripe_connected_account = Mock(
            stripe_account_id="acct_123",
            onboarding_completed=True,
        )
        mock_instructor_repo.return_value.get_by_user_id.return_value = mock_profile

        mock_stripe_service.return_value.create_referral_bonus_transfer.return_value = {
            "transfer_id": "tr_test123"
        }

        result = process_instructor_referral_payout.run("payout_123")

        assert result["status"] == "completed"
        assert result["transfer_id"] == "tr_test123"
        assert mock_payout.stripe_transfer_status == "completed"
        assert mock_payout.stripe_transfer_id == "tr_test123"
        assert mock_payout.transferred_at is not None

    @patch("app.tasks.referral_tasks.get_db_session")
    def test_payout_not_found(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db
        (
            mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value
        ) = None

        result = process_instructor_referral_payout.run("missing")

        assert result["status"] == "error"
        assert result["reason"] == "payout_not_found"

    @patch("app.tasks.referral_tasks.get_db_session")
    def test_already_completed_is_idempotent(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout = Mock(spec=InstructorReferralPayout)
        mock_payout.stripe_transfer_status = "completed"
        mock_payout.stripe_transfer_id = "tr_existing"
        (
            mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value
        ) = mock_payout

        result = process_instructor_referral_payout.run("payout_123")

        assert result["status"] == "already_completed"
        assert result["transfer_id"] == "tr_existing"

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.InstructorProfileRepository")
    def test_referrer_no_stripe_account(self, mock_instructor_repo, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout = Mock(spec=InstructorReferralPayout)
        mock_payout.referrer_user_id = "referrer_456"
        mock_payout.stripe_transfer_status = "pending"
        (
            mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value
        ) = mock_payout

        mock_profile = Mock()
        mock_profile.stripe_connected_account = None
        mock_instructor_repo.return_value.get_by_user_id.return_value = mock_profile

        result = process_instructor_referral_payout.run("payout_123")

        assert result["status"] == "error"
        assert result["reason"] == "no_stripe_account"
        assert mock_payout.stripe_transfer_status == "failed"
        assert mock_payout.failure_reason == "referrer_no_stripe_account"

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.StripeService")
    @patch("app.tasks.referral_tasks.InstructorProfileRepository")
    def test_stripe_failure_marks_payout_failed(
        self, mock_instructor_repo, mock_stripe_service, mock_db_session
    ):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout = Mock(spec=InstructorReferralPayout)
        mock_payout.referrer_user_id = "referrer_456"
        mock_payout.stripe_transfer_status = "pending"
        (
            mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value
        ) = mock_payout

        mock_profile = Mock()
        mock_profile.stripe_connected_account = Mock(
            stripe_account_id="acct_123",
            onboarding_completed=True,
        )
        mock_instructor_repo.return_value.get_by_user_id.return_value = mock_profile

        mock_stripe_service.return_value.create_referral_bonus_transfer.side_effect = Exception(
            "Stripe error"
        )

        with pytest.raises(Exception):
            process_instructor_referral_payout.run("payout_123")

        assert mock_payout.stripe_transfer_status == "failed"
        assert mock_payout.failed_at is not None


class TestRetryFailedPayouts:
    """Tests for the retry failed payouts periodic task."""

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.process_instructor_referral_payout")
    def test_retries_recent_failures(self, mock_process_task, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout1 = Mock(id="payout_1")
        mock_payout2 = Mock(id="payout_2")
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_payout1,
            mock_payout2,
        ]

        result = retry_failed_instructor_referral_payouts.run()

        assert result["retried"] == 2
        assert mock_process_task.delay.call_count == 2
        assert mock_payout1.stripe_transfer_status == "pending"
        assert mock_payout1.failed_at is None

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.process_instructor_referral_payout")
    def test_no_failures_to_retry(self, mock_process_task, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = retry_failed_instructor_referral_payouts.run()

        assert result["retried"] == 0
        mock_process_task.delay.assert_not_called()


class TestCheckPendingPayouts:
    """Tests for the pending payout safety net task."""

    @patch("app.tasks.referral_tasks.get_db_session")
    @patch("app.tasks.referral_tasks.process_instructor_referral_payout")
    def test_queues_stale_pending_payouts(self, mock_process_task, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        mock_payout = Mock(id="payout_1")
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_payout]

        result = check_pending_instructor_referral_payouts.run()

        assert result["queued"] == 1
        mock_process_task.delay.assert_called_once_with("payout_1")
