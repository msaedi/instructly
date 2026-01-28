"""
MCP Admin endpoints for founding instructor funnel analytics.

All endpoints require a valid MCP service token.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.mcp import (
    MCPActor,
    MCPConversionRate,
    MCPFoundingCap,
    MCPFunnelStage,
    MCPFunnelSummaryResponse,
    MCPMeta,
    MCPStuckInstructor,
    MCPStuckResponse,
    MCPStuckSummary,
    MCPTimeWindow,
)
from app.services.instructor_lifecycle_service import InstructorLifecycleService
from app.services.timezone_service import TimezoneService

router = APIRouter(tags=["MCP Admin - Founding"])


def _window_start(value: date | None) -> datetime | None:
    if value is None:
        return None
    return TimezoneService.local_to_utc(value, time.min, "UTC")


def _window_end(value: date | None) -> datetime | None:
    if value is None:
        return None
    return TimezoneService.local_to_utc(value, time.max, "UTC")


@router.get(
    "/funnel",
    response_model=MCPFunnelSummaryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_funnel_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPFunnelSummaryResponse:
    """
    Get founding instructor funnel summary.

    Returns stage counts, conversion rates, and founding cap status.
    """
    service = InstructorLifecycleService(db)
    start_dt = _window_start(start_date)
    end_dt = _window_end(end_date)
    summary = service.get_funnel_summary(start_date=start_dt, end_date=end_dt)

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(
            id=principal.id,
            email=principal.identifier,
            principal_type=principal.principal_type,
        ),
    )

    stages = [MCPFunnelStage(**stage) for stage in summary.get("stages", [])]
    conversions = [MCPConversionRate(**rate) for rate in summary.get("conversion_rates", [])]
    founding_cap = MCPFoundingCap(**summary.get("founding_cap", {}))
    window = summary.get("time_window", {})

    return MCPFunnelSummaryResponse(
        meta=meta,
        stages=stages,
        conversion_rates=conversions,
        founding_cap=founding_cap,
        time_window=MCPTimeWindow(start=window.get("start"), end=window.get("end")),
    )


@router.get(
    "/stuck",
    response_model=MCPStuckResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_stuck_instructors(
    stuck_days: int = Query(default=7, ge=1, le=90),
    stage: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPStuckResponse:
    """
    Get instructors stuck in onboarding.

    Returns summary by stage and list of stuck instructors.
    """
    service = InstructorLifecycleService(db)
    payload = service.get_stuck_instructors(
        stuck_days=stuck_days,
        stage=stage,
        limit=limit,
    )

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(
            id=principal.id,
            email=principal.identifier,
            principal_type=principal.principal_type,
        ),
    )

    summary = [MCPStuckSummary(**row) for row in payload.get("summary", [])]
    instructors = [
        MCPStuckInstructor(
            user_id=row.get("user_id", ""),
            name=row.get("name", ""),
            email=row.get("email", ""),
            current_stage=row.get("stage", ""),
            days_in_stage=row.get("days_stuck", 0),
            occurred_at=row.get("occurred_at"),
        )
        for row in payload.get("instructors", [])
    ]

    return MCPStuckResponse(
        meta=meta,
        summary=summary,
        instructors=instructors,
        total_stuck=int(payload.get("total_stuck", 0)),
    )
