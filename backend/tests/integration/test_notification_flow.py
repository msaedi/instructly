"""Integration tests for end-to-end notification flows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.notification_repository import NotificationRepository
from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_service import NotificationService
from app.services.notification_templates import STUDENT_BOOKING_CONFIRMED
from app.services.sms_templates import BOOKING_CONFIRMED_STUDENT


class FakeSMSService:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_to_user(self, user_id: str, message: str, user_repository=None):
        self.sent.append((user_id, message))
        return {"sid": "test-sid"}


class FakePushService:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_push_notification(self, user_id: str, title: str, body: str, **kwargs: Any) -> dict[str, int]:
        self.sent.append({"user_id": user_id, "title": title, "body": body, **kwargs})
        return {"sent": 1, "failed": 0, "expired": 0}


@pytest.mark.asyncio
async def test_booking_confirmation_respects_preferences(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "email", False)
    preference_service.update_preference(test_student.id, "lesson_updates", "sms", True)

    sms_service = FakeSMSService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
        sms_service=sms_service,
    )
    email_service.send_email.reset_mock()

    with patch("app.services.notification_service.publish_to_user", new_callable=AsyncMock):
        notification = await service.notify_user(
            user_id=test_student.id,
            template=STUDENT_BOOKING_CONFIRMED,
            instructor_name="Test Instructor",
            service_name="Piano Lessons",
            date="January 15",
            time="2:00 PM",
            booking_id="booking_123",
            send_push=False,
            send_sms=True,
            sms_template=BOOKING_CONFIRMED_STUDENT,
        )

    assert notification.user_id == test_student.id
    email_service.send_email.assert_not_called()
    assert len(sms_service.sent) == 1

    notifications = NotificationRepository(db).get_user_notifications(test_student.id)
    assert notifications


@pytest.mark.asyncio
async def test_security_notifications_bypass_preferences(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "email", False)
    preference_service.update_preference(test_student.id, "messages", "email", False)

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
    )
    email_service.send_email.reset_mock()

    sent = service.send_new_device_login_notification(
        user_id=test_student.id,
        ip_address="1.2.3.4",
        user_agent="Test Browser",
        login_time=datetime.now(timezone.utc),
    )

    assert sent is True
    email_service.send_email.assert_called_once()


@pytest.mark.asyncio
async def test_message_notification_all_channels(
    db,
    test_student,
    test_instructor_with_availability,
    test_booking,
    template_service,
    email_service,
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "messages", "email", True)
    preference_service.update_preference(test_student.id, "messages", "sms", True)
    preference_service.update_preference(test_student.id, "messages", "push", True)

    sms_service = FakeSMSService()
    push_service = FakePushService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
        sms_service=sms_service,
        push_service=push_service,
    )
    email_service.send_email.reset_mock()

    tasks: list[asyncio.Task[None]] = []

    def _run_immediately(coro_func, _context: str) -> None:
        tasks.append(asyncio.create_task(coro_func()))

    service._run_async_task = _run_immediately  # type: ignore[method-assign]

    with patch("app.services.notification_service.publish_to_user", new_callable=AsyncMock):
        service.send_message_notification(
            recipient_id=test_student.id,
            booking=test_booking,
            sender_id=test_instructor_with_availability.id,
            message_content="Hi! Looking forward to our lesson.",
        )

        if tasks:
            await asyncio.gather(*tasks)

    email_service.send_email.assert_called_once()
    assert len(sms_service.sent) == 1
    assert len(push_service.sent) == 1

    notifications = NotificationRepository(db).get_user_notifications(test_student.id)
    assert notifications
    assert notifications[0].category == "messages"
