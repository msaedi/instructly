"""Repository coverage for referrals data access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import ulid

from app.core.exceptions import RepositoryException
from app.models.instructor import InstructorProfile
from app.models.referrals import (
    InstructorReferralPayout,
    ReferralAttribution,
    ReferralCode,
    ReferralCodeStatus,
    ReferralReward,
    RewardSide,
    RewardStatus,
)
from app.repositories.referral_repository import (
    ReferralAttributionRepository,
    ReferralClickRepository,
    ReferralCodeRepository,
    ReferralRewardRepository,
)
from app.repositories.user_repository import UserRepository
from app.services import referral_utils


def _create_user(db, email: str, first_name: str = "Test", last_name: str = "User"):
    repo = UserRepository(db)
    user = repo.create(
        email=email,
        hashed_password="hashed",
        first_name=first_name,
        last_name=last_name,
        zip_code="11215",
        is_active=True,
    )
    db.commit()
    return user


def _create_instructor_profile(db, user_id: str, *, is_live: bool = False) -> InstructorProfile:
    profile = InstructorProfile(user_id=user_id, is_live=is_live)
    db.add(profile)
    db.flush()
    return profile


def _create_referral_code(db, referrer_user_id: str, code_value: str | None = None) -> ReferralCode:
    code = ReferralCode(
        id=str(ulid.ULID()),
        code=code_value or f"CODE{uuid.uuid4().hex[:8].upper()}",
        referrer_user_id=referrer_user_id,
        status=ReferralCodeStatus.ACTIVE,
    )
    db.add(code)
    db.flush()
    return code


def _create_reward(
    db,
    *,
    referrer_user_id: str,
    referred_user_id: str,
    side: RewardSide = RewardSide.STUDENT,
    status: RewardStatus = RewardStatus.PENDING,
    unlock_ts: datetime | None = None,
    expire_ts: datetime | None = None,
    amount_cents: int = 2000,
) -> ReferralReward:
    reward = ReferralReward(
        id=str(ulid.ULID()),
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        side=side,
        status=status,
        amount_cents=amount_cents,
        unlock_ts=unlock_ts,
        expire_ts=expire_ts,
        rule_version="T1",
    )
    db.add(reward)
    db.flush()
    return reward


def _create_attribution(db, *, code_id: str, referred_user_id: str) -> ReferralAttribution:
    attribution = ReferralAttribution(
        id=str(ulid.ULID()),
        code_id=code_id,
        referred_user_id=referred_user_id,
        source="test",
        ts=datetime.now(timezone.utc),
    )
    db.add(attribution)
    db.flush()
    return attribution


def test_referral_code_get_by_id_for_update(db):
    user = _create_user(db, "user_for_update@example.com")
    code = _create_referral_code(db, user.id)

    repo = ReferralCodeRepository(db)
    fetched = repo.get_by_id(code.id, for_update=True)

    assert fetched is not None
    assert fetched.id == code.id


def test_referral_code_get_or_create_returns_existing(db):
    user = _create_user(db, "existing_code@example.com")
    code = _create_referral_code(db, user.id)

    repo = ReferralCodeRepository(db)
    fetched = repo.get_or_create_for_user(user.id)

    assert fetched.id == code.id


def test_referral_code_get_or_create_insert_error_raises(db, monkeypatch):
    user = _create_user(db, "insert_error@example.com")
    repo = ReferralCodeRepository(db)
    original_execute = db.execute

    def _execute(stmt, *args, **kwargs):
        if isinstance(stmt, sa.sql.dml.Insert):
            raise SQLAlchemyError("boom")
        if isinstance(stmt, sa.sql.elements.TextClause):
            return None
        return original_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db, "execute", _execute)

    with pytest.raises(RepositoryException, match="Unable to issue referral code"):
        repo.get_or_create_for_user(user.id)


def test_referral_code_get_or_create_reload_missing_raises(db, monkeypatch):
    user = _create_user(db, "reload_missing@example.com")
    repo = ReferralCodeRepository(db)
    inserted_id = str(ulid.ULID())
    original_execute = db.execute

    class _Result:
        def __init__(self, *, first_value=None, scalar_value=None):
            self._first_value = first_value
            self._scalar_value = scalar_value

        def first(self):
            return self._first_value

        def scalar_one_or_none(self):
            return self._scalar_value

    def _execute(stmt, *args, **kwargs):
        if isinstance(stmt, sa.sql.dml.Insert):
            return _Result(first_value=(inserted_id,))
        if isinstance(stmt, sa.sql.Select):
            return _Result(scalar_value=None)
        if isinstance(stmt, sa.sql.elements.TextClause):
            return None
        return original_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(repo, "_get_by_user_id", lambda user_id: None)
    monkeypatch.setattr(db, "execute", _execute)

    with pytest.raises(RepositoryException, match="could not be reloaded"):
        repo.get_or_create_for_user(user.id)


def test_referral_code_get_or_create_retries_exhausted(db, monkeypatch):
    existing_owner = _create_user(db, "existing_owner@example.com")
    code_value = "DUPLICATE1"
    _create_referral_code(db, existing_owner.id, code_value=code_value)

    new_owner = _create_user(db, "new_owner@example.com")
    repo = ReferralCodeRepository(db)
    original_execute = db.execute

    monkeypatch.setattr(referral_utils, "gen_code", lambda: code_value)

    def _execute(stmt, *args, **kwargs):
        if isinstance(stmt, sa.sql.elements.TextClause):
            return None
        return original_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db, "execute", _execute)

    with pytest.raises(RepositoryException, match="unique referral code"):
        repo.get_or_create_for_user(new_owner.id)


def test_referral_click_get_fingerprint_snapshot(db):
    referrer = _create_user(db, "click_referrer@example.com")
    code = _create_referral_code(db, referrer.id)

    click_repo = ReferralClickRepository(db)
    attribution_ts = datetime.now(timezone.utc)
    click_repo.create(
        code_id=code.id,
        device_fp_hash="click-device",
        ip_hash="click-ip",
        ua_hash="ua",
        channel="email",
        ts=attribution_ts - timedelta(minutes=1),
    )
    click_repo.create(
        code_id=code.id,
        device_fp_hash="signup-device",
        ip_hash="signup-ip",
        ua_hash="ua",
        channel="signup",
        ts=attribution_ts,
    )

    snapshot = click_repo.get_fingerprint_snapshot(code.id, attribution_ts)

    assert snapshot["click_device"] == "click-device"
    assert snapshot["click_ip"] == "click-ip"
    assert snapshot["signup_device"] == "signup-device"
    assert snapshot["signup_ip"] == "signup-ip"


def test_referral_attribution_get_by_referred_user_id_for_update(db):
    referrer = _create_user(db, "attr_referrer@example.com")
    referred = _create_user(db, "attr_referred@example.com")
    code = _create_referral_code(db, referrer.id)
    _create_attribution(db, code_id=code.id, referred_user_id=referred.id)

    repo = ReferralAttributionRepository(db)
    fetched = repo.get_by_referred_user_id(referred.id, for_update=True)

    assert fetched is not None
    assert fetched.referred_user_id == referred.id


def test_referral_attribution_create_if_absent_flushes(db):
    referrer = _create_user(db, "attr_flush_referrer@example.com")
    referred = _create_user(db, "attr_flush_referred@example.com")
    code = _create_referral_code(db, referrer.id)

    repo = ReferralAttributionRepository(db)
    created = repo.create_if_absent(
        code_id=code.id,
        referred_user_id=referred.id,
        source="test",
        ts=datetime.now(timezone.utc),
    )

    assert created is True
    assert repo.exists_for_user(referred.id) is True


def test_create_instructor_referrer_reward(db):
    referrer = _create_user(db, "instructor_referrer@example.com")
    referred = _create_user(db, "instructor_referred@example.com")

    repo = ReferralRewardRepository(db)
    reward = repo.create_instructor_referrer_reward(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        amount_cents=5000,
        unlock_ts=datetime.now(timezone.utc),
        expire_ts=datetime.now(timezone.utc) + timedelta(days=30),
        rule_version="I1",
    )

    assert reward.side == RewardSide.INSTRUCTOR


def test_create_instructor_referral_payout_integrity_error(db, monkeypatch, test_booking, test_instructor, test_instructor_with_availability):
    repo = ReferralRewardRepository(db)

    def _raise_flush():
        raise IntegrityError("stmt", {}, Exception("boom"))

    monkeypatch.setattr(db, "flush", _raise_flush)

    payout = repo.create_instructor_referral_payout(
        referrer_user_id=test_instructor.id,
        referred_instructor_id=test_instructor_with_availability.id,
        triggering_booking_id=test_booking.id,
        amount_cents=5000,
        was_founding_bonus=False,
        idempotency_key="dup-key",
    )

    assert payout is None


def test_get_instructor_referral_payout_by_id(db, test_booking, test_instructor, test_instructor_with_availability):
    repo = ReferralRewardRepository(db)
    payout = repo.create_instructor_referral_payout(
        referrer_user_id=test_instructor.id,
        referred_instructor_id=test_instructor_with_availability.id,
        triggering_booking_id=test_booking.id,
        amount_cents=5000,
        was_founding_bonus=True,
        idempotency_key="unique-key",
    )

    assert payout is not None

    fetched = repo.get_instructor_referral_payout_by_id(payout.id)
    assert fetched is not None
    assert fetched.id == payout.id


def test_get_referrer_payouts_filters_status(db, test_booking):
    referrer = _create_user(db, "payout_referrer@example.com")
    referred_one = _create_user(db, "payout_referred_one@example.com")
    referred_two = _create_user(db, "payout_referred_two@example.com")

    payout_one = InstructorReferralPayout(
        referrer_user_id=referrer.id,
        referred_instructor_id=referred_one.id,
        triggering_booking_id=test_booking.id,
        amount_cents=5000,
        was_founding_bonus=False,
        idempotency_key="key-1",
        stripe_transfer_status="pending",
    )
    payout_two = InstructorReferralPayout(
        referrer_user_id=referrer.id,
        referred_instructor_id=referred_two.id,
        triggering_booking_id=test_booking.id,
        amount_cents=7500,
        was_founding_bonus=True,
        idempotency_key="key-2",
        stripe_transfer_status="completed",
    )
    db.add(payout_one)
    db.add(payout_two)
    db.commit()

    repo = ReferralRewardRepository(db)
    completed = repo.get_referrer_payouts(referrer.id, status="completed")

    assert len(completed) == 1
    assert completed[0].stripe_transfer_status == "completed"


def test_get_referred_instructors_with_payout_status(db, test_booking):
    referrer = _create_user(db, "referrer_list@example.com", first_name="Ref", last_name="Errer")
    referred = _create_user(db, "referred_list@example.com", first_name="Ada", last_name="Lovelace")
    _create_instructor_profile(db, referred.id, is_live=True)

    code = _create_referral_code(db, referrer.id)
    _create_attribution(db, code_id=code.id, referred_user_id=referred.id)

    payout = InstructorReferralPayout(
        referrer_user_id=referrer.id,
        referred_instructor_id=referred.id,
        triggering_booking_id=test_booking.id,
        amount_cents=5000,
        was_founding_bonus=False,
        idempotency_key="list-key",
        stripe_transfer_status="completed",
    )
    db.add(payout)
    db.commit()

    repo = ReferralRewardRepository(db)
    rows = repo.get_referred_instructors_with_payout_status(referrer.id, limit=10, offset=0)

    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == referred.id
    assert row["payout_amount_cents"] == 5000


def test_mark_unlocked_missing_raises(db):
    repo = ReferralRewardRepository(db)
    with pytest.raises(RepositoryException):
        repo.mark_unlocked(str(ulid.ULID()))


def test_mark_void_updates_status(db):
    referrer = _create_user(db, "void_referrer@example.com")
    referred = _create_user(db, "void_referred@example.com")
    reward = _create_reward(db, referrer_user_id=referrer.id, referred_user_id=referred.id)

    repo = ReferralRewardRepository(db)
    repo.mark_void(reward.id)

    db.refresh(reward)
    assert reward.status == RewardStatus.VOID


def test_void_rewards_empty_noop(db):
    repo = ReferralRewardRepository(db)
    repo.void_rewards([])


def test_mark_redeemed_missing_raises(db):
    repo = ReferralRewardRepository(db)
    with pytest.raises(RepositoryException):
        repo.mark_redeemed(str(ulid.ULID()))


def test_void_expired_marks_and_returns_ids(db):
    referrer = _create_user(db, "expired_referrer@example.com")
    referred = _create_user(db, "expired_referred@example.com")
    reward = _create_reward(
        db,
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        status=RewardStatus.UNLOCKED,
        unlock_ts=datetime.now(timezone.utc) - timedelta(days=10),
        expire_ts=datetime.now(timezone.utc) - timedelta(days=1),
    )

    repo = ReferralRewardRepository(db)
    expired_ids = repo.void_expired(datetime.now(timezone.utc))

    assert reward.id in expired_ids
    db.refresh(reward)
    assert reward.status == RewardStatus.VOID


def test_top_referrers_includes_code(db):
    referrer = _create_user(db, "top_referrer@example.com")
    referred = _create_user(db, "top_referred@example.com")
    code = _create_referral_code(db, referrer.id)

    _create_reward(
        db,
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        status=RewardStatus.UNLOCKED,
    )
    _create_reward(
        db,
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        status=RewardStatus.REDEEMED,
    )

    repo = ReferralRewardRepository(db)
    top = repo.top_referrers(limit=5)

    assert top
    assert top[0][0] == referrer.id
    assert top[0][2] == code.code
