from datetime import datetime, timezone

from app.models.referrals import ReferralReward, RewardSide, RewardStatus, WalletTransaction
from app.services.wallet_service import WalletService


def _create_reward(db, *, referrer_id, referred_id, side, amount_cents, status=RewardStatus.UNLOCKED):
    reward = ReferralReward(
        referrer_user_id=referrer_id,
        referred_user_id=referred_id,
        side=side,
        status=status,
        amount_cents=amount_cents,
        unlock_ts=datetime.now(timezone.utc),
    )
    db.add(reward)
    db.flush()
    return reward


def test_apply_fee_rebate_on_payout_success(db, test_instructor, test_student, monkeypatch):
    def _noop_emit(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", _noop_emit)

    reward = _create_reward(
        db,
        referrer_id=test_instructor.id,
        referred_id=test_student.id,
        side=RewardSide.INSTRUCTOR,
        amount_cents=500,
    )
    db.commit()

    service = WalletService(db)
    txn = service.apply_fee_rebate_on_payout(
        user_id=test_instructor.id,
        payout_id="po_123",
        platform_fee_cents=300,
    )

    assert txn is not None
    assert txn.amount_cents == 300
    db.refresh(reward)
    assert reward.status == RewardStatus.REDEEMED


def test_apply_fee_rebate_on_payout_no_reward(db, test_instructor, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    service = WalletService(db)
    txn = service.apply_fee_rebate_on_payout(
        user_id=test_instructor.id,
        payout_id="po_none",
        platform_fee_cents=100,
    )
    assert txn is None


def test_apply_fee_rebate_on_payout_non_positive_amount(db, test_instructor, test_student, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    reward = _create_reward(
        db,
        referrer_id=test_instructor.id,
        referred_id=test_student.id,
        side=RewardSide.INSTRUCTOR,
        amount_cents=0,
    )
    db.commit()

    service = WalletService(db)
    txn = service.apply_fee_rebate_on_payout(
        user_id=test_instructor.id,
        payout_id="po_zero",
        platform_fee_cents=0,
    )
    assert txn is None
    db.refresh(reward)
    assert reward.status == RewardStatus.UNLOCKED


def test_consume_student_credit_success(db, test_student, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    reward = _create_reward(
        db,
        referrer_id=test_student.id,
        referred_id=test_student.id,
        side=RewardSide.STUDENT,
        amount_cents=800,
    )
    db.commit()

    service = WalletService(db)
    txn = service.consume_student_credit(
        user_id=test_student.id,
        order_id="order_1",
        amount_cents=500,
    )

    assert txn is not None
    assert isinstance(txn, WalletTransaction)
    assert txn.amount_cents == 500
    db.refresh(reward)
    assert reward.status == RewardStatus.REDEEMED


def test_consume_student_credit_non_positive(db, test_student, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    service = WalletService(db)
    txn = service.consume_student_credit(
        user_id=test_student.id,
        order_id="order_2",
        amount_cents=0,
    )
    assert txn is None


def test_consume_student_credit_no_reward(db, test_student, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    service = WalletService(db)
    txn = service.consume_student_credit(
        user_id=test_student.id,
        order_id="order_3",
        amount_cents=100,
    )
    assert txn is None


def test_consume_student_credit_zero_reward_amount(db, test_student, monkeypatch):
    monkeypatch.setattr("app.services.wallet_service.emit_reward_redeemed", lambda **_k: None)

    reward = _create_reward(
        db,
        referrer_id=test_student.id,
        referred_id=test_student.id,
        side=RewardSide.STUDENT,
        amount_cents=0,
    )
    db.commit()

    service = WalletService(db)
    txn = service.consume_student_credit(
        user_id=test_student.id,
        order_id="order_zero",
        amount_cents=50,
    )
    assert txn is None
    db.refresh(reward)
    assert reward.status == RewardStatus.UNLOCKED
