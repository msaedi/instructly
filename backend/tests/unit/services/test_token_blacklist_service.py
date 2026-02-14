from __future__ import annotations

import logging

import pytest

from app.services.token_blacklist_service import TokenBlacklistService


class _FakeRedis:
    def __init__(self, *, exists_value: int = 0, setex_error: Exception | None = None):
        self.exists_value = exists_value
        self.setex_error = setex_error
        self.setex_calls: list[tuple[str, int, str]] = []
        self.exists_calls: list[str] = []

    async def setex(self, key: str, ttl: int, value: str) -> None:
        if self.setex_error:
            raise self.setex_error
        self.setex_calls.append((key, ttl, value))

    async def exists(self, key: str) -> int:
        self.exists_calls.append(key)
        return self.exists_value


@pytest.mark.asyncio
async def test_revoke_token_sets_key_with_ttl(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)

    await service.revoke_token("jti-1", 1060)

    assert redis.setex_calls == [("auth:blacklist:jti:jti-1", 60, "1")]


@pytest.mark.asyncio
async def test_revoke_token_expired_noop(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)

    await service.revoke_token("jti-1", 999)

    assert redis.setex_calls == []


@pytest.mark.asyncio
async def test_is_revoked_true_for_revoked_token():
    redis = _FakeRedis(exists_value=1)
    service = TokenBlacklistService(redis_client=redis)

    assert await service.is_revoked("jti-1") is True
    assert redis.exists_calls == ["auth:blacklist:jti:jti-1"]


@pytest.mark.asyncio
async def test_is_revoked_false_for_non_revoked_token():
    redis = _FakeRedis(exists_value=0)
    service = TokenBlacklistService(redis_client=redis)

    assert await service.is_revoked("jti-1") is False


@pytest.mark.asyncio
async def test_is_revoked_fail_closed_when_redis_unavailable():
    class _BrokenService(TokenBlacklistService):
        async def _get_redis_client(self):
            raise RuntimeError("redis unavailable")

    service = _BrokenService()
    assert await service.is_revoked("jti-1") is True


@pytest.mark.asyncio
async def test_revoke_token_logs_and_does_not_raise_on_redis_error(caplog):
    redis = _FakeRedis(setex_error=RuntimeError("write failed"))
    service = TokenBlacklistService(redis_client=redis)

    with caplog.at_level(logging.WARNING):
        await service.revoke_token("jti-1", 9999999999)

    assert any("Failed to revoke token" in rec.message for rec in caplog.records)


def test_revoke_token_sync_bridge(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 100)

    service.revoke_token_sync("sync-jti", 130)

    assert redis.setex_calls == [("auth:blacklist:jti:sync-jti", 30, "1")]


def test_is_revoked_sync_bridge():
    redis = _FakeRedis(exists_value=1)
    service = TokenBlacklistService(redis_client=redis)

    assert service.is_revoked_sync("sync-jti") is True


@pytest.mark.asyncio
async def test_sync_bridges_work_with_running_loop(monkeypatch):
    redis = _FakeRedis(exists_value=0)
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 100)

    service.revoke_token_sync("loop-jti", 130)
    assert service.is_revoked_sync("loop-jti") is False
    assert redis.setex_calls
