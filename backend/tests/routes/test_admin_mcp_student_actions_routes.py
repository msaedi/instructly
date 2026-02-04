from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.principal import UserPrincipal
from app.routes.v1.admin.mcp import student_actions as student_actions_module
from app.schemas.admin_student_actions import (
    CreditAdjustAction,
    CreditAdjustExecuteRequest,
    CreditAdjustPreviewRequest,
    CreditAdjustReasonCode,
    StudentSuspendExecuteRequest,
    StudentSuspendPreviewRequest,
    StudentSuspendReasonCode,
    StudentUnsuspendRequest,
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
        student_actions_module._handle_exception(
            HTTPException(status_code=400, detail="bad"), "detail"
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        student_actions_module._handle_exception(_ErrorWithHttp(418, "teapot"), "detail")
    assert exc.value.status_code == 418

    with pytest.raises(HTTPException) as exc:
        student_actions_module._handle_exception(RuntimeError("boom"), "detail")
    assert exc.value.detail == "detail"


@pytest.mark.asyncio
async def test_suspend_preview_route_success(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_suspend=lambda **_kwargs: {"ok": True})
    request = StudentSuspendPreviewRequest(
        reason_code=StudentSuspendReasonCode.FRAUD,
        note="note",
        notify_student=False,
        cancel_pending_bookings=False,
        forfeit_credits=True,
    )
    result = await student_actions_module.suspend_preview(
        student_id="01STU",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_suspend_preview_route_error(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(preview_suspend=_boom)
    request = StudentSuspendPreviewRequest(
        reason_code=StudentSuspendReasonCode.FRAUD,
        note="note",
    )
    with pytest.raises(HTTPException):
        await student_actions_module.suspend_preview(
            student_id="01STU",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_suspend_execute_route_success():
    async def _exec(**_kwargs):
        return {"ok": True}

    service = SimpleNamespace(execute_suspend=_exec)
    request = StudentSuspendExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await student_actions_module.suspend_execute(
        student_id="01STU",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_suspend_execute_route_error():
    async def _boom(**_kwargs):
        raise HTTPException(status_code=409, detail="conflict")

    service = SimpleNamespace(execute_suspend=_boom)
    request = StudentSuspendExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await student_actions_module.suspend_execute(
            student_id="01STU",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_unsuspend_route_success(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(unsuspend=lambda **_kwargs: {"ok": True})
    request = StudentUnsuspendRequest(reason="ok", restore_credits=True)
    result = await student_actions_module.unsuspend(
        student_id="01STU",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_unsuspend_route_error(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(unsuspend=_boom)
    request = StudentUnsuspendRequest(reason="ok", restore_credits=True)
    with pytest.raises(HTTPException):
        await student_actions_module.unsuspend(
            student_id="01STU",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_credit_adjust_preview_route_success(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_credit_adjust=lambda **_kwargs: {"ok": True})
    request = CreditAdjustPreviewRequest(
        action=CreditAdjustAction.ADD,
        amount=Decimal("10.00"),
        reason_code=CreditAdjustReasonCode.GOODWILL,
        note=None,
        expires_at=None,
    )
    result = await student_actions_module.credit_adjust_preview(
        student_id="01STU",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_credit_adjust_preview_route_error(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=422, detail="bad")

    service = SimpleNamespace(preview_credit_adjust=_boom)
    request = CreditAdjustPreviewRequest(
        action=CreditAdjustAction.ADD,
        amount=Decimal("10.00"),
        reason_code=CreditAdjustReasonCode.GOODWILL,
        note=None,
        expires_at=None,
    )
    with pytest.raises(HTTPException):
        await student_actions_module.credit_adjust_preview(
            student_id="01STU",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_credit_adjust_execute_route_success():
    async def _exec(**_kwargs):
        return {"ok": True}

    service = SimpleNamespace(execute_credit_adjust=_exec)
    request = CreditAdjustExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await student_actions_module.credit_adjust_execute(
        student_id="01STU",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_credit_adjust_execute_route_error():
    async def _boom(**_kwargs):
        raise HTTPException(status_code=409, detail="conflict")

    service = SimpleNamespace(execute_credit_adjust=_boom)
    request = CreditAdjustExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await student_actions_module.credit_adjust_execute(
            student_id="01STU",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_credit_history_route_success(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(credit_history=lambda **_kwargs: {"ok": True})
    result = await student_actions_module.credit_history(
        student_id="01STU",
        include_expired=True,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_credit_history_route_error(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(credit_history=_boom)
    with pytest.raises(HTTPException):
        await student_actions_module.credit_history(
            student_id="01STU",
            include_expired=True,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_refund_history_route_success(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(refund_history=lambda **_kwargs: {"ok": True})
    result = await student_actions_module.refund_history(
        student_id="01STU",
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_refund_history_route_error(monkeypatch):
    monkeypatch.setattr(student_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(refund_history=_boom)
    with pytest.raises(HTTPException):
        await student_actions_module.refund_history(
            student_id="01STU",
            principal=_principal(),
            service=service,
        )
