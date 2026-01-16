from __future__ import annotations

from hashlib import sha256
import hmac

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.routes.v1 import internal as routes


def _make_request(body: bytes = b"", signature: str | None = None) -> Request:
    headers = []
    if signature is not None:
        headers.append((b"x-config-reload-signature", signature.encode()))
    scope = {"type": "http", "headers": headers, "body": body}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, sha256).hexdigest()


@pytest.mark.asyncio
async def test_verify_hmac_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("CONFIG_RELOAD_SECRET", raising=False)
    request = _make_request(b"payload", "sig")

    with pytest.raises(HTTPException) as exc:
        routes._verify_hmac(request)

    assert exc.value.status_code == 403
    assert exc.value.detail == "reload disabled"


@pytest.mark.asyncio
async def test_verify_hmac_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("CONFIG_RELOAD_SECRET", "secret")
    request = _make_request(b"payload", "bad")

    with pytest.raises(HTTPException) as exc:
        routes._verify_hmac(request)

    assert exc.value.status_code == 403
    assert exc.value.detail == "invalid signature"


@pytest.mark.asyncio
async def test_verify_hmac_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("CONFIG_RELOAD_SECRET", "secret")
    body = b"payload"
    request = _make_request(body, _sign("secret", body))

    routes._verify_hmac(request)


@pytest.mark.asyncio
async def test_reload_endpoint_returns_payload(monkeypatch):
    monkeypatch.setenv("CONFIG_RELOAD_SECRET", "secret")
    body = b"payload"
    request = _make_request(body, _sign("secret", body))

    monkeypatch.setattr(
        routes,
        "reload_config",
        lambda: {
            "enabled": True,
            "shadow": False,
            "bucket_shadows": None,
            "policy_overrides_count": 3,
        },
    )

    response = await routes.reload_endpoint(request)

    assert response.ok is True
    assert response.enabled is True
    assert response.shadow is False
    assert response.bucket_shadows == {}
    assert response.policy_overrides_count == 3


@pytest.mark.asyncio
async def test_policy_introspection_fills_defaults(monkeypatch):
    monkeypatch.setattr(routes, "get_effective_policy", lambda *_args, **_kwargs: {})

    response = await routes.policy_introspection(route="/v1", method="GET", bucket="read")

    assert response.bucket == "read"
    assert response.rate_per_min == 60
    assert response.burst == 0
    assert response.window_s == 60
    assert response.shadow is False


@pytest.mark.asyncio
async def test_policy_introspection_uses_returned_values(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_effective_policy",
        lambda *_args, **_kwargs: {
            "bucket": "custom",
            "rate_per_min": 10,
            "burst": 2,
            "window_s": 15,
            "shadow": True,
        },
    )

    response = await routes.policy_introspection()

    assert response.bucket == "custom"
    assert response.rate_per_min == 10
    assert response.burst == 2
    assert response.window_s == 15
    assert response.shadow is True
