from unittest.mock import AsyncMock

import pytest

from app.services import permission_cache


@pytest.mark.asyncio
async def test_get_cached_permissions_hit(monkeypatch):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value='["a","b"]')
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))

    perms = await permission_cache.get_cached_permissions("user-1")
    assert perms == {"a", "b"}


@pytest.mark.asyncio
async def test_get_cached_permissions_miss(monkeypatch):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))

    perms = await permission_cache.get_cached_permissions("user-1")
    assert perms is None


@pytest.mark.asyncio
async def test_get_cached_permissions_redis_unavailable(monkeypatch):
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=None))
    assert await permission_cache.get_cached_permissions("user-1") is None


@pytest.mark.asyncio
async def test_get_cached_permissions_handles_exception(monkeypatch):
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))
    assert await permission_cache.get_cached_permissions("user-1") is None


@pytest.mark.asyncio
async def test_set_cached_permissions(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))
    await permission_cache.set_cached_permissions("user-1", {"p1", "p2"})
    redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_cached_permissions_redis_unavailable(monkeypatch):
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=None))
    await permission_cache.set_cached_permissions("user-1", {"p1"})


@pytest.mark.asyncio
async def test_set_cached_permissions_handles_exception(monkeypatch):
    redis = AsyncMock()
    redis.setex = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))
    await permission_cache.set_cached_permissions("user-1", {"p1"})


@pytest.mark.asyncio
async def test_invalidate_cached_permissions(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))
    await permission_cache.invalidate_cached_permissions("user-1")
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidate_cached_permissions_redis_unavailable(monkeypatch):
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=None))
    await permission_cache.invalidate_cached_permissions("user-1")


@pytest.mark.asyncio
async def test_invalidate_cached_permissions_handles_exception(monkeypatch):
    redis = AsyncMock()
    redis.delete = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(permission_cache, "get_async_cache_redis_client", AsyncMock(return_value=redis))
    await permission_cache.invalidate_cached_permissions("user-1")
