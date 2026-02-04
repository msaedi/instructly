from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.principal import UserPrincipal
from app.routes.v1.admin.mcp import communications as communications_module
from app.schemas.admin_communications import (
    AnnouncementExecuteRequest,
    AnnouncementPreviewRequest,
    BulkNotificationExecuteRequest,
    BulkNotificationPreviewRequest,
    BulkTarget,
    CommunicationChannel,
    EmailPreviewRequest,
)


async def _direct_to_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


class _ErrorWithHttp(Exception):
    def __init__(self, status_code: int, detail: str):
        self._status_code = status_code
        self._detail = detail

    def to_http_exception(self):
        return HTTPException(status_code=self._status_code, detail=self._detail)


def _principal() -> UserPrincipal:
    return UserPrincipal(user_id="admin", email="admin@example.com")


def test_handle_exception_branches():
    with pytest.raises(HTTPException) as exc:
        communications_module._handle_exception(
            HTTPException(status_code=400, detail="bad"), "detail"
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        communications_module._handle_exception(_ErrorWithHttp(418, "teapot"), "detail")
    assert exc.value.status_code == 418

    with pytest.raises(HTTPException) as exc:
        communications_module._handle_exception(RuntimeError("boom"), "detail")
    assert exc.value.detail == "detail"


@pytest.mark.asyncio
async def test_announcement_preview_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_announcement=lambda **_kwargs: {"ok": True})
    request = AnnouncementPreviewRequest(
        audience="all_users",
        channels=[CommunicationChannel.EMAIL],
        title="Hello",
        body="Body",
        subject="Subject",
        schedule_at=None,
        high_priority=False,
    )
    result = await communications_module.announcement_preview(
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_announcement_preview_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(preview_announcement=_boom)
    request = AnnouncementPreviewRequest(
        audience="all_users",
        channels=[CommunicationChannel.EMAIL],
        title="Hello",
        body="Body",
    )
    with pytest.raises(HTTPException):
        await communications_module.announcement_preview(
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_announcement_execute_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(execute_announcement=lambda **_kwargs: {"ok": True})
    request = AnnouncementExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await communications_module.announcement_execute(
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_announcement_execute_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=409, detail="conflict")

    service = SimpleNamespace(execute_announcement=_boom)
    request = AnnouncementExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await communications_module.announcement_execute(
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_bulk_preview_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_bulk_notification=lambda **_kwargs: {"ok": True})
    request = BulkNotificationPreviewRequest(
        target=BulkTarget(user_type="student"),
        channels=[CommunicationChannel.IN_APP],
        title="Hello",
        body="Body",
        subject=None,
        variables={},
        schedule_at=None,
    )
    result = await communications_module.bulk_preview(
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_bulk_preview_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=422, detail="bad")

    service = SimpleNamespace(preview_bulk_notification=_boom)
    request = BulkNotificationPreviewRequest(
        target=BulkTarget(user_type="student"),
        channels=[CommunicationChannel.IN_APP],
        title="Hello",
        body="Body",
    )
    with pytest.raises(HTTPException):
        await communications_module.bulk_preview(
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_bulk_execute_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(execute_bulk_notification=lambda **_kwargs: {"ok": True})
    request = BulkNotificationExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await communications_module.bulk_execute(
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_bulk_execute_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=409, detail="conflict")

    service = SimpleNamespace(execute_bulk_notification=_boom)
    request = BulkNotificationExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await communications_module.bulk_execute(
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_history_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(notification_history=lambda **_kwargs: {"ok": True})
    result = await communications_module.communication_history(
        kind="announcement",
        channel=None,
        status=None,
        start_date=datetime.now(timezone.utc),
        end_date=None,
        creator_id=None,
        limit=25,
        _=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_history_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=500, detail="bad")

    service = SimpleNamespace(notification_history=_boom)
    with pytest.raises(HTTPException):
        await communications_module.communication_history(
            kind=None,
            channel=None,
            status=None,
            start_date=None,
            end_date=None,
            creator_id=None,
            limit=100,
            _=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_templates_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(notification_templates=lambda **_kwargs: {"ok": True})
    result = await communications_module.communication_templates(
        _=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_templates_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=500, detail="bad")

    service = SimpleNamespace(notification_templates=_boom)
    with pytest.raises(HTTPException):
        await communications_module.communication_templates(
            _=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_email_preview_route_success(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(email_preview=lambda **_kwargs: {"ok": True})
    request = EmailPreviewRequest(
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com"},
        subject="Preview",
        test_send_to=None,
    )
    result = await communications_module.communication_email_preview(
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_email_preview_route_error(monkeypatch):
    monkeypatch.setattr(communications_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(email_preview=_boom)
    request = EmailPreviewRequest(
        template="email/auth/password_reset.html",
        variables={},
        subject=None,
        test_send_to=None,
    )
    with pytest.raises(HTTPException):
        await communications_module.communication_email_preview(
            request=request,
            principal=_principal(),
            service=service,
        )
