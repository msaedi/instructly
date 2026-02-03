"""MCP Admin endpoints for webhook ledger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.api.dependencies.repositories import (
    get_background_job_repo,
    get_bgc_webhook_log_repo,
)
from app.api.dependencies.services import get_background_check_workflow_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.models.webhook_event import WebhookEvent
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.repositories.background_job_repository import BackgroundJobRepository
from app.repositories.bgc_webhook_log_repository import BGCWebhookLogRepository
from app.routes.v1.payments import get_stripe_service
from app.routes.v1.webhooks_checkr import _process_checkr_payload, _resolve_resource_id
from app.schemas.mcp_webhooks import (
    MCPWebhookDetail,
    MCPWebhookDetailMeta,
    MCPWebhookDetailResponse,
    MCPWebhookEventItem,
    MCPWebhookFailedItem,
    MCPWebhookFailedMeta,
    MCPWebhookFailedResponse,
    MCPWebhookListMeta,
    MCPWebhookListResponse,
    MCPWebhookListSummary,
    MCPWebhookReplayMeta,
    MCPWebhookReplayResponse,
    MCPWebhookReplayResult,
)
from app.services.background_check_workflow_service import BackgroundCheckWorkflowService
from app.services.stripe_service import StripeService
from app.services.webhook_ledger_service import WebhookLedgerService

router = APIRouter(tags=["MCP Admin - Webhooks"])


def _serialize_event(event: WebhookEvent) -> dict[str, Any]:
    related_entity = None
    if event.related_entity_type and event.related_entity_id:
        related_entity = f"{event.related_entity_type}/{event.related_entity_id}"

    return {
        "id": event.id,
        "source": event.source,
        "event_type": event.event_type,
        "event_id": event.event_id,
        "status": event.status,
        "received_at": event.received_at,
        "processed_at": event.processed_at,
        "processing_duration_ms": event.processing_duration_ms,
        "related_entity": related_entity,
        "replay_of": event.replay_of,
        "replay_count": event.replay_count or 0,
    }


@router.get(
    "",
    response_model=MCPWebhookListResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def list_webhooks(
    source: str | None = None,
    status: str | None = None,
    event_type: str | None = None,
    since_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPWebhookListResponse:
    service = WebhookLedgerService(db)
    events = await asyncio.to_thread(
        service.list_events,
        source=source,
        status=status,
        event_type=event_type,
        since_hours=since_hours,
        limit=limit,
    )
    total_count = await asyncio.to_thread(service.count_events, since_hours=since_hours)
    by_status = await asyncio.to_thread(service.summarize_by_status, since_hours=since_hours)
    by_source = await asyncio.to_thread(service.summarize_by_source, since_hours=since_hours)

    meta = MCPWebhookListMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        since_hours=since_hours,
        total_count=total_count,
        returned_count=len(events),
    )
    summary = MCPWebhookListSummary(by_status=by_status, by_source=by_source)
    items = [MCPWebhookEventItem(**_serialize_event(event)) for event in events]

    return MCPWebhookListResponse(
        meta=meta,
        summary=summary,
        events=items,
    )


@router.get(
    "/failed",
    response_model=MCPWebhookFailedResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def list_failed_webhooks(
    source: str | None = None,
    since_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPWebhookFailedResponse:
    service = WebhookLedgerService(db)
    events = await asyncio.to_thread(
        service.get_failed_events,
        source=source,
        since_hours=since_hours,
        limit=limit,
    )

    meta = MCPWebhookFailedMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        since_hours=since_hours,
        returned_count=len(events),
    )
    items = [
        MCPWebhookFailedItem(
            **{
                **_serialize_event(event),
                "processing_error": event.processing_error,
            }
        )
        for event in events
    ]

    return MCPWebhookFailedResponse(meta=meta, events=items)


@router.get(
    "/{event_id}",
    response_model=MCPWebhookDetailResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def webhook_detail(
    event_id: str,
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPWebhookDetailResponse:
    service = WebhookLedgerService(db)
    event = await asyncio.to_thread(service.get_event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="webhook_not_found")

    meta = MCPWebhookDetailMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
    )
    detail = MCPWebhookDetail(
        **{
            **_serialize_event(event),
            "payload": event.payload,
            "headers": event.headers,
            "processing_error": event.processing_error,
            "idempotency_key": event.idempotency_key,
        }
    )
    return MCPWebhookDetailResponse(meta=meta, event=detail)


@router.post(
    "/{event_id}/replay",
    response_model=MCPWebhookReplayResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def replay_webhook(
    event_id: str,
    dry_run: bool = True,
    principal: Principal = Depends(require_mcp_scope("mcp:write")),
    db: Session = Depends(get_db),
    stripe_service: StripeService = Depends(get_stripe_service),
    workflow_service: BackgroundCheckWorkflowService = Depends(
        get_background_check_workflow_service
    ),
    job_repository: BackgroundJobRepository = Depends(get_background_job_repo),
    log_repository: BGCWebhookLogRepository = Depends(get_bgc_webhook_log_repo),
) -> MCPWebhookReplayResponse:
    service = WebhookLedgerService(db)
    original = await asyncio.to_thread(service.get_event, event_id)
    if not original:
        raise HTTPException(status_code=404, detail="webhook_not_found")

    if dry_run:
        meta = MCPWebhookReplayMeta(
            request_id=str(uuid4()),
            generated_at=datetime.now(timezone.utc),
            dry_run=True,
        )
        return MCPWebhookReplayResponse(
            meta=meta,
            event=MCPWebhookEventItem(**_serialize_event(original)),
            note="dry_run_only",
        )

    replay_event = await asyncio.to_thread(service.create_replay, original)
    start_time = time.monotonic()
    processing_error: str | None = None

    if original.source == "stripe":
        try:
            await asyncio.to_thread(stripe_service.handle_webhook_event, original.payload)
        except Exception as exc:
            processing_error = str(exc)
    elif original.source == "checkr":
        data_object = original.payload.get("data", {}).get("object") or {}
        if not isinstance(data_object, dict):
            data_object = {}
        resource_id = _resolve_resource_id(original.event_type, data_object)
        processing_error = await _process_checkr_payload(
            event_type=original.event_type,
            data_object=data_object,
            payload=original.payload,
            headers=original.headers or {},
            workflow_service=workflow_service,
            job_repository=job_repository,
            log_repository=log_repository,
            resource_id=resource_id,
            skip_dedup=True,
        )
    else:
        processing_error = f"unsupported_source:{original.source}"

    duration_ms = int((time.monotonic() - start_time) * 1000)
    if processing_error:
        await asyncio.to_thread(
            service.mark_failed,
            replay_event,
            error=processing_error,
            duration_ms=duration_ms,
        )
        status_value = "failed"
    else:
        await asyncio.to_thread(
            service.mark_processed,
            replay_event,
            duration_ms=duration_ms,
            status="replayed",
        )
        status_value = "replayed"

    meta = MCPWebhookReplayMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        dry_run=False,
    )
    result = MCPWebhookReplayResult(
        status=status_value,
        replay_event_id=replay_event.id,
        error=processing_error,
    )
    return MCPWebhookReplayResponse(meta=meta, result=result)
