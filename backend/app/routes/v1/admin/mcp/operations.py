"""
MCP Admin endpoints for operations (bookings, payments, user support).

All endpoints require a valid MCP service token with mcp:read scope.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_ops import (
    AdminBookingSummary,
    BookingListItem,
    BookingSummaryResponse,
    PaymentPipelineResponse,
    PendingPayoutItem,
    PendingPayoutsResponse,
    RecentBookingsResponse,
    TopCategory,
    UserBookingHistoryResponse,
    UserInfo,
    UserLookupResponse,
)
from app.services.admin_ops_service import AdminOpsService

router = APIRouter(tags=["MCP Admin - Operations"])


# ==================== Bookings ====================


class BookingPeriod(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_7_DAYS = "last_7_days"
    THIS_MONTH = "this_month"


@router.get(
    "/bookings/summary",
    response_model=BookingSummaryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_booking_summary(
    period: BookingPeriod = Query(
        default=BookingPeriod.TODAY,
        description="Time period: today, yesterday, this_week, last_7_days, this_month",
    ),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> BookingSummaryResponse:
    """
    Get booking summary for a time period.

    Returns total bookings, revenue, breakdown by status, and top categories.
    """
    service = AdminOpsService(db)
    result = await service.get_booking_summary(period=period.value)

    summary_data = result["summary"]
    top_categories = [TopCategory(**tc) for tc in summary_data["top_categories"]]

    return BookingSummaryResponse(
        summary=AdminBookingSummary(
            period=summary_data["period"],
            total_bookings=summary_data["total_bookings"],
            by_status=summary_data["by_status"],
            total_revenue_cents=summary_data["total_revenue_cents"],
            avg_booking_value_cents=summary_data["avg_booking_value_cents"],
            new_students=summary_data["new_students"],
            repeat_students=summary_data["repeat_students"],
            top_categories=top_categories,
        ),
        checked_at=result["checked_at"],
    )


@router.get(
    "/bookings/recent",
    response_model=RecentBookingsResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_recent_bookings(
    status: str
    | None = Query(
        default=None,
        description="Filter by status: confirmed, completed, cancelled, pending",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Max results (max 100)"),
    hours: int = Query(
        default=24, ge=1, le=168, description="Look back window in hours (max 168 = 1 week)"
    ),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> RecentBookingsResponse:
    """
    Get recent bookings with optional filters.

    Returns a list of bookings with privacy-safe names.
    """
    service = AdminOpsService(db)
    result = await service.get_recent_bookings(status=status, limit=limit, hours=hours)

    bookings = [BookingListItem(**b) for b in result["bookings"]]

    return RecentBookingsResponse(
        bookings=bookings,
        count=result["count"],
        filters_applied=result["filters_applied"],
        checked_at=result["checked_at"],
    )


# ==================== Payments ====================


@router.get(
    "/payments/pipeline",
    response_model=PaymentPipelineResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_payment_pipeline(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> PaymentPipelineResponse:
    """
    Get payment pipeline status.

    Returns counts of payments in each state, alerts, and revenue metrics.
    """
    service = AdminOpsService(db)
    result = await service.get_payment_pipeline()

    return PaymentPipelineResponse(
        pending_authorization=result["pending_authorization"],
        authorized=result["authorized"],
        pending_capture=result["pending_capture"],
        captured=result["captured"],
        failed=result["failed"],
        refunded=result["refunded"],
        overdue_authorizations=result["overdue_authorizations"],
        overdue_captures=result["overdue_captures"],
        total_captured_cents=result["total_captured_cents"],
        total_refunded_cents=result["total_refunded_cents"],
        net_revenue_cents=result["net_revenue_cents"],
        platform_fees_cents=result["platform_fees_cents"],
        instructor_payouts_cents=result["instructor_payouts_cents"],
        checked_at=result["checked_at"],
    )


@router.get(
    "/payments/pending-payouts",
    response_model=PendingPayoutsResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_pending_payouts(
    limit: int = Query(default=20, ge=1, le=100, description="Max results (max 100)"),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> PendingPayoutsResponse:
    """
    Get instructors with pending payouts.

    Returns instructors awaiting transfer with amount and lesson count.
    """
    service = AdminOpsService(db)
    result = await service.get_pending_payouts(limit=limit)

    payouts = [PendingPayoutItem(**p) for p in result["payouts"]]

    return PendingPayoutsResponse(
        payouts=payouts,
        total_pending_cents=result["total_pending_cents"],
        instructor_count=result["instructor_count"],
        checked_at=result["checked_at"],
    )


# ==================== Users ====================


@router.get(
    "/users/lookup",
    response_model=UserLookupResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def lookup_user(
    identifier: str = Query(description="Email, phone number, or user ID"),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> UserLookupResponse:
    """
    Look up a user by email, phone, or ID.

    Returns user profile and stats for support purposes.
    Full name is shown (admin access).
    """
    service = AdminOpsService(db)
    result = await service.lookup_user(identifier=identifier)

    user_info = None
    if result["user"]:
        user_info = UserInfo(**result["user"])

    return UserLookupResponse(
        found=result["found"],
        user=user_info,
        checked_at=result["checked_at"],
    )


@router.get(
    "/users/{user_id}/bookings",
    response_model=UserBookingHistoryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_user_booking_history(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max results (max 100)"),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> UserBookingHistoryResponse:
    """
    Get a user's booking history.

    Returns bookings as student or instructor depending on user role.
    """
    service = AdminOpsService(db)
    result = await service.get_user_booking_history(user_id=user_id, limit=limit)

    bookings = [BookingListItem(**b) for b in result["bookings"]]

    return UserBookingHistoryResponse(
        user_id=result["user_id"],
        user_name=result["user_name"],
        user_role=result["user_role"],
        bookings=bookings,
        total_count=result["total_count"],
        checked_at=result["checked_at"],
    )
