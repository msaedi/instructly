from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routes.v1 import sse as routes


class _RedisStub:
    def __init__(self):
        self.calls: list[tuple[str, int, str]] = []

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.calls.append((key, ttl, value))


@pytest.mark.asyncio
async def test_get_sse_token_requires_cache(monkeypatch):
    async def _none():
        return None

    monkeypatch.setattr(routes, "get_async_cache_redis_client", _none)

    with pytest.raises(HTTPException) as exc:
        await routes.get_sse_token(current_user=SimpleNamespace(id="user-1"))

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_sse_token_sets_cache(monkeypatch):
    redis = _RedisStub()

    async def _redis():
        return redis

    monkeypatch.setattr(routes, "get_async_cache_redis_client", _redis)
    monkeypatch.setattr(routes.secrets, "token_urlsafe", lambda _n: "tok")

    response = await routes.get_sse_token(current_user=SimpleNamespace(id="user-9"))

    assert response.token == "tok"
    assert response.expires_in_s == routes.SSE_TOKEN_TTL_SECONDS
    assert redis.calls == [
        (f"{routes.SSE_KEY_PREFIX}tok", routes.SSE_TOKEN_TTL_SECONDS, "user-9")
    ]
