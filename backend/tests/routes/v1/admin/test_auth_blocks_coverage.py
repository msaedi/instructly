from __future__ import annotations

import fnmatch
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routes.v1.admin import auth_blocks


class FakeRedis:
    def __init__(self, store=None, ttls=None):
        self.store = store or {}
        self.ttls = ttls or {}

    async def ttl(self, key: str) -> int:
        return int(self.ttls.get(key, -1))

    async def get(self, key: str):
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.store
        self.store.pop(key, None)
        self.ttls.pop(key, None)
        return 1 if existed else 0

    async def scan_iter(self, pattern: str):
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, pattern):
                yield key


def test_get_lockout_level_thresholds():
    assert auth_blocks._get_lockout_level(2) == "30sec"
    assert auth_blocks._get_lockout_level(10) == "5min"
    assert auth_blocks._get_lockout_level(15) == "30min"
    assert auth_blocks._get_lockout_level(20) == "1hr"


@pytest.mark.asyncio
async def test_get_account_state_builds_blocks(monkeypatch):
    email = "User@Example.com"
    store = {
        "login:lockout:user@example.com": "1",
        "login:failures:user@example.com": "10",
        "login:minute:user@example.com": "5",
        "login:hour:user@example.com": "12",
    }
    ttls = {
        "login:lockout:user@example.com": 120,
        "login:minute:user@example.com": 30,
        "login:hour:user@example.com": 300,
    }
    redis = FakeRedis(store=store, ttls=ttls)

    monkeypatch.setattr(auth_blocks.settings, "login_attempts_per_minute", 5, raising=False)
    monkeypatch.setattr(auth_blocks.settings, "login_attempts_per_hour", 10, raising=False)
    monkeypatch.setattr(auth_blocks.settings, "captcha_failure_threshold", 3, raising=False)

    account = await auth_blocks._get_account_state(redis, email)

    assert account.email == "user@example.com"
    assert account.blocks.lockout is not None
    assert account.blocks.lockout.level == "5min"
    assert account.blocks.rate_limit_minute is not None
    assert account.blocks.rate_limit_minute.active is True
    assert account.blocks.rate_limit_hour is not None
    assert account.blocks.captcha_required is not None


def test_has_active_blocks_filters():
    account = auth_blocks.BlockedAccount(
        email="user@example.com",
        failure_count=3,
        blocks=auth_blocks.BlocksState(
            lockout=auth_blocks.LockoutState(active=True, ttl_seconds=10, level="5min"),
            rate_limit_minute=auth_blocks.RateLimitState(
                active=False,
                count=1,
                limit=5,
                ttl_seconds=10,
            ),
            rate_limit_hour=None,
            captcha_required=auth_blocks.CaptchaState(active=True),
        ),
    )

    assert auth_blocks._has_active_blocks(account) is True
    assert auth_blocks._has_active_blocks(account, "lockout") is True
    assert auth_blocks._has_active_blocks(account, "rate_limit") is False
    assert auth_blocks._has_active_blocks(account, "captcha") is True
    assert auth_blocks._has_active_blocks(account, "unknown") is False


@pytest.mark.asyncio
async def test_list_auth_issues_returns_accounts(monkeypatch):
    store = {
        "login:lockout:one@example.com": "1",
        "login:failures:one@example.com": "5",
        "login:failures:two@example.com": "3",
    }
    ttls = {"login:lockout:one@example.com": 30}
    redis = FakeRedis(store=store, ttls=ttls)

    async def _get_redis():
        return redis

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)
    monkeypatch.setattr(auth_blocks.settings, "captcha_failure_threshold", 3, raising=False)
    monkeypatch.setattr(auth_blocks.settings, "login_attempts_per_minute", 5, raising=False)
    monkeypatch.setattr(auth_blocks.settings, "login_attempts_per_hour", 10, raising=False)

    result = await auth_blocks.list_auth_issues(
        type=None,
        email=None,
        current_user=SimpleNamespace(email="admin@example.com"),
    )

    assert result.total == 2
    assert len(result.accounts) == 2


