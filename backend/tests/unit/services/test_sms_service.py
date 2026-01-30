"""Tests for SMSService."""

from unittest.mock import AsyncMock, Mock

import pytest
from twilio.base.exceptions import TwilioRestException

from app.core.config import settings
from app.services.sms_service import SMSService, SMSStatus


def _enable_sms_settings(monkeypatch, *, from_number="+15551234567", messaging_service_sid=None):
    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "sid")
    monkeypatch.setattr(settings, "twilio_auth_token", Mock(get_secret_value=lambda: "token"))
    monkeypatch.setattr(settings, "twilio_phone_number", from_number)
    monkeypatch.setattr(settings, "twilio_messaging_service_sid", messaging_service_sid)


class FakeCache:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.set_calls: list[tuple[str, int]] = []

    async def get(self, key: str):
        return self.value

    async def set(self, key: str, value: int, ttl: int | None = None):
        self.set_calls.append((key, value))
        return True


class FakeUser:
    def __init__(self, phone: str | None, verified: bool) -> None:
        self.phone = phone
        self.phone_verified = verified


class FakeUserRepo:
    def __init__(self, user: FakeUser | None) -> None:
        self.user = user

    def get_by_id(self, user_id: str):
        return self.user


@pytest.mark.asyncio
async def test_send_sms_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "sms_enabled", False)
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_phone_number", None)

    service = SMSService()
    result = await service.send_sms("+15551234567", "Test message")

    assert result is None


@pytest.mark.asyncio
async def test_send_sms_success(monkeypatch):
    class FakeMessage:
        sid = "test-sid"
        status = "queued"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = Mock()
            self.messages.create = Mock(return_value=FakeMessage())

    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "sid")
    monkeypatch.setattr(settings, "twilio_auth_token", Mock(get_secret_value=lambda: "token"))
    monkeypatch.setattr(settings, "twilio_phone_number", "+15551234567")
    monkeypatch.setattr("app.services.sms_service.Client", FakeClient)

    service = SMSService()
    result = await service.send_sms("+15551234567", "Hello")

    assert result is not None
    assert result["sid"] == "test-sid"


@pytest.mark.asyncio
async def test_send_to_user_respects_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "sid")
    monkeypatch.setattr(settings, "twilio_auth_token", Mock(get_secret_value=lambda: "token"))
    monkeypatch.setattr(settings, "twilio_phone_number", "+15551234567")
    monkeypatch.setattr(settings, "sms_daily_limit_per_user", 1)

    cache = FakeCache(value="1")
    service = SMSService(cache)
    service.send_sms = AsyncMock()

    repo = FakeUserRepo(FakeUser(phone="+15551234567", verified=True))
    result = await service.send_to_user("user_1", "Hello", user_repository=repo)

    assert result is None
    service.send_sms.assert_not_called()


@pytest.mark.asyncio
async def test_send_sms_with_status_missing_number(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = Mock()
            self.messages.create = Mock()

    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", FakeClient)

    service = SMSService()
    result, status = await service.send_sms_with_status("", "Hello")

    assert result is None
    assert status is SMSStatus.ERROR


@pytest.mark.asyncio
async def test_send_sms_with_status_returns_error_on_send_failure(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = Mock()
            self.messages.create = Mock()

    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", FakeClient)

    service = SMSService()
    service._send_sms_sync = Mock(return_value=None)

    result, status = await service.send_sms_with_status("+15551234567", "Hello")

    assert result is None
    assert status is SMSStatus.ERROR


@pytest.mark.asyncio
async def test_send_to_user_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "sms_enabled", False)
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_phone_number", None)

    service = SMSService()
    result = await service.send_to_user("user-1", "Hello", user_repository=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_send_to_user_missing_user(monkeypatch):
    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", Mock())

    repo = Mock()
    repo.get_by_id.return_value = None

    service = SMSService()
    result = await service.send_to_user("user-1", "Hello", user_repository=repo)

    assert result is None


@pytest.mark.asyncio
async def test_send_to_user_missing_phone(monkeypatch):
    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", Mock())

    repo = Mock()
    repo.get_by_id.return_value = FakeUser(phone=None, verified=True)

    service = SMSService()
    result = await service.send_to_user("user-1", "Hello", user_repository=repo)

    assert result is None


@pytest.mark.asyncio
async def test_send_to_user_calls_send_sms(monkeypatch):
    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", Mock())

    repo = Mock()
    repo.get_by_id.return_value = FakeUser(phone="+15551234567", verified=True)

    service = SMSService()
    service._check_and_increment_rate_limit = AsyncMock(return_value=True)
    service.send_sms = AsyncMock(return_value={"sid": "sid-1"})

    result = await service.send_to_user("user-1", "Hello", user_repository=repo)

    assert result == {"sid": "sid-1"}
    service.send_sms.assert_called_once_with("+15551234567", "Hello")


def test_send_sms_sync_no_client(monkeypatch):
    monkeypatch.setattr(settings, "sms_enabled", False)
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_phone_number", None)

    service = SMSService()

    assert service._send_sms_sync("+15551234567", "Hi") is None


def test_send_sms_sync_uses_from_number(monkeypatch):
    payload = {}

    class FakeMessage:
        sid = "sid-1"
        status = "queued"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = Mock()

            def _create(**kwargs):
                payload.update(kwargs)
                return FakeMessage()

            self.messages.create = Mock(side_effect=_create)

    _enable_sms_settings(monkeypatch, from_number="+15551234567", messaging_service_sid=None)
    monkeypatch.setattr("app.services.sms_service.Client", FakeClient)

    service = SMSService()
    result = service._send_sms_sync("+15551234567", "Hi")

    assert result is not None
    assert payload.get("from_") == "+15551234567"
    assert "messaging_service_sid" not in payload


def test_send_sms_sync_twilio_error(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = Mock()
            self.messages.create = Mock(
                side_effect=TwilioRestException(400, "uri", "error")
            )

    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", FakeClient)

    service = SMSService()

    assert service._send_sms_sync("+15551234567", "Hi") is None


@pytest.mark.asyncio
async def test_rate_limit_redis_unavailable(monkeypatch):
    _enable_sms_settings(monkeypatch)
    monkeypatch.setattr("app.services.sms_service.Client", Mock())

    cache_service = Mock()
    cache_service.get_redis_client = AsyncMock(return_value=None)

    service = SMSService(cache_service=cache_service)

    assert await service._check_and_increment_rate_limit("user-1") is False
