"""Referral helper utilities."""

import secrets

from app.core.config import settings

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
MIN_BASKET_CENTS = settings.referrals_min_basket_cents


def gen_code(n: int = 8) -> str:
    """Generate a human-friendly referral code of length *n*.

    The alphabet omits ambiguous characters such as 0/O and 1/I to
    improve readability when codes are shared verbally.
    """

    if n <= 0:
        raise ValueError("Referral code length must be positive")

    return "".join(secrets.choice(ALPHABET) for _ in range(n))
