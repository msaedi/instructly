"""MCP audit log endpoints for governance and debugging."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query
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


@router.get("/search", response_model=AuditSearchResponse)
async def audit_search(
    actor_email: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since_hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    entries, total, summary = repo.search(
        actor_email=actor_email,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        since_hours=since_hours,
        limit=limit,
    )

    items = [_to_entry(entry) for entry in entries]
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=since_hours,
            total_count=total,
            returned_count=len(items),
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
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    since_hours = since_days * 24
    repo = RepositoryFactory.create_governance_audit_repository(db)
    entries, total, summary = repo.search(
        actor_email=user_email,
        since_hours=since_hours,
        limit=limit,
    )
    items = [_to_entry(entry) for entry in entries]
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=since_hours,
            total_count=total,
            returned_count=len(items),
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
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    entries = list(
        repo.list_by_resource(resource_type=resource_type, resource_id=resource_id, limit=limit)
    )
    items = [_to_entry(entry) for entry in entries]
    summary = _summarize(entries)
    return AuditSearchResponse(
        meta=AuditSearchMeta(
            since_hours=0,
            total_count=len(entries),
            returned_count=len(items),
        ),
        summary=summary,
        entries=items,
    )


@router.get("/admin-actions/recent", response_model=AuditSearchResponse)
async def audit_recent_admin_actions(
    since_hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AuditSearchResponse:
    repo = RepositoryFactory.create_governance_audit_repository(db)
    entries, _total, _summary = repo.search(
        since_hours=since_hours,
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
            since_hours=since_hours,
            total_count=len(filtered),
            returned_count=len(items),
        ),
        summary=summary,
        entries=items,
    )
