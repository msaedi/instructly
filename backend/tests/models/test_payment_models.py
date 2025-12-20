from datetime import datetime, timedelta, timezone

from app.models.payment import PlatformCredit


def test_platform_credit_not_expired_without_expires_at() -> None:
    credit = PlatformCredit(user_id="user_1", amount_cents=1000, reason="test")
    assert credit.is_expired is False
    assert credit.is_available is True


def test_platform_credit_expired_with_naive_expiry() -> None:
    expires_at = datetime.now() - timedelta(days=1)
    credit = PlatformCredit(
        user_id="user_1",
        amount_cents=1000,
        reason="test",
        expires_at=expires_at,
    )
    assert credit.is_expired is True


def test_platform_credit_not_expired_with_aware_expiry() -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    credit = PlatformCredit(
        user_id="user_1",
        amount_cents=1000,
        reason="test",
        expires_at=expires_at,
    )
    assert credit.is_expired is False
