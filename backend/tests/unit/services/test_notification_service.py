"""Tests for NotificationService in-app notifications."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_create_notification_creates_record_and_sends_sse(db, test_student):
    service = NotificationService(db)

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ) as mock_publish:
        notification = await service.create_notification(
            user_id=test_student.id,
            category="lesson_updates",
            notification_type="booking_confirmed",
            title="Booking confirmed",
            body="Your lesson is booked",
            data={"url": "/instructor/dashboard"},
            send_push=False,
        )

    assert notification.user_id == test_student.id
    assert notification.read_at is None
    mock_publish.assert_called_once()
    event = mock_publish.call_args[0][1]
    assert event["type"] == "notification_update"
    assert event["payload"]["unread_count"] == 1


def test_get_notifications_pagination(db, test_student):
    repo = NotificationRepository(db)
    for idx in range(3):
        repo.create_notification(
            user_id=test_student.id,
            category="lesson_updates",
            type=f"type_{idx}",
            title=f"Title {idx}",
            body="Body",
        )
    db.commit()

    service = NotificationService(db)
    first_page = service.get_notifications(test_student.id, limit=2, offset=0)
    second_page = service.get_notifications(test_student.id, limit=2, offset=2)

    assert len(first_page) == 2
    assert len(second_page) == 1


def test_get_unread_count(db, test_student):
    repo = NotificationRepository(db)
    first = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Booking confirmed",
        body="Body",
    )
    repo.create_notification(
        user_id=test_student.id,
        category="messages",
        type="new_message",
        title="New message",
        body="Body",
    )
    db.commit()

    service = NotificationService(db)
    service.mark_as_read(test_student.id, first.id)

    assert service.get_unread_count(test_student.id) == 1


def test_mark_as_read(db, test_student):
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Booking confirmed",
        body="Body",
    )
    db.commit()

    service = NotificationService(db)
    assert service.mark_as_read(test_student.id, notification.id) is True

    db.expire_all()
    refreshed = db.get(Notification, notification.id)
    assert refreshed is not None
    assert refreshed.read_at is not None


def test_mark_all_as_read(db, test_student):
    repo = NotificationRepository(db)
    for idx in range(2):
        repo.create_notification(
            user_id=test_student.id,
            category="lesson_updates",
            type=f"type_{idx}",
            title=f"Title {idx}",
            body="Body",
        )
    db.commit()

    service = NotificationService(db)
    updated = service.mark_all_as_read(test_student.id)

    assert updated == 2
    assert service.get_unread_count(test_student.id) == 0


def test_delete_notification(db, test_student):
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Booking confirmed",
        body="Body",
    )
    db.commit()

    service = NotificationService(db)
    assert service.delete_notification(test_student.id, notification.id) is True
    assert service.get_notification_count(test_student.id) == 0
