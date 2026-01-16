from datetime import date

import pytest

from app.services import cache_strategies


class _KeyBuilder:
    def build(self, *parts):
        return ":".join(str(p) for p in parts)


class _CacheStub:
    TTL_TIERS = {"hot": 60, "warm": 300}

    def __init__(self):
        self.key_builder = _KeyBuilder()
        self.set_json_calls = []
        self.get_calls = []
        self.cache_week_availability_calls = []
        self.invalidate_instructor_availability_calls = []
        self.get_return = None

    async def set_json(self, key, value, ttl=None):
        self.set_json_calls.append((key, value, ttl))

    async def get(self, key):
        self.get_calls.append(key)
        return self.get_return

    async def cache_week_availability(self, *args, **kwargs):
        self.cache_week_availability_calls.append((args, kwargs))

    async def invalidate_instructor_availability(self, *args, **kwargs):
        self.invalidate_instructor_availability_calls.append((args, kwargs))


@pytest.mark.asyncio
async def test_warm_with_verification_no_cache(db):
    strategy = cache_strategies.CacheWarmingStrategy(None, db)
    result = await strategy.warm_with_verification("instr", date.today())
    assert result == {}


@pytest.mark.asyncio
async def test_warm_with_verification_expected_count_matches(db, monkeypatch):
    cache = _CacheStub()
    strategy = cache_strategies.CacheWarmingStrategy(cache, db)

    class _AvailabilityService:
        def __init__(self, _db, _cache):
            pass

        def get_week_availability(self, *_args, **_kwargs):
            return {"2024-01-01": [1, 2], "2024-01-02": [3]}

    monkeypatch.setattr(
        "app.services.availability_service.AvailabilityService", _AvailabilityService
    )
    monkeypatch.setattr(
        "app.services.cache_strategies.get_user_today_by_id",
        lambda *_args, **_kwargs: date.today(),
    )

    result = await strategy.warm_with_verification("instr", date.today(), expected_window_count=3)
    assert result["2024-01-01"] == [1, 2]
    assert len(cache.set_json_calls) == 2


@pytest.mark.asyncio
async def test_warm_with_verification_retries_and_caches(db, monkeypatch):
    cache = _CacheStub()
    strategy = cache_strategies.CacheWarmingStrategy(cache, db, max_retries=2)

    class _AvailabilityService:
        def __init__(self, _db, _cache):
            pass

        def get_week_availability(self, *_args, **_kwargs):
            return {"2024-01-01": []}

    monkeypatch.setattr(
        "app.services.availability_service.AvailabilityService", _AvailabilityService
    )
    async def _sleep(_delay):
        return None

    monkeypatch.setattr(cache_strategies.asyncio, "sleep", _sleep)
    monkeypatch.setattr(
        "app.services.cache_strategies.get_user_today_by_id",
        lambda *_args, **_kwargs: date.today(),
    )

    result = await strategy.warm_with_verification("instr", date.today(), expected_window_count=1)
    assert result == {"2024-01-01": []}
    assert len(cache.set_json_calls) == 2


@pytest.mark.asyncio
async def test_invalidate_and_warm_groups_weeks(db, monkeypatch):
    cache = _CacheStub()
    strategy = cache_strategies.CacheWarmingStrategy(cache, db)
    warm_calls = []

    async def _warm(*_args, **_kwargs):
        warm_calls.append((_args, _kwargs))
        return None

    strategy.warm_with_verification = _warm

    days = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 8)]
    await strategy.invalidate_and_warm("instr", days, expected_changes={"2024-01-01": 1})

    assert len(cache.invalidate_instructor_availability_calls) == 1
    assert len(warm_calls) == 2


@pytest.mark.asyncio
async def test_read_through_cache_hit(db):
    cache = _CacheStub()
    cache.get_return = {"cached": True}
    reader = cache_strategies.ReadThroughCache(cache, db)
    result = await reader.get_week_availability("instr", date(2024, 1, 1))
    assert result == {"cached": True}


@pytest.mark.asyncio
async def test_read_through_cache_miss_updates_cache(db, monkeypatch):
    cache = _CacheStub()
    cache.get_return = None

    class _AvailabilityService:
        def __init__(self, _db, _cache):
            pass

        def get_week_availability(self, *_args, **_kwargs):
            return {"fresh": True}

    monkeypatch.setattr(
        "app.services.availability_service.AvailabilityService", _AvailabilityService
    )

    reader = cache_strategies.ReadThroughCache(cache, db)
    result = await reader.get_week_availability("instr", date(2024, 1, 1))
    assert result == {"fresh": True}
    assert len(cache.cache_week_availability_calls) == 1
