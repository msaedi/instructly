from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.routes.v1.admin import config as routes
from app.schemas.pricing_config import PricingConfigPayload


class _ServiceStub:
    def __init__(self, _db, *, fail=False):
        self.fail = fail

    def get_pricing_config(self):
        return (PRICING_DEFAULTS, datetime.now(timezone.utc))

    def set_pricing_config(self, _payload):
        if self.fail:
            raise RuntimeError("boom")
        return (PRICING_DEFAULTS, datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_get_pricing_config_sync(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _ServiceStub(_db))

    response = await routes.get_pricing_config(db=None, _=None)

    assert response.config.student_fee_pct == PRICING_DEFAULTS["student_fee_pct"]


@pytest.mark.asyncio
async def test_update_pricing_config_commits(monkeypatch):
    service = _ServiceStub(None)
    monkeypatch.setattr(routes, "ConfigService", lambda _db: service)
    payload = PricingConfigPayload(**PRICING_DEFAULTS)

    response = await routes.update_pricing_config(payload=payload, db=None, _=None)

    assert response.config.founding_search_boost == PRICING_DEFAULTS["founding_search_boost"]


@pytest.mark.asyncio
async def test_update_pricing_config_propagates_error(monkeypatch):
    service = _ServiceStub(None, fail=True)
    monkeypatch.setattr(routes, "ConfigService", lambda _db: service)
    payload = PricingConfigPayload(**PRICING_DEFAULTS)

    with pytest.raises(RuntimeError, match="boom"):
        await routes.update_pricing_config(payload=payload, db=None, _=None)
