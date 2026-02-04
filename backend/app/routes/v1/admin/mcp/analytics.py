"""MCP Admin endpoints for platform analytics."""

from __future__ import annotations

import asyncio
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies.services import (
    get_funnel_analytics_service,
    get_platform_analytics_service,
)
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.admin_analytics import (
    AlertCategory,
    AlertSeverity,
    BookingFunnel,
    BookingFunnelPeriod,
    CategoryPerformance,
    CategoryPerformancePeriod,
    CategorySortBy,
    CohortMetric,
    CohortPeriod,
    CohortRetention,
    CohortUserType,
    FunnelSegmentBy,
    FunnelSnapshotComparison,
    FunnelSnapshotPeriod,
    FunnelSnapshotResponse,
    PlatformAlerts,
    RevenueBreakdownBy,
    RevenueComparisonMode,
    RevenueDashboard,
    RevenuePeriod,
    SupplyDemand,
    SupplyDemandPeriod,
)
from app.services.funnel_analytics_service import FunnelAnalyticsService
from app.services.platform_analytics_service import PlatformAnalyticsService

router = APIRouter(tags=["MCP Admin - Analytics"])


def _handle_exception(exc: Exception, detail: str) -> NoReturn:
    if isinstance(exc, HTTPException):
        raise exc
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    ) from exc


@router.get(
    "/analytics/revenue",
    response_model=RevenueDashboard,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def revenue_dashboard(
    period: RevenuePeriod = Query(RevenuePeriod.LAST_7_DAYS),
    compare_to: RevenueComparisonMode | None = Query(RevenueComparisonMode.PREVIOUS_PERIOD),
    breakdown_by: RevenueBreakdownBy | None = Query(None),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> RevenueDashboard:
    try:
        return await asyncio.to_thread(
            service.revenue_dashboard,
            period=period,
            compare_to=compare_to,
            breakdown_by=breakdown_by,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_revenue_failed")


@router.get(
    "/analytics/funnel",
    response_model=BookingFunnel,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def booking_funnel(
    period: BookingFunnelPeriod = Query(BookingFunnelPeriod.LAST_7_DAYS),
    segment_by: FunnelSegmentBy | None = Query(None),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> BookingFunnel:
    try:
        return await asyncio.to_thread(
            service.booking_funnel,
            period=period,
            segment_by=segment_by,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_funnel_failed")


@router.get(
    "/funnel/snapshot",
    response_model=FunnelSnapshotResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def funnel_snapshot(
    period: FunnelSnapshotPeriod = Query(FunnelSnapshotPeriod.LAST_7_DAYS),
    compare_to: FunnelSnapshotComparison | None = Query(None),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: FunnelAnalyticsService = Depends(get_funnel_analytics_service),
) -> FunnelSnapshotResponse:
    try:
        return await asyncio.to_thread(
            service.get_funnel_snapshot,
            period=period,
            compare_to=compare_to,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_funnel_snapshot_failed")


@router.get(
    "/analytics/supply-demand",
    response_model=SupplyDemand,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def supply_demand(
    period: SupplyDemandPeriod = Query(SupplyDemandPeriod.LAST_7_DAYS),
    location: str | None = Query(None),
    category: str | None = Query(None),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> SupplyDemand:
    try:
        return await asyncio.to_thread(
            service.supply_demand,
            period=period,
            location=location,
            category=category,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_supply_demand_failed")


@router.get(
    "/analytics/categories",
    response_model=CategoryPerformance,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def category_performance(
    period: CategoryPerformancePeriod = Query(CategoryPerformancePeriod.LAST_7_DAYS),
    sort_by: CategorySortBy = Query(CategorySortBy.REVENUE),
    limit: int = Query(20, ge=1, le=100),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> CategoryPerformance:
    try:
        return await asyncio.to_thread(
            service.category_performance,
            period=period,
            sort_by=sort_by,
            limit=limit,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_category_failed")


@router.get(
    "/analytics/cohorts",
    response_model=CohortRetention,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def cohort_retention(
    user_type: CohortUserType = Query(CohortUserType.STUDENT),
    cohort_period: CohortPeriod = Query(CohortPeriod.MONTH),
    periods_back: int = Query(6, ge=1, le=24),
    metric: CohortMetric = Query(CohortMetric.ACTIVE),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> CohortRetention:
    try:
        return await asyncio.to_thread(
            service.cohort_retention,
            user_type=user_type,
            cohort_period=cohort_period,
            periods_back=periods_back,
            metric=metric,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_cohort_failed")


@router.get(
    "/analytics/alerts",
    response_model=PlatformAlerts,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def platform_alerts(
    severity: AlertSeverity | None = Query(None),
    category: AlertCategory | None = Query(None),
    acknowledged: bool = Query(False),
    _: Principal = Depends(require_mcp_scope("mcp:read")),
    service: PlatformAnalyticsService = Depends(get_platform_analytics_service),
) -> PlatformAlerts:
    try:
        return await asyncio.to_thread(
            service.platform_alerts,
            severity=severity,
            category=category,
            acknowledged=acknowledged,
        )
    except Exception as exc:
        _handle_exception(exc, "analytics_alerts_failed")


__all__ = ["router"]
