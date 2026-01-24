"""MCP Admin endpoints for search analytics."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.core.enums import PermissionName
from app.dependencies.permissions import require_all_permissions
from app.models.user import User
from app.schemas.mcp import (
    MCPActor,
    MCPDateWindow,
    MCPMeta,
    MCPTopQueriesData,
    MCPTopQueriesResponse,
    MCPTopQuery,
    MCPZeroResultQuery,
    MCPZeroResultsData,
    MCPZeroResultsResponse,
)
from app.services.mcp_search_analytics_service import MCPSearchAnalyticsService

router = APIRouter(tags=["MCP Admin - Search"])


def _resolve_date_range(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end_value = end_date or datetime.now(timezone.utc).date()
    start_value = start_date or (end_value - timedelta(days=29))
    if start_value > end_value:
        raise HTTPException(status_code=400, detail="start_date_after_end_date")
    return start_value, end_value


@router.get("/top-queries", response_model=MCPTopQueriesResponse)
async def get_top_queries(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    min_count: int = Query(default=2, ge=1, le=1000),
    current_user: User = Depends(
        require_all_permissions(PermissionName.MCP_ACCESS, PermissionName.ADMIN_READ)
    ),
    db: Session = Depends(get_db),
) -> MCPTopQueriesResponse:
    start_value, end_value = _resolve_date_range(start_date, end_date)

    service = MCPSearchAnalyticsService(db)
    payload = await asyncio.to_thread(
        service.get_top_queries,
        start_date=start_value,
        end_date=end_value,
        limit=limit,
        min_count=min_count,
    )

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    queries = [MCPTopQuery(**row) for row in payload.get("queries", [])]

    return MCPTopQueriesResponse(
        meta=meta,
        data=MCPTopQueriesData(
            time_window=MCPDateWindow(start=start_value, end=end_value),
            queries=queries,
            total_searches=int(payload.get("total_searches", 0)),
        ),
    )


@router.get("/zero-results", response_model=MCPZeroResultsResponse)
async def get_zero_result_queries(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(
        require_all_permissions(PermissionName.MCP_ACCESS, PermissionName.ADMIN_READ)
    ),
    db: Session = Depends(get_db),
) -> MCPZeroResultsResponse:
    start_value, end_value = _resolve_date_range(start_date, end_date)

    service = MCPSearchAnalyticsService(db)
    payload = await asyncio.to_thread(
        service.get_zero_result_queries,
        start_date=start_value,
        end_date=end_value,
        limit=limit,
    )

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    queries = [MCPZeroResultQuery(**row) for row in payload.get("queries", [])]

    return MCPZeroResultsResponse(
        meta=meta,
        data=MCPZeroResultsData(
            time_window=MCPDateWindow(start=start_value, end=end_value),
            queries=queries,
            total_zero_result_searches=int(payload.get("total_zero_result_searches", 0)),
            zero_result_rate=float(payload.get("zero_result_rate", 0.0)),
        ),
    )
