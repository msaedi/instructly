from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from app.services.email_subjects import EmailSubject
from app.services.template_registry import TemplateRegistry


class DummyUserRepository:
    def __init__(self, user):
        self.user = user

    def get_by_id(self, _user_id):
        return self.user


def test_account_paused_email_uses_template_and_is_not_preference_gated(
    notification_service_with_mocked_email,
):
    service = notification_service_with_mocked_email
    service.user_repository = DummyUserRepository(
        SimpleNamespace(id="user-1", email="alex@example.com", first_name="Alex")
    )
    service._should_send_email = Mock(side_effect=AssertionError("preference gate should not run"))

    assert service.send_account_paused_confirmation("user-1") is True

    service.email_service.send_email.assert_called_once()
    call = service.email_service.send_email.call_args.kwargs
    assert call["to_email"] == "alex@example.com"
    assert call["subject"] == EmailSubject.account_paused()
    assert call["template"] == TemplateRegistry.ACCOUNT_PAUSED
    assert "Your iNSTAiNSTRU instructor account is now paused" in call["html_content"]


def test_account_resumed_email_uses_template(notification_service_with_mocked_email):
    service = notification_service_with_mocked_email
    service.user_repository = DummyUserRepository(
        SimpleNamespace(id="user-1", email="alex@example.com", first_name="Alex")
    )

    assert service.send_account_resumed_confirmation("user-1") is True

    service.email_service.send_email.assert_called_once()
    call = service.email_service.send_email.call_args.kwargs
    assert call["to_email"] == "alex@example.com"
    assert call["subject"] == EmailSubject.account_resumed()
    assert call["template"] == TemplateRegistry.ACCOUNT_RESUMED
    assert "active again" in call["html_content"]


def test_account_deleted_email_uses_captured_recipient(notification_service_with_mocked_email):
    service = notification_service_with_mocked_email

    assert (
        service.send_account_deleted_confirmation(
            to_email="alex@example.com",
            first_name="Alex",
        )
        is True
    )

    service.email_service.send_email.assert_called_once()
    call = service.email_service.send_email.call_args.kwargs
    assert call["to_email"] == "alex@example.com"
    assert call["subject"] == EmailSubject.account_deleted()
    assert call["template"] == TemplateRegistry.ACCOUNT_DELETED
    assert "support@instainstru.com" in call["html_content"]


def test_account_anonymized_email_uses_captured_recipient(notification_service_with_mocked_email):
    service = notification_service_with_mocked_email

    assert (
        service.send_account_anonymized_confirmation(
            to_email="alex@example.com",
            first_name="Alex",
        )
        is True
    )

    service.email_service.send_email.assert_called_once()
    call = service.email_service.send_email.call_args.kwargs
    assert call["to_email"] == "alex@example.com"
    assert call["subject"] == EmailSubject.account_anonymized()
    assert call["template"] == TemplateRegistry.ACCOUNT_ANONYMIZED
    assert "no longer be identifiable" in call["html_content"]
    assert "support@instainstru.com" in call["html_content"]


def test_account_deactivated_email_uses_template(notification_service_with_mocked_email):
    service = notification_service_with_mocked_email
    service.user_repository = DummyUserRepository(
        SimpleNamespace(id="user-1", email="alex@example.com", first_name="Alex")
    )
    service._should_send_email = Mock(side_effect=AssertionError("preference gate should not run"))

    assert service.send_account_deactivated_confirmation("user-1") is True

    service.email_service.send_email.assert_called_once()
    call = service.email_service.send_email.call_args.kwargs
    assert call["to_email"] == "alex@example.com"
    assert call["subject"] == EmailSubject.account_deactivated()
    assert call["template"] == TemplateRegistry.ACCOUNT_DEACTIVATED
    assert "not reversible from within the product" in call["html_content"]
