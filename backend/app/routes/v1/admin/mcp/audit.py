"""MCP audit log endpoints for governance and debugging."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.models.audit_log import AuditLogEntry
from app.principal import Principal
from app.repositories.factory import RepositoryFactory
from app.schemas.audit_governance import (
    AuditActor,
    AuditEntry,
    AuditResource,
    AuditSearchMeta,
    AuditSearchResponse,
    AuditSearchSummary,
)
from app.schemas.mcp import MCPTimeWindow

router = APIRouter(tags=["MCP Admin - Audit"])


def _to_entry(entry: AuditLogEntry) -> AuditEntry:
    return AuditEntry(
        id=entry.id,
        timestamp=entry.timestamp,
        actor=AuditActor(type=entry.actor_type, id=entry.actor_id, email=entry.actor_email),
        action=entry.action,
        resource=AuditResource(type=entry.resource_type, id=entry.resource_id),
        description=entry.description,
        changes=entry.changes,
        status=entry.status,
        request_id=entry.request_id,
    )


def _summarize(entries: list[AuditLogEntry]) -> AuditSearchSummary:
    by_action = Counter([entry.action for entry in entries if entry.action])
    by_actor_type = Counter([entry.actor_type for entry in entries if entry.actor_type])
    by_status = Counter([entry.status for entry in entries if entry.status])
    return AuditSearchSummary(
        by_action=dict(by_action),
        by_actor_type=dict(by_actor_type),
        by_status=dict(by_status),
    )


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_time_window(
    *,
    since_hours: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[datetime, datetime, int]:
    now = datetime.now(timezone.utc)
    if start_time or end_time:
        if not start_time or not end_time:
            raise HTTPException(
                status_code=422,
                detail="start_time and end_time must be provided together",
            )
        start = _ensure_utc(start_time)
        end = _ensure_utc(end_time)
        if start > end:
            raise HTTPException(
                status_code=422,
                detail="start_time must be on or before end_time",
            )
    else:
        start = now - timedelta(hours=max(0, since_hours))
        end = now
    effective_since_hours = max(int((end - start).total_seconds() // 3600), 0)
    return start, end, effective_since_hours


@router.get("/search", response_model=AuditSearchResponse)
async def audit_search(
    actor_email: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since_hours: int = Query(default=24, ge=1, le=720),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    start_dt, end_dt, effective_since_hours = _resolve_time_window(
        since_hours=since_hours,
        start_time=start_time,
        end_time=end_time,
    )
    entries, total, summary = repo.search(
        actor_email=actor_email,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        since_hours=effective_since_hours,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit,
    )

    items = [_to_entry(entry) for entry in entries]
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=effective_since_hours,
            total_count=total,
            returned_count=len(items),
            time_window=MCPTimeWindow(start=start_dt, end=end_dt),
        ),
        summary=AuditSearchSummary(
            by_action=summary["by_action"],
            by_actor_type=summary["by_actor_type"],
            by_status=summary["by_status"],
        ),
        entries=items,
    )


@router.get("/users/{user_email}/activity", response_model=AuditSearchResponse)
async def audit_user_activity(
    user_email: str,
    since_days: int = Query(default=30, ge=1, le=365),
    since_hours: int | None = Query(default=None, ge=1, le=720),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    effective_since_hours = since_hours if since_hours is not None else since_days * 24
    start_dt, end_dt, effective_since_hours = _resolve_time_window(
        since_hours=effective_since_hours,
        start_time=start_time,
        end_time=end_time,
    )
    repo = RepositoryFactory.create_governance_audit_repository(db)
    entries, total, summary = repo.search(
        actor_email=user_email,
        since_hours=effective_since_hours,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit,
    )
    items = [_to_entry(entry) for entry in entries]
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=effective_since_hours,
            total_count=total,
            returned_count=len(items),
            time_window=MCPTimeWindow(start=start_dt, end=end_dt),
        ),
        summary=AuditSearchSummary(
            by_action=summary["by_action"],
            by_actor_type=summary["by_actor_type"],
            by_status=summary["by_status"],
        ),
        entries=items,
    )


@router.get(
    "/resources/{resource_type}/{resource_id}/history",
    response_model=AuditSearchResponse,
)
async def audit_resource_history(
    resource_type: str,
    resource_id: str,
    since_hours: int | None = Query(default=None, ge=1, le=720),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    if start_time or end_time or since_hours is not None:
        window_hours = since_hours or 0
        start_dt, end_dt, effective_since_hours = _resolve_time_window(
            since_hours=window_hours,
            start_time=start_time,
            end_time=end_time,
        )
        entries = list(
            repo.list_by_resource(
                resource_type=resource_type,
                resource_id=resource_id,
                start_time=start_dt,
                end_time=end_dt,
                limit=limit,
            )
        )
        time_window = MCPTimeWindow(start=start_dt, end=end_dt)
        meta_since_hours = effective_since_hours
    else:
        entries = list(
            repo.list_by_resource(resource_type=resource_type, resource_id=resource_id, limit=limit)
        )
        if entries:
            time_window = MCPTimeWindow(
                start=entries[-1].timestamp,
                end=entries[0].timestamp,
            )
        else:
            time_window = MCPTimeWindow()
        meta_since_hours = 0
    items = [_to_entry(entry) for entry in entries]
    summary = _summarize(entries)
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=meta_since_hours,
            total_count=len(entries),
            returned_count=len(items),
            time_window=time_window,
        ),
        summary=summary,
        entries=items,
    )


@router.get("/admin-actions/recent", response_model=AuditSearchResponse)
async def audit_recent_admin_actions(
    since_hours: int = Query(default=24, ge=1, le=720),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    start_dt, end_dt, effective_since_hours = _resolve_time_window(
        since_hours=since_hours,
        start_time=start_time,
        end_time=end_time,
    )
    entries, _total, _summary = repo.search(
        since_hours=effective_since_hours,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit * 2,
    )
    filtered = [
        entry
        for entry in entries
        if entry.actor_type in {"mcp", "system"}
        or (
            isinstance(entry.metadata_json, dict)
            and "actor_roles" in entry.metadata_json
            and "admin" in [str(role).lower() for role in entry.metadata_json["actor_roles"]]
        )
    ]
    filtered = filtered[:limit]
    items = [_to_entry(entry) for entry in filtered]
    summary = _summarize(filtered)
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=effective_since_hours,
            total_count=len(filtered),
            returned_count=len(items),
            time_window=MCPTimeWindow(start=start_dt, end=end_dt),
        ),
        summary=summary,
        entries=items,
    )
