from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from jinja2.exceptions import TemplateNotFound
import pytest

from app.core.exceptions import ServiceException
from app.services.cache_service import CacheService, CacheServiceSyncAdapter
from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_service import NotificationService, retry
from app.services.notification_templates import STUDENT_BOOKING_CONFIRMED, NotificationTemplate
from app.services.sms_templates import PAYMENT_FAILED
from app.services.template_registry import TemplateRegistry


class FakeSMSService:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_to_user(self, user_id: str, message: str, user_repository=None):
        self.sent.append((user_id, message))
        return {"sid": "sms-test"}


class FakePushService:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_push_notification(self, user_id: str, title: str, body: str, **kwargs):
        self.sent.append({"user_id": user_id, "title": title, "body": body})
        return {"sent": 1, "failed": 0, "expired": 0}


def _run_sync(coro_func, _context: str) -> None:
    coro = coro_func()
    coro.close()


def test_booking_confirmation_and_cancellation(
    db, test_booking, test_student, test_instructor_with_availability, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "email", False)

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
    )
    email_service.send_email.reset_mock()

    assert service.send_booking_confirmation(test_booking) is True
    assert email_service.send_email.call_count >= 1

    email_service.send_email.reset_mock()
    assert (
        service.send_cancellation_notification(
            test_booking, cancelled_by=test_student, reason="Student cancel"
        )
        is True
    )
    assert email_service.send_email.call_count >= 1

    email_service.send_email.reset_mock()
    assert (
        service.send_cancellation_notification(
            test_booking, cancelled_by=test_instructor_with_availability, reason="Instructor cancel"
        )
        is True
    )
    assert email_service.send_email.call_count >= 1


def test_payment_and_reminder_notifications(
    db, test_booking, test_student, template_service, email_service
):
    sms_service = FakeSMSService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        sms_service=sms_service,
    )
    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    test_student.phone_verified = True
    db.commit()

    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(test_booking) is True
    assert email_service.send_email.call_count >= 1

    email_service.send_email.reset_mock()
    assert service.send_payment_failed_notification(test_booking) is True
    assert email_service.send_email.call_count >= 1

    email_service.send_email.reset_mock()
    assert service.send_final_payment_warning(test_booking, hours_until_lesson=24.0) is True
    assert email_service.send_email.call_count >= 1

    assert service.send_booking_reminder(test_booking, reminder_type="24h") is True
    assert sms_service.sent


def test_send_message_notification_full(
    db,
    test_booking,
    test_student,
    test_instructor_with_availability,
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
        push_service=push_service,
        preference_service=preference_service,
        sms_service=sms_service,
    )

    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    long_message = "x" * 250
    with patch("app.services.notification_service.publish_to_user", new_callable=AsyncMock):
        result = service.send_message_notification(
            recipient_id=test_student.id,
            booking=test_booking,
            sender_id=test_instructor_with_availability.id,
            message_content=long_message,
        )

    assert result is True
    assert email_service.send_email.called
    assert sms_service.sent


