import json
from types import SimpleNamespace

import pytest

from app.ratelimit import config as rl_config


class _MetricStub:
    def __init__(self) -> None:
        self.calls = []

    def inc(self) -> None:
        self.calls.append("inc")

    def set(self, value) -> None:
        self.calls.append(("set", value))


def test_is_shadow_mode_uses_overrides(monkeypatch):
    monkeypatch.setattr(rl_config, "settings", SimpleNamespace(shadow=True))
    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {})
    assert rl_config.is_shadow_mode("read") is True

    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {"read": False})
    assert rl_config.is_shadow_mode("read") is False


def test_load_overrides_from_env_invalid_json(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", "not-json")
    assert rl_config._load_overrides_from_env() == {}


def test_load_overrides_from_env_empty(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", raising=False)
    assert rl_config._load_overrides_from_env() == {}


def test_load_overrides_from_env_non_dict(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", json.dumps(["not-a-dict"]))
    assert rl_config._load_overrides_from_env() == {}


def test_load_overrides_from_env_valid(monkeypatch):
    payload = {"#/api": {"rate": 5, "burst": 2}}
    monkeypatch.setenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", json.dumps(payload))
    assert rl_config._load_overrides_from_env() == payload


@pytest.mark.asyncio
async def test_load_overrides_from_redis_async(monkeypatch):
    class _RedisStub:
        async def get(self, key):
            assert key.endswith(":rl:overrides")
            return json.dumps({"/api": {"rate": 3}})

    async def _get_redis():
        return _RedisStub()

    monkeypatch.setattr("app.ratelimit.redis_backend.get_redis", _get_redis)
    result = await rl_config._load_overrides_from_redis_async()
    assert result == {"/api": {"rate": 3}}


@pytest.mark.asyncio
async def test_load_overrides_from_redis_async_empty_value(monkeypatch):
    class _RedisStub:
        async def get(self, _key):
            return None

    async def _get_redis():
        return _RedisStub()

    monkeypatch.setattr("app.ratelimit.redis_backend.get_redis", _get_redis)
    assert await rl_config._load_overrides_from_redis_async() == {}


@pytest.mark.asyncio
async def test_load_overrides_from_redis_async_non_dict(monkeypatch):
    class _RedisStub:
        async def get(self, _key):
            return json.dumps(["bad"])

    async def _get_redis():
        return _RedisStub()

    monkeypatch.setattr("app.ratelimit.redis_backend.get_redis", _get_redis)
    assert await rl_config._load_overrides_from_redis_async() == {}


@pytest.mark.asyncio
async def test_load_overrides_from_redis_async_handles_error(monkeypatch):
    async def _get_redis():
        raise RuntimeError("boom")

    monkeypatch.setattr("app.ratelimit.redis_backend.get_redis", _get_redis)
    assert await rl_config._load_overrides_from_redis_async() == {}


def test_reload_config_updates_overrides_and_metrics(monkeypatch):
    metric_reload = _MetricStub()
    metric_active = _MetricStub()
    monkeypatch.setattr(rl_config, "rl_config_reload_total", metric_reload)
    monkeypatch.setattr(rl_config, "rl_active_overrides", metric_active)

    payload = {"/api": {"rate": 9}}
    monkeypatch.setenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", json.dumps(payload))
    info = rl_config.reload_config()

    assert info["policy_overrides_count"] == 1
    assert "inc" in metric_reload.calls
    assert ("set", 1) in metric_active.calls


def test_reload_config_handles_metric_failure(monkeypatch):
    class _MetricBoom:
        def inc(self):
            raise RuntimeError("boom")

        def set(self, _value):
            raise RuntimeError("boom")

    monkeypatch.setattr(rl_config, "rl_config_reload_total", _MetricBoom())
    monkeypatch.setattr(rl_config, "rl_active_overrides", _MetricBoom())
    info = rl_config.reload_config()
    assert "policy_overrides_count" in info


@pytest.mark.asyncio
async def test_reload_config_async_merges_env_and_redis(monkeypatch):
    metric_reload = _MetricStub()
    metric_active = _MetricStub()
    monkeypatch.setattr(rl_config, "rl_config_reload_total", metric_reload)
    monkeypatch.setattr(rl_config, "rl_active_overrides", metric_active)

    monkeypatch.setenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", json.dumps({"/env": {"rate": 1}}))

    async def _fake_redis():
        return {"/redis": {"burst": 2}}

    monkeypatch.setattr(rl_config, "_load_overrides_from_redis_async", _fake_redis)
    info = await rl_config.reload_config_async()
    assert info["policy_overrides_count"] == 2


@pytest.mark.asyncio
async def test_reload_config_async_handles_metric_failure(monkeypatch):
    class _MetricBoom:
        def inc(self):
            raise RuntimeError("boom")

        def set(self, _value):
            raise RuntimeError("boom")

    monkeypatch.setattr(rl_config, "rl_config_reload_total", _MetricBoom())
    monkeypatch.setattr(rl_config, "rl_active_overrides", _MetricBoom())

    async def _fake_redis():
        return {}

    monkeypatch.setattr(rl_config, "_load_overrides_from_redis_async", _fake_redis)
    info = await rl_config.reload_config_async()
    assert "policy_overrides_count" in info


def test_get_effective_policy_applies_override(monkeypatch):
    monkeypatch.setattr(
        rl_config,
        "BUCKETS",
        {"read": {"rate_per_min": 60, "burst": 3, "window_s": 60}},
    )
    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {"read": False})
    monkeypatch.setattr(
        rl_config,
        "_POLICY_OVERRIDES",
        {"/api": {"rate": 10, "burst": 1, "window": 5, "shadow": True}},
    )
    policy = rl_config.get_effective_policy("/api/v1/foo", "GET", "read")
    assert policy["rate_per_min"] == 10
    assert policy["burst"] == 1
    assert policy["window_s"] == 5
    assert policy["shadow"] is True


def test_get_effective_policy_no_route_returns_base(monkeypatch):
    monkeypatch.setattr(rl_config, "BUCKETS", {"read": {"rate_per_min": 1}})
    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {"read": False})
    monkeypatch.setattr(rl_config, "_POLICY_OVERRIDES", {})
    policy = rl_config.get_effective_policy(None, "GET", "read")
    assert policy["bucket"] == "read"


def test_get_effective_policy_no_match_returns_base(monkeypatch):
    monkeypatch.setattr(rl_config, "BUCKETS", {"read": {"rate_per_min": 2}})
    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {"read": False})
    monkeypatch.setattr(rl_config, "_POLICY_OVERRIDES", {"/other": {"rate": 9}})
    policy = rl_config.get_effective_policy("/api", "GET", "read")
    assert policy["rate_per_min"] == 2


def test_get_effective_policy_skips_invalid_override(monkeypatch):
    monkeypatch.setattr(rl_config, "BUCKETS", {"read": {"rate_per_min": 2}})
    monkeypatch.setattr(rl_config, "BUCKET_SHADOW_OVERRIDES", {"read": False})
    monkeypatch.setattr(rl_config, "_POLICY_OVERRIDES", {"/api": {"rate": "bad"}})
    policy = rl_config.get_effective_policy("/api", "GET", "read")
    assert policy["rate_per_min"] == 2
