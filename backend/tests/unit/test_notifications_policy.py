from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.notifications import policy


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id
        self.email = f"{user_id}@example.com"


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.store[key] = value
        return True


def make_local_time(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.replace(tzinfo=tz)


def test_quiet_hours_block(monkeypatch):
    user = FakeUser("u1")
    tz = ZoneInfo("America/New_York")
    monkeypatch.setattr(policy, "_resolve_timezone", lambda _: tz)
    local_dt = datetime(2024, 1, 1, 22, 30, tzinfo=tz)
    now_utc = local_dt.astimezone(timezone.utc)
    allowed, reason, _ = policy.can_send_now(user, now_utc, FakeCache())
    assert not allowed
    assert reason == "quiet_hours"


def test_allowed_outside_quiet_hours(monkeypatch):
    user = FakeUser("u2")
    tz = ZoneInfo("America/Los_Angeles")
    monkeypatch.setattr(policy, "_resolve_timezone", lambda _: tz)
    local_dt = datetime(2024, 1, 2, 9, 0, tzinfo=tz)
    now_utc = local_dt.astimezone(timezone.utc)
    allowed, reason, key = policy.can_send_now(user, now_utc, FakeCache())
    assert allowed
    assert reason == "ok"
    assert key.startswith("notif:u2:")


def test_daily_cap_blocks_third_send(monkeypatch):
    user = FakeUser("u3")
    tz = ZoneInfo("America/New_York")
    monkeypatch.setattr(policy, "_resolve_timezone", lambda _: tz)
    local_dt = datetime(2024, 1, 3, 12, 0, tzinfo=tz)
    now_utc = local_dt.astimezone(timezone.utc)
    cache = FakeCache()
    for _ in range(policy.DAILY_CAP):
        allowed, _, key = policy.can_send_now(user, now_utc, cache)
        assert allowed
        policy.record_send(key, cache)

    allowed, reason, _ = policy.can_send_now(user, now_utc, cache)
    assert not allowed
    assert reason == "daily_cap"


def test_no_timezone_blocks(monkeypatch):
    user = FakeUser("u4")
    monkeypatch.setattr(policy, "_resolve_timezone", lambda _: None)
    now_utc = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    allowed, reason, key = policy.can_send_now(user, now_utc, FakeCache())
    assert not allowed
    assert reason == "no_timezone"
    assert key == ""
