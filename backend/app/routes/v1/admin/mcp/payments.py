"""MCP Admin endpoints for payment timelines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_payments import (
    AdminPaymentTimelineFlags,
    AdminPaymentTimelineItem,
    AdminPaymentTimelineMeta,
    AdminPaymentTimelineResponse,
    AdminPaymentTimelineSummary,
)
from app.schemas.mcp import MCPTimeWindow
from app.services.admin_ops_service import AdminOpsService

router = APIRouter(tags=["MCP Admin - Payments"])


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_time_window(
    *,
    since_hours: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if start_time:
        start = _ensure_utc(start_time)
        if end_time:
            end = _ensure_utc(end_time)
            source = (
                f"start_time={start.isoformat().replace('+00:00', 'Z')},"
                f"end_time={end.isoformat().replace('+00:00', 'Z')}"
            )
        else:
            end = now
            source = f"start_time={start.isoformat().replace('+00:00', 'Z')},end_time=now"
        if start > end:
            raise HTTPException(
                status_code=422,
                detail="start_time must be on or before end_time",
            )
        return start, end, source
    if end_time and not start_time:
        raise HTTPException(
            status_code=422,
            detail="start_time must be provided when end_time is set",
        )

    start = now - timedelta(hours=max(1, since_hours))
    end = now
    return start, end, f"since_hours={max(1, since_hours)}"


@router.get(
    "/timeline",
    response_model=AdminPaymentTimelineResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_payment_timeline(
    booking_id: str | None = Query(default=None, description="Booking ID to inspect"),
    user_id: str | None = Query(default=None, description="User ID (student) to inspect"),
    since_days: int = Query(default=30, ge=1, le=365),
    since_hours: int | None = Query(default=None, ge=1, le=8760),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> AdminPaymentTimelineResponse:
    """
    Get a redacted payment timeline for a booking or user.

    Provide either booking_id or user_id (student). Time filtering supports
    since_hours or explicit start_time/end_time.
    """
    if (booking_id and user_id) or (not booking_id and not user_id):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of booking_id or user_id",
        )

    effective_hours = since_hours if since_hours is not None else since_days * 24
    start_dt, end_dt, source = _resolve_time_window(
        since_hours=effective_hours,
        start_time=start_time,
        end_time=end_time,
    )

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=booking_id,
        user_id=user_id,
        start_time=start_dt,
        end_time=end_dt,
    )

    payments = [AdminPaymentTimelineItem(**item) for item in result["payments"]]
    summary = AdminPaymentTimelineSummary(**result["summary"])
    flags = AdminPaymentTimelineFlags(**result["flags"])

    meta = AdminPaymentTimelineMeta(
        time_window=MCPTimeWindow(start=start_dt, end=end_dt, source=source),
        total_count=result["total_count"],
    )

    return AdminPaymentTimelineResponse(
        payments=payments,
        summary=summary,
        flags=flags,
        meta=meta,
    )
