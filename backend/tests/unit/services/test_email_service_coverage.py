from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.exceptions import ServiceException
import app.services.email as email_module
from app.services.email import EmailService
from app.services.template_registry import TemplateRegistry

settings = email_module.settings


def _build_service(db, mock_cache, monkeypatch) -> EmailService:
    from app.services.base import BaseService

    BaseService._class_metrics.clear()
    monkeypatch.setattr(settings, "resend_api_key", "test-key", raising=False)
    return EmailService(db, mock_cache)


def test_email_service_allows_missing_api_key_in_test_mode(db, mock_cache, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None, raising=False)
    monkeypatch.setattr(settings, "is_testing", True, raising=False)
    service = EmailService(db, mock_cache)
    assert service.default_sender


def test_email_service_uses_noreply_fallback(db, mock_cache, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "from_email", None, raising=False)
    monkeypatch.setattr(settings, "email_from_address", None, raising=False)
    monkeypatch.setattr(settings, "email_from_name", None, raising=False)

    service = EmailService(db, mock_cache)

    assert service.default_from_address
    assert service.default_sender


def test_parse_sender_and_format_sender(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)

    name, address = service._parse_sender('Jane Doe <jane@example.com>')
    assert name == "Jane Doe"
    assert address == "jane@example.com"

    assert service._format_sender("Jane <jane@example.com>", None) == "Jane <jane@example.com>"
    assert service._format_sender("only@example.com", None).endswith("<only@example.com>")
    formatted = service._format_sender(None, None)
    assert service.default_from_address in formatted


def test_send_password_reset_email_handles_service_exception(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)

    with patch.object(service, "send_email", side_effect=ServiceException("boom")):
        assert service.send_password_reset_email("user@example.com", "https://reset") is False


def test_send_password_reset_email_handles_unexpected_exception(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)

    with patch("app.services.template_service.TemplateService.render_template", side_effect=Exception("boom")):
        assert service.send_password_reset_email("user@example.com", "https://reset") is False


def test_send_password_reset_confirmation_handles_unexpected_exception(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)

    with patch("app.services.template_service.TemplateService.render_template", side_effect=Exception("boom")):
        assert service.send_password_reset_confirmation("user@example.com") is False


def test_validate_email_config_missing_sender(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)
    service.default_sender = ""

    with pytest.raises(ServiceException, match="From email address not configured"):
        service.validate_email_config()


def test_send_referral_invite_uses_template(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)

    with patch("app.services.template_service.TemplateService.render_template", return_value="<p>ok</p>"):
        with patch.object(service, "send_email", return_value={"id": "email-1"}) as mock_send:
            response = service.send_referral_invite("user@example.com", "https://ref", "Alice")

    assert response == {"id": "email-1"}
    assert mock_send.call_args.kwargs["template"] == TemplateRegistry.REFERRALS_INVITE


def test_get_send_stats_default(db, mock_cache, monkeypatch):
    service = _build_service(db, mock_cache, monkeypatch)
    stats = service.get_send_stats()

    assert stats["emails_sent"] == 0
    assert stats["success_rate"] == 0.0
