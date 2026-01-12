"""Tests for phone verification security measures."""

from __future__ import annotations

from typing import Any, Optional

from app.api.dependencies.services import get_cache_service_dep
from app.main import fastapi_app as app


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.expire_times: dict[str, int] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        current = int(self.store.get(key, 0) or 0)
        current += 1
        self.store[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.expire_times.pop(key, None)


class FakeCacheService:
    def __init__(self, redis_client: Optional[FakeRedis] = None) -> None:
        self._redis = redis_client
        self.store: dict[str, Any] = {}

    async def get_redis_client(self) -> Optional[FakeRedis]:
        return self._redis

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        self.store.pop(key, None)
        return True


def test_confirm_blocks_after_five_failed_attempts(
    client, auth_headers_instructor, test_instructor
) -> None:
    fake_cache = FakeCacheService(FakeRedis())
    code_key = f"phone_verify:{test_instructor.id}"
    fake_cache.store[code_key] = "123456"

    previous_override = app.dependency_overrides.get(get_cache_service_dep)
    app.dependency_overrides[get_cache_service_dep] = lambda: fake_cache
    try:
        for _ in range(5):
            response = client.post(
                "/api/v1/account/phone/verify/confirm",
                json={"code": "000000"},
                headers=auth_headers_instructor,
            )
            assert response.status_code == 400

        response = client.post(
            "/api/v1/account/phone/verify/confirm",
            json={"code": "123456"},
            headers=auth_headers_instructor,
        )
        assert response.status_code == 429
        assert fake_cache.store.get(code_key) is None
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_cache_service_dep, None)
        else:
            app.dependency_overrides[get_cache_service_dep] = previous_override


def test_failed_attempts_cleared_on_success(
    client, auth_headers_instructor, test_instructor
) -> None:
    redis_client = FakeRedis()
    attempts_key = f"phone_confirm_attempts:{test_instructor.id}"
    redis_client.store[attempts_key] = 2
    fake_cache = FakeCacheService(redis_client)
    fake_cache.store[f"phone_verify:{test_instructor.id}"] = "123456"

    previous_override = app.dependency_overrides.get(get_cache_service_dep)
    app.dependency_overrides[get_cache_service_dep] = lambda: fake_cache
    try:
        response = client.post(
            "/api/v1/account/phone/verify/confirm",
            json={"code": "123456"},
            headers=auth_headers_instructor,
        )
        assert response.status_code == 200
        assert redis_client.store.get(attempts_key) is None
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_cache_service_dep, None)
        else:
            app.dependency_overrides[get_cache_service_dep] = previous_override


def test_code_invalidated_after_max_attempts(
    client, auth_headers_instructor, test_instructor
) -> None:
    redis_client = FakeRedis()
    attempts_key = f"phone_confirm_attempts:{test_instructor.id}"
    redis_client.store[attempts_key] = 5
    fake_cache = FakeCacheService(redis_client)
    code_key = f"phone_verify:{test_instructor.id}"
    fake_cache.store[code_key] = "123456"

    previous_override = app.dependency_overrides.get(get_cache_service_dep)
    app.dependency_overrides[get_cache_service_dep] = lambda: fake_cache
    try:
        response = client.post(
            "/api/v1/account/phone/verify/confirm",
            json={"code": "123456"},
            headers=auth_headers_instructor,
        )
        assert response.status_code == 429
        assert fake_cache.store.get(code_key) is None
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_cache_service_dep, None)
        else:
            app.dependency_overrides[get_cache_service_dep] = previous_override
