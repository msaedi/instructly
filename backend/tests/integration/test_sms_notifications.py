"""Integration tests for SMS notifications via NotificationService."""

from unittest.mock import AsyncMock, patch

import pytest

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


@pytest.mark.asyncio
async def test_notify_user_respects_sms_preferences(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    sms_service = FakeSMSService()
    notification_service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
        sms_service=sms_service,
    )

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ):
        await notification_service.notify_user(
            user_id=test_student.id,
            template=STUDENT_BOOKING_CONFIRMED,
            send_push=False,
            send_sms=True,
            sms_template=BOOKING_CONFIRMED_STUDENT,
            instructor_name="Test Instructor",
            service_name="Piano Lessons",
            date="January 15",
            time="2:00 PM",
            booking_id="booking_123",
        )

    assert sms_service.sent == []

    preference_service.update_preference(test_student.id, "lesson_updates", "sms", True)

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ):
        await notification_service.notify_user(
            user_id=test_student.id,
            template=STUDENT_BOOKING_CONFIRMED,
            send_push=False,
            send_sms=True,
            sms_template=BOOKING_CONFIRMED_STUDENT,
            instructor_name="Test Instructor",
            service_name="Piano Lessons",
            date="January 15",
            time="2:00 PM",
            booking_id="booking_123",
        )

    assert len(sms_service.sent) == 1
