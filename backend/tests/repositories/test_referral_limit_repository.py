from __future__ import annotations

from datetime import datetime, timezone

from app.models.user import User
from app.repositories.referral_repository import ReferralLimitRepository


def _create_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        first_name="Test",
        last_name="User",
        zip_code="11215",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def test_referral_limit_get_and_upsert(db):
    repo = ReferralLimitRepository(db)
    assert repo.get("non-existent") is None

    user = _create_user(db, "limits@example.com")
    now = datetime.now(timezone.utc)

    record = repo.upsert(
        user_id=user.id,
        daily_ok=3,
        weekly_ok=7,
        month_cap=20,
        trust_score=1,
        last_reviewed_at=now,
    )
    assert record.daily_ok == 3
    assert record.weekly_ok == 7
    assert record.month_cap == 20
    assert record.trust_score == 1
    assert record.last_reviewed_at == now

    fetched = repo.get(user.id)
    assert fetched is not None
    assert fetched.daily_ok == 3


def test_referral_limit_increment_daily(db):
    repo = ReferralLimitRepository(db)
    user = _create_user(db, "limits-increment@example.com")

    repo.increment_daily(user.id)
    record = repo.get(user.id)
    assert record is not None
    assert record.daily_ok == 1
    assert record.weekly_ok == 1

    repo.increment_daily(user.id, increment=2)
    updated = repo.get(user.id)
    assert updated is not None
    assert updated.daily_ok == 3
    assert updated.weekly_ok == 3
    assert updated.last_reviewed_at is not None
