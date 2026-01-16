from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.routes.v1.admin import config as routes
from app.schemas.pricing_config import PricingConfigPayload


class _ServiceStub:
    def __init__(self, _db, *, async_result=False, fail=False):
        self.async_result = async_result
        self.fail = fail
        self.committed = False
        self.rolled_back = False

    def get_pricing_config(self):
        result = (PRICING_DEFAULTS, datetime.now(timezone.utc))
        if self.async_result:
            async def _async():
                return result

            return _async()
        return result

    def set_pricing_config(self, _payload):
        if self.fail:
            raise RuntimeError("boom")
        result = (PRICING_DEFAULTS, datetime.now(timezone.utc))
        if self.async_result:
            async def _async():
                return result

            return _async()
        return result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_get_pricing_config_sync(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _ServiceStub(_db))

    response = await routes.get_pricing_config(db=None, _=None)

    assert response.config.student_fee_pct == PRICING_DEFAULTS["student_fee_pct"]


@pytest.mark.asyncio
async def test_get_pricing_config_async(monkeypatch):
    monkeypatch.setattr(
        routes, "ConfigService", lambda _db: _ServiceStub(_db, async_result=True)
    )

    response = await routes.get_pricing_config(db=None, _=None)

    assert response.config.founding_instructor_cap == PRICING_DEFAULTS["founding_instructor_cap"]


@pytest.mark.asyncio
async def test_update_pricing_config_commits(monkeypatch):
    service = _ServiceStub(None)
    monkeypatch.setattr(routes, "ConfigService", lambda _db: service)
    payload = PricingConfigPayload(**PRICING_DEFAULTS)

    response = await routes.update_pricing_config(payload=payload, db=None, _=None)

    assert response.config.founding_search_boost == PRICING_DEFAULTS["founding_search_boost"]
    assert service.committed is True


@pytest.mark.asyncio
async def test_update_pricing_config_rolls_back_on_error(monkeypatch):
    service = _ServiceStub(None, fail=True)
    monkeypatch.setattr(routes, "ConfigService", lambda _db: service)
    payload = PricingConfigPayload(**PRICING_DEFAULTS)

    with pytest.raises(RuntimeError, match="boom"):
        await routes.update_pricing_config(payload=payload, db=None, _=None)

    assert service.rolled_back is True
