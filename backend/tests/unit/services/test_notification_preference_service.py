"""Tests for NotificationPreferenceService."""

import pytest

from app.models.notification import LOCKED_NOTIFICATION_PREFERENCES
from app.repositories.notification_repository import DEFAULT_PREFERENCES
from app.services.notification_preference_service import NotificationPreferenceService


def _preference_map(preferences):
    return {(pref.category, pref.channel): pref for pref in preferences}


def test_get_user_preferences_creates_defaults(db, test_student):
    service = NotificationPreferenceService(db)

    preferences = service.get_user_preferences(test_student.id)

    assert len(preferences) == 15
    pref_map = _preference_map(preferences)

    for category, channels in DEFAULT_PREFERENCES.items():
        for channel, enabled in channels.items():
            pref = pref_map[(category, channel)]
            assert pref.enabled is enabled
            assert pref.locked is ((category, channel) in LOCKED_NOTIFICATION_PREFERENCES)


def test_get_preferences_by_category(db, test_student):
    service = NotificationPreferenceService(db)

    prefs_by_category = service.get_preferences_by_category(test_student.id)

    assert prefs_by_category["lesson_updates"]["email"] is True
    assert prefs_by_category["lesson_updates"]["push"] is True
    assert prefs_by_category["lesson_updates"]["sms"] is False
    assert prefs_by_category["messages"]["push"] is True
    assert prefs_by_category["learning_tips"]["email"] is True
    assert prefs_by_category["learning_tips"]["push"] is True
    assert prefs_by_category["learning_tips"]["sms"] is False
    assert prefs_by_category["system_updates"]["email"] is True
    assert prefs_by_category["system_updates"]["push"] is False
    assert prefs_by_category["system_updates"]["sms"] is False
    assert prefs_by_category["promotional"]["push"] is False


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