def test_send_message_notification_missing_user(
    db, test_booking, test_instructor_with_availability, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    assert (
        service.send_message_notification(
            recipient_id="missing",
            booking=test_booking,
            sender_id=test_instructor_with_availability.id,
            message_content="Hello",
        )
        is False
    )


def test_send_payout_and_security_notifications(
    db, test_instructor_with_availability, template_service, email_service
):
    sms_service = FakeSMSService()
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    assert (
        service.send_payout_notification(
            test_instructor_with_availability.id,
            amount_cents=12345,
            payout_date=datetime.now(timezone.utc),
        )
        is True
    )
    assert (
        service.send_payout_notification(
            "missing",
            amount_cents=12345,
            payout_date=datetime.now(timezone.utc),
        )
        is False
    )

    assert (
        service.send_new_device_login_notification(
            test_instructor_with_availability.id,
            ip_address="127.0.0.1",
            user_agent="test",
            login_time=datetime.now(timezone.utc),
        )
        is True
    )
    assert sms_service.sent


def test_retry_decorator_retries(monkeypatch):
    calls = {"count": 0}

    monkeypatch.setattr(time, "sleep", lambda *_: None)

    @retry(max_attempts=2, backoff_seconds=0)
    def _flaky() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("boom")
        return "ok"

    assert _flaky() == "ok"
    assert calls["count"] == 2


def test_retry_decorator_exhausts(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    @retry(max_attempts=2, backoff_seconds=0)
    def _always_fail() -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _always_fail()


def _build_dummy_cache():
    cache_service = CacheService.__new__(CacheService)
    cache_service.key_builder = object()
    return cache_service


def test_resolve_db_cache_and_del(monkeypatch):
    class DummySession:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    dummy_session = DummySession()
    dummy_cache = _build_dummy_cache()
    adapter = CacheServiceSyncAdapter(dummy_cache)

    monkeypatch.setattr("app.database.SessionLocal", lambda: dummy_session)

    service = NotificationService(
        db=None,
        cache=adapter,
        template_service=SimpleNamespace(),
        email_service=SimpleNamespace(),
        push_service=SimpleNamespace(),
        preference_service=SimpleNamespace(),
        sms_service=SimpleNamespace(),
    )
    service.__del__()
    assert dummy_session.closed is True


def test_resolve_cache_variants(db, template_service, email_service, monkeypatch):
    service = NotificationService(db, None, template_service, email_service)
    dummy_cache = _build_dummy_cache()

    cache_service, cache_adapter = service._resolve_cache(dummy_cache)
    assert cache_service is dummy_cache
    assert cache_adapter is not None

    adapter = CacheServiceSyncAdapter(dummy_cache)
    cache_service, cache_adapter = service._resolve_cache(adapter)
    assert cache_service is dummy_cache
    assert cache_adapter is adapter

    def _boom(self, *_args, **_kwargs):
        raise RuntimeError("cache init failed")

    monkeypatch.setattr(CacheService, "__init__", _boom)
    cache_service, cache_adapter = service._resolve_cache(None)
    assert cache_service is None
    assert cache_adapter is None


def test_init_services_when_missing(db, monkeypatch):
    email_stub = SimpleNamespace()
    template_stub = SimpleNamespace()
    sms_stub = SimpleNamespace()
    cache_service = _build_dummy_cache()

    monkeypatch.setattr(
        "app.services.notification_service.EmailService", lambda *_a, **_k: email_stub
    )
    monkeypatch.setattr(
        "app.services.notification_service.TemplateService",
        lambda *_a, **_k: template_stub,
    )

    service = NotificationService(
        db,
        cache_service,
        template_service=None,
        email_service=None,
        push_service=SimpleNamespace(),
        preference_service=SimpleNamespace(),
        sms_service=sms_stub,
    )
    assert service.email_service is email_stub
    assert service.template_service is template_stub
    assert getattr(sms_stub, "cache_service", None) is cache_service


def test_preference_checks_and_security_notifications(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "promotional", "email", True)
    preference_service.update_preference(test_student.id, "messages", "sms", False)
    preference_service.update_preference(test_student.id, "messages", "push", True)

    sms_service = FakeSMSService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        sms_service=sms_service,
        preference_service=preference_service,
    )
    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    assert service._should_send_email(test_student.id, "promotional", "badge_awarded") is True
    assert service._should_send_sms(test_student.id, "messages", "notify") is False
    assert service._should_send_push(test_student.id, "messages") is True

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    preference_service.is_enabled = _raise  # type: ignore[assignment]
    assert service._should_send_email(test_student.id, "messages", "notify") is True
    assert service._should_send_sms(test_student.id, "messages", "notify") is False

    test_student.phone_verified = True
    db.commit()
    assert (
        service.send_password_changed_notification(
            test_student.id, changed_at=datetime.now(timezone.utc)
        )
        is True
    )
    assert (
        service.send_two_factor_changed_notification(
            test_student.id, enabled=True, changed_at=datetime.now(timezone.utc)
        )
        is True
    )
    assert sms_service.sent

    assert service.send_badge_awarded_email(test_student, badge_name="Mentor") is True
    assert (
        service.send_badge_digest_email(
            test_student,
            items=[{"name": "Streak", "percent": 90, "remaining": 1}],
        )
        is True
    )


def test_notify_user_best_effort_creates_notification(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "push", False)

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
    )
    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    service.notify_user_best_effort(
        test_student.id,
        STUDENT_BOOKING_CONFIRMED,
        send_push=False,
        send_email=False,
        service_name="Guitar",
        instructor_name="Test Instructor",
        date="Jan 20",
    )
    assert service.get_notification_count(test_student.id) >= 1


def test_booking_cancelled_payment_failed_preference_disabled(
    db, test_booking, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_booking.student_id, "lesson_updates", "email", False)
    preference_service.update_preference(
        test_booking.instructor_id, "lesson_updates", "email", False
    )

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
    )
    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(test_booking) is True
    assert email_service.send_email.call_count == 0


def test_booking_cancelled_payment_failed_custom_templates(
    db, test_booking, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    template_service.template_exists = lambda *_args, **_kwargs: True
    template_service.render_template = lambda *_args, **_kwargs: "<p>custom</p>"

    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(test_booking) is True
    assert email_service.send_email.call_count >= 1


def test_payment_failed_notification_email_failure_and_sms(
    db, test_booking, test_student, template_service, email_service
):
    sms_service = FakeSMSService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        sms_service=sms_service,
    )
    service._run_async_task = lambda coro_func, _ctx: asyncio.run(coro_func())

    test_student.phone_verified = True
    db.commit()

    email_service.send_email.side_effect = RuntimeError("email fail")
    with patch("app.services.notification_service.render_sms", return_value="sms"):
        assert service.send_payment_failed_notification(test_booking) is True

    assert sms_service.sent
    email_service.send_email.side_effect = None


