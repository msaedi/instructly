from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.search import cache_invalidation as cache_module
from app.services.search.search_cache import SearchCacheService


def test_get_search_cache_warns_and_returns_default() -> None:
    cache_module._cache_service = None
    cache = cache_module.get_search_cache()
    assert isinstance(cache, SearchCacheService)


def test_init_and_set_search_cache() -> None:
    fake_cache_service = SimpleNamespace()
    cache_module.init_search_cache(fake_cache_service)
    cache = cache_module.get_search_cache()
    assert cache.cache is fake_cache_service

    explicit = SearchCacheService(cache_service=None)
    cache_module.set_search_cache(explicit)
    assert cache_module.get_search_cache() is explicit


def test_fire_and_forget_no_event_loop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "is_testing", False, raising=False)

    async def _noop() -> None:
        return None

    cache_module._fire_and_forget(lambda: _noop(), context="sync-no-loop")


@pytest.mark.asyncio
async def test_fire_and_forget_runs_task(monkeypatch) -> None:
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    event = asyncio.Event()

    async def _mark() -> None:
        event.set()

    cache_module._fire_and_forget(lambda: _mark(), context="async-loop")
    await asyncio.wait_for(event.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_invalidate_all_search_cache_increments_version() -> None:
    cache_module.set_search_cache(SearchCacheService(cache_service=None))
    version = await cache_module.invalidate_all_search_cache()
    assert version >= 2


def test_invalidate_on_change_skips_in_tests(monkeypatch) -> None:
    monkeypatch.setattr(settings, "is_testing", True, raising=False)
    fake_cache = SearchCacheService(cache_service=None)
    fake_cache.invalidate_response_cache = AsyncMock(return_value=2)
    cache_module.set_search_cache(fake_cache)

    cache_module.invalidate_on_service_change("svc-1")
    cache_module.invalidate_on_availability_change("inst-1")
    cache_module.invalidate_on_price_change("inst-2")
    cache_module.invalidate_on_instructor_profile_change("inst-3")
    cache_module.invalidate_on_review_change("inst-4")
