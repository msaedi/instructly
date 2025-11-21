# backend/tests/unit/services/test_email_service.py
"""
Unit tests for the refactored EmailService.

Tests the EmailService extends BaseService properly and uses dependency injection.
"""

import copy
import json
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.exceptions import ServiceException
from app.services.email import EmailService
from app.services.template_registry import TemplateRegistry


class TestEmailService:
    """Test the refactored EmailService."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        """Reset BaseService metrics before each test."""
        from app.services.base import BaseService

        BaseService._class_metrics.clear()
        yield

    @pytest.fixture(autouse=True)
    def reset_sender_profiles(self, monkeypatch):
        original_profiles = copy.deepcopy(getattr(settings, "_sender_profiles", {}))
        original_warning_flag = getattr(settings, "_sender_profiles_warning_logged", False)

        monkeypatch.setattr(settings, "email_sender_profiles_file", None, raising=False)
        monkeypatch.setattr(settings, "email_sender_profiles_json", None, raising=False)
        monkeypatch.setattr(settings, "_sender_profiles_warning_logged", False, raising=False)

        settings._sender_profiles = {}  # type: ignore[attr-defined]
        settings.refresh_sender_profiles("")

        yield

        settings._sender_profiles = original_profiles  # type: ignore[attr-defined]
        settings._sender_profiles_warning_logged = original_warning_flag  # type: ignore[attr-defined]
        settings.refresh_sender_profiles()

    def test_email_service_extends_base_service(self, db, mock_cache):
        """Test that EmailService properly extends BaseService."""
        service = EmailService(db, mock_cache)

        # Should have BaseService methods
        assert hasattr(service, "transaction")
        assert hasattr(service, "measure_operation")
        assert hasattr(service, "get_metrics")
        assert hasattr(service, "log_operation")

    def test_email_service_initialization(self, db, mock_cache):
        """Test EmailService initialization with dependencies."""
        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            assert service.db == db
            assert service.cache == mock_cache
            assert isinstance(service.default_sender, str)
            assert service.default_sender
            assert isinstance(service.default_from_name, str)
            assert service.default_from_name

    def test_email_service_no_api_key_raises_exception(self, db, mock_cache, monkeypatch):
        """Test that missing API key raises ServiceException."""
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        with patch("app.core.config.settings.resend_api_key", None):
            with pytest.raises(ServiceException, match="Resend API key not configured"):
                EmailService(db, mock_cache)

    @patch("resend.Emails.send")
    def test_send_email_success(self, mock_resend_send, db, mock_cache):
        """Test successful email sending."""
        # Mock Resend response
        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            result = service.send_email(
                to_email="test@example.com", subject="Test Subject", html_content="<p>Test content</p>"
            )

            assert result["id"] == "test-email-id"
            assert result["status"] == "sent"
            mock_resend_send.assert_called_once()

    @patch("resend.Emails.send")
    def test_send_email_failure(self, mock_resend_send, db, mock_cache):
        """Test email sending failure."""
        # Mock Resend failure
        mock_resend_send.side_effect = Exception("API Error")

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            with pytest.raises(ServiceException, match="Email sending failed"):
                service.send_email(
                    to_email="test@example.com", subject="Test Subject", html_content="<p>Test content</p>"
                )

    @patch("resend.Emails.send")
    def test_sends_with_sender_profile(self, mock_resend_send, db, mock_cache, monkeypatch):
        """EmailService should apply sender headers from an explicit profile key."""

        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        monkeypatch.setattr(settings, "email_from_name", "Default Name", raising=False)
        monkeypatch.setattr(settings, "email_from_address", "default@example.com", raising=False)
        monkeypatch.setattr(settings, "email_reply_to", "reply-default@example.com", raising=False)
        self._apply_sender_profiles(
            monkeypatch,
            {
                "trust": {
                    "from_name": "iNSTAiNSTRU Trust & Safety",
                    "from": "notifications@instainstru.com",
                    "reply_to": "support@instainstru.com",
                }
            },
        )

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)
            service.send_email(
                to_email="test@example.com",
                subject="Subject",
                html_content="<p>body</p>",
                sender_key="trust",
            )

        mock_resend_send.assert_called_once()
        email_payload = mock_resend_send.call_args[0][0]
        assert (
            email_payload["from"]
            == "iNSTAiNSTRU Trust & Safety <notifications@instainstru.com>"
        )
        assert email_payload["reply_to"] == "support@instainstru.com"

    @patch("resend.Emails.send")
    def test_template_default_sender(self, mock_resend_send, db, mock_cache, monkeypatch):
        """Template defaults should determine the sender profile when none is provided."""

        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        monkeypatch.setattr(settings, "email_from_name", "Default Name", raising=False)
        monkeypatch.setattr(settings, "email_from_address", "default@example.com", raising=False)
        monkeypatch.setattr(settings, "email_reply_to", "reply-default@example.com", raising=False)
        self._apply_sender_profiles(
            monkeypatch,
            {
                "trust": {
                    "from_name": "iNSTAiNSTRU Trust",
                    "from": "trust@example.com",
                    "reply_to": "trust-support@example.com",
                }
            },
        )

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)
            service.send_email(
                to_email="test@example.com",
                subject="Subject",
                html_content="<p>body</p>",
                template=TemplateRegistry.BGC_REVIEW_STATUS,
            )

        mock_resend_send.assert_called_once()
        email_payload = mock_resend_send.call_args[0][0]
        assert email_payload["from"] == "iNSTAiNSTRU Trust <trust@example.com>"
        assert email_payload["reply_to"] == "trust-support@example.com"

    @patch("resend.Emails.send")
    def test_template_default_sender_bookings(self, mock_resend_send, db, mock_cache, monkeypatch):
        """Bookings templates should resolve to the bookings sender profile by default."""

        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        monkeypatch.setattr(settings, "email_from_name", "Default Name", raising=False)
        monkeypatch.setattr(settings, "email_from_address", "default@example.com", raising=False)
        monkeypatch.setattr(settings, "email_reply_to", "reply-default@example.com", raising=False)
        self._apply_sender_profiles(
            monkeypatch,
            {
                "bookings": {
                    "from_name": "iNSTAiNSTRU Bookings",
                    "from": "bookings@instainstru.com",
                    "reply_to": "support@instainstru.com",
                }
            },
        )

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)
            service.send_email(
                to_email="student@example.com",
                subject="Subject",
                html_content="<p>body</p>",
                template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
            )

        mock_resend_send.assert_called_once()
        email_payload = mock_resend_send.call_args[0][0]
        assert email_payload["from"] == "iNSTAiNSTRU Bookings <bookings@instainstru.com>"
        assert email_payload["reply_to"] == "support@instainstru.com"

    @patch("resend.Emails.send")
    def test_template_default_sender_account(self, mock_resend_send, db, mock_cache, monkeypatch):
        """Account/auth templates should resolve to the account sender profile."""

        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        monkeypatch.setattr(settings, "email_from_name", "Default Name", raising=False)
        monkeypatch.setattr(settings, "email_from_address", "default@example.com", raising=False)
        monkeypatch.setattr(settings, "email_reply_to", "reply-default@example.com", raising=False)
        self._apply_sender_profiles(
            monkeypatch,
            {
                "account": {
                    "from_name": "iNSTAiNSTRU",
                    "from": "hello@instainstru.com",
                    "reply_to": "support@instainstru.com",
                }
            },
        )

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)
            service.send_email(
                to_email="user@example.com",
                subject="Subject",
                html_content="<p>body</p>",
                template=TemplateRegistry.AUTH_PASSWORD_RESET,
            )

        mock_resend_send.assert_called_once()
        email_payload = mock_resend_send.call_args[0][0]
        assert email_payload["from"] == "iNSTAiNSTRU <hello@instainstru.com>"
        assert email_payload.get("reply_to") == "support@instainstru.com"

    @patch("resend.Emails.send")
    def test_send_password_reset_email(self, mock_resend_send, db, mock_cache):
        """Test password reset email sending."""
        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            result = service.send_password_reset_email(
                to_email="test@example.com", reset_url="https://example.com/reset?token=abc123", user_name="Test User"
            )

            assert result is True
            mock_resend_send.assert_called_once()

            # Check email content
            call_args = mock_resend_send.call_args[0][0]
            assert "test@example.com" in call_args["to"]
            assert "Reset Your" in call_args["subject"]
            assert "Test User" in call_args["html"]
            assert "abc123" in call_args["html"]

    def test_validate_email_config_success(self, db, mock_cache):
        """Test email configuration validation success."""
        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            result = service.validate_email_config()
            assert result is True

    def test_validate_email_config_no_api_key(self, db, mock_cache):
        """Test email configuration validation with missing API key."""
        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

        # Remove API key after initialization
        with patch("app.core.config.settings.resend_api_key", None):
            with pytest.raises(ServiceException, match="Resend API key not configured"):
                service.validate_email_config()

    def test_get_send_stats(self, db, mock_cache):
        """Test getting email send statistics."""
        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            # Simulate some metrics
            service._record_metric("send_email", 0.5, True)
            service._record_metric("send_email", 0.3, True)
            service._record_metric("send_email", 0.4, False)

            stats = service.get_send_stats()

            assert stats["emails_sent"] == 2
            assert stats["emails_failed"] == 1
            assert stats["success_rate"] == 2 / 3
            assert stats["avg_send_time"] > 0

    def test_metrics_decorator_applied(self, db, mock_cache):
        """Test that measure_operation decorator is applied to methods."""
        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            # Check that methods have the decorator marker
            assert hasattr(service.send_email, "_is_measured")
            assert hasattr(service.send_password_reset_email, "_is_measured")
            assert hasattr(service.send_password_reset_confirmation, "_is_measured")
            assert hasattr(service.validate_email_config, "_is_measured")

    @patch("resend.Emails.send")
    def test_email_with_custom_from(self, mock_resend_send, db, mock_cache):
        """Test sending email with custom from address."""
        mock_resend_send.return_value = {"id": "test-email-id", "status": "sent"}

        with patch("app.core.config.settings.resend_api_key", "test-api-key"):
            service = EmailService(db, mock_cache)

            service.send_email(
                to_email="test@example.com",
                subject="Test",
                html_content="<p>Test</p>",
                from_email="custom@example.com",
                from_name="Custom Sender",
            )

            call_args = mock_resend_send.call_args[0][0]
            assert call_args["from"] == "Custom Sender <custom@example.com>"
    @staticmethod
    def _apply_sender_profiles(_monkeypatch: pytest.MonkeyPatch, payload: dict[str, dict[str, str]]) -> None:
        settings.refresh_sender_profiles(json.dumps(payload))
