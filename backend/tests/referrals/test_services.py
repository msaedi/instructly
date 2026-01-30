"""Referral service integration tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import uuid

import pytest
import ulid

from app.core.config import settings
from app.events import referral_events
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.referrals import (
    InstructorReferralPayout,
    ReferralReward,
    RewardSide,
    RewardStatus,
)
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services import referral_fraud
from app.services.referral_service import ReferralService
from app.services.referral_unlocker import ReferralUnlocker
from app.services.wallet_service import WalletService

try:  # pragma: no cover - allow repo root or backend/ test execution
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


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


def _create_instructor_profile(db, user: User) -> InstructorProfile:
    profile = InstructorProfile(user_id=user.id)
    db.add(profile)
    db.flush()
    return profile


def _create_instructor_with_stripe(db, user: User) -> InstructorProfile:
    profile = _create_instructor_profile(db, user)

    connected = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        stripe_account_id=f"acct_{ulid.ULID()}",
        onboarding_completed=True,
    )
    db.add(connected)
    db.flush()
    return profile


def _get_or_create_catalog_entry(db) -> ServiceCatalog:
    catalog = db.query(ServiceCatalog).first()
    if catalog:
        return catalog

    category = ServiceCategory(
        name="Test Category",
        slug=f"test-category-{uuid.uuid4().hex[:6]}",
        description="Test category",
    )
    db.add(category)
    db.flush()

    catalog = ServiceCatalog(
        category_id=category.id,
        name="Test Service",
        slug=f"test-service-{uuid.uuid4().hex[:6]}",
        description="Test service",
    )
    db.add(catalog)
    db.flush()
    return catalog


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


def test_self_referral_blocked_at_signup(db, referral_service, capture_events, monkeypatch):
    """Proactive self-referral prevention: user cannot use their own referral code."""
    user = _create_user(db, "self")
    code = referral_service.issue_code(referrer_user_id=user.id)

    now = datetime.now(timezone.utc)
    referral_service.record_click(code=code.code, device_fp_hash="dup", ip_hash="dup", channel="share")

    # User tries to use their own code - should be blocked at signup
    result = referral_service.attribute_signup(
        referred_user_id=user.id,
        code=code.code,
        source="web_click",
        ts=now,
        device_fp_hash="dup",
        ip_hash="dup",
    )

    # Attribution should fail (returns False)
    assert result is False

    # No attribution should be created
    attribution = referral_service.referral_attribution_repo.get_by_referred_user_id(str(user.id))
    assert attribution is None

    # Attempting first booking completion should not create any rewards
    # (because no attribution exists)
    referral_service.on_first_booking_completed(
        user_id=user.id,
        booking_id=str(ulid.ULID()),
        amount_cents=9000,
        completed_at=now,
    )

    # No rewards should be created since attribution was blocked
    rewards = db.query(ReferralReward).all()
    assert len(rewards) == 0


def test_self_referral_fingerprint_detection_voids_rewards(db, referral_service, capture_events, monkeypatch):
    """
    Fingerprint-based self-referral detection (defense-in-depth).

    Even if proactive blocking is bypassed (e.g., different user IDs but same device),
    fingerprint detection at booking completion still voids rewards.
    """
    referrer = _create_user(db, "referrer")
    referred = _create_user(db, "referred")  # Different user ID
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    # Force fingerprint-based detection to trigger
    monkeypatch.setattr(
        "app.services.referral_fraud.is_self_referral",
        lambda **_: True,
    )

    now = datetime.now(timezone.utc)
    referral_service.record_click(code=code.code, device_fp_hash="dup", ip_hash="dup", channel="share")

    # Attribution succeeds (different user IDs)
    result = referral_service.attribute_signup(
        referred_user_id=referred.id,
        code=code.code,
        source="web_click",
        ts=now,
        device_fp_hash="dup",
        ip_hash="dup",
    )
    assert result is True

    # Booking completion triggers fingerprint check, voids rewards
    referral_service.on_first_booking_completed(
        user_id=referred.id,
        booking_id=str(ulid.ULID()),
        amount_cents=9000,
        completed_at=now,
    )

    rewards = db.query(ReferralReward).all()
    # Rewards are created but voided due to fingerprint detection
    assert len(rewards) == 2  # Student and referrer rewards (both voided)
    assert all(r.status == RewardStatus.VOID for r in rewards)

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


def test_instructor_flow_creates_payout(db, referral_service, monkeypatch):
    referrer = _create_user(db, "referrer")
    instructor = _create_user(db, "instructor")
    signup_ts = datetime.now(timezone.utc) - timedelta(days=40)
    _create_instructor_with_stripe(db, referrer)
    instructor_profile = _create_instructor_profile(db, instructor)
    catalog = _get_or_create_catalog_entry(db)
    service = InstructorService(
        instructor_profile_id=instructor_profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=120.0,
        duration_options=[60],
        is_active=True,
    )
    db.add(service)
    db.flush()
    booking = create_booking_pg_safe(
        db,
        student_id=_create_user(db, "student").id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        service_name="Test Service",
        hourly_rate=120.0,
        total_price=120.0,
        duration_minutes=60,
        meeting_location="Test",
        service_area="Manhattan",
    )
    booking.completed_at = signup_ts
    db.flush()
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    referral_service.record_click(code=code.code, channel="share")
    referral_service.attribute_signup(
        referred_user_id=instructor.id,
        code=code.code,
        source="web_click",
        ts=signup_ts,
    )

    monkeypatch.setattr(
        referral_service.booking_repo,
        "count_instructor_total_completed",
        lambda _instructor_id: 1,
    )

    payout_id = referral_service.on_instructor_lesson_completed(
        instructor_user_id=instructor.id,
        booking_id=booking.id,
        completed_at=signup_ts,
    )
    assert payout_id is not None

    payout = (
        db.query(InstructorReferralPayout)
        .filter(InstructorReferralPayout.referred_instructor_id == instructor.id)
        .one()
    )
    assert payout.referrer_user_id == referrer.id
    assert payout.amount_cents == 7500
    assert payout.was_founding_bonus is True

    second_attempt = referral_service.on_instructor_lesson_completed(
        instructor_user_id=instructor.id,
        booking_id=booking.id,
        completed_at=signup_ts,
    )
    assert second_attempt is None
    assert (
        db.query(InstructorReferralPayout)
        .filter(InstructorReferralPayout.referred_instructor_id == instructor.id)
        .count()
        == 1
    )


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
