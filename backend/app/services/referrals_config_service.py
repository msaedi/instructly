from __future__ import annotations

import threading
import time
from typing import Any, Literal, Mapping, TypedDict, cast

from sqlalchemy.orm import Session

from app.repositories.referral_config_repository import ReferralConfigRepository


class ReferralsEffectiveConfig(TypedDict):
    enabled: bool
    student_amount_cents: int
    instructor_amount_cents: int
    instructor_founding_bonus_cents: int
    instructor_standard_bonus_cents: int
    min_basket_cents: int
    hold_days: int
    expiry_months: int
    student_global_cap: int
    version: int | None
    source: Literal["db", "defaults"]


_CACHE_TTL_SECONDS = 45.0
_cache_lock = threading.Lock()
_cached_config: tuple[ReferralsEffectiveConfig, float] | None = None


def _defaults() -> ReferralsEffectiveConfig:
    return cast(
        ReferralsEffectiveConfig,
        {
            "enabled": True,
            "student_amount_cents": 2000,
            "instructor_amount_cents": 5000,
            "instructor_founding_bonus_cents": 7500,
            "instructor_standard_bonus_cents": 5000,
            "min_basket_cents": 8000,
            "hold_days": 7,
            "expiry_months": 6,
            "student_global_cap": 20,
            "version": None,
            "source": "defaults",
        },
    )


def _fetch_latest(db: Session) -> Mapping[str, Any] | None:
    return ReferralConfigRepository.read_latest(db)


def get_effective_config(db: Session) -> ReferralsEffectiveConfig:
    global _cached_config

    now = time.monotonic()
    cached = _cached_config
    if cached and cached[1] > now:
        return cast(ReferralsEffectiveConfig, dict(cached[0]))

    if not _cache_lock.acquire(timeout=1.0):
        cached = _cached_config
        if cached and cached[1] > time.monotonic():
            return cast(ReferralsEffectiveConfig, dict(cached[0]))
        return _defaults()

    try:
        cached = _cached_config
        if cached and cached[1] > time.monotonic():
            return cast(ReferralsEffectiveConfig, dict(cached[0]))

        row = _fetch_latest(db)
        if row is None:
            config = _defaults()
        else:
            config = cast(
                ReferralsEffectiveConfig,
                {
                    "enabled": bool(row["enabled"]),
                    "student_amount_cents": int(row["student_amount_cents"]),
                    "instructor_amount_cents": int(row["instructor_amount_cents"]),
                    "instructor_founding_bonus_cents": int(row["instructor_founding_bonus_cents"]),
                    "instructor_standard_bonus_cents": int(row["instructor_standard_bonus_cents"]),
                    "min_basket_cents": int(row["min_basket_cents"]),
                    "hold_days": int(row["hold_days"]),
                    "expiry_months": int(row["expiry_months"]),
                    "student_global_cap": int(row["student_global_cap"]),
                    "version": int(row["version"]),
                    "source": "db",
                },
            )

        expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        snapshot = cast(ReferralsEffectiveConfig, dict(config))
        _cached_config = (snapshot, expires_at)
        return cast(ReferralsEffectiveConfig, dict(snapshot))
    finally:
        _cache_lock.release()


def invalidate_cache() -> None:
    global _cached_config

    with _cache_lock:
        _cached_config = None


class ReferralsConfigService:
    """Service wrapper for referral configuration access."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_referral_config(self) -> ReferralsEffectiveConfig:
        """Get referral configuration as a dictionary."""
        return get_effective_config(self.db)

    def invalidate_cache(self) -> None:
        """Invalidate cached referral configuration."""
        invalidate_cache()


__all__ = [
    "ReferralsConfigService",
    "ReferralsEffectiveConfig",
    "get_effective_config",
    "invalidate_cache",
]
