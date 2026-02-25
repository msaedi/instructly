"""Coverage tests for config routes — L26 (isawaitable) and L69 (public config async)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.routes.v1 import config as routes


class _AsyncServiceStub:
    """Service that returns an awaitable from get_pricing_config."""

    def __init__(self, config: dict | None = None):
        self.config = config or PRICING_DEFAULTS

    def get_pricing_config(self):
        result = (self.config, datetime.now(timezone.utc))

        async def _async():
            return result

        return _async()


class _SyncServiceStub:
    """Service that returns a tuple synchronously from get_pricing_config."""

    def __init__(self, config: dict | None = None):
        self.config = config or PRICING_DEFAULTS

    def get_pricing_config(self):
        return (self.config, datetime.now(timezone.utc))


# ---- L26: isawaitable branch for pricing config — sync ----
@pytest.mark.asyncio
async def test_get_public_pricing_config_sync(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _SyncServiceStub())
    response = await routes.get_public_pricing_config(db=None)
    assert response.config is not None


# ---- L26: isawaitable branch for pricing config — async ----
@pytest.mark.asyncio
async def test_get_public_pricing_config_async(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _AsyncServiceStub())
    response = await routes.get_public_pricing_config(db=None)
    assert response.config is not None


# ---- L69: public config async path ----
@pytest.mark.asyncio
async def test_get_public_config_async(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _AsyncServiceStub())
    response = await routes.get_public_config(db=None)
    assert response.fees is not None


# ---- L69: public config sync path ----
@pytest.mark.asyncio
async def test_get_public_config_sync(monkeypatch):
    monkeypatch.setattr(routes, "ConfigService", lambda _db: _SyncServiceStub())
    response = await routes.get_public_config(db=None)
    assert response.fees is not None


# ---- _build_platform_fees with missing tiers ----
def test_build_platform_fees_empty_config():
    fees = routes._build_platform_fees({})
    assert fees.founding_instructor >= 0
    assert fees.tier_1 >= 0
