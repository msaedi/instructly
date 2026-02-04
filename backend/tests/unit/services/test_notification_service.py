"""Tests for NotificationService in-app notifications."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from jinja2.exceptions import TemplateNotFound
import pytest

from app.core.exceptions import ServiceException
from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.services.cache_service import CacheService
from app.services.notification_service import NotificationService, retry
from app.services.notification_templates import STUDENT_BOOKING_CONFIRMED
from app.services.sms_templates import PAYMENT_FAILED


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


def test_retry_zero_attempts_raises_runtimeerror():
    @retry(max_attempts=0, backoff_seconds=0)
    def _noop() -> str:
        return "ok"

    with pytest.raises(RuntimeError):
        _noop()


def _build_dummy_cache():
    cache_service = CacheService.__new__(CacheService)
    cache_service.key_builder = object()
    return cache_service


def _build_booking_stub(student_id: str = "student-1", instructor_id: str = "instructor-1"):
    student = SimpleNamespace(
        id=student_id,
        email="student@example.com",
        first_name="Student",
        phone_verified=False,
    )
    instructor = SimpleNamespace(
        id=instructor_id,
        email="instructor@example.com",
        first_name="Instructor",
        user=SimpleNamespace(timezone="UTC"),
    )
    return SimpleNamespace(
        id="booking-1",
        student_id=student_id,
        instructor_id=instructor_id,
        service_name="Guitar",
        booking_start_utc=datetime.now(timezone.utc),
        lesson_timezone="UTC",
        instructor_tz_at_booking=None,
        student=student,
        instructor=instructor,
    )


def test_init_sms_service_does_not_override_existing_cache(
    db, template_service, email_service
):
    dummy_cache = _build_dummy_cache()
    existing_cache = object()
    sms_stub = SimpleNamespace(cache_service=existing_cache)

    service = NotificationService(
        db,
        cache=dummy_cache,
        template_service=template_service,
        email_service=email_service,
        push_service=SimpleNamespace(),
        preference_service=SimpleNamespace(),
        sms_service=sms_stub,
    )

    assert service.sms_service is sms_stub
    assert sms_stub.cache_service is existing_cache


def test_send_booking_confirmation_unexpected_exception(
    db, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)

    class ExplodingBooking:
        @property
        def id(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        service.send_booking_confirmation(ExplodingBooking())


def test_send_cancellation_notification_template_not_found_student_path(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(
        service,
        "_send_instructor_cancellation_notification",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TemplateNotFound("missing")),
    )

    with pytest.raises(ServiceException):
        service.send_cancellation_notification(
            booking, cancelled_by="student", reason="test"
        )


def test_send_cancellation_notification_template_not_found_student_confirmation(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(service, "_send_instructor_cancellation_notification", lambda *_: True)
    monkeypatch.setattr(
        service,
        "_send_student_cancellation_confirmation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TemplateNotFound("missing")),
    )

    with pytest.raises(ServiceException):
        service.send_cancellation_notification(
            booking, cancelled_by="student", reason="test"
        )


def test_send_cancellation_notification_instructor_template_errors(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(
        service,
        "_send_student_cancellation_notification",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TemplateNotFound("missing")),
    )
    with pytest.raises(ServiceException):
        service.send_cancellation_notification(
            booking, cancelled_by="instructor", reason="test"
        )

    monkeypatch.setattr(
        service,
        "_send_student_cancellation_notification",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        service, "_send_instructor_cancellation_confirmation", lambda *_: True
    )
    assert (
        service.send_cancellation_notification(
            booking, cancelled_by="instructor", reason="test"
        )
        is False
    )


def test_send_cancellation_notification_instructor_confirmation_errors(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(service, "_send_student_cancellation_notification", lambda *_: True)
    monkeypatch.setattr(
        service,
        "_send_instructor_cancellation_confirmation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TemplateNotFound("missing")),
    )
    with pytest.raises(ServiceException):
        service.send_cancellation_notification(
            booking, cancelled_by="instructor", reason="test"
        )

    monkeypatch.setattr(
        service,
        "_send_instructor_cancellation_confirmation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert (
        service.send_cancellation_notification(
            booking, cancelled_by="instructor", reason="test"
        )
        is False
    )


def test_send_cancellation_notification_outer_exception(
    db, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)

    class ExplodingBooking:
        @property
        def id(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        service.send_cancellation_notification(ExplodingBooking(), cancelled_by="student")


def test_send_reminder_emails_success(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(service, "_get_tomorrows_bookings", lambda: [booking])
    monkeypatch.setattr(service, "_send_booking_reminders", lambda *_: 1)

    assert service.send_reminder_emails() == 1


def test_send_booking_reminder_success(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(service, "_send_student_reminder", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(service, "_send_instructor_reminder", lambda *_args, **_kwargs: True)

    assert service.send_booking_reminder(booking) is True


def test_booking_cancelled_payment_failed_student_only(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(
        service, "_should_send_email", lambda user_id, *_: user_id == booking.student_id
    )
    monkeypatch.setattr(template_service, "template_exists", lambda *_: False)
    monkeypatch.setattr(template_service, "render_string", lambda *_: "<p>ok</p>")

    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(booking) is True
    assert email_service.send_email.call_count == 1


def test_booking_cancelled_payment_failed_instructor_only(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    monkeypatch.setattr(
        service,
        "_should_send_email",
        lambda user_id, *_: user_id == booking.instructor_id,
    )
    monkeypatch.setattr(template_service, "template_exists", lambda *_: False)
    monkeypatch.setattr(template_service, "render_string", lambda *_: "<p>ok</p>")

    email_service.send_email.reset_mock()
    assert service.send_booking_cancelled_payment_failed(booking) is True
    assert email_service.send_email.call_count == 1


def test_booking_cancelled_payment_failed_exception(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(template_service, "template_exists", lambda *_: False)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(template_service, "render_string", _raise)
    assert service.send_booking_cancelled_payment_failed(booking) is False


def test_payment_failed_notification_missing_student_user(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: None)

    booking_stub = SimpleNamespace(student_id="missing")
    assert service.send_payment_failed_notification(booking_stub) is False


def test_payment_failed_notification_instructor_missing(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub(student_id=test_student.id, instructor_id="missing-inst")

    def _get_by_id(user_id):
        if user_id == booking.student_id:
            return test_student
        return None

    monkeypatch.setattr(service.user_repository, "get_by_id", _get_by_id)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    test_student.phone_verified = False
    assert service.send_payment_failed_notification(booking) is True


def test_payment_failed_notification_instructor_name_set(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub(student_id=test_student.id, instructor_id="inst-1")
    instructor = SimpleNamespace(first_name="Coach", email="coach@example.com")

    def _get_by_id(user_id):
        if user_id == booking.student_id:
            return test_student
        if user_id == booking.instructor_id:
            return instructor
        return None

    monkeypatch.setattr(service.user_repository, "get_by_id", _get_by_id)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    test_student.phone_verified = False
    assert service.send_payment_failed_notification(booking) is True


def test_payment_failed_notification_sms_skipped_when_unverified(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    booking = _build_booking_stub(student_id=test_student.id, instructor_id="inst-1")

    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: test_student)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    test_student.phone_verified = False
    assert service.send_payment_failed_notification(booking) is True


def test_final_payment_warning_preference_disabled(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)

    assert service.send_final_payment_warning(booking, hours_until_lesson=12.0) is True


def test_final_payment_warning_template_exception_fallback(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(template_service, "template_exists", _raise)
    monkeypatch.setattr(template_service, "render_string", lambda *_: "<p>ok</p>")

    assert service.send_final_payment_warning(booking, hours_until_lesson=24.0) is True


def test_final_payment_warning_send_failure(
    db, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    email_service.send_email.side_effect = RuntimeError("boom")

    assert service.send_final_payment_warning(booking, hours_until_lesson=24.0) is False
    email_service.send_email.side_effect = None


def test_email_preference_short_circuits_templates(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)

    email_service.send_email.reset_mock()

    assert service._send_instructor_booking_notification(booking) is True
    assert (
        service._send_instructor_cancellation_notification(
            booking, reason="test", cancelled_by="student"
        )
        is True
    )
    assert service._send_instructor_cancellation_confirmation(booking) is True
    assert service._send_student_reminder(booking) is True
    assert service._send_instructor_reminder(booking) is True

    assert email_service.send_email.call_count == 0


def test_send_message_notification_skips_email_when_disabled(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    recipient = SimpleNamespace(id="recipient", email="rec@example.com", first_name="Rec")
    sender = SimpleNamespace(id="sender", email="sender@example.com", first_name="Sender")
    booking = _build_booking_stub(student_id=recipient.id, instructor_id=sender.id)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_by_id(self, user_id):
            if user_id == recipient.id:
                return recipient
            if user_id == sender.id:
                return sender
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", FakeRepo)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    service._run_async_task = lambda *_: None

    result = service.send_message_notification(
        recipient_id=recipient.id,
        booking=booking,
        sender_id=sender.id,
        message_content="Hello",
    )

    assert result is True
    assert email_service.send_email.call_count == 0


def test_send_message_notification_email_returns_false(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    recipient = SimpleNamespace(id="recipient", email="rec@example.com", first_name="Rec")
    sender = SimpleNamespace(id="sender", email="sender@example.com", first_name="Sender")
    booking = _build_booking_stub(student_id=recipient.id, instructor_id=sender.id)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_by_id(self, user_id):
            if user_id == recipient.id:
                return recipient
            if user_id == sender.id:
                return sender
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", FakeRepo)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: True)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")
    service._run_async_task = lambda *_: None

    email_service.send_email.return_value = None
    result = service.send_message_notification(
        recipient_id=recipient.id,
        booking=booking,
        sender_id=sender.id,
        message_content="Hello",
    )

    assert result is False


def test_send_message_notification_sms_render_error(
    db, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db,
        None,
        template_service,
        email_service,
        sms_service=sms_service,
    )
    recipient = SimpleNamespace(id="recipient", email="rec@example.com", first_name="Rec")
    sender = SimpleNamespace(id="sender", email="sender@example.com", first_name="Sender")
    booking = _build_booking_stub(student_id=recipient.id, instructor_id=sender.id)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_by_id(self, user_id):
            if user_id == recipient.id:
                return recipient
            if user_id == sender.id:
                return sender
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", FakeRepo)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    monkeypatch.setattr(service, "_should_send_sms", lambda *_: True)
    service._run_async_task = lambda *_: None

    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        assert (
            service.send_message_notification(
                recipient_id=recipient.id,
                booking=booking,
                sender_id=sender.id,
                message_content="Hello",
            )
            is True
        )


def test_send_message_notification_sms_skipped_when_disabled(
    db, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    recipient = SimpleNamespace(id="recipient", email="rec@example.com", first_name="Rec")
    sender = SimpleNamespace(id="sender", email="sender@example.com", first_name="Sender")
    booking = _build_booking_stub(student_id=recipient.id, instructor_id=sender.id)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_by_id(self, user_id):
            if user_id == recipient.id:
                return recipient
            if user_id == sender.id:
                return sender
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", FakeRepo)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    monkeypatch.setattr(service, "_should_send_sms", lambda *_: False)
    service._run_async_task = lambda *_: None

    assert (
        service.send_message_notification(
            recipient_id=recipient.id,
            booking=booking,
            sender_id=sender.id,
            message_content="Hello",
        )
        is True
    )


def test_send_message_notification_outer_exception(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    booking = _build_booking_stub()
    monkeypatch.setattr(
        service, "_should_send_email", lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    assert (
        service.send_message_notification(
            recipient_id="recipient",
            booking=booking,
            sender_id="sender",
            message_content="Hello",
        )
        is False
    )


def test_send_payout_notification_email_failure(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    user = SimpleNamespace(id="inst", email="inst@example.com", first_name="Inst")
    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: user)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")
    email_service.send_email.side_effect = RuntimeError("boom")

    assert (
        service.send_payout_notification(
            user.id,
            amount_cents=123,
            payout_date=datetime.now(timezone.utc),
        )
        is False
    )
    email_service.send_email.side_effect = None


def test_new_device_login_missing_user(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: None)

    assert (
        service.send_new_device_login_notification(
            "missing",
            ip_address="127.0.0.1",
            user_agent="test",
            login_time=datetime.now(timezone.utc),
        )
        is False
    )


def test_new_device_login_email_failure(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")
    email_service.send_email.side_effect = RuntimeError("boom")

    assert (
        service.send_new_device_login_notification(
            test_student.id,
            ip_address="127.0.0.1",
            user_agent="test",
            login_time=datetime.now(timezone.utc),
        )
        is False
    )
    email_service.send_email.side_effect = None


def test_new_device_login_sms_render_error(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        assert (
            service.send_new_device_login_notification(
                test_student.id,
                ip_address="127.0.0.1",
                user_agent="test",
                login_time=datetime.now(timezone.utc),
            )
            is True
        )


def test_new_device_login_without_sms_service(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    assert (
        service.send_new_device_login_notification(
            test_student.id,
            ip_address="127.0.0.1",
            user_agent="test",
            login_time=datetime.now(timezone.utc),
        )
        is True
    )


def test_password_changed_notification_missing_user(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: None)

    assert (
        service.send_password_changed_notification("missing", changed_at=datetime.now(timezone.utc))
        is False
    )


def test_password_changed_notification_email_failure(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")
    email_service.send_email.side_effect = RuntimeError("boom")

    assert (
        service.send_password_changed_notification(
            test_student.id, changed_at=datetime.now(timezone.utc)
        )
        is False
    )
    email_service.send_email.side_effect = None


def test_password_changed_notification_sms_render_error(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        assert (
            service.send_password_changed_notification(
                test_student.id, changed_at=datetime.now(timezone.utc)
            )
            is True
        )


def test_two_factor_changed_notification_missing_user(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    monkeypatch.setattr(service.user_repository, "get_by_id", lambda *_: None)

    assert (
        service.send_two_factor_changed_notification(
            "missing", enabled=True, changed_at=datetime.now(timezone.utc)
        )
        is False
    )


def test_two_factor_changed_notification_email_failure(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")
    email_service.send_email.side_effect = RuntimeError("boom")

    assert (
        service.send_two_factor_changed_notification(
            test_student.id, enabled=True, changed_at=datetime.now(timezone.utc)
        )
        is False
    )
    email_service.send_email.side_effect = None


def test_two_factor_changed_notification_sms_render_error(
    db, test_student, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    monkeypatch.setattr(template_service, "render_template", lambda *_: "<p>ok</p>")

    test_student.phone_verified = True
    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        assert (
            service.send_two_factor_changed_notification(
                test_student.id, enabled=True, changed_at=datetime.now(timezone.utc)
            )
            is True
        )


def test_badge_awarded_email_short_circuits_and_errors(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    missing_user = SimpleNamespace(id=None, email="missing@example.com", first_name="Missing")
    assert service.send_badge_awarded_email(missing_user, badge_name="Mentor") is False

    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    assert service.send_badge_awarded_email(test_student, badge_name="Mentor") is False

    monkeypatch.setattr(service, "_should_send_email", lambda *_: True)
    email_service.send_email.side_effect = RuntimeError("boom")
    assert service.send_badge_awarded_email(test_student, badge_name="Mentor") is False
    email_service.send_email.side_effect = None


def test_badge_digest_email_short_circuits_and_errors(
    db, test_student, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)

    missing_user = SimpleNamespace(id=None, email="missing@example.com", first_name="Missing")
    assert service.send_badge_digest_email(missing_user, items=[{"name": "A"}]) is False

    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    assert (
        service.send_badge_digest_email(test_student, items=[{"name": "A"}]) is False
    )

    monkeypatch.setattr(service, "_should_send_email", lambda *_: True)
    assert service.send_badge_digest_email(test_student, items=[]) is False

    email_service.send_email.side_effect = RuntimeError("boom")
    assert (
        service.send_badge_digest_email(
            test_student, items=[{"name": "Streak", "percent": 90, "remaining": 1}]
        )
        is False
    )
    email_service.send_email.side_effect = None


def test_run_async_task_without_running_loop(
    db, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    ran = {"value": False}

    async def _coro() -> None:
        ran["value"] = True

    service._run_async_task(_coro, "no-loop")
    assert ran["value"] is True


@pytest.mark.asyncio
async def test_run_async_task_with_running_loop(
    db, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    event = asyncio.Event()

    async def _coro() -> None:
        event.set()

    service._run_async_task(_coro, "loop")
    await asyncio.wait_for(event.wait(), timeout=1)


@pytest.mark.asyncio
async def test_notify_user_skips_email_when_pref_disabled(
    db, template_service, email_service, monkeypatch
):
    service = NotificationService(db, None, template_service, email_service)
    notification_stub = SimpleNamespace(
        id="notif",
        created_at=None,
        read_at=None,
        title="title",
        body="body",
        category="lesson_updates",
        type="booking_confirmed",
        data=None,
    )

    monkeypatch.setattr(service, "create_notification", AsyncMock(return_value=notification_stub))
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)
    send_email_mock = Mock()
    monkeypatch.setattr(service, "_send_notification_email", send_email_mock)

    result = await service.notify_user(
        user_id="user",
        template=STUDENT_BOOKING_CONFIRMED,
        send_push=False,
        send_email=True,
        service_name="Piano",
        instructor_name="Test",
        date="Jan 1",
        time="10:00",
        booking_id="booking_1",
    )

    assert result is notification_stub
    assert send_email_mock.call_count == 0


@pytest.mark.asyncio
async def test_notify_user_sms_render_error(
    db, template_service, email_service, monkeypatch
):
    sms_service = SimpleNamespace(send_to_user=AsyncMock())
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    notification_stub = SimpleNamespace(
        id="notif",
        created_at=None,
        read_at=None,
        title="title",
        body="body",
        category="lesson_updates",
        type="booking_confirmed",
        data=None,
    )

    monkeypatch.setattr(service, "create_notification", AsyncMock(return_value=notification_stub))
    monkeypatch.setattr(service, "_should_send_sms", lambda *_: True)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)

    with patch("app.services.notification_service.render_sms", side_effect=RuntimeError("boom")):
        await service.notify_user(
            user_id="user",
            template=STUDENT_BOOKING_CONFIRMED,
            send_push=False,
            send_email=False,
            send_sms=True,
            sms_template=PAYMENT_FAILED,
            instructor_name="Test",
            service_name="Piano",
            date="Jan 1",
            time="10:00",
            booking_id="booking_1",
        )


@pytest.mark.asyncio
async def test_notify_user_sms_send_failure(
    db, template_service, email_service, monkeypatch
):
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    sms_service = SimpleNamespace(send_to_user=AsyncMock(side_effect=_raise))
    service = NotificationService(
        db, None, template_service, email_service, sms_service=sms_service
    )
    notification_stub = SimpleNamespace(
        id="notif",
        created_at=None,
        read_at=None,
        title="title",
        body="body",
        category="lesson_updates",
        type="booking_confirmed",
        data=None,
    )

    monkeypatch.setattr(service, "create_notification", AsyncMock(return_value=notification_stub))
    monkeypatch.setattr(service, "_should_send_sms", lambda *_: True)
    monkeypatch.setattr(service, "_should_send_email", lambda *_: False)

    with patch("app.services.notification_service.render_sms", return_value="sms"):
        await service.notify_user(
            user_id="user",
            template=STUDENT_BOOKING_CONFIRMED,
            send_push=False,
            send_email=False,
            send_sms=True,
            sms_template=PAYMENT_FAILED,
            instructor_name="Test",
            service_name="Piano",
            date="Jan 1",
            time="10:00",
            booking_id="booking_1",
        )


@pytest.mark.asyncio
async def test_create_notification_push_failure_and_url(
    db, test_student, template_service, email_service
):
    service = NotificationService(db, None, template_service, email_service)
    service._should_send_push = lambda *_: True
    service.push_notification_service.send_push_notification = Mock(
        side_effect=RuntimeError("boom")
    )

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ) as mock_publish:
        notification = await service.create_notification(
            user_id=test_student.id,
            category="lesson_updates",
            notification_type="booking_confirmed",
            title="Booking confirmed",
            body="Your lesson is booked",
            data={"url": "https://example.com"},
            send_push=True,
        )

    assert notification.user_id == test_student.id
    mock_publish.assert_called_once()