@pytest.mark.asyncio
async def test_list_auth_issues_redis_unavailable(monkeypatch):
    async def _get_none():
        return None

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_none)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.list_auth_issues(
            type=None,
            email=None,
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_list_auth_issues_raises_500_on_redis_error(monkeypatch):
    class BrokenRedis(FakeRedis):
        async def scan_iter(self, pattern: str):
            raise RuntimeError("scan-boom")
            yield  # pragma: no cover

    async def _get_redis():
        return BrokenRedis(store={"login:lockout:err@example.com": "1"})

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.list_auth_issues(
            type=None,
            email=None,
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_summary_stats_counts(monkeypatch):
    store = {
        "login:lockout:one@example.com": "1",
        "login:failures:one@example.com": "5",
        "login:minute:two@example.com": "6",
    }
    redis = FakeRedis(store=store)

    async def _get_redis():
        return redis

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)
    monkeypatch.setattr(auth_blocks.settings, "captcha_failure_threshold", 3, raising=False)
    monkeypatch.setattr(auth_blocks.settings, "login_attempts_per_minute", 5, raising=False)

    result = await auth_blocks.get_summary_stats(current_user=SimpleNamespace(email="admin@example.com"))

    assert result.locked_out == 1
    assert result.captcha_required == 1
    assert result.rate_limited == 1
    assert result.total_blocked == 2


@pytest.mark.asyncio
async def test_get_summary_stats_redis_unavailable(monkeypatch):
    async def _get_none():
        return None

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_none)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.get_summary_stats(current_user=SimpleNamespace(email="admin@example.com"))

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_summary_stats_handles_redis_errors(monkeypatch):
    class BrokenRedis(FakeRedis):
        async def scan_iter(self, pattern: str):
            raise RuntimeError("stats-boom")
            yield  # pragma: no cover

    async def _get_redis():
        return BrokenRedis(store={"login:lockout:a@example.com": "1"})

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.get_summary_stats(current_user=SimpleNamespace(email="admin@example.com"))

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_account_state_404_when_empty(monkeypatch):
    redis = FakeRedis(store={})
    async def _get_redis():
        return redis

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.get_account_state(
            "missing@example.com",
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_account_state_redis_unavailable(monkeypatch):
    async def _get_none():
        return None

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_none)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.get_account_state(
            "missing@example.com",
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_account_state_handles_internal_error(monkeypatch):
    class BrokenRedis(FakeRedis):
        async def ttl(self, key: str) -> int:
            raise RuntimeError("ttl-boom")

    async def _get_redis():
        return BrokenRedis(store={"login:lockout:user@example.com": "1"})

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.get_account_state(
            "user@example.com",
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_clear_account_blocks_deletes_keys(monkeypatch):
    store = {
        "login:lockout:user@example.com": "1",
        "login:minute:user@example.com": "2",
        "login:hour:user@example.com": "3",
        "login:failures:user@example.com": "4",
    }
    redis = FakeRedis(store=store)
    async def _get_redis():
        return redis

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    response = await auth_blocks.clear_account_blocks(
        "user@example.com",
        request=auth_blocks.ClearBlocksRequest(reason="support"),
        current_user=SimpleNamespace(email="admin@example.com"),
    )

    assert response.email == "user@example.com"
    assert set(response.cleared) == {"lockout", "rate_limit_minute", "rate_limit_hour", "failures"}
    assert response.reason == "support"


@pytest.mark.asyncio
async def test_clear_account_blocks_partial_types_and_no_matches(monkeypatch):
    store = {
        "login:lockout:user@example.com": "1",
        "login:minute:user@example.com": "2",
    }
    redis = FakeRedis(store=store)

    async def _get_redis():
        return redis

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)
    response = await auth_blocks.clear_account_blocks(
        "user@example.com",
        request=auth_blocks.ClearBlocksRequest(types=["rate_limit", "failures"], reason="ops"),
        current_user=SimpleNamespace(email="admin@example.com"),
    )

    assert response.email == "user@example.com"
    assert response.cleared == ["rate_limit_minute"]
    assert response.reason == "ops"


@pytest.mark.asyncio
async def test_clear_account_blocks_redis_unavailable(monkeypatch):
    async def _get_none():
        return None

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_none)
    with pytest.raises(HTTPException) as exc:
        await auth_blocks.clear_account_blocks(
            "user@example.com",
            request=None,
            current_user=SimpleNamespace(email="admin@example.com"),
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_clear_account_blocks_handles_delete_error(monkeypatch):
    class BrokenRedis(FakeRedis):
        async def delete(self, key: str) -> int:
            raise RuntimeError("delete-boom")

    async def _get_redis():
        return BrokenRedis(store={"login:lockout:user@example.com": "1"})

    monkeypatch.setattr(auth_blocks, "get_async_cache_redis_client", _get_redis)

    with pytest.raises(HTTPException) as exc:
        await auth_blocks.clear_account_blocks(
            "user@example.com",
            request=auth_blocks.ClearBlocksRequest(types=["lockout"]),
            current_user=SimpleNamespace(email="admin@example.com"),
        )

    assert exc.value.status_code == 500
