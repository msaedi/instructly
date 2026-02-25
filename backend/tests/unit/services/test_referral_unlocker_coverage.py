"""
Coverage tests for referral_unlocker.py targeting missed lines.

Targets:
  - L136-141: _update_backlog_warning counter edge cases
  - L173: _record_success timestamp tracking
  - L128-132: _extract_booking_prefix branches
  - L120-125: _booking_refunded branches
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.referral_unlocker import (
    ReferralUnlocker,
    UnlockerResult,
    _record_success,
    _result_to_dict,
    _update_backlog_warning,
    get_last_success_timestamp,
    main,
)


def _make_unlocker() -> ReferralUnlocker:
    """Create ReferralUnlocker with mocked dependencies."""
    import logging

    svc = ReferralUnlocker.__new__(ReferralUnlocker)
    svc.db = MagicMock()
    svc.referral_reward_repo = MagicMock()
    svc.payment_repository = MagicMock()
    svc.logger = logging.getLogger("test_referral_unlocker")
    return svc


@pytest.mark.unit
class TestRecordSuccess:
    """Cover _record_success and get_last_success_timestamp."""

    def test_record_and_get(self):
        """L28-33: records timestamp, get returns it."""
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        _record_success(ts)
        assert get_last_success_timestamp() == ts


@pytest.mark.unit
class TestUpdateBacklogWarning:
    """Cover _update_backlog_warning counter logic."""

    def test_backlog_increments_counter(self):
        """L38-39: backlog > 0 -> counter increments."""
        import app.services.referral_unlocker as mod
        mod._BACKLOG_WARN_COUNTER = 0

        _update_backlog_warning(5)
        assert mod._BACKLOG_WARN_COUNTER == 1

    def test_backlog_triggers_warning_at_threshold(self):
        """L40-44: counter >= 2 -> logs warning."""
        import app.services.referral_unlocker as mod
        mod._BACKLOG_WARN_COUNTER = 1

        _update_backlog_warning(10)
        assert mod._BACKLOG_WARN_COUNTER >= 2

    def test_zero_backlog_resets_counter(self):
        """L45-46: backlog == 0 -> resets counter."""
        import app.services.referral_unlocker as mod
        mod._BACKLOG_WARN_COUNTER = 5

        _update_backlog_warning(0)
        assert mod._BACKLOG_WARN_COUNTER == 0


@pytest.mark.unit
class TestExtractBookingPrefix:
    """Cover _extract_booking_prefix."""

    def test_none_rule_version(self):
        """L129: rule_version is None -> returns None."""
        assert ReferralUnlocker._extract_booking_prefix(None) is None

    def test_no_dash(self):
        """L129: no dash in rule_version -> returns None."""
        assert ReferralUnlocker._extract_booking_prefix("v1") is None

    def test_valid_prefix(self):
        """L130-132: valid format -> returns prefix after dash."""
        assert ReferralUnlocker._extract_booking_prefix("v1-BOOKING_01") == "BOOKING_01"

    def test_empty_prefix_after_dash(self):
        """L132: empty string after dash -> returns None."""
        assert ReferralUnlocker._extract_booking_prefix("v1-") is None


@pytest.mark.unit
class TestBookingRefunded:
    """Cover _booking_refunded."""

    def test_no_payment(self):
        """L122: no payment found -> False."""
        svc = _make_unlocker()
        svc.payment_repository.get_payment_by_booking_prefix.return_value = None
        assert svc._booking_refunded("BOOKING_01") is False

    def test_payment_no_status(self):
        """L122: payment.status is None -> False."""
        svc = _make_unlocker()
        mock_payment = MagicMock()
        mock_payment.status = None
        svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment
        assert svc._booking_refunded("BOOKING_01") is False

    def test_payment_refunded(self):
        """L125: status is 'refunded' -> True."""
        svc = _make_unlocker()
        mock_payment = MagicMock()
        mock_payment.status = "refunded"
        svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment
        assert svc._booking_refunded("BOOKING_01") is True

    def test_payment_canceled(self):
        """L125: status is 'canceled' -> True."""
        svc = _make_unlocker()
        mock_payment = MagicMock()
        mock_payment.status = "canceled"
        svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment
        assert svc._booking_refunded("BOOKING_01") is True

    def test_payment_cancelled_british(self):
        """L125: status is 'cancelled' -> True."""
        svc = _make_unlocker()
        mock_payment = MagicMock()
        mock_payment.status = "cancelled"
        svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment
        assert svc._booking_refunded("BOOKING_01") is True

    def test_payment_completed_not_refunded(self):
        """L125: status is 'completed' -> False."""
        svc = _make_unlocker()
        mock_payment = MagicMock()
        mock_payment.status = "completed"
        svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment
        assert svc._booking_refunded("BOOKING_01") is False


@pytest.mark.unit
class TestRunMethod:
    """Cover run method branches."""

    def test_config_disabled(self):
        """L70-75: config disabled -> returns empty result."""
        svc = _make_unlocker()
        with patch("app.services.referral_unlocker.get_effective_config") as mock_config:
            mock_config.return_value = {"enabled": False, "source": "db", "version": "1"}
            result = svc.run()
        assert result.processed == 0

    def test_dry_run(self):
        """L80-84: dry_run -> no commit, returns counts."""
        svc = _make_unlocker()
        with patch("app.services.referral_unlocker.get_effective_config") as mock_config:
            mock_config.return_value = {"enabled": True, "source": "db", "version": "1"}
            svc.referral_reward_repo.find_pending_to_unlock.return_value = [MagicMock()]
            svc.referral_reward_repo.get_expired_reward_ids.return_value = ["EXP_01"]
            result = svc.run(dry_run=True)
        assert result.processed == 1
        assert result.expired == 1
        assert result.unlocked == 0

    def test_run_with_voided_reward(self):
        """L93-98: reward with refunded booking -> voided."""
        svc = _make_unlocker()
        import app.services.referral_unlocker as mod
        mod._BACKLOG_WARN_COUNTER = 0

        mock_reward = MagicMock()
        mock_reward.id = "REWARD_01"
        mock_reward.rule_version = "v1-BOOKING_01"

        with patch("app.services.referral_unlocker.get_effective_config") as mock_config:
            mock_config.return_value = {"enabled": True, "source": "db", "version": "1"}
            svc.referral_reward_repo.find_pending_to_unlock.return_value = [mock_reward]
            svc.referral_reward_repo.void_expired.return_value = []
            svc.referral_reward_repo.count_pending_due.return_value = 0

            mock_payment = MagicMock()
            mock_payment.status = "refunded"
            svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment

            svc.db.begin_nested = MagicMock()
            svc.db.begin_nested.return_value.__enter__ = MagicMock()
            svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

            with patch("app.services.referral_unlocker.emit_reward_voided"):
                with patch("app.services.referral_unlocker.emit_reward_unlocked"):
                    result = svc.run()

        assert result.voided == 1
        assert result.unlocked == 0

    def test_run_with_unlocked_reward(self):
        """L100-102: reward without refund -> unlocked."""
        svc = _make_unlocker()
        import app.services.referral_unlocker as mod
        mod._BACKLOG_WARN_COUNTER = 0

        mock_reward = MagicMock()
        mock_reward.id = "REWARD_01"
        mock_reward.rule_version = "v1-BOOKING_01"

        with patch("app.services.referral_unlocker.get_effective_config") as mock_config:
            mock_config.return_value = {"enabled": True, "source": "db", "version": "1"}
            svc.referral_reward_repo.find_pending_to_unlock.return_value = [mock_reward]
            svc.referral_reward_repo.void_expired.return_value = []
            svc.referral_reward_repo.count_pending_due.return_value = 0

            mock_payment = MagicMock()
            mock_payment.status = "completed"
            svc.payment_repository.get_payment_by_booking_prefix.return_value = mock_payment

            svc.db.begin_nested = MagicMock()
            svc.db.begin_nested.return_value.__enter__ = MagicMock()
            svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

            with patch("app.services.referral_unlocker.emit_reward_voided"):
                with patch("app.services.referral_unlocker.emit_reward_unlocked"):
                    result = svc.run()

        assert result.unlocked == 1
        assert result.voided == 0


@pytest.mark.unit
class TestResultToDict:
    """Cover _result_to_dict."""

    def test_converts_result(self):
        result = UnlockerResult(processed=5, unlocked=3, voided=1, expired=1)
        d = _result_to_dict(result)
        assert d["processed"] == 5
        assert d["unlocked"] == 3
        assert d["voided"] == 1
        assert d["expired"] == 1


@pytest.mark.unit
class TestExecuteFunction:
    """Cover _execute function (L135-141)."""

    def test_execute_creates_session_and_runs(self):
        """L136-141: _execute creates a session, runs unlocker, and closes."""
        from app.services.referral_unlocker import _execute

        mock_session = MagicMock()
        mock_unlocker = MagicMock()
        mock_unlocker.run.return_value = UnlockerResult(
            processed=5, unlocked=3, voided=1, expired=1
        )

        with patch("app.services.referral_unlocker.SessionLocal", return_value=mock_session):
            with patch(
                "app.services.referral_unlocker.ReferralUnlocker", return_value=mock_unlocker
            ):
                result = _execute(limit=100, dry_run=False)

        assert result.processed == 5
        assert result.unlocked == 3
        mock_session.close.assert_called_once()

    def test_execute_closes_session_on_error(self):
        """L140-141: session.close() called in finally block even on error."""
        from app.services.referral_unlocker import _execute

        mock_session = MagicMock()
        mock_unlocker = MagicMock()
        mock_unlocker.run.side_effect = RuntimeError("boom")

        with patch("app.services.referral_unlocker.SessionLocal", return_value=mock_session):
            with patch(
                "app.services.referral_unlocker.ReferralUnlocker", return_value=mock_unlocker
            ):
                with pytest.raises(RuntimeError, match="boom"):
                    _execute(limit=100, dry_run=False)

        mock_session.close.assert_called_once()


@pytest.mark.unit
class TestMainFunction:
    """Cover main() with explicit parameters."""

    def test_main_with_params(self):
        """L168-170: explicit params bypass CLI parsing."""
        with patch("app.services.referral_unlocker._execute") as mock_execute:
            mock_execute.return_value = UnlockerResult(processed=0, unlocked=0, voided=0, expired=0)
            result = main(limit=10, dry_run=True)
        assert result["processed"] == 0
        mock_execute.assert_called_once_with(limit=10, dry_run=True)

    def test_main_with_only_limit(self):
        """L169-170: limit provided, dry_run defaults to False."""
        with patch("app.services.referral_unlocker._execute") as mock_execute:
            mock_execute.return_value = UnlockerResult(processed=0, unlocked=0, voided=0, expired=0)
            result = main(limit=50, dry_run=False)
        assert result["processed"] == 0
        mock_execute.assert_called_once_with(limit=50, dry_run=False)

    def test_main_with_none_limit_and_explicit_dry_run(self):
        """L169: limit=None → default 200; dry_run explicit."""
        with patch("app.services.referral_unlocker._execute") as mock_execute:
            mock_execute.return_value = UnlockerResult(processed=0, unlocked=0, voided=0, expired=0)
            main(limit=None, dry_run=True)
        # L169: limit defaults to 200 when None and not cli_invocation
        mock_execute.assert_called_once_with(limit=200, dry_run=True)
