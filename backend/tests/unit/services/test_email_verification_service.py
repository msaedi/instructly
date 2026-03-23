from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
import pytest

from app.auth import create_email_verification_token, decode_email_verification_token
from app.core.exceptions import ValidationException
from app.services.email_verification_service import (
    EMAIL_VERIFICATION_ATTEMPT_MAX,
    EMAIL_VERIFICATION_LOCK_TTL_SECONDS,
    EMAIL_VERIFICATION_SEND_IP_MAX,
    EMAIL_VERIFICATION_SEND_MAX,
    EmailVerificationService,
    email_verification_lock_key,
    email_verification_send_ip_key,
    email_verification_send_key,
    email_verification_token_jti_key,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.expire_times: dict[str, int] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        current = int(self.store.get(key, 0) or 0) + 1
        self.store[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.store:
                deleted += 1
            self.store.pop(key, None)
            self.expire_times.pop(key, None)
        return deleted


class FakeCacheService:
    def __init__(self, redis_client: FakeRedis | None = None) -> None:
        self._redis = redis_client
        self.store: dict[str, Any] = {}

    async def get_redis_client(self) -> FakeRedis | None:
        return self._redis

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        existed = key in self.store
        self.store.pop(key, None)
        return existed


def _service(cache_service: FakeCacheService) -> EmailVerificationService:
    return EmailVerificationService(MagicMock(), cache_service, MagicMock())


@pytest.mark.asyncio
async def test_check_send_rate_limit_rejects_email_limit() -> None:
    cache = FakeCacheService(FakeRedis())
    cache.store[email_verification_send_key("limited@example.com")] = EMAIL_VERIFICATION_SEND_MAX

    service = _service(cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.check_send_rate_limit("limited@example.com", "127.0.0.1")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "EMAIL_VERIFICATION_RATE_LIMITED"


@pytest.mark.asyncio
async def test_check_send_rate_limit_rejects_ip_limit() -> None:
    cache = FakeCacheService(FakeRedis())
    cache.store[email_verification_send_ip_key("127.0.0.1")] = EMAIL_VERIFICATION_SEND_IP_MAX

    service = _service(cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.check_send_rate_limit("ok@example.com", "127.0.0.1")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "EMAIL_VERIFICATION_IP_RATE_LIMITED"


@pytest.mark.asyncio
async def test_send_code_stores_code_and_resets_attempt_keys() -> None:
    redis = FakeRedis()
    cache = FakeCacheService(redis)
    cache.store["email_verify_attempts:user@example.com"] = 3
    cache.store["email_verify_lock:user@example.com"] = True
    service = _service(cache)
    service.send_verification_email = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await service.send_code("user@example.com", "127.0.0.1")

    assert "email_verify:user@example.com" in cache.store
    assert "email_verify_attempts:user@example.com" not in cache.store
    assert "email_verify_lock:user@example.com" not in cache.store
    assert redis.store[email_verification_send_key("user@example.com")] == 1
    assert redis.store[email_verification_send_ip_key("127.0.0.1")] == 1


@pytest.mark.asyncio
async def test_verify_code_returns_token_and_invalidates_code() -> None:
    cache = FakeCacheService()
    cache.store["email_verify:verify@example.com"] = "123456"
    service = _service(cache)

    token, expires_in = await service.verify_code("verify@example.com", "123456")

    payload = decode_email_verification_token(token)
    assert payload["sub"] == "verify@example.com"
    assert expires_in > 0
    assert cache.store[email_verification_token_jti_key(str(payload["jti"]))] is True
    assert "email_verify:verify@example.com" not in cache.store


@pytest.mark.asyncio
async def test_verify_code_locks_after_too_many_attempts() -> None:
    cache = FakeCacheService(FakeRedis())
    cache.store["email_verify:locked@example.com"] = "123456"
    service = _service(cache)

    for _ in range(EMAIL_VERIFICATION_ATTEMPT_MAX - 1):
        with pytest.raises(HTTPException):
            await service.verify_code("locked@example.com", "000000")

    with pytest.raises(HTTPException) as exc_info:
        await service.verify_code("locked@example.com", "000000")

    assert exc_info.value.detail["code"] == "EMAIL_VERIFICATION_LOCKED"
    assert cache.store[email_verification_lock_key("locked@example.com")] is True


@pytest.mark.asyncio
async def test_verify_code_rejects_expired_and_locked_states() -> None:
    cache = FakeCacheService(FakeRedis())
    service = _service(cache)

    with pytest.raises(HTTPException) as expired_exc:
        await service.verify_code("expired@example.com", "123456")
    assert expired_exc.value.detail["details"]["expired"] is True

    cache.store[email_verification_lock_key("locked@example.com")] = True
    with pytest.raises(HTTPException) as locked_exc:
        await service.verify_code("locked@example.com", "123456")
    assert locked_exc.value.detail["code"] == "EMAIL_VERIFICATION_LOCKED"
    assert locked_exc.value.detail["details"]["retry_after_seconds"] == EMAIL_VERIFICATION_LOCK_TTL_SECONDS


def test_validate_registration_token_accepts_matching_email() -> None:
    service = _service(FakeCacheService())
    token = create_email_verification_token("match@example.com")

    claims = service.validate_registration_token("match@example.com", token)

    assert claims["sub"] == "match@example.com"


def test_validate_registration_token_rejects_missing_or_mismatched_token() -> None:
    service = _service(FakeCacheService())

    with pytest.raises(ValidationException):
        service.validate_registration_token("user@example.com", "")

    with pytest.raises(ValidationException) as exc_info:
        service.validate_registration_token(
            "user@example.com",
            create_email_verification_token("other@example.com"),
        )
    assert exc_info.value.code == "EMAIL_VERIFICATION_EMAIL_MISMATCH"


@pytest.mark.asyncio
async def test_consume_token_jti_requires_existing_jti_marker() -> None:
    cache = FakeCacheService()
    service = _service(cache)
    token = create_email_verification_token("consume@example.com")
    claims = decode_email_verification_token(token)
    jti_key = email_verification_token_jti_key(str(claims["jti"]))
    cache.store[jti_key] = True

    await service.consume_token_jti(claims)
    assert jti_key not in cache.store

    with pytest.raises(ValidationException):
        await service.consume_token_jti(claims)
