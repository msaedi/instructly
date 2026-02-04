"""MCP Admin endpoints for instructor actions."""

from __future__ import annotations

import asyncio
from typing import NoReturn

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.dependencies.services import get_instructor_admin_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_instructor_actions import (
    PayoutHoldRequest,
    PayoutHoldResponse,
    SuspendExecuteRequest,
    SuspendExecuteResponse,
    SuspendPreviewRequest,
    SuspendPreviewResponse,
    UnsuspendRequest,
    UnsuspendResponse,
    UpdateCommissionExecuteRequest,
    UpdateCommissionExecuteResponse,
    UpdateCommissionPreviewRequest,
    UpdateCommissionPreviewResponse,
    VerifyOverrideRequest,
    VerifyOverrideResponse,
)
from app.services.instructor_admin_service import InstructorAdminService

router = APIRouter(tags=["MCP Admin - Instructor Actions"])


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
    "/instructors/{instructor_id}/suspend/preview",
    response_model=SuspendPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def suspend_preview(
    instructor_id: str,
    request: SuspendPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> SuspendPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_suspend,
            instructor_id=instructor_id,
            reason_code=request.reason_code.value,
            note=request.note,
            notify_instructor=request.notify_instructor,
            cancel_pending_bookings=request.cancel_pending_bookings,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_suspend_preview_failed")


@router.post(
    "/instructors/{instructor_id}/suspend/execute",
    response_model=SuspendExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def suspend_execute(
    instructor_id: str,
    request: SuspendExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> SuspendExecuteResponse:
    try:
        return await service.execute_suspend(
            instructor_id=instructor_id,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_suspend_execute_failed")


@router.post(
    "/instructors/{instructor_id}/unsuspend",
    response_model=UnsuspendResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def unsuspend(
    instructor_id: str,
    request: UnsuspendRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> UnsuspendResponse:
    try:
        return await asyncio.to_thread(
            service.unsuspend,
            instructor_id=instructor_id,
            reason=request.reason,
            restore_visibility=request.restore_visibility,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_unsuspend_failed")


@router.post(
    "/instructors/{instructor_id}/verify-override",
    response_model=VerifyOverrideResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def verify_override(
    instructor_id: str,
    request: VerifyOverrideRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> VerifyOverrideResponse:
    try:
        return await asyncio.to_thread(
            service.verify_override,
            instructor_id=instructor_id,
            verification_type=request.verification_type,
            reason=request.reason,
            evidence=request.evidence,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_verify_override_failed")


@router.post(
    "/instructors/{instructor_id}/commission/preview",
    response_model=UpdateCommissionPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def commission_preview(
    instructor_id: str,
    request: UpdateCommissionPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> UpdateCommissionPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_update_commission,
            instructor_id=instructor_id,
            action=request.action,
            tier=request.tier,
            temporary_rate=request.temporary_rate,
            temporary_until=request.temporary_until,
            reason=request.reason,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_update_commission_preview_failed")


@router.post(
    "/instructors/{instructor_id}/commission/execute",
    response_model=UpdateCommissionExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def commission_execute(
    instructor_id: str,
    request: UpdateCommissionExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> UpdateCommissionExecuteResponse:
    try:
        return await service.execute_update_commission(
            instructor_id=instructor_id,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_update_commission_execute_failed")


@router.post(
    "/instructors/{instructor_id}/payout-hold",
    response_model=PayoutHoldResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def payout_hold(
    instructor_id: str,
    request: PayoutHoldRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: InstructorAdminService = Depends(get_instructor_admin_service),
) -> PayoutHoldResponse:
    try:
        return await asyncio.to_thread(
            service.payout_hold,
            instructor_id=instructor_id,
            action=request.action,
            reason=request.reason,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "instructor_payout_hold_failed")


__all__ = ["router"]
