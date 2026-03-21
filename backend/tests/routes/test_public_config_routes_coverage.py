from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.routes.v1 import config as routes


class _ServiceStub:
    def __init__(
        self,
        *,
        async_result: bool = False,
        config: dict | None = None,
        public_platform_config: dict | None = None,
        pricing_updated_at: datetime | None = None,
        public_platform_updated_at: datetime | None = None,
    ):
        self.async_result = async_result
        self.config = config or PRICING_DEFAULTS
        self.public_platform_config = public_platform_config or {"student_launch_enabled": False}
        self.pricing_updated_at = pricing_updated_at or datetime.now(timezone.utc)
        self.public_platform_updated_at = public_platform_updated_at

    def get_pricing_config(self):
        result = (self.config, self.pricing_updated_at)
        if self.async_result:
            async def _async():
                return result

            return _async()
        return result

    def get_public_platform_config(self):
        result = (self.public_platform_config, self.public_platform_updated_at)
        if self.async_result:
            async def _async():
                return result

            return _async()
        return result


@pytest.mark.asyncio
async def test_get_public_pricing_config_sync(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _ServiceStub())

    response = await routes.get_public_pricing_config(db=None)

    assert response.config.student_fee_pct == PRICING_DEFAULTS["student_fee_pct"]


@pytest.mark.asyncio
async def test_get_public_pricing_config_async(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _ServiceStub(async_result=True))

    response = await routes.get_public_pricing_config(db=None)

    assert response.config.founding_instructor_cap == PRICING_DEFAULTS["founding_instructor_cap"]


def test_build_platform_fees_falls_back_to_defaults(monkeypatch):
    defaults = {
        "instructor_tiers": [
            {"min": 0, "pct": 0.10},
            {"min": 10, "pct": 0.12},
            {"min": 20, "pct": 0.14},
        ],
        "founding_instructor_rate_pct": 0.05,
        "student_fee_pct": 0.07,
    }
    config = {
        "instructor_tiers": [
            {"min": 10, "pct": 0.11},
            {"min": 0, "pct": 0.09},
        ],
        "student_fee_pct": 0.08,
    }

    monkeypatch.setattr(routes, "PRICING_DEFAULTS", defaults)

    fees = routes._build_platform_fees(config)

    assert fees.tier_1 == 0.09
    assert fees.tier_2 == 0.11
    assert fees.tier_3 == 0.14
    assert fees.founding_instructor == 0.05
    assert fees.student_booking_fee == 0.08


@pytest.mark.asyncio
async def test_get_public_config_uses_platform_fees(monkeypatch):
    config = {
        "instructor_tiers": [{"min": 0, "pct": 0.06}],
        "founding_instructor_rate_pct": 0.04,
        "student_fee_pct": 0.02,
    }

    monkeypatch.setattr(routes, "ConfigService", lambda _db: _ServiceStub(config=config))

    response = await routes.get_public_config(db=None)

    assert response.fees.founding_instructor == 0.04
    assert response.fees.tier_1 == 0.06
    assert response.fees.student_booking_fee == 0.02
    assert response.student_launch_enabled is False


@pytest.mark.asyncio
async def test_get_public_config_includes_student_launch_flag_and_latest_timestamp(monkeypatch):
    pricing_updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    public_platform_updated_at = datetime(2026, 3, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(
        routes,
        "ConfigService",
        lambda _db: _ServiceStub(
            public_platform_config={"student_launch_enabled": True},
            pricing_updated_at=pricing_updated_at,
            public_platform_updated_at=public_platform_updated_at,
        ),
    )

    response = await routes.get_public_config(db=None)

    assert response.student_launch_enabled is True
    assert response.updated_at == public_platform_updated_at
