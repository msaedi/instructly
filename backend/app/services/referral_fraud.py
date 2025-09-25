"""Lightweight referral fraud detection helpers."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from . import referral_utils


def _normalize(value: Optional[str]) -> Optional[str]:
    return value.lower() if value else None


def is_self_referral(
    *,
    click_device_fp_hash: Optional[str],
    click_ip_hash: Optional[str],
    signup_device_fp_hash: Optional[str],
    signup_ip_hash: Optional[str],
    payment_fingerprint_referrer: Optional[str] = None,
    payment_fingerprint_signup: Optional[str] = None,
) -> bool:
    """Detect whether a referral likely originates from the same user."""

    match_device = bool(
        click_device_fp_hash
        and signup_device_fp_hash
        and _normalize(click_device_fp_hash) == _normalize(signup_device_fp_hash)
    )
    match_ip = bool(click_ip_hash and signup_ip_hash and click_ip_hash == signup_ip_hash)
    match_payment = bool(
        payment_fingerprint_referrer
        and payment_fingerprint_signup
        and payment_fingerprint_referrer == payment_fingerprint_signup
    )
    return match_device or match_ip or match_payment


def is_velocity_abuse(
    *, daily_count: int, weekly_count: int, daily_limit: int = 5, weekly_limit: int = 15
) -> bool:
    """Flag suspicious velocity of successful attributions for a referrer."""

    return daily_count > daily_limit or weekly_count > weekly_limit


def is_low_value_booking(
    amount_cents: int, *, minimum_cents: int = referral_utils.MIN_BASKET_CENTS
) -> bool:
    """Check whether a booking amount falls under the referral threshold."""

    return amount_cents < minimum_cents


def referral_window() -> timedelta:
    """Expose a standard window for referral activity (for tests/helpers)."""

    return timedelta(days=30)
