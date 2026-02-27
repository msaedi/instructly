import asyncio
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
import pytest

from app.core import login_protection as lp


class FakePipeline:
    def __init__(self, backend: "FakeRedis") -> None:
        self.backend = backend
        self.ops: List[Any] = []

    def get(self, key: str) -> "FakePipeline":
        self.ops.append(lambda: self.backend.store.get(key))
        return self

    def incr(self, key: str) -> "FakePipeline":
        self.ops.append(lambda: self.backend._incr_sync(key))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self.ops.append(lambda: self.backend._expire(key, seconds))
        return self

    def setex(self, key: str, seconds: int, value: Any) -> "FakePipeline":
        self.ops.append(lambda: self.backend._setex(key, seconds, value))
        return self

    async def execute(self) -> List[Any]:
        results: List[Any] = []
        for op in self.ops:
            result = op()
            results.append(result)
        self.ops = []
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}
        self.expire_times: Dict[str, int] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def get(self, key: str) -> Any:
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

    def _expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def expire(self, key: str, seconds: int) -> None:
        self._expire(key, seconds)

    def _setex(self, key: str, seconds: int, value: Any) -> None:
        self.store[key] = value
        self.expire_times[key] = seconds

    async def setex(self, key: str, seconds: int, value: Any) -> None:
        self._setex(key, seconds, value)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.expire_times.pop(key, None)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_login_slot_blocks_when_saturated(monkeypatch: pytest.MonkeyPatch) -> None:
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(lp, "LOGIN_SEMAPHORE", semaphore)

    async with lp.login_slot(timeout=0.1):
        with pytest.raises(HTTPException) as exc:
            await lp.acquire_login_slot(timeout=0.05)
        assert exc.value.status_code == 429

    # Slot should be free again
    await lp.acquire_login_slot(timeout=0.1)
    lp.LOGIN_SEMAPHORE.release()


@pytest.mark.asyncio
async def test_rate_limiter_allows_and_blocks(fake_redis: FakeRedis) -> None:
    limiter = lp.AccountRateLimiter(redis=fake_redis)
    limiter.attempts_per_minute = 3
    # Allow under limit
    for _ in range(limiter.attempts_per_minute):
        allowed, _ = await limiter.check("test@example.com")
        assert allowed is True
        await limiter.record_attempt("test@example.com")

    # Next attempt should be blocked
    allowed, info = await limiter.check("test@example.com")
    assert allowed is False
    assert info["reason"] == "minute_limit"
    assert info["retry_after"] >= 1


@pytest.mark.asyncio
async def test_lockout_applies_progressively(fake_redis: FakeRedis) -> None:
    lockout = lp.AccountLockout(redis=fake_redis)
    email = "lock@example.com"

    # Below threshold should not lock
    for _ in range(4):
        await lockout.record_failure(email)
    locked, info = await lockout.check_lockout(email)
    assert locked is False
    assert info["locked"] is False

    # 5th failure triggers first lockout
    result = await lockout.record_failure(email)
    assert result["lockout_applied"] is True
    assert result["lockout_seconds"] == 30
    locked, info = await lockout.check_lockout(email)
    assert locked is True
    assert info["retry_after"] >= 1

    # Increase to 10 failures triggers longer lockout
    for _ in range(5):
        await lockout.record_failure(email)
    locked, info = await lockout.check_lockout(email)
    assert locked is True
    assert info["retry_after"] >= 300 - 5  # approximate, since we do not track elapsed time


@pytest.mark.asyncio
async def test_captcha_required_after_failures(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = lp.CaptchaVerifier(secret_key="secret", redis=fake_redis)
    email = "captcha@example.com"
    assert await verifier.is_captcha_required(email) is False

    lockout = lp.AccountLockout(redis=fake_redis)
    for _ in range(verifier.failure_threshold):
        await lockout.record_failure(email)

    assert await verifier.is_captcha_required(email) is True

    async def _verify(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
        return token == "valid"

    monkeypatch.setattr(verifier, "verify", _verify)
    assert await verifier.verify("valid", "127.0.0.1") is True
    assert await verifier.verify(None, "127.0.0.1") is False


@pytest.mark.asyncio
async def test_resets_clear_counters(fake_redis: FakeRedis) -> None:
    limiter = lp.AccountRateLimiter(redis=fake_redis)
    lockout = lp.AccountLockout(redis=fake_redis)
    email = "reset@example.com"

    await limiter.check(email)
    await limiter.record_attempt(email)
    await lockout.record_failure(email)
    assert fake_redis.store  # counters present

    await limiter.reset(email)
    await lockout.reset(email)
    assert fake_redis.store == {}
