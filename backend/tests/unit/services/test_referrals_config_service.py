"""Unit tests for referral config caching logic."""

from __future__ import annotations

import time
from unittest.mock import Mock

from app.services import referrals_config_service as config_service


class DummyLock:
    def __init__(self, acquire_result: bool = True):
        self.acquire_result = acquire_result
        self.released = False

    def acquire(self, timeout: float | None = None) -> bool:
        return self.acquire_result

    def release(self) -> None:
        self.released = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def test_get_effective_config_returns_cached_when_lock_unavailable(monkeypatch):
    cached = config_service._defaults()
    config_service._cached_config = (cached, time.monotonic() - 1)

    class HookLock(DummyLock):
        def acquire(self, timeout: float | None = None) -> bool:
            config_service._cached_config = (cached, time.monotonic() + 120)
            return False

    monkeypatch.setattr(config_service, "_cache_lock", HookLock(acquire_result=False))

    result = config_service.get_effective_config(Mock())

    assert result["source"] == cached["source"]
    assert result["student_amount_cents"] == cached["student_amount_cents"]


def test_get_effective_config_returns_defaults_when_lock_unavailable(monkeypatch):
    config_service._cached_config = None
    monkeypatch.setattr(config_service, "_cache_lock", DummyLock(acquire_result=False))

    result = config_service.get_effective_config(Mock())

    assert result["source"] == "defaults"
    assert result["version"] is None


def test_get_effective_config_returns_cached_after_lock(monkeypatch):
    expired = config_service._defaults()
    config_service._cached_config = (expired, time.monotonic() - 1)

    fresh = dict(expired)
    fresh["student_amount_cents"] = 3456
    fresh["source"] = "defaults"

    class HookLock(DummyLock):
        def acquire(self, timeout: float | None = None) -> bool:
            config_service._cached_config = (fresh, time.monotonic() + 120)
            return True

    monkeypatch.setattr(config_service, "_cache_lock", HookLock(acquire_result=True))

    result = config_service.get_effective_config(Mock())

    assert result["student_amount_cents"] == 3456


def test_referrals_config_service_methods_use_helpers(monkeypatch):
    sentinel = {"source": "db"}
    called = {"invalidate": False}

    def _fake_get(db):
        return sentinel

    def _fake_invalidate():
        called["invalidate"] = True

    monkeypatch.setattr(config_service, "get_effective_config", _fake_get)
    monkeypatch.setattr(config_service, "invalidate_cache", _fake_invalidate)

    service = config_service.ReferralsConfigService(db=Mock())
    assert service.get_referral_config() is sentinel
    service.invalidate_cache()
    assert called["invalidate"] is True
