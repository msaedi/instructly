"""MCP Admin endpoints for refund preview/execute flow."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.dependencies.services import get_refund_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_refund import (
    RefundExecuteRequest,
    RefundExecuteResponse,
    RefundPreviewRequest,
    RefundPreviewResponse,
)
from app.services.refund_service import RefundService

router = APIRouter(prefix="/refunds", tags=["MCP Admin - Refunds"])


@router.post(
    "/preview",
    response_model=RefundPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def preview_refund(
    request: RefundPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: RefundService = Depends(get_refund_service),
) -> RefundPreviewResponse:
    """Preview a refund to see eligibility and impact before executing."""
    try:
        return await asyncio.to_thread(
            service.preview_refund,
            booking_id=request.booking_id,
            reason_code=request.reason_code,
            amount=request.amount,
            note=request.note,
            actor_id=principal.id,
        )
    except Exception as exc:
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="refund_preview_failed",
        ) from exc


@router.post(
    "/execute",
    response_model=RefundExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def execute_refund(
    request: RefundExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: RefundService = Depends(get_refund_service),
) -> RefundExecuteResponse:
    """Execute a previously previewed refund using confirm token."""
    try:
        return await service.execute_refund(
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        if hasattr(exc, "to_http_exception"):
            raise exc.to_http_exception()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="refund_execute_failed",
        ) from exc


__all__ = ["router"]
