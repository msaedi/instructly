from __future__ import annotations

from datetime import timedelta

from app.services import referral_fraud


def test_is_self_referral_by_device() -> None:
    assert referral_fraud.is_self_referral(
        click_device_fp_hash="ABC",
        click_ip_hash=None,
        signup_device_fp_hash="abc",
        signup_ip_hash=None,
    )


def test_is_self_referral_by_ip_or_payment() -> None:
    assert referral_fraud.is_self_referral(
        click_device_fp_hash=None,
        click_ip_hash="ip",
        signup_device_fp_hash=None,
        signup_ip_hash="ip",
    )
    assert referral_fraud.is_self_referral(
        click_device_fp_hash=None,
        click_ip_hash=None,
        signup_device_fp_hash=None,
        signup_ip_hash=None,
        payment_fingerprint_referrer="fp",
        payment_fingerprint_signup="fp",
    )


def test_velocity_and_low_value_checks() -> None:
    assert referral_fraud.is_velocity_abuse(daily_count=6, weekly_count=1)
    assert referral_fraud.is_velocity_abuse(daily_count=1, weekly_count=20)
    assert referral_fraud.is_velocity_abuse(daily_count=1, weekly_count=1) is False

    assert referral_fraud.is_low_value_booking(50, minimum_cents=100)
    assert referral_fraud.is_low_value_booking(150, minimum_cents=100) is False


def test_referral_window_constant() -> None:
    assert referral_fraud.referral_window() == timedelta(days=30)
