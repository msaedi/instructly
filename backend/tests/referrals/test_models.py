"""Tests for referral data layer models."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models.referrals import (
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralCodeStatus,
    ReferralLimit,
    ReferralReward,
    RewardSide,
    RewardStatus,
    WalletTransaction,
    WalletTransactionType,
)
from app.models.user import User


def _make_user(db, prefix: str) -> User:
    """Create and persist a test user with a unique email."""

    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"{prefix}.{suffix}@example.com",
        hashed_password="hashed",
        first_name=f"{prefix.title()}",
        last_name="Tester",
        zip_code="11215",
    )
    db.add(user)
    db.flush()
    return user


def test_referral_code_unique_code_enforced(db):
    referrer = _make_user(db, "referrer")

    code = ReferralCode(referrer_user_id=referrer.id, code="ABCDEFGH")
    db.add(code)
    db.flush()

    assert code.status == ReferralCodeStatus.ACTIVE

    db.add(ReferralCode(referrer_user_id=referrer.id, code="ABCDEFGH"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_referral_code_unique_vanity_enforced(db):
    referrer = _make_user(db, "referrer")

    db.add(ReferralCode(referrer_user_id=referrer.id, code="IJKLMNPQ", vanity_slug="instainstru-beta"))
    db.flush()

    db.add(ReferralCode(referrer_user_id=referrer.id, code="QRSTUVWX", vanity_slug="instainstru-beta"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_referral_click_and_attribution_enforce_uniques(db):
    referrer = _make_user(db, "referrer")
    referred = _make_user(db, "referred")

    code = ReferralCode(referrer_user_id=referrer.id, code="YZABCDEF")
    db.add(code)
    db.flush()

    click = ReferralClick(code_id=code.id, channel="sms")
    db.add(click)
    db.flush()
    assert click.code_id == code.id

    attribution = ReferralAttribution(
        code_id=code.id,
        referred_user_id=referred.id,
        source="web_click",
        ts=datetime.now(timezone.utc),
    )
    db.add(attribution)
    db.flush()

    db.add(
        ReferralAttribution(
            code_id=code.id,
            referred_user_id=referred.id,
            source="manual",
            ts=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_referral_reward_and_wallet_transaction_flow(db):
    referrer = _make_user(db, "referrer")
    referred = _make_user(db, "referred")

    reward = ReferralReward(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        side=RewardSide.STUDENT,
        amount_cents=2000,
    )
    db.add(reward)
    db.flush()

    assert reward.status == RewardStatus.PENDING

    wallet_txn = WalletTransaction(
        user_id=referrer.id,
        type=WalletTransactionType.REFERRAL_CREDIT,
        amount_cents=2000,
        related_reward_id=reward.id,
    )
    db.add(wallet_txn)
    db.flush()

    assert wallet_txn.related_reward_id == reward.id


def test_referral_reward_amount_must_be_non_negative(db):
    referrer = _make_user(db, "referrer")
    referred = _make_user(db, "referred")

    db.add(
        ReferralReward(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            side=RewardSide.INSTRUCTOR,
            amount_cents=-5,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_wallet_transaction_amount_must_be_non_negative(db):
    user = _make_user(db, "ledger")

    db.add(
        WalletTransaction(
            user_id=user.id,
            type=WalletTransactionType.FEE_REBATE,
            amount_cents=-10,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_referral_limits_round_trip(db):
    user = _make_user(db, "limited")

    limits = ReferralLimit(
        user_id=user.id,
        daily_ok=3,
        weekly_ok=10,
        month_cap=25,
        trust_score=5,
        last_reviewed_at=datetime.now(timezone.utc),
    )
    db.add(limits)
    db.flush()

    fetched = db.get(ReferralLimit, user.id)
    assert fetched is not None
    assert fetched.daily_ok == 3
    assert fetched.trust_score == 5


def test_referral_indexes_exist(db):
    inspector = inspect(db.bind)

    idx_referral_codes = {idx["name"] for idx in inspector.get_indexes("referral_codes")}
    idx_referral_clicks = {idx["name"] for idx in inspector.get_indexes("referral_clicks")}
    idx_referral_rewards = {idx["name"] for idx in inspector.get_indexes("referral_rewards")}
    idx_wallet_txns = {idx["name"] for idx in inspector.get_indexes("wallet_transactions")}

    assert "idx_referral_codes_referrer_user_id" in idx_referral_codes
    assert "idx_referral_clicks_code_ts" in idx_referral_clicks
    assert "idx_referral_rewards_referrer_status" in idx_referral_rewards
    assert "idx_referral_rewards_referred_side" in idx_referral_rewards
    assert "idx_wallet_transactions_user_created_at" in idx_wallet_txns
