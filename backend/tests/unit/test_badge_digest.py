from datetime import datetime, timezone

from app.tasks import badge_digest


class FakeDefinition:
    def __init__(self, slug: str, name: str):
        self.slug = slug
        self.name = name


class FakeRepo:
    def __init__(self, defs, awards, progress):
        self._defs = defs
        self._awards = awards
        self._progress = progress

    def list_active_badge_definitions(self):
        return self._defs

    def list_student_badge_awards(self, user_id: str):
        return self._awards.get(user_id, [])

    def list_student_badge_progress(self, user_id: str):
        return self._progress.get(user_id, [])


class FakeNotificationService:
    def __init__(self):
        self.sent = []

    def send_badge_digest_email(self, user, items):
        self.sent.append((user, items))
        return True


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.store[key] = value
        return True


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id
        self.email = f"{user_id}@example.com"
        self.first_name = user_id


def test_build_weekly_digest_picks_top_two():
    defs = [
        FakeDefinition("badge_a", "Badge A"),
        FakeDefinition("badge_b", "Badge B"),
        FakeDefinition("badge_c", "Badge C"),
    ]
    awards = {"user": [{"slug": "badge_c", "status": "confirmed"}]}
    progress = {
        "user": [
            {"slug": "badge_a", "current_progress": {"current": 3, "goal": 5}},
            {"slug": "badge_b", "current_progress": {"current": 8, "goal": 10}},
            {"slug": "badge_c", "current_progress": {"current": 1, "goal": 3}},
        ]
    }
    repo = FakeRepo(defs, awards, progress)
    digest = badge_digest.build_weekly_badge_progress_digest(
        "user", datetime.now(timezone.utc), repo
    )
    assert [item["slug"] for item in digest["items"]] == ["badge_b", "badge_a"]


def test_send_weekly_digest_respects_policy(monkeypatch):
    defs = [FakeDefinition("badge_a", "Badge A")]
    progress = {
        "user": [{"slug": "badge_a", "current_progress": {"current": 2, "goal": 4}}]
    }
    repo = FakeRepo(defs, {"user": []}, progress)
    notif = FakeNotificationService()
    cache = FakeCache()
    user = FakeUser("user")

    monkeypatch.setattr(badge_digest, "can_send_now", lambda *args, **kwargs: (True, "ok", "key"))
    monkeypatch.setattr(badge_digest, "record_send", lambda key, cache, ttl_hours=36: cache.set(key, 1))

    summary = badge_digest.send_weekly_digest(
        datetime.now(timezone.utc),
        [user],
        repo,
        notif,
        cache,
    )
    assert summary == {"scanned": 1, "sent": 1}
    assert len(notif.sent) == 1
