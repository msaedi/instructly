from __future__ import annotations

from unittest.mock import Mock

from fastapi import HTTPException
import pytest

from app.core import login_protection as lp


class FakePipeline:
    def __init__(self, backend: "FakeRedis") -> None:
        self.backend = backend
        self.ops = []

    def get(self, key: str) -> "FakePipeline":
        self.ops.append(("get", key))
        return self

    def incr(self, key: str) -> "FakePipeline":
        self.ops.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self.ops.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        for op in self.ops:
            if op[0] == "get":
                results.append(self.backend.store.get(op[1]))
            elif op[0] == "incr":
                results.append(self.backend._incr_sync(op[1]))
            elif op[0] == "expire":
                self.backend.expire_times[op[1]] = op[2]
                results.append(True)
        self.ops = []
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.store = {}
        self.expire_times = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def get(self, key: str):
        return self.store.get(key)

    async def ttl(self, key: str) -> int:
        return int(self.expire_times.get(key, -1))

    def _incr_sync(self, key: str) -> int:
        current = int(self.store.get(key, 0) or 0)
        new_val = current + 1
        self.store[key] = new_val
        return new_val

    async def incr(self, key: str) -> int:
        return self._incr_sync(key)

    async def expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self.store[key] = value
        self.expire_times[key] = seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.expire_times.pop(key, None)


def test_record_login_result_swallows_metrics_error(monkeypatch):
    monkeypatch.setattr(lp.login_attempts_total, "labels", Mock(side_effect=RuntimeError("boom")))
    lp.record_login_result("success")


def test_record_captcha_event_swallows_metrics_error(monkeypatch):
    monkeypatch.setattr(lp.login_captcha_required_total, "labels", Mock(side_effect=RuntimeError("boom")))
    lp.record_captcha_event("passed")


@pytest.mark.asyncio
async def test_get_redis_client_explicit():
    redis = FakeRedis()
    result = await lp._get_redis_client(explicit=redis)
    assert result is redis


@pytest.mark.asyncio
async def test_get_redis_client_default(monkeypatch):
    redis = FakeRedis()

    async def _get_client():
        return redis

    monkeypatch.setattr(lp, "get_async_cache_redis_client", _get_client)

    result = await lp._get_redis_client()
    assert result is redis


@pytest.mark.asyncio
async def test_acquire_login_slot_timeout_raises(monkeypatch):
    monkeypatch.setattr(lp, "LOGIN_SEMAPHORE", lp.asyncio.Semaphore(0))

    with pytest.raises(HTTPException) as exc:
        await lp.acquire_login_slot(timeout=0.01)

    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


@pytest.mark.asyncio
async def test_acquire_login_slot_success(monkeypatch):
    monkeypatch.setattr(lp, "LOGIN_SEMAPHORE", lp.asyncio.Semaphore(1))

    waited = await lp.acquire_login_slot(timeout=0.1)

    assert waited >= 0
    lp.LOGIN_SEMAPHORE.release()


@pytest.mark.asyncio
async def test_login_slot_context_manager_releases(monkeypatch):
    monkeypatch.setattr(lp, "LOGIN_SEMAPHORE", lp.asyncio.Semaphore(1))

    async with lp.login_slot():
        pass

    await lp.acquire_login_slot(timeout=0.1)
    lp.LOGIN_SEMAPHORE.release()


@pytest.mark.asyncio
async def test_account_rate_limiter_minute_limit():
    redis = FakeRedis()
    redis.store["login:minute:user@example.com"] = 1
    redis.expire_times["login:minute:user@example.com"] = 30
    limiter = lp.AccountRateLimiter(redis=redis)
    limiter.attempts_per_minute = 1
    limiter.attempts_per_hour = 10

    allowed, info = await limiter.check("user@example.com")

    assert allowed is False
    assert info["reason"] == "minute_limit"


@pytest.mark.asyncio
async def test_account_rate_limiter_hour_limit():
    redis = FakeRedis()
    redis.store["login:hour:user@example.com"] = 2
    redis.expire_times["login:hour:user@example.com"] = 120
    limiter = lp.AccountRateLimiter(redis=redis)
    limiter.attempts_per_minute = 5
    limiter.attempts_per_hour = 2

    allowed, info = await limiter.check("user@example.com")

    assert allowed is False
    assert info["reason"] == "hour_limit"


@pytest.mark.asyncio
async def test_account_rate_limiter_allowed_returns_remaining():
    redis = FakeRedis()
    redis.store["login:minute:user@example.com"] = 1
    redis.store["login:hour:user@example.com"] = 2
    limiter = lp.AccountRateLimiter(redis=redis)
    limiter.attempts_per_minute = 5
    limiter.attempts_per_hour = 10

    allowed, info = await limiter.check("user@example.com")

    assert allowed is True
    assert info["remaining_minute"] == 4
    assert info["remaining_hour"] == 8


@pytest.mark.asyncio
async def test_account_rate_limiter_check_in_tests_without_explicit_redis():
    limiter = lp.AccountRateLimiter(redis=None)
    allowed, info = await limiter.check("user@example.com")

    assert allowed is True
    assert info["remaining_minute"] is None


@pytest.mark.asyncio
async def test_account_rate_limiter_check_redis_none(monkeypatch):
    redis = FakeRedis()
    limiter = lp.AccountRateLimiter(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)

    allowed, info = await limiter.check("user@example.com")
    assert allowed is True
    assert info["remaining_minute"] is None


@pytest.mark.asyncio
async def test_account_rate_limiter_record_attempt_updates_store():
    redis = FakeRedis()
    limiter = lp.AccountRateLimiter(redis=redis)

    await limiter.record_attempt("user@example.com")

    assert redis.store["login:minute:user@example.com"] == 1
    assert redis.store["login:hour:user@example.com"] == 1


