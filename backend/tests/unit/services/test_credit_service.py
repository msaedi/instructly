from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.repositories.factory import RepositoryFactory
from app.services.credit_service import CreditService


def _make_credit(**overrides):
    data = {
        "id": "credit_1",
        "amount_cents": 1000,
        "reserved_amount_cents": None,
        "reserved_for_booking_id": None,
        "reserved_at": None,
        "status": "available",
        "expires_at": None,
        "source_booking_id": None,
        "source_type": "manual",
        "original_expires_at": None,
        "used_at": None,
        "used_booking_id": None,
        "forfeited_at": None,
        "revoked": False,
        "revoked_at": None,
        "revoked_reason": None,
        "frozen_at": None,
        "frozen_reason": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def db():
    session = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    return session


@pytest.fixture
def credit_repo():
    return Mock()


@pytest.fixture
def payment_repo():
    return Mock()


@pytest.fixture
def user_repo():
    return Mock()


@pytest.fixture
def service(db, credit_repo, payment_repo, user_repo, monkeypatch):
    monkeypatch.setattr(
        RepositoryFactory, "create_credit_repository", Mock(return_value=credit_repo)
    )
    monkeypatch.setattr(
        RepositoryFactory, "create_payment_repository", Mock(return_value=payment_repo)
    )
    monkeypatch.setattr(
        RepositoryFactory, "create_base_repository", Mock(return_value=user_repo)
    )
    return CreditService(db)


class TestCreditService:
    """Tests for CreditService - platform credit management."""

    class TestReserveCreditsForBooking:
        @pytest.mark.parametrize("max_amount", [0, -25])
        def test_reserve_credits_for_booking_non_positive_max_returns_zero(
            self, service, credit_repo, max_amount
        ):
            result = service.reserve_credits_for_booking(
                user_id="user_1",
                booking_id="booking_1",
                max_amount_cents=max_amount,
                use_transaction=False,
            )

            assert result == 0
            credit_repo.get_available_credits.assert_not_called()

        def test_reserve_credits_for_booking_skips_zero_amount_credit(self, service, payment_repo):
            credit = _make_credit(amount_cents=0)
            service.credit_repository.get_reserved_credits_for_booking.return_value = []
            service.credit_repository.get_available_credits.return_value = [credit]

            result = service.reserve_credits_for_booking(
                user_id="user_1",
                booking_id="booking_1",
                max_amount_cents=500,
                use_transaction=False,
            )

            assert result == 0
            payment_repo.bulk_create_payment_events.assert_not_called()
            payment_repo.create_payment_event.assert_not_called()

    class TestReleaseCreditsForBooking:
        def test_release_credits_for_booking_skips_zero_reserved_amount(self, service, payment_repo):
            credit = _make_credit(reserved_amount_cents=0, amount_cents=0)
            service.credit_repository.get_reserved_credits_for_booking.return_value = [credit]

            result = service.release_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 0
            payment_repo.create_payment_event.assert_not_called()

        def test_release_credits_for_booking_marks_expired_when_past_expiry(self, service):
            credit = _make_credit(
                reserved_amount_cents=250,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                status="reserved",
            )
            service.credit_repository.get_reserved_credits_for_booking.return_value = [credit]

            result = service.release_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 250
            assert credit.status == "expired"

    class TestForfeitCreditsForBooking:
        def test_forfeit_credits_for_booking_skips_zero_amount(self, service, payment_repo):
            credit = _make_credit(reserved_amount_cents=0, amount_cents=0)
            service.credit_repository.get_reserved_credits_for_booking.return_value = [credit]

            result = service.forfeit_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 0
            payment_repo.create_payment_event.assert_not_called()

    class TestIssueCredit:
        @pytest.mark.parametrize("amount", [0, -100])
        def test_issue_credit_rejects_non_positive_amount(self, service, payment_repo, amount):
            result = service.issue_credit(
                user_id="user_1",
                amount_cents=amount,
                source_type="referral",
                use_transaction=False,
            )

            assert result is None
            payment_repo.create_platform_credit.assert_not_called()

    class TestFreezeCreditsForBooking:
        def test_freeze_credits_for_booking_uses_transaction(self, service, db):
            credits = [_make_credit(id="c1"), _make_credit(id="c2")]
            service.credit_repository.get_credits_for_source_booking.return_value = credits

            result = service.freeze_credits_for_booking(
                booking_id="booking_1",
                reason="dispute",
                use_transaction=True,
            )

            assert result == 2
            db.commit.assert_called_once()

    class TestRevokeCreditsForBooking:
        def test_revoke_credits_for_booking_returns_zero_when_no_credits(self, service):
            service.credit_repository.get_credits_for_source_booking.return_value = []

            result = service.revoke_credits_for_booking(
                booking_id="booking_1",
                reason="chargeback",
                use_transaction=False,
            )

            assert result == 0

        def test_revoke_credits_for_booking_skips_already_revoked(self, service):
            already_revoked = _make_credit(status="revoked")
            active_credit = _make_credit(id="c2", status="available")
            service.credit_repository.get_credits_for_source_booking.return_value = [
                already_revoked,
                active_credit,
            ]

            result = service.revoke_credits_for_booking(
                booking_id="booking_1",
                reason="chargeback",
                use_transaction=False,
            )

            assert result == 1
            assert active_credit.status == "revoked"

        def test_revoke_credits_for_booking_uses_transaction(self, service, db):
            service.credit_repository.get_credits_for_source_booking.return_value = [_make_credit()]

            result = service.revoke_credits_for_booking(
                booking_id="booking_1",
                reason="chargeback",
                use_transaction=True,
            )

            assert result == 1
            db.commit.assert_called_once()

    class TestUnfreezeCreditsForBooking:
        def test_unfreeze_credits_for_booking_returns_zero_when_none(self, service):
            service.credit_repository.get_credits_for_source_booking.return_value = []

            result = service.unfreeze_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 0

        def test_unfreeze_credits_for_booking_sets_reserved_status(self, service):
            credit = _make_credit(
                status="frozen",
                reserved_for_booking_id="booking_1",
                reserved_amount_cents=0,
            )
            service.credit_repository.get_credits_for_source_booking.return_value = [credit]

            result = service.unfreeze_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 1
            assert credit.status == "reserved"
            assert credit.frozen_at is None
            assert credit.frozen_reason is None

        def test_unfreeze_credits_for_booking_sets_expired_status(self, service):
            credit = _make_credit(
                status="frozen",
                reserved_for_booking_id=None,
                reserved_amount_cents=0,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            service.credit_repository.get_credits_for_source_booking.return_value = [credit]

            result = service.unfreeze_credits_for_booking(
                booking_id="booking_1",
                use_transaction=False,
            )

            assert result == 1
            assert credit.status == "expired"

        def test_unfreeze_credits_for_booking_uses_transaction(self, service, db):
            service.credit_repository.get_credits_for_source_booking.return_value = [_make_credit()]

            result = service.unfreeze_credits_for_booking(
                booking_id="booking_1",
                use_transaction=True,
            )

            assert result == 1
            db.commit.assert_called_once()

    class TestGetSpentCreditsForBooking:
        def test_get_spent_credits_for_booking_returns_zero_on_exception(self, service):
            service.credit_repository.get_credits_for_source_booking.side_effect = Exception("boom")

            result = service.get_spent_credits_for_booking(booking_id="booking_1")

            assert result == 0

        def test_get_spent_credits_for_booking_counts_used_at(self, service):
            credit = _make_credit(used_at=datetime.now(timezone.utc), amount_cents=1200)
            service.credit_repository.get_credits_for_source_booking.return_value = [credit]

            result = service.get_spent_credits_for_booking(booking_id="booking_1")

            assert result == 1200

        def test_get_spent_credits_for_booking_counts_used_booking_id(self, service):
            credit = _make_credit(used_booking_id="booking_1", amount_cents=900)
            service.credit_repository.get_credits_for_source_booking.return_value = [credit]

            result = service.get_spent_credits_for_booking(booking_id="booking_1")

            assert result == 900

    class TestApplyNegativeBalance:
        def test_apply_negative_balance_ignores_non_positive_amount(self, service, user_repo):
            service.apply_negative_balance(
                user_id="user_1",
                amount_cents=0,
                reason="chargeback",
                use_transaction=False,
            )

            user_repo.get_by_id.assert_not_called()

        def test_apply_negative_balance_returns_when_user_missing(self, service, user_repo):
            user_repo.get_by_id.return_value = None

            service.apply_negative_balance(
                user_id="user_1",
                amount_cents=200,
                reason="chargeback",
                use_transaction=False,
            )

            user_repo.get_by_id.assert_called_once_with("user_1")

        def test_apply_negative_balance_marks_account_restricted(self, service, user_repo):
            user = _make_credit(credit_balance_cents=0, account_restricted=False)
            user_repo.get_by_id.return_value = user

            service.apply_negative_balance(
                user_id="user_1",
                amount_cents=500,
                reason="chargeback",
                use_transaction=False,
            )

            assert user.credit_balance_cents == -500
            assert user.account_restricted is True
            assert user.account_restricted_reason == "chargeback"

        def test_apply_negative_balance_uses_transaction(self, service, user_repo, db):
            user = _make_credit(credit_balance_cents=0, account_restricted=False)
            user_repo.get_by_id.return_value = user

            service.apply_negative_balance(
                user_id="user_1",
                amount_cents=100,
                reason="chargeback",
                use_transaction=True,
            )

            db.commit.assert_called_once()

    class TestClearNegativeBalance:
        def test_clear_negative_balance_ignores_non_positive_amount(self, service, user_repo):
            service.clear_negative_balance(
                user_id="user_1",
                amount_cents=0,
                reason="resolved",
                use_transaction=False,
            )

            user_repo.get_by_id.assert_not_called()

        def test_clear_negative_balance_returns_when_user_missing(self, service, user_repo):
            user_repo.get_by_id.return_value = None

            service.clear_negative_balance(
                user_id="user_1",
                amount_cents=200,
                reason="resolved",
                use_transaction=False,
            )

            user_repo.get_by_id.assert_called_once_with("user_1")

        def test_clear_negative_balance_clears_restriction(self, service, user_repo):
            user = _make_credit(
                credit_balance_cents=-50,
                account_restricted=True,
                account_restricted_at=datetime.now(timezone.utc),
                account_restricted_reason="chargeback",
            )
            user_repo.get_by_id.return_value = user

            service.clear_negative_balance(
                user_id="user_1",
                amount_cents=100,
                reason="resolved",
                use_transaction=False,
            )

            assert user.credit_balance_cents == 50
            assert user.account_restricted is False
            assert user.account_restricted_at is None
            assert user.account_restricted_reason is None

        def test_clear_negative_balance_uses_transaction(self, service, user_repo, db):
            user = _make_credit(
                credit_balance_cents=-100,
                account_restricted=True,
            )
            user_repo.get_by_id.return_value = user

            service.clear_negative_balance(
                user_id="user_1",
                amount_cents=200,
                reason="resolved",
                use_transaction=True,
            )

            db.commit.assert_called_once()

    class TestCreditSummary:
        def test_get_credit_summary_returns_totals(self, service):
            service.credit_repository.get_total_available_credits.return_value = 300
            service.credit_repository.get_total_reserved_credits.return_value = 200

            result = service.get_credit_summary(user_id="user_1")

            assert result == {
                "available_cents": 300,
                "reserved_cents": 200,
                "total_cents": 500,
            }

    class TestExpireOldCredits:
        def test_expire_old_credits_uses_transaction(self, service, db):
            credit = _make_credit(status="available")
            service.credit_repository.get_expired_available_credits.return_value = [credit]

            result = service.expire_old_credits(use_transaction=True)

            assert result == 1
            assert credit.status == "expired"
            db.commit.assert_called_once()
