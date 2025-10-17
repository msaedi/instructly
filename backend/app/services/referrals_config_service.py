"""Read-only service for referral program configuration."""

from __future__ import annotations

from threading import RLock
import time
from typing import Any, Literal, Mapping, Optional, TypedDict, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from .base import BaseService, CacheInvalidationProtocol


class ReferralsEffectiveConfig(TypedDict):
    enabled: bool
    student_amount_cents: int
    instructor_amount_cents: int
    min_basket_cents: int
    hold_days: int
    expiry_months: int
    student_global_cap: int
    version: int | None
    source: Literal["db", "defaults"]


def _new_defaults() -> ReferralsEffectiveConfig:
    return cast(
        ReferralsEffectiveConfig,
        {
            "enabled": True,
            "student_amount_cents": 2000,
            "instructor_amount_cents": 5000,
            "min_basket_cents": 8000,
            "hold_days": 7,
            "expiry_months": 6,
            "student_global_cap": 20,
            "version": None,
            "source": "defaults",
        },
    )


class ReferralsConfigService(BaseService):
    """Expose effective referral configuration with short-lived caching."""

    _CACHE_TTL_SECONDS = 45
    _cache_lock = RLock()
    _cached_config: ReferralsEffectiveConfig | None = None
    _cache_expires_at: float = 0.0

    def __init__(self, db: Session, cache: CacheInvalidationProtocol | None = None):
        super().__init__(db, cache)

    @BaseService.measure_operation("referrals.config.get_effective")
    def get_effective_config(self) -> ReferralsEffectiveConfig:
        now = time.monotonic()
        cls = type(self)

        with cls._cache_lock:
            if cls._cached_config is not None and now < cls._cache_expires_at:
                return self._clone(cls._cached_config)

        row = self._fetch_latest()
        if row is None:
            config = _new_defaults()
        else:
            config = cast(
                ReferralsEffectiveConfig,
                {
                    "enabled": bool(row["enabled"]),
                    "student_amount_cents": int(row["student_amount_cents"]),
                    "instructor_amount_cents": int(row["instructor_amount_cents"]),
                    "min_basket_cents": int(row["min_basket_cents"]),
                    "hold_days": int(row["hold_days"]),
                    "expiry_months": int(row["expiry_months"]),
                    "student_global_cap": int(row["student_global_cap"]),
                    "version": int(row["version"]),
                    "source": "db",
                },
            )

        with cls._cache_lock:
            cls._cached_config = self._clone(config)
            cls._cache_expires_at = now + cls._CACHE_TTL_SECONDS

        return self._clone(config)

    @BaseService.measure_operation("referrals.config.invalidate")
    def invalidate(self) -> None:
        cls = type(self)
        with cls._cache_lock:
            cls._cached_config = None
            cls._cache_expires_at = 0.0

    def _fetch_latest(self) -> Mapping[str, Any] | None:
        stmt = sa.text(
            """
            SELECT
                enabled,
                student_amount_cents,
                instructor_amount_cents,
                min_basket_cents,
                hold_days,
                expiry_months,
                student_global_cap,
                version
            FROM referral_config
            ORDER BY version DESC
            LIMIT 1
            """
        )
        # repo-pattern-migrate: TODO: migrate referral config reads to repository
        result = self.db.execute(stmt).mappings().first()
        return cast(Optional[Mapping[str, Any]], result)

    @staticmethod
    def _clone(payload: ReferralsEffectiveConfig) -> ReferralsEffectiveConfig:
        return cast(ReferralsEffectiveConfig, dict(payload))


__all__ = ["ReferralsConfigService", "ReferralsEffectiveConfig"]
