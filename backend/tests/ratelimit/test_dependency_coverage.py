from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.ratelimit import dependency as rl_dep


class _MetricStub:
    def labels(self, **_kwargs):
        return self

    def inc(self):
        return None

    def observe(self, _value):
        return None


def _make_request(headers=None):
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dummy",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_compute_interval_ms():
    assert rl_dep._compute_interval_ms(0) == 0
    assert rl_dep._compute_interval_ms(60) == 1000


def test_namespaced_key(monkeypatch):
    monkeypatch.setattr(rl_dep, "settings", SimpleNamespace(namespace="ns"))
    assert rl_dep._namespaced_key("read", "abc") == "ns:read:abc"


def test_is_testing_env_uses_flags(monkeypatch):
    monkeypatch.setattr(rl_dep, "settings", SimpleNamespace(is_testing=True))
    assert rl_dep._is_testing_env() is True

    monkeypatch.setattr(rl_dep, "settings", SimpleNamespace(is_testing=False))
    monkeypatch.setenv("IS_TESTING", "true")
    assert rl_dep._is_testing_env() is True


def test_is_testing_env_handles_attr_error(monkeypatch):
    class _BadSettings:
        @property
        def is_testing(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(rl_dep, "settings", _BadSettings())
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("IS_TESTING", "yes")
    assert rl_dep._is_testing_env() is True


@pytest.mark.asyncio
async def test_rate_limit_bypass_token(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(
        rl_dep,
        "core_config",
        SimpleNamespace(settings=SimpleNamespace(rate_limit_bypass_token="token")),
    )
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(rl_dep, "settings", SimpleNamespace(enabled=True, namespace="ns"))
    req = _make_request(headers={"X-Rate-Limit-Bypass": "token"})
    res = Response()
    await dep(req, res)
    assert "X-RateLimit-Limit" not in res.headers


@pytest.mark.asyncio
async def test_rate_limit_testing_env_sets_headers(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: True)
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: False)
    req = _make_request()
    res = Response()
    await dep(req, res)
    assert res.headers["X-RateLimit-Limit"] == "1000"
    assert res.headers["X-RateLimit-Policy"] == "read"


@pytest.mark.asyncio
async def test_rate_limit_disabled(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(rl_dep, "settings", SimpleNamespace(enabled=False))
    req = _make_request()
    res = Response()
    await dep(req, res)
    assert "X-RateLimit-Limit" not in res.headers


@pytest.mark.asyncio
async def test_rate_limit_missing_policy_returns(monkeypatch):
    dep = rl_dep.rate_limit("unknown")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="missing"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {})

    req = _make_request()
    res = Response()
    await dep(req, res)
    assert "X-RateLimit-Limit" not in res.headers


@pytest.mark.asyncio
async def test_rate_limit_identity_uses_client_when_state_errors(monkeypatch):
    dep = rl_dep.rate_limit("read")
    captured = {}

    def _namespaced_key(bucket, identity):
        captured["identity"] = identity
        return f"{bucket}:{identity}"

    class _BadState:
        def __getattr__(self, _name):
            raise RuntimeError("boom")

    req = SimpleNamespace(
        headers={}, state=_BadState(), client=SimpleNamespace(host="1.2.3.4")
    )

    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 1}})
    monkeypatch.setattr(rl_dep, "_namespaced_key", _namespaced_key)
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: False)
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    class _RedisStub:
        async def eval(self, *_args, **_kwargs):
            return [1, 0, 1, 2, 1234, 0]

    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(return_value=_RedisStub()))

    res = Response()
    await dep(req, res)
    assert captured["identity"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_rate_limit_identity_uses_header_when_no_client(monkeypatch):
    dep = rl_dep.rate_limit("read")
    captured = {}

    def _namespaced_key(bucket, identity):
        captured["identity"] = identity
        return f"{bucket}:{identity}"

    req = SimpleNamespace(
        headers={"x-forwarded-for": "9.9.9.9"},
        state=SimpleNamespace(rate_identity=None),
        client=None,
    )

    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 1}})
    monkeypatch.setattr(rl_dep, "_namespaced_key", _namespaced_key)
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: False)
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    class _RedisStub:
        async def eval(self, *_args, **_kwargs):
            return [1, 0, 1, 2, 1234, 0]

    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(return_value=_RedisStub()))

    res = Response()
    await dep(req, res)
    assert captured["identity"] == "9.9.9.9"


@pytest.mark.asyncio
async def test_rate_limit_redis_unavailable_allows(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 2}})
    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(side_effect=RuntimeError("down")))
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    req = _make_request()
    res = Response()
    await dep(req, res)
    assert res.headers["X-RateLimit-Limit"] == "3"


@pytest.mark.asyncio
async def test_rate_limit_blocks_when_not_shadow(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 1}})
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: False)
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    class _RedisStub:
        async def eval(self, *args, **kwargs):
            return [0, 5000, 0, 2, 1234, 0]

    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(return_value=_RedisStub()))

    req = _make_request()
    res = Response()
    with pytest.raises(HTTPException) as exc:
        await dep(req, res)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_metrics_errors_do_not_bubble(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 1}})
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: True)

    class _RedisStub:
        async def eval(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    class _MetricBoom:
        def labels(self, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(return_value=_RedisStub()))
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricBoom())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricBoom())
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    req = _make_request()
    res = Response()
    await dep(req, res)
    assert res.headers["X-RateLimit-Limit"] == "2"


@pytest.mark.asyncio
async def test_rate_limit_shadow_block_returns(monkeypatch):
    dep = rl_dep.rate_limit("read")
    monkeypatch.setattr(rl_dep, "_is_testing_env", lambda: False)
    monkeypatch.setattr(
        rl_dep,
        "settings",
        SimpleNamespace(enabled=True, namespace="ns", default_policy="read"),
    )
    monkeypatch.setattr(rl_dep, "BUCKETS", {"read": {"rate_per_min": 60, "burst": 1}})
    monkeypatch.setattr(rl_dep, "is_shadow_mode", lambda _bucket: True)
    monkeypatch.setattr(rl_dep, "rl_decisions", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_duration", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_eval_errors", _MetricStub())
    monkeypatch.setattr(rl_dep, "rl_retry_after", _MetricStub())

    class _RedisStub:
        async def eval(self, *_args, **_kwargs):
            return [0, 5000, 0, 2, 1234, 0]

    monkeypatch.setattr(rl_dep, "get_redis", AsyncMock(return_value=_RedisStub()))

    req = _make_request()
    res = Response()
    await dep(req, res)
    assert res.headers["X-RateLimit-Limit"] == "2"
