from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.referrals import ReferralReward, RewardSide, RewardStatus
from app.services import referral_unlocker
from app.services.referral_unlocker import ReferralUnlocker, UnlockerResult


@pytest.fixture
def unlocker(db):
    return ReferralUnlocker(db)


def _create_user(db, suffix: str) -> str:
    from app.models.user import User

    user = User(
        email=f"unlocker-{suffix}@example.com",
        hashed_password="x",
        first_name="Test",
        last_name="User",
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    return user.id


def _create_reward(
    db,
    *,
    referrer_id: str,
    referred_id: str,
    status: RewardStatus,
    unlock_ts: datetime | None,
    expire_ts: datetime | None,
    rule_version: str | None = None,
) -> ReferralReward:
    reward = ReferralReward(
        referrer_user_id=referrer_id,
        referred_user_id=referred_id,
        side=RewardSide.STUDENT,
        status=status,
        amount_cents=2500,
        unlock_ts=unlock_ts,
        expire_ts=expire_ts,
        rule_version=rule_version,
    )
    db.add(reward)
    db.flush()
    return reward


def test_unlocker_config_disabled(db, unlocker, monkeypatch):
    monkeypatch.setattr(
        referral_unlocker,
        "get_effective_config",
        lambda *_: {"enabled": False, "source": "test", "version": 1},
    )

    result = unlocker.run()

    assert result == UnlockerResult(processed=0, unlocked=0, voided=0, expired=0)


def test_unlocker_dry_run_counts(db, unlocker, monkeypatch):
    now = datetime.now(timezone.utc)
    referrer_id = _create_user(db, "referrer")
    referred_id = _create_user(db, "referred")

    _create_reward(
        db,
        referrer_id=referrer_id,
        referred_id=referred_id,
        status=RewardStatus.PENDING,
        unlock_ts=now - timedelta(days=1),
        expire_ts=now + timedelta(days=1),
    )
    _create_reward(
        db,
        referrer_id=referrer_id,
        referred_id=referred_id,
        status=RewardStatus.PENDING,
        unlock_ts=now - timedelta(hours=2),
        expire_ts=now + timedelta(days=2),
    )
    _create_reward(
        db,
        referrer_id=referrer_id,
        referred_id=referred_id,
        status=RewardStatus.UNLOCKED,
        unlock_ts=now - timedelta(days=2),
        expire_ts=now - timedelta(hours=1),
    )
    db.commit()

    monkeypatch.setattr(
        referral_unlocker,
        "get_effective_config",
        lambda *_: {"enabled": True, "source": "test", "version": 1},
    )

    result = unlocker.run(limit=10, dry_run=True)

    assert result.processed == 2
    assert result.expired == 1
    assert result.unlocked == 0
    assert result.voided == 0


def test_backlog_warning_and_reset(monkeypatch):
    referral_unlocker._BACKLOG_WARN_COUNTER = 0
    warnings: list[int] = []

    def _warn(*_args, **_kwargs):
        warnings.append(1)

    monkeypatch.setattr(referral_unlocker.logger, "warning", _warn)

    referral_unlocker._update_backlog_warning(2)
    referral_unlocker._update_backlog_warning(3)

    assert warnings == [1]
    assert referral_unlocker._BACKLOG_WARN_COUNTER >= 2

    referral_unlocker._update_backlog_warning(0)
    assert referral_unlocker._BACKLOG_WARN_COUNTER == 0


def test_extract_booking_prefix_variants():
    assert referral_unlocker.ReferralUnlocker._extract_booking_prefix(None) is None
    assert referral_unlocker.ReferralUnlocker._extract_booking_prefix("") is None
    assert referral_unlocker.ReferralUnlocker._extract_booking_prefix("v1") is None
    assert referral_unlocker.ReferralUnlocker._extract_booking_prefix("v1-") is None
    assert referral_unlocker.ReferralUnlocker._extract_booking_prefix("v1-abc") == "abc"


def test_booking_refunded_status(unlocker, monkeypatch):
    class Payment:
        def __init__(self, status):
            self.status = status

    monkeypatch.setattr(
        unlocker.payment_repository,
        "get_payment_by_booking_prefix",
        lambda _prefix: Payment("refunded"),
    )
    assert unlocker._booking_refunded("bk") is True

    monkeypatch.setattr(
        unlocker.payment_repository,
        "get_payment_by_booking_prefix",
        lambda _prefix: Payment("cancelled"),
    )
    assert unlocker._booking_refunded("bk") is True

    monkeypatch.setattr(
        unlocker.payment_repository,
        "get_payment_by_booking_prefix",
        lambda _prefix: Payment("authorized"),
    )
    assert unlocker._booking_refunded("bk") is False

    monkeypatch.setattr(
        unlocker.payment_repository,
        "get_payment_by_booking_prefix",
        lambda _prefix: Payment(None),
    )
    assert unlocker._booking_refunded("bk") is False


def test_record_success_and_get_last_success():
    now = datetime.now(timezone.utc)
    referral_unlocker._record_success(now)
    assert referral_unlocker.get_last_success_timestamp() == now


def test_main_non_cli(monkeypatch):
    expected = UnlockerResult(processed=1, unlocked=1, voided=0, expired=0)
    monkeypatch.setattr(referral_unlocker, "_execute", lambda **_kwargs: expected)

    result = referral_unlocker.main(limit=5, dry_run=True)

    assert result == {"processed": 1, "unlocked": 1, "voided": 0, "expired": 0}


def test_main_cli_invocation_with_parser(monkeypatch):
    expected = UnlockerResult(processed=2, unlocked=1, voided=0, expired=1)
    monkeypatch.setattr(referral_unlocker, "_execute", lambda **_kwargs: expected)

    class DummyParser:
        def add_argument(self, *_args, **_kwargs):
            return None

        def parse_args(self):
            return SimpleNamespace(limit=7, dry_run=True)

    monkeypatch.setattr(referral_unlocker.argparse, "ArgumentParser", lambda **_kw: DummyParser())

    result = referral_unlocker.main()

    assert result == {"processed": 2, "unlocked": 1, "voided": 0, "expired": 1}


def test_unlocker_run_unlocks_voids_and_expires(unlocker, monkeypatch):
    class Reward:
        def __init__(self, rid: str, rule_version: str | None) -> None:
            self.id = rid
            self.rule_version = rule_version

    reward_void = Reward("reward-void", "v1-bk123")
    reward_ok = Reward("reward-ok", None)

    monkeypatch.setattr(
        referral_unlocker,
        "get_effective_config",
        lambda *_: {"enabled": True, "source": "test", "version": 1},
    )

    unlocker.referral_reward_repo = SimpleNamespace(
        find_pending_to_unlock=lambda *_args, **_kwargs: [reward_void, reward_ok],
        mark_void=lambda _reward_id: None,
        mark_unlocked=lambda _reward_id: None,
        void_expired=lambda _now: ["expired-1"],
        count_pending_due=lambda _now: 2,
    )

    class Payment:
        def __init__(self, status: str | None) -> None:
            self.status = status

    monkeypatch.setattr(
        unlocker.payment_repository,
        "get_payment_by_booking_prefix",
        lambda prefix: Payment("refunded") if prefix == "bk123" else Payment("authorized"),
    )

    voided: list[str] = []
    unlocked: list[str] = []
    monkeypatch.setattr(referral_unlocker, "emit_reward_voided", lambda reward_id, **_: voided.append(reward_id))
    monkeypatch.setattr(
        referral_unlocker, "emit_reward_unlocked", lambda reward_id, **_: unlocked.append(reward_id)
    )

    result = unlocker.run(limit=10, dry_run=False)

    assert result.processed == 2
    assert result.voided == 1
    assert result.unlocked == 1
    assert result.expired == 1
    assert "reward-void" in voided
    assert "reward-ok" in unlocked


def test_main_cli_invocation_overrides(monkeypatch):
    expected = UnlockerResult(processed=2, unlocked=1, voided=1, expired=0)
    monkeypatch.setattr(referral_unlocker, "_execute", lambda **_kwargs: expected)
    monkeypatch.setattr(
        referral_unlocker.argparse, "ArgumentParser", lambda **_kwargs: SimpleNamespace(
            add_argument=lambda *_args, **_kwargs: None,
            parse_args=lambda: SimpleNamespace(limit=3, dry_run=True),
        )
    )

    result = referral_unlocker.main()

    assert result["processed"] == 2
