"""MCP Admin endpoints for student actions."""

from __future__ import annotations

import asyncio
from typing import NoReturn

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.api.dependencies.services import get_student_admin_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_student_actions import (
    CreditAdjustExecuteRequest,
    CreditAdjustExecuteResponse,
    CreditAdjustPreviewRequest,
    CreditAdjustPreviewResponse,
    CreditHistoryResponse,
    RefundHistoryResponse,
    StudentSuspendExecuteRequest,
    StudentSuspendExecuteResponse,
    StudentSuspendPreviewRequest,
    StudentSuspendPreviewResponse,
    StudentUnsuspendRequest,
    StudentUnsuspendResponse,
)
from app.services.student_admin_service import StudentAdminService

router = APIRouter(tags=["MCP Admin - Student Actions"])


def _handle_exception(exc: Exception, detail: str) -> NoReturn:
    if isinstance(exc, HTTPException):
        raise exc
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    ) from exc


@router.post(
    "/students/{student_id}/suspend/preview",
    response_model=StudentSuspendPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def suspend_preview(
    student_id: str,
    request: StudentSuspendPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> StudentSuspendPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_suspend,
            student_id=student_id,
            reason_code=request.reason_code.value,
            note=request.note,
            notify_student=request.notify_student,
            cancel_pending_bookings=request.cancel_pending_bookings,
            forfeit_credits=request.forfeit_credits,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_suspend_preview_failed")


@router.post(
    "/students/{student_id}/suspend/execute",
    response_model=StudentSuspendExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def suspend_execute(
    student_id: str,
    request: StudentSuspendExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> StudentSuspendExecuteResponse:
    try:
        return await service.execute_suspend(
            student_id=student_id,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_suspend_execute_failed")


@router.post(
    "/students/{student_id}/unsuspend",
    response_model=StudentUnsuspendResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def unsuspend(
    student_id: str,
    request: StudentUnsuspendRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> StudentUnsuspendResponse:
    try:
        return await asyncio.to_thread(
            service.unsuspend,
            student_id=student_id,
            reason=request.reason,
            restore_credits=request.restore_credits,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_unsuspend_failed")


@router.post(
    "/students/{student_id}/credits/adjust/preview",
    response_model=CreditAdjustPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def credit_adjust_preview(
    student_id: str,
    request: CreditAdjustPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> CreditAdjustPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_credit_adjust,
            student_id=student_id,
            action=request.action,
            amount=request.amount,
            reason_code=request.reason_code.value,
            note=request.note,
            expires_at=request.expires_at,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_credit_adjust_preview_failed")


@router.post(
    "/students/{student_id}/credits/adjust/execute",
    response_model=CreditAdjustExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def credit_adjust_execute(
    student_id: str,
    request: CreditAdjustExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> CreditAdjustExecuteResponse:
    try:
        return await service.execute_credit_adjust(
            student_id=student_id,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_credit_adjust_execute_failed")


@router.get(
    "/students/{student_id}/credits/history",
    response_model=CreditHistoryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def credit_history(
    student_id: str,
    include_expired: bool = Query(True),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> CreditHistoryResponse:
    _ = principal
    try:
        return await asyncio.to_thread(
            service.credit_history,
            student_id=student_id,
            include_expired=include_expired,
        )
    except Exception as exc:
        _handle_exception(exc, "student_credit_history_failed")


@router.get(
    "/students/{student_id}/refunds/history",
    response_model=RefundHistoryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def refund_history(
    student_id: str,
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    service: StudentAdminService = Depends(get_student_admin_service),
) -> RefundHistoryResponse:
    _ = principal
    try:
        return await asyncio.to_thread(
            service.refund_history,
            student_id=student_id,
        )
    except Exception as exc:
        _handle_exception(exc, "student_refund_history_failed")


__all__ = ["router"]
