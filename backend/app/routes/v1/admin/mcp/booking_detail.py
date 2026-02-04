"""MCP Admin endpoint for booking detail support view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies.services import get_booking_detail_service
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_booking_detail import BookingDetailResponse
from app.services.booking_detail_service import BookingDetailService

router = APIRouter(tags=["MCP Admin - Booking Detail"])


@router.get(
    "/bookings/{booking_id}/detail",
    response_model=BookingDetailResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_booking_detail(
    booking_id: str,
    include_messages_summary: bool = False,
    include_webhooks: bool = True,
    include_trace_links: bool = False,
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    service: BookingDetailService = Depends(get_booking_detail_service),
) -> BookingDetailResponse:
    detail = service.get_booking_detail(
        booking_id=booking_id,
        include_messages_summary=include_messages_summary,
        include_webhooks=include_webhooks,
        include_trace_links=include_trace_links,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return detail


__all__ = ["router"]
