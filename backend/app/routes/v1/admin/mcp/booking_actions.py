"""MCP Admin endpoints for booking admin actions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.dependencies.services import get_booking_admin_service
from app.core.booking_lock import booking_lock
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_booking_actions import (
    AddNoteRequest,
    AddNoteResponse,
    ForceCancelExecuteRequest,
    ForceCancelExecuteResponse,
    ForceCancelPreviewRequest,
    ForceCancelPreviewResponse,
    ForceCompleteExecuteRequest,
    ForceCompleteExecuteResponse,
    ForceCompletePreviewRequest,
    ForceCompletePreviewResponse,
    ResendNotificationRequest,
    ResendNotificationResponse,
)
from app.services.booking_admin_service import BookingAdminService

router = APIRouter(tags=["MCP Admin - Booking Actions"])


@router.post(
    "/bookings/{booking_id}/force-cancel/preview",
    response_model=ForceCancelPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_cancel_preview(
    booking_id: str,
    request: ForceCancelPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> ForceCancelPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_force_cancel,
            booking_id=booking_id,
            reason_code=request.reason_code.value,
            note=request.note,
            refund_preference=request.refund_preference,
            actor_id=principal.id,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="force_cancel_preview_failed",
        ) from exc


@router.post(
    "/bookings/{booking_id}/force-cancel/execute",
    response_model=ForceCancelExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_cancel_execute(
    booking_id: str,
    request: ForceCancelExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> ForceCancelExecuteResponse:
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            return await service.execute_force_cancel(
                booking_id=booking_id,
                confirm_token=request.confirm_token,
                idempotency_key=request.idempotency_key,
                actor_id=principal.id,
            )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="force_cancel_execute_failed",
        ) from exc


@router.post(
    "/bookings/{booking_id}/force-complete/preview",
    response_model=ForceCompletePreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_complete_preview(
    booking_id: str,
    request: ForceCompletePreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> ForceCompletePreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_force_complete,
            booking_id=booking_id,
            reason_code=request.reason_code.value,
            note=request.note,
            actor_id=principal.id,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="force_complete_preview_failed",
        ) from exc


@router.post(
    "/bookings/{booking_id}/force-complete/execute",
    response_model=ForceCompleteExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_complete_execute(
    booking_id: str,
    request: ForceCompleteExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> ForceCompleteExecuteResponse:
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            return await service.execute_force_complete(
                booking_id=booking_id,
                confirm_token=request.confirm_token,
                idempotency_key=request.idempotency_key,
                actor_id=principal.id,
            )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="force_complete_execute_failed",
        ) from exc


@router.post(
    "/bookings/{booking_id}/resend-notification",
    response_model=ResendNotificationResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def resend_notification(
    booking_id: str,
    request: ResendNotificationRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> ResendNotificationResponse:
    try:
        return await asyncio.to_thread(
            service.resend_notification,
            booking_id=booking_id,
            notification_type=request.notification_type,
            recipient=request.recipient,
            note=request.note,
            actor_id=principal.id,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="resend_notification_failed",
        ) from exc


@router.post(
    "/bookings/{booking_id}/notes",
    response_model=AddNoteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def add_booking_note(
    booking_id: str,
    request: AddNoteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: BookingAdminService = Depends(get_booking_admin_service),
) -> AddNoteResponse:
    try:
        return await asyncio.to_thread(
            service.add_note,
            booking_id=booking_id,
            note=request.note,
            visibility=request.visibility.value,
            category=request.category.value,
            actor_id=principal.id,
            actor_type=principal.principal_type,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="add_booking_note_failed",
        ) from exc


__all__ = ["router"]
