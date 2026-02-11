"""Additional coverage tests for NotificationService."""

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notification_service import NotificationService


@pytest.fixture
def notification_service() -> NotificationService:
    service = NotificationService.__new__(NotificationService)
    service.db = MagicMock()
    service.logger = MagicMock()
    service.template_service = MagicMock()
    service.email_service = MagicMock()
    service.user_repository = MagicMock()
    service.notification_repository = MagicMock()
    service.preference_service = MagicMock()
    service.push_notification_service = MagicMock()
    service.sms_service = None
    service.frontend_url = "https://example.com"
    return service


def test_should_send_email_handles_preference_exception(notification_service) -> None:
    notification_service.preference_service.is_enabled.side_effect = RuntimeError("boom")

    assert (
        notification_service._should_send_email("user", "lesson_updates", "context") is True
    )


def test_should_send_sms_handles_preference_exception(notification_service) -> None:
    notification_service.preference_service.is_enabled.side_effect = RuntimeError("boom")

    assert notification_service._should_send_sms("user", "messages", "context") is False


def test_send_notification_email_subject_format_and_template_error(
    notification_service,
) -> None:
    template = SimpleNamespace(
        type="promo",
        title="Promo",
        category="promotional",
        email_template="email/promo.html",
        email_subject_template="Hello {missing}",
    )
    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.side_effect = RuntimeError("fail")

    assert notification_service._send_notification_email("user", template) is False


def test_send_message_notification_handles_email_failure_and_sms_render_error(
    notification_service,
) -> None:
    recipient = SimpleNamespace(id="u1", first_name="A", email="a@example.com")
    sender = SimpleNamespace(id="u2", first_name="B", email="b@example.com")
    booking = SimpleNamespace(
        id="b1",
        instructor_id="u2",
        service_name="Piano",
        booking_start_utc=datetime.now(timezone.utc),
    )

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_id(self, user_id: str):
            return recipient if user_id == recipient.id else sender

    notification_service.preference_service.is_enabled.return_value = True
    notification_service.template_service.render_template.return_value = "<html />"
    notification_service.email_service.send_email.return_value = None
    notification_service.sms_service = MagicMock()
    notification_service._run_async_task = MagicMock()

    with patch("app.services.notification_service.UserRepository", DummyUserRepo):
        with patch(
            "app.services.notification_service.render_sms",
            side_effect=RuntimeError("sms"),
        ):
            result = notification_service.send_message_notification(
                recipient_id=recipient.id,
                booking=booking,
                sender_id=sender.id,
                message_content="Hello there",
            )

    assert result is False


def test_send_booking_cancelled_payment_failed_sends_both(notification_service) -> None:
    student = SimpleNamespace(email="s@example.com")
    instructor = SimpleNamespace(email="i@example.com")
    booking = SimpleNamespace(
        id="b1",
        student_id="s1",
        instructor_id="i1",
        student=student,
        instructor=instructor,
        service_name="Piano",
    )

    notification_service.preference_service.is_enabled.return_value = True
    notification_service.template_service.template_exists.return_value = False
    notification_service.template_service.render_string.return_value = "<html />"

    assert notification_service.send_booking_cancelled_payment_failed(booking) is True
    assert notification_service.email_service.send_email.call_count == 2


def test_send_payment_failed_notification_student_missing(notification_service) -> None:
    booking = SimpleNamespace(student_id="s1")
    notification_service.user_repository.get_by_id.return_value = None

    assert notification_service.send_payment_failed_notification(booking) is False


def test_send_payment_failed_notification_instructor_name(notification_service) -> None:
    student = SimpleNamespace(
        first_name="Student",
        email="student@example.com",
        phone_verified=False,
    )
    instructor = SimpleNamespace(first_name="Instructor", email="inst@example.com")
    booking = SimpleNamespace(
        student_id="s1",
        instructor_id="i1",
        service_name="Piano",
        booking_start_utc=datetime.now(timezone.utc),
    )

    notification_service.user_repository.get_by_id.side_effect = [student, instructor]
    notification_service.template_service.render_template.return_value = "<html />"

    assert notification_service.send_payment_failed_notification(booking) is True
    notification_service.template_service.render_template.assert_called_once()


def test_send_final_payment_warning_skips_when_email_disabled(notification_service) -> None:
    student = SimpleNamespace(email="s@example.com")
    booking = SimpleNamespace(student_id="s1", student=student, id="b1", service_name="Piano")
    notification_service.preference_service.is_enabled.return_value = False

    assert notification_service.send_final_payment_warning(booking, hours_until_lesson=24) is True


def test_send_new_device_login_notification_user_not_found(notification_service) -> None:
    notification_service.user_repository.get_by_id.return_value = None

    assert (
        notification_service.send_new_device_login_notification(
            user_id="u1",
            ip_address="127.0.0.1",
            user_agent="agent",
            login_time=datetime.now(timezone.utc),
        )
        is False
    )


