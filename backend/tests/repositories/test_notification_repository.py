"""Tests for NotificationRepository (preferences, inbox, push subscriptions)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import RepositoryException
from app.models.notification import LOCKED_NOTIFICATION_PREFERENCES
from app.repositories.notification_repository import NotificationRepository


def _preference_map(preferences):
    return {(pref.category, pref.channel): pref for pref in preferences}


def test_create_default_preferences(db, test_student):
    repo = NotificationRepository(db)
    prefs = repo.create_default_preferences(test_student.id)
    db.commit()

    assert len(prefs) == 9
    pref_map = _preference_map(prefs)

    expected = {
        "lesson_updates": {"email": True, "push": True, "sms": False},
        "messages": {"email": False, "push": True, "sms": False},
        "promotional": {"email": False, "push": False, "sms": False},
    }

    for category, channel_map in expected.items():
        for channel, enabled in channel_map.items():
            pref = pref_map[(category, channel)]
            assert pref.enabled is enabled
            assert pref.locked is ((category, channel) in LOCKED_NOTIFICATION_PREFERENCES)


def test_get_user_preferences(db, test_student):
    repo = NotificationRepository(db)
    repo.create_default_preferences(test_student.id)
    db.commit()

    prefs = repo.get_user_preferences(test_student.id)
    assert len(prefs) == 9
    assert all(pref.user_id == test_student.id for pref in prefs)


def test_get_preference(db, test_student):
    repo = NotificationRepository(db)
    repo.create_default_preferences(test_student.id)
    db.commit()

    pref = repo.get_preference(test_student.id, "lesson_updates", "email")
    assert pref is not None
    assert pref.category == "lesson_updates"
    assert pref.channel == "email"


def test_upsert_preference_create(db, test_instructor):
    repo = NotificationRepository(db)
    pref = repo.upsert_preference(test_instructor.id, "promotional", "email", True)
    db.commit()

    assert pref.user_id == test_instructor.id
    assert pref.category == "promotional"
    assert pref.channel == "email"
    assert pref.enabled is True


def test_upsert_preference_update(db, test_student):
    repo = NotificationRepository(db)
    repo.create_default_preferences(test_student.id)
    db.commit()

    updated = repo.upsert_preference(test_student.id, "lesson_updates", "email", False)
    db.commit()

    assert updated.enabled is False


def test_upsert_locked_preference_fails(db, test_student):
    repo = NotificationRepository(db)
    repo.create_default_preferences(test_student.id)
    db.commit()

    with pytest.raises(RepositoryException):
        repo.upsert_preference(test_student.id, "messages", "push", False)

    pref = repo.get_preference(test_student.id, "messages", "push")
    assert pref is not None
    assert pref.enabled is True
    assert pref.locked is True


def test_create_notification(db, test_student):
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Booking confirmed",
        body="Your lesson is booked.",
        data={"booking_id": "booking-1"},
    )
    db.commit()

    assert notification.id is not None
    assert notification.user_id == test_student.id
    assert notification.category == "lesson_updates"
    assert notification.type == "booking_confirmed"
    assert notification.title == "Booking confirmed"
    assert notification.body == "Your lesson is booked."
    assert notification.data == {"booking_id": "booking-1"}
    assert notification.read_at is None


def test_get_user_notifications_pagination(db, test_student):
    repo = NotificationRepository(db)
    base_time = datetime.now(timezone.utc) - timedelta(hours=1)

    created = []
    for idx in range(5):
        notif = repo.create_notification(
            user_id=test_student.id,
            category="lesson_updates",
            type="event",
            title=f"Notification {idx}",
        )
        notif.created_at = base_time + timedelta(minutes=idx)
        created.append(notif)
    db.commit()

    page1 = repo.get_user_notifications(test_student.id, limit=2, offset=0)
    page2 = repo.get_user_notifications(test_student.id, limit=2, offset=2)

    assert [n.title for n in page1] == ["Notification 4", "Notification 3"]
    assert [n.title for n in page2] == ["Notification 2", "Notification 1"]


def test_get_user_notifications_ordering(db, test_student):
    repo = NotificationRepository(db)
    base_time = datetime.now(timezone.utc) - timedelta(days=1)

    for idx in range(3):
        notif = repo.create_notification(
            user_id=test_student.id,
            category="messages",
            type="message",
            title=f"Msg {idx}",
        )
        notif.created_at = base_time + timedelta(minutes=idx)
    db.commit()

    notifications = repo.get_user_notifications(test_student.id, limit=3, offset=0)
    assert [n.title for n in notifications] == ["Msg 2", "Msg 1", "Msg 0"]


def test_get_unread_count(db, test_student):
    repo = NotificationRepository(db)
    repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="reminder",
        title="Reminder",
    )
    read = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="reminder",
        title="Reminder 2",
    )
    read.read_at = datetime.now(timezone.utc)
    db.commit()

    assert repo.get_unread_count(test_student.id) == 1
    assert repo.get_unread_count("nonexistent") == 0


def test_mark_as_read(db, test_student):
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_student.id,
        category="messages",
        type="message",
        title="New message",
    )
    db.commit()

    updated = repo.mark_as_read(notification.id)
    db.commit()

    assert updated is True
    refreshed = repo.get_user_notifications(test_student.id, limit=1)[0]
    assert refreshed.read_at is not None


def test_mark_all_as_read(db, test_student, test_instructor):
    repo = NotificationRepository(db)
    repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="reminder",
        title="Reminder 1",
    )
    repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="reminder",
        title="Reminder 2",
    )
    repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="reminder",
        title="Other user",
    )
    db.commit()

    updated = repo.mark_all_as_read(test_student.id)
    db.commit()

    assert updated == 2
    assert repo.get_unread_count(test_student.id) == 0
    assert repo.get_unread_count(test_instructor.id) == 1


def test_create_subscription(db, test_student):
    repo = NotificationRepository(db)
    sub = repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/1",
        p256dh_key="p256dh",
        auth_key="auth",
        user_agent="agent",
    )
    db.commit()

    assert sub.user_id == test_student.id
    assert sub.endpoint == "https://push.example.com/1"
    assert sub.p256dh_key == "p256dh"
    assert sub.auth_key == "auth"
    assert sub.user_agent == "agent"


def test_create_duplicate_subscription(db, test_student):
    repo = NotificationRepository(db)
    first = repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/dup",
        p256dh_key="p256dh",
        auth_key="auth",
        user_agent="agent",
    )
    db.commit()

    updated = repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/dup",
        p256dh_key="p256dh-new",
        auth_key="auth-new",
        user_agent="agent-new",
    )
    db.commit()

    assert updated.id == first.id
    assert updated.p256dh_key == "p256dh-new"
    assert updated.auth_key == "auth-new"
    assert updated.user_agent == "agent-new"

    subs = repo.get_user_subscriptions(test_student.id)
    assert len(subs) == 1


def test_get_user_subscriptions(db, test_student):
    repo = NotificationRepository(db)
    repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/one",
        p256dh_key="p256dh-1",
        auth_key="auth-1",
    )
    repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/two",
        p256dh_key="p256dh-2",
        auth_key="auth-2",
    )
    db.commit()

    subs = repo.get_user_subscriptions(test_student.id)
    assert len(subs) == 2
    endpoints = {sub.endpoint for sub in subs}
    assert endpoints == {"https://push.example.com/one", "https://push.example.com/two"}


def test_delete_subscription(db, test_student):
    repo = NotificationRepository(db)
    repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/delete",
        p256dh_key="p256dh",
        auth_key="auth",
    )
    db.commit()

    deleted = repo.delete_subscription(test_student.id, "https://push.example.com/delete")
    db.commit()

    assert deleted is True
    assert repo.get_user_subscriptions(test_student.id) == []


def test_delete_all_user_subscriptions(db, test_student, test_instructor):
    repo = NotificationRepository(db)
    repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/a",
        p256dh_key="p256dh-a",
        auth_key="auth-a",
    )
    repo.create_subscription(
        user_id=test_student.id,
        endpoint="https://push.example.com/b",
        p256dh_key="p256dh-b",
        auth_key="auth-b",
    )
    repo.create_subscription(
        user_id=test_instructor.id,
        endpoint="https://push.example.com/c",
        p256dh_key="p256dh-c",
        auth_key="auth-c",
    )
    db.commit()

    deleted = repo.delete_all_user_subscriptions(test_student.id)
    db.commit()

    assert deleted == 2
    assert repo.get_user_subscriptions(test_student.id) == []
    assert len(repo.get_user_subscriptions(test_instructor.id)) == 1
