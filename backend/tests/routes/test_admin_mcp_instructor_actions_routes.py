from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.principal import UserPrincipal
from app.routes.v1.admin.mcp import instructor_actions as instructor_actions_module
from app.schemas.admin_instructor_actions import (
    CommissionAction,
    CommissionTier,
    PayoutHoldAction,
    PayoutHoldRequest,
    SuspendExecuteRequest,
    SuspendPreviewRequest,
    UnsuspendRequest,
    UpdateCommissionExecuteRequest,
    UpdateCommissionPreviewRequest,
    VerificationType,
    VerifyOverrideRequest,
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
        instructor_actions_module._handle_exception(
            HTTPException(status_code=400, detail="bad"), "detail"
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        instructor_actions_module._handle_exception(_ErrorWithHttp(418, "teapot"), "detail")
    assert exc.value.status_code == 418

    with pytest.raises(HTTPException) as exc:
        instructor_actions_module._handle_exception(RuntimeError("boom"), "detail")
    assert exc.value.detail == "detail"


@pytest.mark.asyncio
async def test_suspend_preview_route_success(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_suspend=lambda **_kwargs: {"ok": True})
    request = SuspendPreviewRequest(reason_code="FRAUD", note="note")
    result = await instructor_actions_module.suspend_preview(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_suspend_preview_route_error(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(preview_suspend=_boom)
    request = SuspendPreviewRequest(reason_code="FRAUD", note="note")
    with pytest.raises(HTTPException):
        await instructor_actions_module.suspend_preview(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_suspend_execute_route_success():
    async def _exec(**_kwargs):
        return {"ok": True}

    service = SimpleNamespace(execute_suspend=_exec)
    request = SuspendExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await instructor_actions_module.suspend_execute(
        instructor_id="01INS",
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
    request = SuspendExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await instructor_actions_module.suspend_execute(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_unsuspend_route_success(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(unsuspend=lambda **_kwargs: {"ok": True})
    request = UnsuspendRequest(reason="ok", restore_visibility=True)
    result = await instructor_actions_module.unsuspend(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_unsuspend_route_error(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(unsuspend=_boom)
    request = UnsuspendRequest(reason="ok", restore_visibility=True)
    with pytest.raises(HTTPException):
        await instructor_actions_module.unsuspend(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_verify_override_route_success(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(verify_override=lambda **_kwargs: {"ok": True})
    request = VerifyOverrideRequest(
        verification_type=VerificationType.IDENTITY,
        reason="note",
        evidence=None,
    )
    result = await instructor_actions_module.verify_override(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_verify_override_route_error(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=422, detail="bad")

    service = SimpleNamespace(verify_override=_boom)
    request = VerifyOverrideRequest(
        verification_type=VerificationType.IDENTITY,
        reason="note",
        evidence=None,
    )
    with pytest.raises(HTTPException):
        await instructor_actions_module.verify_override(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_commission_preview_route_success(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(preview_update_commission=lambda **_kwargs: {"ok": True})
    request = UpdateCommissionPreviewRequest(
        action=CommissionAction.SET_TIER,
        tier=CommissionTier.ENTRY,
        temporary_rate=None,
        temporary_until=None,
        reason="note",
    )
    result = await instructor_actions_module.commission_preview(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_commission_preview_route_error(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=500, detail="boom")

    service = SimpleNamespace(preview_update_commission=_boom)
    request = UpdateCommissionPreviewRequest(
        action=CommissionAction.SET_TIER,
        tier=CommissionTier.ENTRY,
        temporary_rate=None,
        temporary_until=None,
        reason="note",
    )
    with pytest.raises(HTTPException):
        await instructor_actions_module.commission_preview(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_commission_execute_route_success():
    async def _exec(**_kwargs):
        return {"ok": True}

    service = SimpleNamespace(execute_update_commission=_exec)
    request = UpdateCommissionExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await instructor_actions_module.commission_execute(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_commission_execute_route_error():
    async def _boom(**_kwargs):
        raise HTTPException(status_code=500, detail="boom")

    service = SimpleNamespace(execute_update_commission=_boom)
    request = UpdateCommissionExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException):
        await instructor_actions_module.commission_execute(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )


@pytest.mark.asyncio
async def test_payout_hold_route_success(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(payout_hold=lambda **_kwargs: {"ok": True})
    request = PayoutHoldRequest(action=PayoutHoldAction.HOLD, reason="note")
    result = await instructor_actions_module.payout_hold(
        instructor_id="01INS",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_payout_hold_route_error(monkeypatch):
    monkeypatch.setattr(instructor_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=500, detail="boom")

    service = SimpleNamespace(payout_hold=_boom)
    request = PayoutHoldRequest(action=PayoutHoldAction.HOLD, reason="note")
    with pytest.raises(HTTPException):
        await instructor_actions_module.payout_hold(
            instructor_id="01INS",
            request=request,
            principal=_principal(),
            service=service,
        )
