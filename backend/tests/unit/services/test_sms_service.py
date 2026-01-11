"""Tests for SMSService."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.services.sms_service import SMSService


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
