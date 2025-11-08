# backend/app/routes/admin_audit.py
"""Admin audit log routes."""

from datetime import datetime
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.authz import requires_roles
from app.api.dependencies.database import get_db
from app.monitoring.prometheus_metrics import prometheus_metrics
from app.repositories.factory import RepositoryFactory
from app.schemas.audit import AuditLogListResponse, AuditLogView

router = APIRouter(prefix="/api/admin/audit", tags=["admin-audit"])


@router.get("", response_model=AuditLogListResponse)
@requires_roles("admin")
async def list_audit_logs(
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=30)] = None,
    actor_id: Annotated[str | None, Query(max_length=26)] = None,
    actor_role: Annotated[str | None, Query(max_length=30)] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AuditLogListResponse:
    """List audit log entries with filtering and pagination."""
    start_time = monotonic()
    repository = RepositoryFactory.create_audit_repository(db)
    items, total = repository.list(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )

    views = [
        AuditLogView(
            id=item.id,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            action=item.action,
            actor_id=item.actor_id,
            actor_role=item.actor_role,
            occurred_at=item.occurred_at,
            before=item.before,
            after=item.after,
        )
        for item in items
    ]

    duration = monotonic() - start_time
    try:
        prometheus_metrics.record_audit_read(duration)
    except Exception:
        pass

    return AuditLogListResponse(items=views, total=total, limit=limit, offset=offset)
