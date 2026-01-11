"""Tests for email preference checks in NotificationService."""

from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_service import NotificationService


def test_booking_confirmation_skips_email_when_disabled(
    db, test_booking, email_service, template_service
):
    service = NotificationService(db, None, template_service, email_service)
    preference_service = NotificationPreferenceService(db)

    preference_service.update_preference(test_booking.student_id, "lesson_updates", "email", False)
    preference_service.update_preference(
        test_booking.instructor_id, "lesson_updates", "email", False
    )

    email_service.send_email.reset_mock()

    result = service.send_booking_confirmation(test_booking)

    assert result is True
    email_service.send_email.assert_not_called()


def test_badge_awarded_respects_promotional_preference(
    db, test_student, email_service, template_service
):
    service = NotificationService(db, None, template_service, email_service)
    preference_service = NotificationPreferenceService(db)

    preference_service.update_preference(test_student.id, "promotional", "email", False)
    email_service.send_email.reset_mock()

    assert service.send_badge_awarded_email(test_student, "Superstar") is False
    email_service.send_email.assert_not_called()

    preference_service.update_preference(test_student.id, "promotional", "email", True)
    assert service.send_badge_awarded_email(test_student, "Superstar") is True
    assert email_service.send_email.call_count == 1
