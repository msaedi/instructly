"""Tests for NotificationPreferenceService."""

import pytest

from app.models.notification import LOCKED_NOTIFICATION_PREFERENCES
from app.repositories.notification_repository import DEFAULT_PREFERENCES
from app.services.notification_preference_service import NotificationPreferenceService


def _preference_map(preferences):
    return {(pref.category, pref.channel): pref for pref in preferences}


class FakeCache:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.set_calls = []
        self.deleted_keys = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None, tier="default"):
        self.set_calls.append((key, value, ttl))
        self.store[key] = value
        return True

    def delete(self, key):
        self.deleted_keys.append(key)
        self.store.pop(key, None)
        return True


def test_get_user_preferences_creates_defaults(db, test_student):
    service = NotificationPreferenceService(db)

    preferences = service.get_user_preferences(test_student.id)

    assert len(preferences) == 18
    pref_map = _preference_map(preferences)

    for category, channels in DEFAULT_PREFERENCES.items():
        for channel, enabled in channels.items():
            pref = pref_map[(category, channel)]
            assert pref.enabled is enabled
            assert pref.locked is ((category, channel) in LOCKED_NOTIFICATION_PREFERENCES)


def test_get_user_preferences_returns_existing_without_creating(db, test_student, monkeypatch):
    service = NotificationPreferenceService(db)
    service.get_user_preferences(test_student.id)

    def _no_create(_user_id):
        raise AssertionError("create_default_preferences should not be called")

    monkeypatch.setattr(service.notification_repository, "create_default_preferences", _no_create)
    preferences = service.get_user_preferences(test_student.id)
    assert len(preferences) == 18


def test_get_preferences_by_category(db, test_student):
    service = NotificationPreferenceService(db)

    prefs_by_category = service.get_preferences_by_category(test_student.id)

    assert prefs_by_category["lesson_updates"]["email"] is True
    assert prefs_by_category["lesson_updates"]["push"] is True
    assert prefs_by_category["lesson_updates"]["sms"] is False
    assert prefs_by_category["messages"]["push"] is True
    assert prefs_by_category["reviews"]["email"] is True
    assert prefs_by_category["reviews"]["push"] is True
    assert prefs_by_category["reviews"]["sms"] is False
    assert prefs_by_category["learning_tips"]["email"] is True
    assert prefs_by_category["learning_tips"]["push"] is True
    assert prefs_by_category["learning_tips"]["sms"] is False
    assert prefs_by_category["system_updates"]["email"] is True
    assert prefs_by_category["system_updates"]["push"] is False
    assert prefs_by_category["system_updates"]["sms"] is False
    assert prefs_by_category["promotional"]["push"] is False


def test_get_preferences_by_category_uses_cache(db, test_student, monkeypatch):
    cached = {"lesson_updates": {"email": False, "push": True, "sms": False}}
    cache = FakeCache({NotificationPreferenceService._cache_key(test_student.id): cached})
    service = NotificationPreferenceService(db, cache=cache)

    monkeypatch.setattr(
        service,
        "get_user_preferences",
        lambda _user_id: (_ for _ in ()).throw(AssertionError("should use cache")),
    )

    result = service.get_preferences_by_category(test_student.id)
    assert result == cached


def test_get_preferences_by_category_sets_cache(db, test_student):
    cache = FakeCache()
    service = NotificationPreferenceService(db, cache=cache)

    result = service.get_preferences_by_category(test_student.id)

    assert result["lesson_updates"]["email"] is True
    assert cache.set_calls
    key, _, ttl = cache.set_calls[0]
    assert key == service._cache_key(test_student.id)
    assert ttl == 300


def test_update_preference_create_and_update(db, test_student):
    service = NotificationPreferenceService(db)

    created = service.update_preference(test_student.id, "promotional", "email", True)
    assert created.enabled is True

    updated = service.update_preference(test_student.id, "promotional", "email", False)
    assert updated.enabled is False


def test_update_preference_locked_raises(db, test_student):
    service = NotificationPreferenceService(db)
    service.get_user_preferences(test_student.id)

    with pytest.raises(ValueError):
        service.update_preference(test_student.id, "messages", "push", False)

    locked_pref = service.notification_repository.get_preference(
        test_student.id, "messages", "push"
    )
    assert locked_pref is not None
    assert locked_pref.enabled is True
    assert locked_pref.locked is True


def test_update_preference_invalid_category_raises(db, test_student):
    service = NotificationPreferenceService(db)

    with pytest.raises(ValueError):
        service.update_preference(test_student.id, "not_a_category", "email", True)


def test_update_preferences_bulk_skips_locked(db, test_student):
    service = NotificationPreferenceService(db)

    updates = [
        {"category": "lesson_updates", "channel": "push", "enabled": False},
        {"category": "messages", "channel": "push", "enabled": False},
        {"category": "promotional", "channel": "email", "enabled": True},
    ]

    updated = service.update_preferences_bulk(test_student.id, updates)

    assert len(updated) == 2
    prefs_by_category = service.get_preferences_by_category(test_student.id)
    assert prefs_by_category["lesson_updates"]["push"] is False
    assert prefs_by_category["promotional"]["email"] is True
    assert prefs_by_category["messages"]["push"] is True


def test_update_preferences_bulk_skips_invalid_and_invalidates_cache(db, test_student):
    cache = FakeCache()
    service = NotificationPreferenceService(db, cache=cache)

    updates = [
        {"category": None, "channel": "email", "enabled": True},
        {"category": "lesson_updates", "channel": 5, "enabled": True},
        {"category": "lesson_updates", "channel": "email", "enabled": "yes"},
        {"category": "not_a_category", "channel": "email", "enabled": True},
        {"category": "lesson_updates", "channel": "email", "enabled": False},
    ]

    results = service.update_preferences_bulk(test_student.id, updates)

    assert len(results) == 1
    assert results[0].category == "lesson_updates"
    assert cache.deleted_keys == [service._cache_key(test_student.id)]


def test_is_enabled_returns_cached_value(db, test_student, monkeypatch):
    cache = FakeCache(
        {
            NotificationPreferenceService._cache_key(test_student.id): {
                "lesson_updates": {"email": False}
            }
        }
    )
    service = NotificationPreferenceService(db, cache=cache)

    monkeypatch.setattr(
        service.notification_repository,
        "get_preference",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("db lookup not expected")),
    )

    assert service.is_enabled(test_student.id, "lesson_updates", "email") is False


def test_is_enabled_falls_back_to_default(db, test_student):
    service = NotificationPreferenceService(db)

    assert service.is_enabled(test_student.id, "lesson_updates", "email") is True
    assert service.is_enabled(test_student.id, "promotional", "push") is False