def test_send_password_changed_notification_sms_render_error(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"
    notification_service.sms_service = MagicMock()

    with patch(
        "app.services.notification_service.render_sms",
        side_effect=RuntimeError("sms"),
    ):
        assert (
            notification_service.send_password_changed_notification(
                user_id="u1",
                changed_at=datetime.now(timezone.utc),
            )
            is True
        )


def test_send_two_factor_changed_notification_sms_render_error(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email="ada@example.com", phone_verified=True)
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"
    notification_service.sms_service = MagicMock()

    with patch(
        "app.services.notification_service.render_sms",
        side_effect=RuntimeError("sms"),
    ):
        assert (
            notification_service.send_two_factor_changed_notification(
                user_id="u1",
                enabled=True,
                changed_at=datetime.now(timezone.utc),
            )
            is True
        )


@pytest.mark.asyncio
async def test_create_notification_push_url_and_send_error(notification_service):
    notification = SimpleNamespace(
        id="n1",
        title="Title",
        body="Body",
        category="messages",
        type="booking_new_message",
        data={"url": "/chat"},
        read_at=None,
        created_at=datetime.now(timezone.utc),
    )
    notification_service.notification_repository.create_notification.return_value = notification
    notification_service.notification_repository.get_unread_count.return_value = 2
    notification_service.preference_service.is_enabled.return_value = True
    notification_service.push_notification_service.send_push_notification.side_effect = RuntimeError(
        "push"
    )

    @contextmanager
    def _transaction():
        yield notification_service.db

    notification_service.transaction = _transaction

    with patch(
        "app.services.notification_service.publish_to_user", new_callable=AsyncMock
    ):
        created = await notification_service.create_notification(
            user_id="u1",
            category="messages",
            notification_type="booking_new_message",
            title="Title",
            body="Body",
            data={"url": "/chat"},
            send_push=True,
        )

    assert created.id == "n1"


# ── EmailSubject.welcome() ─────────────────────────────────────


def test_email_subject_welcome_contains_brand_name():
    from app.core.constants import BRAND_NAME
    from app.services.email_subjects import EmailSubject

    result = EmailSubject.welcome()
    assert result == f"Welcome to {BRAND_NAME}!"
    assert "iNSTAiNSTRU" in result


# ── send_welcome_email ──────────────────────────────────────────


def test_send_welcome_email_happy_path(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"

    assert notification_service.send_welcome_email("u1", role="instructor") is True
    notification_service.email_service.send_email.assert_called_once()
    call_kwargs = notification_service.email_service.send_email.call_args
    assert "ada@example.com" in str(call_kwargs)
    assert "Welcome" in str(call_kwargs)


def test_send_welcome_email_user_not_found(notification_service) -> None:
    notification_service.user_repository.get_by_id.return_value = None

    assert notification_service.send_welcome_email("missing") is False
    notification_service.email_service.send_email.assert_not_called()


def test_send_welcome_email_user_no_email(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email=None)
    notification_service.user_repository.get_by_id.return_value = user

    assert notification_service.send_welcome_email("u1") is False
    notification_service.email_service.send_email.assert_not_called()


def test_send_welcome_email_template_error(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.side_effect = RuntimeError("render fail")

    assert notification_service.send_welcome_email("u1") is False


def test_send_welcome_email_send_error(notification_service) -> None:
    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"
    notification_service.email_service.send_email.side_effect = RuntimeError("smtp fail")

    assert notification_service.send_welcome_email("u1") is False


def test_send_welcome_email_uses_email_as_fallback_name(notification_service) -> None:
    user = SimpleNamespace(first_name=None, email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"

    assert notification_service.send_welcome_email("u1") is True
    # The context should use user.email when first_name is None
    render_call = notification_service.template_service.render_template.call_args
    ctx = render_call[0][1] if len(render_call[0]) > 1 else render_call[1].get("context", {})
    assert ctx["user"].first_name == "ada@example.com"


# ── BRAND_NAME in notification subjects ─────────────────────────


def test_payout_notification_subject_uses_brand_name(notification_service) -> None:
    from app.core.constants import BRAND_NAME

    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"

    notification_service.send_payout_notification(
        instructor_id="u1",
        amount_cents=10000,
        payout_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
    )

    call_kwargs = notification_service.email_service.send_email.call_args
    subject = call_kwargs[1].get("subject", "") if call_kwargs[1] else call_kwargs[0][1]
    assert BRAND_NAME in subject


def test_new_device_login_subject_uses_brand_name(notification_service) -> None:
    from app.core.constants import BRAND_NAME

    user = SimpleNamespace(first_name="Ada", email="ada@example.com", phone_verified=False)
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"

    notification_service.send_new_device_login_notification(
        user_id="u1",
        ip_address="127.0.0.1",
        user_agent="test-agent",
        login_time=datetime.now(timezone.utc),
    )

    call_kwargs = notification_service.email_service.send_email.call_args
    subject = call_kwargs[1].get("subject", "") if call_kwargs[1] else call_kwargs[0][1]
    assert BRAND_NAME in subject


def test_password_changed_subject_uses_brand_name(notification_service) -> None:
    from app.core.constants import BRAND_NAME

    user = SimpleNamespace(first_name="Ada", email="ada@example.com")
    notification_service.user_repository.get_by_id.return_value = user
    notification_service.template_service.render_template.return_value = "<html />"

    notification_service.send_password_changed_notification(
        user_id="u1",
        changed_at=datetime.now(timezone.utc),
    )

    call_kwargs = notification_service.email_service.send_email.call_args
    subject = call_kwargs[1].get("subject", "") if call_kwargs[1] else call_kwargs[0][1]
    assert BRAND_NAME in subject
