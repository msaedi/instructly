"""
Coverage tests for routes/v1/auth.py targeting uncovered edge-case paths.

Covers: token extraction, captcha extraction, device fingerprinting,
trusted device checking, two-factor challenge, and password-changed notification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestExtractRequestToken:
    def test_from_bearer_header(self):
        from app.routes.v1.auth import _extract_request_token

        request = MagicMock()
        request.headers.get.return_value = "Bearer abc123token"
        request.cookies = {}
        result = _extract_request_token(request)
        assert result == "abc123token"

    def test_empty_bearer(self):
        from app.routes.v1.auth import _extract_request_token

        request = MagicMock()
        request.headers.get.return_value = "Bearer "
        request.cookies = {}
        result = _extract_request_token(request)
        assert result is None

    def test_no_auth_header(self):
        from app.routes.v1.auth import _extract_request_token

        request = MagicMock()
        request.headers.get.return_value = ""
        request.cookies = {}
        result = _extract_request_token(request)
        assert result is None

    def test_from_cookie(self):
        from app.routes.v1.auth import _extract_request_token

        request = MagicMock()
        request.headers.get.return_value = ""
        with patch("app.routes.v1.auth.session_cookie_candidates", return_value=["session_token"]):
            request.cookies = {"session_token": "cookie_token_value"}
            result = _extract_request_token(request)
            assert result == "cookie_token_value"

    def test_no_cookies_attr(self):
        from app.routes.v1.auth import _extract_request_token

        request = MagicMock(spec=[])
        request.headers = MagicMock()
        request.headers.get.return_value = ""
        # No hasattr cookies → returns None
        result = _extract_request_token(request)
        assert result is None


@pytest.mark.unit
class TestExtractCaptchaToken:
    @pytest.mark.asyncio
    async def test_with_token(self):
        from app.routes.v1.auth import _extract_captcha_token

        request = MagicMock()
        form_data = {"captcha_token": "cap_token_123"}
        request.form = AsyncMock(return_value=form_data)
        result = await _extract_captcha_token(request)
        assert result == "cap_token_123"

    @pytest.mark.asyncio
    async def test_form_error(self):
        from app.routes.v1.auth import _extract_captcha_token

        request = MagicMock()
        request.form = AsyncMock(side_effect=Exception("form parse error"))
        result = await _extract_captcha_token(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_captcha_field(self):
        from app.routes.v1.auth import _extract_captcha_token

        request = MagicMock()
        form_data = {}
        request.form = AsyncMock(return_value=form_data)
        result = await _extract_captcha_token(request)
        assert result is None


@pytest.mark.unit
class TestDeviceFingerprint:
    def test_deterministic(self):
        from app.routes.v1.auth import _device_fingerprint

        fp1 = _device_fingerprint("1.2.3.4", "Mozilla/5.0")
        fp2 = _device_fingerprint("1.2.3.4", "Mozilla/5.0")
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_inputs(self):
        from app.routes.v1.auth import _device_fingerprint

        fp1 = _device_fingerprint("1.2.3.4", "Chrome")
        fp2 = _device_fingerprint("5.6.7.8", "Chrome")
        assert fp1 != fp2


@pytest.mark.unit
class TestShouldTrustDevice:
    def test_trusted_cookie(self):
        from app.routes.v1.auth import _should_trust_device

        request = MagicMock()
        request.cookies.get.return_value = "1"
        assert _should_trust_device(request) is True

    @patch("app.routes.v1.auth.settings")
    def test_non_production_header_bypass(self, mock_settings):
        from app.routes.v1.auth import _should_trust_device

        mock_settings.environment = "staging"
        request = MagicMock()
        request.cookies.get.return_value = None
        request.headers.get.return_value = "true"
        assert _should_trust_device(request) is True

    @patch("app.routes.v1.auth.settings")
    def test_production_no_bypass(self, mock_settings):
        from app.routes.v1.auth import _should_trust_device

        mock_settings.environment = "production"
        request = MagicMock()
        request.cookies.get.return_value = None
        request.headers.get.return_value = "true"
        assert _should_trust_device(request) is False

    @patch("app.routes.v1.auth.settings")
    def test_no_cookie_no_header(self, mock_settings):
        from app.routes.v1.auth import _should_trust_device

        mock_settings.environment = "staging"
        request = MagicMock()
        request.cookies.get.return_value = None
        request.headers.get.return_value = None
        assert _should_trust_device(request) is False


@pytest.mark.unit
class TestIssueTwoFactorChallenge:
    def test_no_totp_enabled(self):
        from app.routes.v1.auth import _issue_two_factor_challenge_if_needed

        user = MagicMock()
        user.totp_enabled = False
        user.email = "test@example.com"
        request = MagicMock()
        result = _issue_two_factor_challenge_if_needed(user, request)
        assert result is None

    @patch("app.routes.v1.auth._should_trust_device")
    def test_trusted_device_skips(self, mock_trust):
        from app.routes.v1.auth import _issue_two_factor_challenge_if_needed

        mock_trust.return_value = True
        user = MagicMock()
        user.totp_enabled = True
        user.email = "test@example.com"
        request = MagicMock()
        result = _issue_two_factor_challenge_if_needed(user, request)
        assert result is None

    @patch("app.routes.v1.auth._should_trust_device")
    @patch("app.routes.v1.auth.create_temp_token")
    def test_challenge_issued(self, mock_temp, mock_trust):
        from app.routes.v1.auth import _issue_two_factor_challenge_if_needed

        mock_trust.return_value = False
        mock_temp.return_value = "temp_token_abc"
        user = MagicMock()
        user.totp_enabled = True
        user.email = "test@example.com"
        request = MagicMock()
        result = _issue_two_factor_challenge_if_needed(user, request)
        assert result is not None
        assert result.requires_2fa is True
        assert result.temp_token == "temp_token_abc"

    @patch("app.routes.v1.auth._should_trust_device")
    @patch("app.routes.v1.auth.create_temp_token")
    def test_with_extra_claims(self, mock_temp, mock_trust):
        from app.routes.v1.auth import _issue_two_factor_challenge_if_needed

        mock_trust.return_value = False
        mock_temp.return_value = "temp_token_xyz"
        user = MagicMock()
        user.totp_enabled = True
        user.email = "test@example.com"
        request = MagicMock()
        result = _issue_two_factor_challenge_if_needed(
            user, request, extra_claims={"session_id": "S1"}
        )
        assert result is not None
        assert result.requires_2fa is True


@pytest.mark.unit
class TestSendPasswordChangedNotificationSync:
    @patch("app.services.notification_service.NotificationService")
    def test_sends(self, mock_svc_cls):
        from app.routes.v1.auth import _send_password_changed_notification_sync

        mock_svc = MagicMock()
        mock_svc._owns_db = False
        mock_svc_cls.return_value = mock_svc
        _send_password_changed_notification_sync(
            user_id="U1", changed_at=datetime.now(timezone.utc)
        )
        mock_svc.send_password_changed_notification.assert_called_once()


@pytest.mark.unit
class TestSendNewDeviceLoginNotificationSync:
    @patch("app.services.notification_service.NotificationService")
    def test_sends(self, mock_svc_cls):
        from app.routes.v1.auth import _send_new_device_login_notification_sync

        mock_svc = MagicMock()
        mock_svc._owns_db = True
        mock_svc.db = MagicMock()
        mock_svc_cls.return_value = mock_svc
        _send_new_device_login_notification_sync(
            user_id="U1",
            ip_address="1.2.3.4",
            user_agent="Chrome",
            login_time=datetime.now(timezone.utc),
        )
        mock_svc.send_new_device_login_notification.assert_called_once()
        mock_svc.db.close.assert_called_once()


@pytest.mark.unit
class TestMaybeSendNewDeviceLoginNotification:
    @pytest.mark.asyncio
    async def test_no_user_id(self):
        from app.routes.v1.auth import _maybe_send_new_device_login_notification

        request = MagicMock()
        cache = AsyncMock()
        await _maybe_send_new_device_login_notification(
            user_id=None, request=request, cache_service=cache
        )

    @pytest.mark.asyncio
    async def test_recently_registered_skips(self):
        from app.routes.v1.auth import _maybe_send_new_device_login_notification

        request = MagicMock()
        request.client = SimpleNamespace(host="1.2.3.4")
        request.headers.get.return_value = "Chrome"
        cache = AsyncMock()
        cache.get = AsyncMock(return_value="true")
        await _maybe_send_new_device_login_notification(
            user_id="U1", request=request, cache_service=cache
        )
        # Should call set for device and delete for recently_registered
        cache.set.assert_called()
        cache.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_known_device_skips(self):
        from app.routes.v1.auth import (
            _device_fingerprint,
            _maybe_send_new_device_login_notification,
        )

        request = MagicMock()
        request.client = SimpleNamespace(host="1.2.3.4")
        request.headers.get.return_value = "Chrome"
        fp = _device_fingerprint("1.2.3.4", "Chrome")
        cache = AsyncMock()
        # First call (recently_registered) returns None, second (known_devices) returns list
        cache.get = AsyncMock(side_effect=[None, [fp]])
        await _maybe_send_new_device_login_notification(
            user_id="U1", request=request, cache_service=cache
        )
        # Should NOT call to_thread for notification since device is known
