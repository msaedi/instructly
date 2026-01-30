from __future__ import annotations

from datetime import datetime, timezone

from app.notifications import policy


class FakeCache:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.set_calls = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.set_calls.append((key, value, ttl))
        self.store[key] = value
        return True


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


def test_build_local_day_key_returns_empty_when_missing():
    assert policy._build_local_day_key("user-1", None) == ""


def test_read_counter_handles_missing_cache_or_key():
    assert policy._read_counter(None, "key") == 0
    assert policy._read_counter(FakeCache(), "") == 0

    cache = FakeCache({"key": "nope"})
    assert policy._read_counter(cache, "key") == 0


def test_read_counter_parses_digit_string():
    cache = FakeCache({"key": "3"})
    assert policy._read_counter(cache, "key") == 3


def test_can_send_now_handles_timezone_exception(monkeypatch):
    user = FakeUser("u-exc")
    now_utc = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    def _raise(_user):
        raise RuntimeError("boom")

    monkeypatch.setattr(policy, "_resolve_timezone", _raise)
    allowed, reason, key = policy.can_send_now(user, now_utc, FakeCache())

    assert not allowed
    assert reason == "no_timezone"
    assert key == ""


def test_record_send_skips_without_cache_or_key():
    cache = FakeCache()
    policy.record_send("", cache)
    assert cache.set_calls == []

    policy.record_send("notif:key", None)


def test_record_send_increments_and_sets_ttl():
    cache = FakeCache({"notif:key": "1"})
    policy.record_send("notif:key", cache, ttl_hours=1)

    assert cache.set_calls
    key, value, ttl = cache.set_calls[0]
    assert key == "notif:key"
    assert value == 2
    assert ttl == 3600
