from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.notification_service import NotificationService
from app.services.template_registry import TemplateRegistry


class DummyTemplateService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def render_template(self, template: str, context: dict) -> str:
        self.calls.append((template, context))
        return "<html>ok</html>"


class DummyEmailService:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_email(self, *, to_email: str, subject: str, html_content: str, template: str):
        self.sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "template": template,
                "html_content": html_content,
            }
        )
        return {"id": "email_1"}


class DummyRepo:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


def _build_notification_service(db):
    template = DummyTemplateService()
    email = DummyEmailService()
    service = NotificationService(
        db,
        template_service=template,
        email_service=email,
        notification_repository=DummyRepo(),
        push_service=DummyRepo(),
        preference_service=DummyRepo(),
        sms_service=DummyRepo(),
    )
    service._should_send_email = lambda *_args, **_kwargs: True
    service._get_booking_local_datetime = lambda _booking: datetime(2026, 2, 3, 12, 0, 0, tzinfo=timezone.utc)
    return service, template, email


def _make_booking():
    return SimpleNamespace(
        id="bk1",
        service_name="Guitar Lesson",
        student_id="student",
        instructor_id="instructor",
        student=SimpleNamespace(email="student@example.com"),
        instructor=SimpleNamespace(email="instructor@example.com"),
    )


def test_send_booking_completed_notification_sends_both(db):
    service, _template, email = _build_notification_service(db)
    booking = _make_booking()

    success = service.send_booking_completed_notification(booking, recipient="both")
    assert success is True
    assert len(email.sent) == 2
    templates = {item["template"] for item in email.sent}
    assert TemplateRegistry.BOOKING_COMPLETED_STUDENT in templates
    assert TemplateRegistry.BOOKING_COMPLETED_INSTRUCTOR in templates


def test_send_booking_completed_notification_student_only_and_none_booking(db):
    service, _template, email = _build_notification_service(db)
    assert service.send_booking_completed_notification(None) is False

    booking = _make_booking()
    success = service.send_booking_completed_notification(booking, recipient="student")
    assert success is True
    assert len(email.sent) == 1
    assert email.sent[0]["to_email"] == "student@example.com"


def test_send_booking_completed_notification_handles_failure(db):
    service, _template, _email = _build_notification_service(db)
    booking = _make_booking()

    def _boom(_booking):
        raise RuntimeError("fail")

    service._send_student_completion_notification = _boom
    success = service.send_booking_completed_notification(booking, recipient="student")
    assert success is False


def test_send_booking_completed_notification_instructor_failure(db):
    service, _template, _email = _build_notification_service(db)
    booking = _make_booking()

    def _boom(_booking):
        raise RuntimeError("fail")

    service._send_instructor_completion_notification = _boom
    success = service.send_booking_completed_notification(booking, recipient="instructor")
    assert success is False


def test_completion_notifications_respect_preferences(db):
    service, _template, email = _build_notification_service(db)
    booking = _make_booking()
    service._should_send_email = lambda *_args, **_kwargs: False

    assert service._send_student_completion_notification(booking) is True
    assert service._send_instructor_completion_notification(booking) is True
    assert email.sent == []


def test_send_reminder_subjects_use_1h_and_24h(db):
    service, _template, email = _build_notification_service(db)
    booking = _make_booking()

    service._send_student_reminder(booking, reminder_type="1h")
    service._send_student_reminder(booking, reminder_type="24h")
    service._send_student_reminder(booking, reminder_type="other")
    service._send_instructor_reminder(booking, reminder_type="1h")
    service._send_instructor_reminder(booking, reminder_type="24h")
    service._send_instructor_reminder(booking, reminder_type="other")

    subjects = {item["subject"] for item in email.sent}
    assert any("1 Hour" in subject for subject in subjects)
    assert any("Tomorrow" in subject for subject in subjects)
    assert "Reminder: Guitar Lesson" in subjects


def test_reminder_respects_preferences(db):
    service, _template, email = _build_notification_service(db)
    booking = _make_booking()
    service._should_send_email = lambda *_args, **_kwargs: False

    assert service._send_student_reminder(booking, reminder_type="24h") is True
    assert service._send_instructor_reminder(booking, reminder_type="24h") is True
    assert email.sent == []