def test_payment_failed_notification_sms_render_error(
    db, test_booking, test_student, template_service, email_service
):
    sms_service = FakeSMSService()
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        sms_service=sms_service,
    )
    service._run_async_task = _run_sync  # type: ignore[method-assign]

    test_student.phone_verified = True
    db.commit()

    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        assert service.send_payment_failed_notification(test_booking) is True


def test_payment_failed_notification_missing_student(db, template_service, email_service):
    service = NotificationService(db, None, template_service, email_service)
    booking_stub = SimpleNamespace(student_id=None)
    assert service.send_payment_failed_notification(booking_stub) is False


def test_final_payment_warning_template_override(
    db, test_booking, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    template_service.template_exists = lambda *_args, **_kwargs: True
    template_service.render_template = lambda *_args, **_kwargs: "<p>override</p>"

    email_service.send_email.reset_mock()
    assert service.send_final_payment_warning(test_booking, hours_until_lesson=24.0) is True
    assert email_service.send_email.call_count >= 1


def test_send_notification_email_variants(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    template = NotificationTemplate(
        category="messages",
        type="custom",
        title="Hello",
        body_template="Hi",
        email_template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
        email_subject_template="Subject {missing}",
    )

    monkeypatch.setattr(
        template_service, "render_template", lambda *_args, **_kwargs: "<p>ok</p>"
    )
    email_service.send_email.reset_mock()
    assert service._send_notification_email(
        test_student.id, template, instructor_name="Test"
    ) is True
    assert email_service.send_email.called

    email_service.send_email.side_effect = RuntimeError("send fail")
    assert (
        service._send_notification_email(test_student.id, template, instructor_name="Test")
        is False
    )
    email_service.send_email.side_effect = None

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(template_service, "render_template", _raise)
    assert (
        service._send_notification_email(test_student.id, template, instructor_name="Test")
        is False
    )

    no_email_template = NotificationTemplate(
        category="messages",
        type="custom",
        title="Hello",
        body_template="Hi",
        email_template=None,
    )
    assert service._send_notification_email(test_student.id, no_email_template) is False


def test_booking_cancelled_payment_failed_template_errors(
    db, test_booking, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(
        test_booking.student_id, "lesson_updates", "email", True
    )
    preference_service.update_preference(
        test_booking.instructor_id, "lesson_updates", "email", True
    )

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        preference_service=preference_service,
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    template_service.template_exists = _raise
    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(test_booking) is True
    assert email_service.send_email.call_count >= 1


def test_send_notification_email_missing_user(db, template_service, email_service):
    service = NotificationService(db, None, template_service, email_service)
    template = NotificationTemplate(
        category="messages",
        type="custom",
        title="Hello",
        body_template="Hi",
        email_template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
    )
    assert service._send_notification_email("missing-user", template) is False


@pytest.mark.asyncio
async def test_create_and_manage_notifications(
    db, test_student, template_service, email_service
):
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "messages", "push", True)
    push_service = FakePushService()

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        push_service=push_service,
        preference_service=preference_service,
    )

    with patch("app.services.notification_service.publish_to_user", new_callable=AsyncMock):
        notification = await service.create_notification(
            user_id=test_student.id,
            category="messages",
            notification_type="test",
            title="Hello",
            body="World",
            data={"url": "https://example.com"},
            send_push=True,
        )

    assert notification.id
    assert push_service.sent
    assert service.get_notifications(test_student.id)
    assert service.get_notification_count(test_student.id) >= 1
    assert service.get_unread_count(test_student.id) >= 1

    assert service.mark_as_read(test_student.id, notification.id) is True
    assert service.mark_all_as_read(test_student.id) >= 0
    assert service.delete_notification(test_student.id, notification.id) is True
    assert service.delete_all_notifications(test_student.id) >= 0


@pytest.mark.asyncio
async def test_notify_user_best_effort(
    db, test_student, template_service, email_service
):
    push_service = FakePushService()
    sms_service = FakeSMSService()
    preference_service = NotificationPreferenceService(db)
    preference_service.update_preference(test_student.id, "lesson_updates", "push", True)

    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        push_service=push_service,
        preference_service=preference_service,
        sms_service=sms_service,
    )

    with patch("app.services.notification_service.publish_to_user", new_callable=AsyncMock):
        await service.notify_user(
            user_id=test_student.id,
            template=STUDENT_BOOKING_CONFIRMED,
            send_push=True,
            send_email=True,
            send_sms=True,
            sms_template=PAYMENT_FAILED,
            instructor_name="Test",
            service_name="Piano",
            date="January 1",
            time="10:00",
            booking_id="booking_123",
        )

    assert push_service.sent


