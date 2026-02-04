"""MCP Admin endpoints for communications."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.api.dependencies.services import get_communication_admin_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_communications import (
    AnnouncementExecuteRequest,
    AnnouncementExecuteResponse,
    AnnouncementPreviewRequest,
    AnnouncementPreviewResponse,
    BulkNotificationExecuteRequest,
    BulkNotificationExecuteResponse,
    BulkNotificationPreviewRequest,
    BulkNotificationPreviewResponse,
    EmailPreviewRequest,
    EmailPreviewResponse,
    NotificationHistoryResponse,
    NotificationTemplatesResponse,
)
from app.services.communication_admin_service import CommunicationAdminService

router = APIRouter(tags=["MCP Admin - Communications"])


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
    "/communications/announcement/preview",
    response_model=AnnouncementPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def announcement_preview(
    request: AnnouncementPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> AnnouncementPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_announcement,
            audience=request.audience,
            channels=request.channels,
            title=request.title,
            body=request.body,
            subject=request.subject,
            schedule_at=request.schedule_at,
            high_priority=request.high_priority,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_announcement_preview_failed")


@router.post(
    "/communications/announcement/execute",
    response_model=AnnouncementExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def announcement_execute(
    request: AnnouncementExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> AnnouncementExecuteResponse:
    try:
        return await asyncio.to_thread(
            service.execute_announcement,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_announcement_execute_failed")


@router.post(
    "/communications/bulk/preview",
    response_model=BulkNotificationPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def bulk_preview(
    request: BulkNotificationPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> BulkNotificationPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.preview_bulk_notification,
            target=request.target,
            channels=request.channels,
            title=request.title,
            body=request.body,
            subject=request.subject,
            variables=request.variables,
            schedule_at=request.schedule_at,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_bulk_preview_failed")


@router.post(
    "/communications/bulk/execute",
    response_model=BulkNotificationExecuteResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def bulk_execute(
    request: BulkNotificationExecuteRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> BulkNotificationExecuteResponse:
    try:
        return await asyncio.to_thread(
            service.execute_bulk_notification,
            confirm_token=request.confirm_token,
            idempotency_key=request.idempotency_key,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_bulk_execute_failed")


@router.get(
    "/communications/history",
    response_model=NotificationHistoryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def communication_history(
    kind: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    creator_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> NotificationHistoryResponse:
    try:
        return await asyncio.to_thread(
            service.notification_history,
            kind=kind,
            channel=channel,
            status=status,
            start_date=start_date,
            end_date=end_date,
            creator_id=creator_id,
            limit=limit,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_history_failed")


@router.get(
    "/communications/templates",
    response_model=NotificationTemplatesResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def communication_templates(
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> NotificationTemplatesResponse:
    try:
        return await asyncio.to_thread(service.notification_templates)
    except Exception as exc:
        _handle_exception(exc, "communication_templates_failed")


@router.post(
    "/communications/email/preview",
    response_model=EmailPreviewResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def communication_email_preview(
    request: EmailPreviewRequest = Body(...),
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    service: CommunicationAdminService = Depends(get_communication_admin_service),
) -> EmailPreviewResponse:
    try:
        return await asyncio.to_thread(
            service.email_preview,
            template=request.template,
            variables=request.variables,
            subject=request.subject,
            test_send_to=request.test_send_to,
            actor_id=principal.id,
        )
    except Exception as exc:
        _handle_exception(exc, "communication_email_preview_failed")


__all__ = ["router"]
