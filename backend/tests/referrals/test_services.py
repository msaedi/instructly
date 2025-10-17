"""Referral service integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import ulid

from app.core.config import settings
from app.events import referral_events
from app.models.referrals import (
    ReferralReward,
    RewardSide,
    RewardStatus,
    WalletTransactionType,
)
from app.models.user import User
from app.services import referral_fraud
from app.services.referral_service import ReferralService
from app.services.referral_unlocker import ReferralUnlocker
from app.services.wallet_service import WalletService


@pytest.fixture
def referral_service(db):
    return ReferralService(db)


@pytest.fixture
def wallet_service(db):
    return WalletService(db)


@pytest.fixture
def unlocker(db):
    return ReferralUnlocker(db)


@pytest.fixture
def capture_events():
    collected = []

    def listener(event):
        collected.append(event)

    referral_events.register_listener(listener)
    yield collected
    referral_events.unregister_listener(listener)


def _create_user(db, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed",
        first_name="Test",
        last_name="User",
        zip_code="11215",
    )
    db.add(user)
    db.flush()
    return user


def test_student_flow_unlocks_and_emits_events(db, referral_service, unlocker, capture_events):
    referrer = _create_user(db, "referrer")
    student = _create_user(db, "student")

    code = referral_service.issue_code(referrer_user_id=referrer.id)
    referral_service.record_click(code=code.code, device_fp_hash="device_ref", ip_hash="ip_ref", channel="sms")

    signup_ts = datetime.now(timezone.utc) - timedelta(days=settings.referrals_hold_days + 10)
    referral_service.attribute_signup(
        referred_user_id=student.id,
        code=code.code,
        source="web_click",
        ts=signup_ts,
        device_fp_hash="device_student",
        ip_hash="ip_student",
    )

    booking_id = str(ulid.ULID())
    completed_at = signup_ts
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=booking_id,
        amount_cents=12000,
        completed_at=completed_at,
    )

    rewards = db.query(ReferralReward).filter(ReferralReward.side == RewardSide.STUDENT).all()
    assert len(rewards) == 2
    for reward in rewards:
        assert reward.status == RewardStatus.PENDING
        assert reward.unlock_ts is not None
        assert reward.expire_ts is not None

    result = unlocker.run(limit=10)
    assert result.unlocked == 2

    refreshed = db.query(ReferralReward).filter(ReferralReward.side == RewardSide.STUDENT).all()
    assert all(reward.status == RewardStatus.UNLOCKED for reward in refreshed)

    unlocked_events = [event for event in capture_events if event.__class__.__name__ == "RewardUnlocked"]
    assert len(unlocked_events) == 2


def test_global_cap_blocks_additional_rewards(db, referral_service, monkeypatch):
    referrer = _create_user(db, "referrer")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    monkeypatch.setattr(referral_service, "_beyond_student_cap", lambda *_: True)

    student = _create_user(db, "student")
    referral_service.record_click(code=code.code, channel="sms")
    referral_service.attribute_signup(
        referred_user_id=student.id,
        code=code.code,
        source="web_click",
        ts=datetime.now(timezone.utc),
    )
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=str(ulid.ULID()),
        amount_cents=12000,
        completed_at=datetime.now(timezone.utc),
    )

    total_rewards = db.query(ReferralReward).filter(ReferralReward.referrer_user_id == referrer.id).count()
    assert total_rewards == 0


def test_self_referral_voids_rewards(db, referral_service, capture_events, monkeypatch):
    user = _create_user(db, "self")
    code = referral_service.issue_code(referrer_user_id=user.id)

    monkeypatch.setattr(
        "app.services.referral_fraud.is_self_referral",
        lambda **_: True,
    )

    now = datetime.now(timezone.utc)
    referral_service.record_click(code=code.code, device_fp_hash="dup", ip_hash="dup", channel="share")
    referral_service.attribute_signup(
        referred_user_id=user.id,
        code=code.code,
        source="web_click",
        ts=now,
        device_fp_hash="dup",
        ip_hash="dup",
    )
    referral_service.on_first_booking_completed(
        user_id=user.id,
        booking_id=str(ulid.ULID()),
        amount_cents=9000,
        completed_at=now,
    )

    rewards = db.query(ReferralReward).all()
    assert len(rewards) == 1
    assert rewards[0].status == RewardStatus.VOID

    void_events = [event for event in capture_events if event.__class__.__name__ == "RewardVoided"]
    assert any(event.reason == "self_referral" for event in void_events)


def test_velocity_abuse_voids_rewards(db, referral_service, capture_events, monkeypatch):
    referrer = _create_user(db, "referrer")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    base_ts = datetime.now(timezone.utc)
    monkeypatch.setattr(
        referral_service.referral_attribution_repo,
        "velocity_counts",
        lambda *args, **kwargs: (6, 20),
    )

    student = _create_user(db, "student")
    referral_service.record_click(code=code.code, channel="share")
    referral_service.attribute_signup(
        referred_user_id=student.id,
        code=code.code,
        source="web_click",
        ts=base_ts,
    )
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=str(ulid.ULID()),
        amount_cents=12000,
        completed_at=base_ts,
    )

    rewards = db.query(ReferralReward).filter(ReferralReward.referrer_user_id == referrer.id).all()
    assert rewards
    assert all(reward.status == RewardStatus.VOID for reward in rewards)
    assert any(event.reason == "velocity" for event in capture_events if event.__class__.__name__ == "RewardVoided")


def test_refund_before_unlock_voids_reward(db, referral_service, unlocker, monkeypatch):
    referrer = _create_user(db, "referrer")
    student = _create_user(db, "student")
    code = referral_service.issue_code(referrer_user_id=referrer.id)
    referral_service.record_click(code=code.code, channel="share")
    now = datetime.now(timezone.utc) - timedelta(days=settings.referrals_hold_days + 5)
    referral_service.attribute_signup(
        referred_user_id=student.id,
        code=code.code,
        source="web_click",
        ts=now,
    )
    booking_id = str(ulid.ULID())
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=booking_id,
        amount_cents=10000,
        completed_at=now,
    )

    monkeypatch.setattr(unlocker, "_booking_refunded", lambda prefix: True)

    result = unlocker.run(limit=5)
    assert result.voided == 2

    rewards = db.query(ReferralReward).all()
    assert all(reward.status == RewardStatus.VOID for reward in rewards)


def test_instructor_flow_unlock_and_redeem(db, referral_service, unlocker, wallet_service, monkeypatch):
    referrer = _create_user(db, "referrer")
    instructor = _create_user(db, "instructor")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    referral_service.record_click(code=code.code, channel="share")
    signup_ts = datetime.now(timezone.utc) - timedelta(days=40)
    referral_service.attribute_signup(
        referred_user_id=instructor.id,
        code=code.code,
        source="web_click",
        ts=signup_ts,
    )

    counts = iter([1, 2, 3])

    def fake_lesson_count(*, instructor_user_id: str, window_start: datetime, window_end: datetime) -> int:
        return next(counts, 3)

    monkeypatch.setattr(referral_service.booking_repo, "count_completed_lessons", fake_lesson_count)

    for _ in range(3):
        referral_service.on_instructor_lesson_completed(
            instructor_user_id=instructor.id,
            lesson_id=str(ulid.ULID()),
            completed_at=signup_ts,
        )

    reward = (
        db.query(ReferralReward)
        .filter(
            ReferralReward.referrer_user_id == referrer.id,
            ReferralReward.referred_user_id == instructor.id,
            ReferralReward.side == RewardSide.INSTRUCTOR,
        )
        .one()
    )
    assert reward.status == RewardStatus.PENDING

    unlocker.run(limit=5)
    db.refresh(reward)
    assert reward.status == RewardStatus.UNLOCKED

    txn = wallet_service.apply_fee_rebate_on_payout(
        user_id=referrer.id,
        payout_id="po_test",
        platform_fee_cents=3000,
    )
    assert txn is not None
    db.refresh(reward)
    assert reward.status == RewardStatus.REDEEMED
    assert txn.type == WalletTransactionType.FEE_REBATE


def test_idempotency_guarantees(db, referral_service, unlocker, wallet_service):
    referrer = _create_user(db, "referrer")
    student = _create_user(db, "student")
    code = referral_service.issue_code(referrer_user_id=referrer.id)
    referral_service.record_click(code=code.code, channel="share")
    ts = datetime.now(timezone.utc) - timedelta(days=settings.referrals_hold_days + 2)
    referral_service.attribute_signup(
        referred_user_id=student.id,
        code=code.code,
        source="web_click",
        ts=ts,
    )
    booking_id = str(ulid.ULID())
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=booking_id,
        amount_cents=11000,
        completed_at=ts,
    )
    referral_service.on_first_booking_completed(
        user_id=student.id,
        booking_id=booking_id,
        amount_cents=11000,
        completed_at=ts,
    )

    rewards = db.query(ReferralReward).filter(ReferralReward.side == RewardSide.STUDENT).all()
    assert len(rewards) == 2

    unlocker.run(limit=5)
    unlocker.run(limit=5)

    unlocked_count = (
        db.query(ReferralReward)
        .filter(ReferralReward.side == RewardSide.STUDENT, ReferralReward.status == RewardStatus.UNLOCKED)
        .count()
    )
    assert unlocked_count == 2

    txn = wallet_service.consume_student_credit(user_id=student.id, order_id="order-1", amount_cents=1500)
    assert txn is not None
    second_attempt = wallet_service.consume_student_credit(user_id=student.id, order_id="order-1", amount_cents=1500)
    assert second_attempt is None


def test_velocity_limits_persist(db, referral_service, monkeypatch):
    referrer = _create_user(db, "velocity-limits@example.com")

    monkeypatch.setattr(
        referral_service.referral_attribution_repo,
        "velocity_counts",
        lambda *_args, **_kwargs: (6, 18),
    )

    monkeypatch.setattr(
        referral_fraud,
        "is_velocity_abuse",
        lambda *, daily_count, weekly_count, **_: daily_count > 5 or weekly_count > 15,
    )

    flagged = referral_service._is_velocity_abuse(referrer.id)
    assert flagged is True

    record = referral_service.referral_limit_repo.get(referrer.id)
    assert record is not None
    assert record.daily_ok == 6
    assert record.weekly_ok == 18
    assert record.trust_score == -1
    assert record.last_reviewed_at is not None


class TestFraudVelocity:
    def test_velocity_review_persists(self, db, referral_service, monkeypatch):
        referrer = _create_user(db, "velocity-review@example.com")

        counts = iter([(3, 12), (7, 22)])

        def fake_counts(*_args, **_kwargs):
            return next(counts)

        monkeypatch.setattr(
            referral_service.referral_attribution_repo,
            "velocity_counts",
            fake_counts,
        )

        def fake_velocity_check(*, daily_count, weekly_count, **_kwargs):
            return daily_count > 5 or weekly_count > 15

        monkeypatch.setattr(referral_fraud, "is_velocity_abuse", fake_velocity_check)

        first_flag = referral_service._is_velocity_abuse(referrer.id)
        assert first_flag is False
        initial_record = referral_service.referral_limit_repo.get(referrer.id)
        assert initial_record is not None
        assert initial_record.daily_ok == 3
        assert initial_record.trust_score == 0

        second_flag = referral_service._is_velocity_abuse(referrer.id)
        assert second_flag is True
        updated_record = referral_service.referral_limit_repo.get(referrer.id)
        assert updated_record is not None
        assert updated_record.daily_ok == 7
        assert updated_record.trust_score == -1