def test_booking_confirmation_failure_paths(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    assert service.send_booking_confirmation(None) is False

    def _raise_template(*_args, **_kwargs):
        raise TemplateNotFound("missing")

    monkeypatch.setattr(service, "_send_student_booking_confirmation", _raise_template)
    with pytest.raises(ServiceException):
        service.send_booking_confirmation(test_booking)

    monkeypatch.setattr(
        service,
        "_send_student_booking_confirmation",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(service, "_send_instructor_booking_notification", lambda *_a, **_k: True)
    assert service.send_booking_confirmation(test_booking) is False

    monkeypatch.setattr(service, "_send_student_booking_confirmation", lambda *_a, **_k: True)
    monkeypatch.setattr(
        service,
        "_send_instructor_booking_notification",
        lambda *_a, **_k: (_ for _ in ()).throw(TemplateNotFound("missing")),
    )
    with pytest.raises(ServiceException):
        service.send_booking_confirmation(test_booking)

    monkeypatch.setattr(service, "_send_student_booking_confirmation", lambda *_a, **_k: True)
    monkeypatch.setattr(
        service,
        "_send_instructor_booking_notification",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert service.send_booking_confirmation(test_booking) is False


def test_send_cancellation_notification_edge_cases(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    assert service.send_cancellation_notification(None, cancelled_by="student") is False
    assert service.send_cancellation_notification(test_booking, cancelled_by=None) is False

    monkeypatch.setattr(
        service,
        "_send_instructor_cancellation_notification",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        service,
        "_send_student_cancellation_confirmation",
        lambda *_args, **_kwargs: True,
    )
    assert (
        service.send_cancellation_notification(
            test_booking, cancelled_by="student", reason="Scheduling conflict"
        )
        is True
    )

    assert (
        service.send_cancellation_notification(
            test_booking, cancelled_by=123, reason="Scheduling conflict"
        )
        is True
    )

    monkeypatch.setattr(
        service,
        "_send_instructor_cancellation_notification",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        service,
        "_send_student_cancellation_confirmation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert (
        service.send_cancellation_notification(
            test_booking, cancelled_by="student", reason="Scheduling conflict"
        )
        is False
    )


def test_send_reminder_emails_empty_and_no_db(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    monkeypatch.setattr(service, "_get_tomorrows_bookings", lambda: [])
    assert service.send_reminder_emails() == 0

    service.db = None
    with pytest.raises(ServiceException):
        service.send_reminder_emails()


def test_send_reminder_emails_error(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(
        service,
        "_get_tomorrows_bookings",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(ServiceException):
        service.send_reminder_emails()


def test_get_tomorrows_bookings(db, template_service, email_service):
    service = NotificationService(db, None, template_service, email_service)
    results = service._get_tomorrows_bookings()
    assert isinstance(results, list)


def test_send_booking_reminders_and_failures(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    monkeypatch.setattr(service, "_send_student_reminder", lambda *_a, **_k: True)
    monkeypatch.setattr(service, "_send_instructor_reminder", lambda *_a, **_k: True)
    assert service._send_booking_reminders([test_booking]) == 1

    monkeypatch.setattr(service, "_send_instructor_reminder", lambda *_a, **_k: False)
    assert service._send_booking_reminders([test_booking]) == 0

    monkeypatch.setattr(
        service,
        "_send_student_reminder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        service,
        "_send_instructor_reminder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert service._send_booking_reminders([test_booking]) == 0
    assert service.send_booking_reminder(test_booking) is False


def test_send_student_booking_confirmation_full(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service, "_should_send_email", lambda *_a, **_k: True)
    monkeypatch.setattr(
        template_service, "render_template", lambda *_args, **_kwargs: "<p>ok</p>"
    )

    email_service.send_email.reset_mock()
    assert service._send_student_booking_confirmation(test_booking) is True
    assert email_service.send_email.called


def test_cancellation_and_reminder_templates(
    db, test_booking, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service, "_should_send_email", lambda *_a, **_k: True)
    monkeypatch.setattr(
        template_service, "render_template", lambda *_args, **_kwargs: "<p>ok</p>"
    )

    assert service._send_instructor_booking_notification(test_booking) is True
    assert (
        service._send_student_cancellation_notification(
            test_booking, reason="Change", cancelled_by="instructor"
        )
        is True
    )
    assert (
        service._send_instructor_cancellation_notification(
            test_booking, reason="Change", cancelled_by="student"
        )
        is True
    )
    assert service._send_student_cancellation_confirmation(test_booking) is True
    assert service._send_instructor_cancellation_confirmation(test_booking) is True
    assert service._send_student_reminder(test_booking) is True
    assert service._send_instructor_reminder(test_booking) is True
