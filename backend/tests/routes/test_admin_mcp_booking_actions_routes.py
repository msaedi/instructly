from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.principal import UserPrincipal
from app.routes.v1.admin.mcp import booking_actions as booking_actions_module
from app.schemas.admin_booking_actions import (
    AddNoteRequest,
    AddNoteResponse,
    BookingState,
    ForceCancelExecuteRequest,
    ForceCancelExecuteResponse,
    ForceCancelPreviewRequest,
    ForceCancelPreviewResponse,
    ForceCancelReasonCode,
    ForceCompleteExecuteRequest,
    ForceCompleteExecuteResponse,
    ForceCompletePreviewRequest,
    ForceCompletePreviewResponse,
    ForceCompleteReasonCode,
    NotificationRecipient,
    NotificationSent,
    NotificationType,
    RefundPreference,
    ResendNotificationRequest,
    ResendNotificationResponse,
)


@asynccontextmanager
async def _lock_true(_booking_id: str):
    yield True


@asynccontextmanager
async def _lock_false(_booking_id: str):
    yield False


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


@pytest.mark.asyncio
async def test_force_cancel_preview_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)
    response = ForceCancelPreviewResponse(
        eligible=True,
        current_state=BookingState(status="CONFIRMED", payment_status="authorized"),
        will_cancel_booking=True,
        will_refund=True,
        refund_method="card",
        refund_amount=Decimal("10.00"),
        will_notify_student=True,
        will_notify_instructor=True,
        instructor_payout_impact=Decimal("0.00"),
        platform_fee_impact=Decimal("0.00"),
        warnings=[],
        confirm_token="token",
        idempotency_key="idem",
    )

    service = SimpleNamespace(preview_force_cancel=lambda **_kwargs: response)
    request = ForceCancelPreviewRequest(
        reason_code=ForceCancelReasonCode.ADMIN_DISCRETION,
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
    )
    result = await booking_actions_module.force_cancel_preview(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.eligible is True


@pytest.mark.asyncio
async def test_force_cancel_preview_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise _ErrorWithHttp(418, "teapot")

    service = SimpleNamespace(preview_force_cancel=_boom)
    request = ForceCancelPreviewRequest(
        reason_code=ForceCancelReasonCode.ADMIN_DISCRETION,
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
    )

    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 418


@pytest.mark.asyncio
async def test_force_cancel_preview_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(preview_force_cancel=_boom)
    request = ForceCancelPreviewRequest(
        reason_code=ForceCancelReasonCode.ADMIN_DISCRETION,
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
    )

    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "force_cancel_preview_failed"


@pytest.mark.asyncio
async def test_force_cancel_preview_route_passes_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(preview_force_cancel=_boom)
    request = ForceCancelPreviewRequest(
        reason_code=ForceCancelReasonCode.ADMIN_DISCRETION,
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_force_cancel_execute_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)
    response = ForceCancelExecuteResponse(
        success=True,
        booking_id="bk1",
        previous_status="CONFIRMED",
        new_status="cancelled",
        refund_issued=False,
        notifications_sent=[],
        audit_id="audit",
    )

    async def _exec(**_kwargs):
        return response

    service = SimpleNamespace(execute_force_cancel=_exec)
    request = ForceCancelExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await booking_actions_module.force_cancel_execute(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_force_cancel_execute_route_lock_blocked(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_false)
    service = SimpleNamespace(execute_force_cancel=lambda **_kwargs: None)
    request = ForceCancelExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_force_cancel_execute_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)

    async def _boom(**_kwargs):
        raise _ErrorWithHttp(409, "conflict")

    service = SimpleNamespace(execute_force_cancel=_boom)
    request = ForceCancelExecuteRequest(confirm_token="token", idempotency_key="idem")

    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_force_cancel_execute_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(execute_force_cancel=_boom)
    request = ForceCancelExecuteRequest(confirm_token="token", idempotency_key="idem")

    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_cancel_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "force_cancel_execute_failed"


@pytest.mark.asyncio
async def test_force_complete_preview_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)
    response = ForceCompletePreviewResponse(
        eligible=True,
        current_state=BookingState(status="CONFIRMED", payment_status="authorized"),
        will_mark_complete=True,
        will_capture_payment=True,
        capture_amount=Decimal("10.00"),
        instructor_payout=Decimal("9.00"),
        platform_fee=Decimal("1.00"),
        lesson_time_passed=True,
        hours_since_scheduled=1.0,
        warnings=[],
        confirm_token="token",
        idempotency_key="idem",
    )

    service = SimpleNamespace(preview_force_complete=lambda **_kwargs: response)
    request = ForceCompletePreviewRequest(
        reason_code=ForceCompleteReasonCode.ADMIN_VERIFIED,
        note="note",
    )
    result = await booking_actions_module.force_complete_preview(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.eligible is True


@pytest.mark.asyncio
async def test_force_complete_preview_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise _ErrorWithHttp(400, "bad")

    service = SimpleNamespace(preview_force_complete=_boom)
    request = ForceCompletePreviewRequest(
        reason_code=ForceCompleteReasonCode.ADMIN_VERIFIED,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_force_complete_preview_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(preview_force_complete=_boom)
    request = ForceCompletePreviewRequest(
        reason_code=ForceCompleteReasonCode.ADMIN_VERIFIED,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "force_complete_preview_failed"


@pytest.mark.asyncio
async def test_force_complete_preview_route_passes_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(preview_force_complete=_boom)
    request = ForceCompletePreviewRequest(
        reason_code=ForceCompleteReasonCode.ADMIN_VERIFIED,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_preview(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_force_complete_execute_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)
    response = ForceCompleteExecuteResponse(
        success=True,
        booking_id="bk1",
        previous_status="CONFIRMED",
        new_status="completed",
        payment_captured=True,
        capture_amount=Decimal("10.00"),
        instructor_payout_scheduled=True,
        payout_amount=Decimal("9.00"),
        audit_id="audit",
    )

    async def _exec(**_kwargs):
        return response

    service = SimpleNamespace(execute_force_complete=_exec)
    request = ForceCompleteExecuteRequest(confirm_token="token", idempotency_key="idem")
    result = await booking_actions_module.force_complete_execute(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_force_complete_execute_route_lock_blocked(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_false)
    service = SimpleNamespace(execute_force_complete=lambda **_kwargs: None)
    request = ForceCompleteExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_force_complete_execute_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)

    async def _boom(**_kwargs):
        raise _ErrorWithHttp(409, "conflict")

    service = SimpleNamespace(execute_force_complete=_boom)
    request = ForceCompleteExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_force_complete_execute_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module, "booking_lock", _lock_true)

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(execute_force_complete=_boom)
    request = ForceCompleteExecuteRequest(confirm_token="token", idempotency_key="idem")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.force_complete_execute(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "force_complete_execute_failed"


@pytest.mark.asyncio
async def test_resend_notification_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)
    response = ResendNotificationResponse(
        success=True,
        notifications_sent=[
            NotificationSent(
                recipient="student",
                channel="email",
                template="booking_confirmation",
                sent_at=datetime.now(timezone.utc),
            )
        ],
        audit_id="audit",
    )

    service = SimpleNamespace(resend_notification=lambda **_kwargs: response)
    request = ResendNotificationRequest(
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.STUDENT,
        note="note",
    )
    result = await booking_actions_module.resend_notification(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_resend_notification_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise _ErrorWithHttp(400, "bad")

    service = SimpleNamespace(resend_notification=_boom)
    request = ResendNotificationRequest(
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.STUDENT,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.resend_notification(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_notification_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(resend_notification=_boom)
    request = ResendNotificationRequest(
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.STUDENT,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.resend_notification(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "resend_notification_failed"


@pytest.mark.asyncio
async def test_resend_notification_route_passes_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(resend_notification=_boom)
    request = ResendNotificationRequest(
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.STUDENT,
        note="note",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.resend_notification(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_booking_note_route_success(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)
    response = AddNoteResponse(
        success=True,
        note_id="note1",
        created_at=datetime.now(timezone.utc),
        audit_id="audit",
    )

    service = SimpleNamespace(add_note=lambda **_kwargs: response)
    request = AddNoteRequest(note="note")
    result = await booking_actions_module.add_booking_note(
        booking_id="bk1",
        request=request,
        principal=_principal(),
        service=service,
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_add_booking_note_route_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise _ErrorWithHttp(400, "bad")

    service = SimpleNamespace(add_note=_boom)
    request = AddNoteRequest(note="note")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.add_booking_note(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_booking_note_route_generic_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise RuntimeError("boom")

    service = SimpleNamespace(add_note=_boom)
    request = AddNoteRequest(note="note")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.add_booking_note(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail == "add_booking_note_failed"


@pytest.mark.asyncio
async def test_add_booking_note_route_passes_http_exception(monkeypatch):
    monkeypatch.setattr(booking_actions_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(add_note=_boom)
    request = AddNoteRequest(note="note")
    with pytest.raises(HTTPException) as exc:
        await booking_actions_module.add_booking_note(
            booking_id="bk1",
            request=request,
            principal=_principal(),
            service=service,
        )
    assert exc.value.status_code == 400
