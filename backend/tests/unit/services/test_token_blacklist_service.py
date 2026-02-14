from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
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
    metric_calls: list[str] = []
    monkeypatch.setattr(
        "app.services.token_blacklist_service.prometheus_metrics.record_token_revocation",
        lambda trigger: metric_calls.append(trigger),
    )

    result = await service.revoke_token("jti-1", 1060)

    assert result is True
    assert redis.setex_calls == [("auth:blacklist:jti:jti-1", 60, "1")]
    assert metric_calls == ["logout"]


@pytest.mark.asyncio
async def test_revoke_token_empty_jti_is_noop(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)

    result = await service.revoke_token("", 1060)

    assert result is False
    assert redis.setex_calls == []


@pytest.mark.asyncio
async def test_revoke_token_invalid_exp_logs_and_skips(caplog):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)

    with caplog.at_level(logging.WARNING):
        result = await service.revoke_token("jti-1", "not-a-number")

    assert result is False
    assert redis.setex_calls == []
    assert any("Invalid exp claim" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_revoke_token_expired_noop(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)

    result = await service.revoke_token("jti-1", 999)

    assert result is False
    assert redis.setex_calls == []


@pytest.mark.asyncio
async def test_revoke_token_emit_metric_can_be_disabled(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    metric_calls: list[str] = []
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)
    monkeypatch.setattr(
        "app.services.token_blacklist_service.prometheus_metrics.record_token_revocation",
        lambda trigger: metric_calls.append(trigger),
    )

    result = await service.revoke_token(
        "jti-1", 1060, trigger="logout_all_devices", emit_metric=False
    )

    assert result is True
    assert redis.setex_calls == [("auth:blacklist:jti:jti-1", 60, "1")]
    assert metric_calls == []


@pytest.mark.asyncio
async def test_revoke_token_redis_none_logs_and_skips(monkeypatch, caplog):
    class _NoRedisService(TokenBlacklistService):
        async def _get_redis_client(self):
            return None

    service = _NoRedisService()
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)

    with caplog.at_level(logging.WARNING):
        result = await service.revoke_token("jti-1", 1060)

    assert result is False
    assert any("Redis unavailable, revoke skipped" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_revoke_token_metric_error_is_non_fatal(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 1000)
    monkeypatch.setattr(
        "app.services.token_blacklist_service.prometheus_metrics.record_token_revocation",
        lambda _trigger: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    result = await service.revoke_token("jti-1", 1060)

    assert result is True
    assert redis.setex_calls == [("auth:blacklist:jti:jti-1", 60, "1")]


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
async def test_is_revoked_empty_jti_is_fail_closed():
    service = TokenBlacklistService(redis_client=_FakeRedis(exists_value=0))
    assert await service.is_revoked("") is True


@pytest.mark.asyncio
async def test_is_revoked_redis_none_is_fail_closed():
    class _NoRedisService(TokenBlacklistService):
        async def _get_redis_client(self):
            return None

    service = _NoRedisService()
    assert await service.is_revoked("jti-1") is True


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
        result = await service.revoke_token("jti-1", 9999999999)

    assert result is False
    assert any("Failed to revoke token" in rec.message for rec in caplog.records)


def test_revoke_token_sync_bridge(monkeypatch):
    redis = _FakeRedis()
    service = TokenBlacklistService(redis_client=redis)
    monkeypatch.setattr("app.services.token_blacklist_service.time.time", lambda: 100)

    result = service.revoke_token_sync("sync-jti", 130, trigger="logout")

    assert result is True
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

    assert service.revoke_token_sync("loop-jti", 130) is True
    assert service.is_revoked_sync("loop-jti") is False
    assert redis.setex_calls


def test_is_revoked_sync_timeout_is_fail_closed(monkeypatch):
    class _Future:
        def result(self, timeout: float):
            raise FuturesTimeoutError()

        def cancel(self):
            return True

    class _Executor:
        def submit(self, _fn):
            return _Future()

    monkeypatch.setattr("app.services.token_blacklist_service._SYNC_BRIDGE_EXECUTOR", _Executor())
    monkeypatch.setattr("app.services.token_blacklist_service.asyncio.get_running_loop", lambda: object())

    service = TokenBlacklistService(redis_client=_FakeRedis(exists_value=0))
    assert service.is_revoked_sync("sync-jti") is True
