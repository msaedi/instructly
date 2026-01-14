from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.services.sms_service import SMSService, SMSStatus


def _build_service(monkeypatch, *, enabled: bool, cache_service=None) -> SMSService:
    monkeypatch.setattr(settings, "sms_enabled", enabled, raising=False)
    monkeypatch.setattr(settings, "twilio_account_sid", "sid" if enabled else None, raising=False)
    monkeypatch.setattr(
        settings,
        "twilio_auth_token",
        SecretStr("token") if enabled else None,
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "twilio_phone_number",
        "+15555551234" if enabled else None,
        raising=False,
    )
    monkeypatch.setattr(settings, "twilio_messaging_service_sid", None, raising=False)

    with patch("app.services.sms_service.Client", Mock()):
        return SMSService(cache_service=cache_service)


@pytest.mark.asyncio
async def test_send_sms_disabled(monkeypatch):
    service = _build_service(monkeypatch, enabled=False)

    result, status = await service.send_sms_with_status("+15555551234", "hi")
    assert result is None
    assert status is SMSStatus.DISABLED


@pytest.mark.asyncio
async def test_send_sms_invalid_number(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)

    result, status = await service.send_sms_with_status("5551234", "hi")
    assert result is None
    assert status is SMSStatus.ERROR


@pytest.mark.asyncio
async def test_send_sms_truncates_long_message(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    captured = {}

    def _capture(_to: str, msg: str):
        captured["msg"] = msg
        return {"sid": "sm-1"}

    service._send_sms_sync = _capture  # type: ignore[assignment]

    long_message = "x" * 2000
    result, status = await service.send_sms_with_status("+15555551234", long_message)

    assert status is SMSStatus.SUCCESS
    assert result["sid"] == "sm-1"
    assert len(captured["msg"]) == 1600
    assert captured["msg"].endswith("...")


@pytest.mark.asyncio
async def test_send_sms_segments_logged(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    service._send_sms_sync = Mock(return_value={"sid": "sm-2"})  # type: ignore[assignment]

    result, status = await service.send_sms_with_status("+15555551234", "x" * 200)
    assert status is SMSStatus.SUCCESS
    assert result["sid"] == "sm-2"


def test_count_sms_segments_ascii_and_unicode():
    assert SMSService._count_sms_segments("") == 1
    assert SMSService._count_sms_segments("x" * 160) == 1
    assert SMSService._count_sms_segments("x" * 161) == 2
    assert SMSService._count_sms_segments("\u0100" * 70) == 1
    assert SMSService._count_sms_segments("\u0100" * 71) == 2


@pytest.mark.asyncio
async def test_send_to_user_missing_repo(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    result = await service.send_to_user("user-1", "hi", user_repository=None)
    assert result is None


@pytest.mark.asyncio
async def test_send_to_user_unverified_or_no_phone(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    repo = Mock()
    repo.get_by_id.return_value = SimpleNamespace(phone_verified=False, phone=None)

    result = await service.send_to_user("user-1", "hi", user_repository=repo)
    assert result is None


@pytest.mark.asyncio
async def test_send_to_user_rate_limited(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    repo = Mock()
    repo.get_by_id.return_value = SimpleNamespace(phone_verified=True, phone="+15555551234")

    with patch.object(service, "_check_and_increment_rate_limit", AsyncMock(return_value=False)):
        result = await service.send_to_user("user-1", "hi", user_repository=repo)

    assert result is None


@pytest.mark.asyncio
async def test_rate_limit_no_cache(monkeypatch):
    service = _build_service(monkeypatch, enabled=True, cache_service=None)
    assert await service._check_and_increment_rate_limit("user-1") is True


@pytest.mark.asyncio
async def test_rate_limit_over_daily_limit(monkeypatch):
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock(return_value=2)
    redis_client.decr = AsyncMock()
    redis_client.expire = AsyncMock()

    cache_service = Mock()
    cache_service.get_redis_client = AsyncMock(return_value=redis_client)

    service = _build_service(monkeypatch, enabled=True, cache_service=cache_service)
    service.daily_limit = 1

    assert await service._check_and_increment_rate_limit("user-1") is False
    redis_client.decr.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_first_hit_sets_expiry(monkeypatch):
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock(return_value=1)
    redis_client.expire = AsyncMock()

    cache_service = Mock()
    cache_service.get_redis_client = AsyncMock(return_value=redis_client)

    service = _build_service(monkeypatch, enabled=True, cache_service=cache_service)

    assert await service._check_and_increment_rate_limit("user-1") is True
    redis_client.expire.assert_called_once()


def test_send_sms_sync_missing_sender(monkeypatch):
    service = _build_service(monkeypatch, enabled=True)
    service.messaging_service_sid = None
    service.from_number = None

    assert service._send_sms_sync("+15555551234", "hi") is None
