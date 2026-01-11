"""Integration coverage for email preference checks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_service import NotificationService
from app.services.notification_templates import STUDENT_BOOKING_CONFIRMED


@pytest.mark.asyncio
async def test_notify_user_skips_email_when_disabled(
    db, test_student, email_service, template_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "email", False)

    service = NotificationService(db, None, template_service, email_service)
    email_service.send_email.reset_mock()

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ):
        notification = await service.notify_user(
            user_id=test_student.id,
            template=STUDENT_BOOKING_CONFIRMED,
            instructor_name="Test Instructor",
            service_name="Piano Lessons",
            date="January 15",
            booking_id="booking_123",
            send_push=False,
        )

    assert notification.user_id == test_student.id
    email_service.send_email.assert_not_called()