@pytest.mark.asyncio
async def test_account_rate_limiter_record_attempt_skips_in_tests():
    limiter = lp.AccountRateLimiter(redis=None)
    await limiter.record_attempt("user@example.com")


@pytest.mark.asyncio
async def test_account_rate_limiter_record_attempt_redis_none(monkeypatch):
    redis = FakeRedis()
    limiter = lp.AccountRateLimiter(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)
    await limiter.record_attempt("user@example.com")


@pytest.mark.asyncio
async def test_account_rate_limiter_reset_deletes_keys():
    redis = FakeRedis()
    redis.store["login:minute:user@example.com"] = 1
    redis.store["login:hour:user@example.com"] = 1
    limiter = lp.AccountRateLimiter(redis=redis)

    await limiter.reset("user@example.com")

    assert redis.store == {}


@pytest.mark.asyncio
async def test_account_rate_limiter_reset_skips_in_tests():
    limiter = lp.AccountRateLimiter(redis=None)
    await limiter.reset("user@example.com")


@pytest.mark.asyncio
async def test_account_rate_limiter_reset_redis_none(monkeypatch):
    redis = FakeRedis()
    limiter = lp.AccountRateLimiter(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)
    await limiter.reset("user@example.com")


@pytest.mark.asyncio
async def test_account_lockout_check_lockout_message():
    redis = FakeRedis()
    redis.store["login:lockout:user@example.com"] = "1"
    redis.expire_times["login:lockout:user@example.com"] = 120
    lockout = lp.AccountLockout(redis=redis)

    locked, info = await lockout.check_lockout("user@example.com")

    assert locked is True
    assert "2 minutes" in info["message"]


@pytest.mark.asyncio
async def test_account_lockout_check_skips_in_tests_without_explicit():
    lockout = lp.AccountLockout(redis=None)
    locked, info = await lockout.check_lockout("user@example.com")

    assert locked is False
    assert info["locked"] is False


@pytest.mark.asyncio
async def test_account_lockout_check_redis_none(monkeypatch):
    redis = FakeRedis()
    lockout = lp.AccountLockout(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)
    locked, info = await lockout.check_lockout("user@example.com")

    assert locked is False
    assert info["locked"] is False


@pytest.mark.asyncio
async def test_account_lockout_record_failure_applies_lockout():
    redis = FakeRedis()
    redis.store["login:failures:user@example.com"] = 4
    lockout = lp.AccountLockout(redis=redis)

    result = await lockout.record_failure("user@example.com")

    assert result["lockout_applied"] is True
    assert result["lockout_seconds"] == 30


@pytest.mark.asyncio
async def test_account_lockout_record_failure_skips_in_tests():
    lockout = lp.AccountLockout(redis=None)
    result = await lockout.record_failure("user@example.com")

    assert result["lockout_applied"] is False


@pytest.mark.asyncio
async def test_account_lockout_record_failure_redis_none(monkeypatch):
    redis = FakeRedis()
    lockout = lp.AccountLockout(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)
    result = await lockout.record_failure("user@example.com")

    assert result["lockout_applied"] is False


def test_account_lockout_format_time():
    lockout = lp.AccountLockout(redis=FakeRedis())
    assert lockout._format_time(30) == "30 seconds"
    assert lockout._format_time(120) == "2 minutes"
    assert lockout._format_time(7200) == "2 hours"


@pytest.mark.asyncio
async def test_account_lockout_reset_skips_in_tests():
    lockout = lp.AccountLockout(redis=None)
    await lockout.reset("user@example.com")


@pytest.mark.asyncio
async def test_account_lockout_reset_redis_none(monkeypatch):
    redis = FakeRedis()
    lockout = lp.AccountLockout(redis=redis)

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)
    await lockout.reset("user@example.com")


@pytest.mark.asyncio
async def test_captcha_required_and_verify(monkeypatch):
    redis = FakeRedis()
    redis.store["login:failures:user@example.com"] = 3
    verifier = lp.CaptchaVerifier(secret_key="secret", redis=redis)

    assert await verifier.is_captcha_required("user@example.com") is True

    assert await verifier.verify(None) is False

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse(self.payload)

    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda: FakeClient({"success": True}))

    assert await verifier.verify("token", "127.0.0.1") is True


@pytest.mark.asyncio
async def test_captcha_required_returns_false_without_secret():
    verifier = lp.CaptchaVerifier(secret_key=None, redis=FakeRedis())
    assert await verifier.is_captcha_required("user@example.com") is False


@pytest.mark.asyncio
async def test_captcha_required_returns_false_when_redis_none(monkeypatch):
    verifier = lp.CaptchaVerifier(secret_key="secret", redis=FakeRedis())

    async def _get_none(_explicit=None):
        return None

    monkeypatch.setattr(lp, "_get_redis_client", _get_none)

    assert await verifier.is_captcha_required("user@example.com") is False


@pytest.mark.asyncio
async def test_captcha_verify_returns_true_in_tests_without_explicit_secret():
    verifier = lp.CaptchaVerifier(secret_key=None, redis=FakeRedis())
    assert await verifier.verify("token") is True


@pytest.mark.asyncio
async def test_captcha_verify_returns_true_without_secret(monkeypatch):
    monkeypatch.setattr(lp.settings, "turnstile_secret_key", "", raising=False)
    verifier = lp.CaptchaVerifier(secret_key="", redis=FakeRedis())
    assert await verifier.verify("token") is True


@pytest.mark.asyncio
async def test_captcha_verify_handles_exception(monkeypatch):
    verifier = lp.CaptchaVerifier(secret_key="secret", redis=FakeRedis())

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda: FakeClient())

    assert await verifier.verify("token") is False
