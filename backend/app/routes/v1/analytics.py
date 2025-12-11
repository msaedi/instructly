# backend/app/routes/v1/analytics.py
"""
Analytics routes for the InstaInstru platform (v1 API).

These routes provide access to analytics dashboards and data exports,
protected by RBAC permissions.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.enums import PermissionName
from ...database import get_db
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...schemas.analytics_responses import (
    CandidateCategoryTrend,
    CandidateCategoryTrendsResponse,
    CandidateScoreDistributionResponse,
    CandidateServiceQueriesResponse,
    CandidateServiceQuery,
    CandidateSummaryResponse,
    CandidateTopService,
    CandidateTopServicesResponse,
    ConversionMetricsResponse,
    DailySearchTrend,
    ExportAnalyticsResponse,
    PopularSearch,
    PopularSearchesResponse,
    SearchAnalyticsSummaryResponse,
    SearchPerformanceResponse,
    SearchReferrer,
    SearchReferrersResponse,
    SearchTrendsResponse,
)
from ...services.search_analytics_service import SearchAnalyticsService

router = APIRouter(tags=["analytics"])
logger = logging.getLogger(__name__)


def get_search_analytics_service(db: Session = Depends(get_db)) -> SearchAnalyticsService:
    """Get an instance of the search analytics service."""
    return SearchAnalyticsService(db)


@router.get("/search/search-trends", response_model=SearchTrendsResponse)
async def get_search_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> SearchTrendsResponse:
    """
    Get search trends over time.

    Returns daily search counts, unique users, and unique guests.
    """
    trends = await asyncio.to_thread(service.get_search_trends, days)

    return SearchTrendsResponse(
        [
            DailySearchTrend(
                date=trend.date.isoformat(),
                total_searches=trend.total_searches,
                unique_users=trend.unique_users,
                unique_guests=trend.unique_guests,
            )
            for trend in trends
        ]
    )


@router.get("/search/popular-searches", response_model=PopularSearchesResponse)
async def get_popular_searches(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> PopularSearchesResponse:
    """
    Get most popular search queries.

    Returns search queries ordered by frequency with user counts and average results.
    """
    searches = await asyncio.to_thread(service.get_popular_searches, days, limit)

    return PopularSearchesResponse(
        [
            PopularSearch(
                query=search.query,
                search_count=search.search_count,
                unique_users=search.unique_users,
                average_results=search.average_results,
            )
            for search in searches
        ]
    )


@router.get("/search/referrers", response_model=SearchReferrersResponse)
async def get_search_referrers(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> SearchReferrersResponse:
    """
    Get pages that drive searches (referrers).

    Returns referrer pages with search counts and unique sessions.
    """
    referrers = await asyncio.to_thread(service.get_search_referrers, days)

    return SearchReferrersResponse(
        [
            SearchReferrer(
                page=referrer.referrer,
                search_count=referrer.search_count,
                unique_sessions=referrer.unique_sessions,
                search_types=[],  # Simplified for database compatibility
            )
            for referrer in referrers
        ]
    )


@router.get("/search/search-analytics-summary", response_model=SearchAnalyticsSummaryResponse)
async def get_search_analytics_summary(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> SearchAnalyticsSummaryResponse:
    """
    Get comprehensive search analytics summary.

    Returns totals, user breakdown, search types, conversions, and performance metrics.
    """
    summary = await asyncio.to_thread(service.get_search_analytics_summary, days)

    return SearchAnalyticsSummaryResponse(
        date_range=summary["date_range"],
        totals=summary["totals"],
        users=summary["users"],
        search_types=summary["search_types"],
        conversions=summary["conversions"],
        performance=summary["performance"],
    )


@router.get("/search/conversion-metrics", response_model=ConversionMetricsResponse)
async def get_conversion_metrics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> ConversionMetricsResponse:
    """
    Get guest-to-user conversion metrics.

    Returns conversion rates and guest engagement data.
    """
    metrics = await asyncio.to_thread(service.get_conversion_metrics, days)

    return ConversionMetricsResponse(
        period=metrics["period"],
        guest_sessions=metrics["guest_sessions"],
        conversion_behavior=metrics["conversion_behavior"],
        guest_engagement=metrics["guest_engagement"],
    )


@router.get("/search/search-performance", response_model=SearchPerformanceResponse)
async def get_search_performance(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> SearchPerformanceResponse:
    """
    Get search performance metrics.

    Returns result distribution, effectiveness metrics, and problematic queries.
    """
    performance = await asyncio.to_thread(service.get_search_performance, days)

    return SearchPerformanceResponse(
        result_distribution=performance["result_distribution"],
        effectiveness=performance["effectiveness"],
        problematic_queries=performance["problematic_queries"],
    )


@router.post("/export", response_model=ExportAnalyticsResponse)
async def export_analytics(
    format: str = "csv",
    current_user: User = Depends(require_permission(PermissionName.EXPORT_ANALYTICS)),
) -> ExportAnalyticsResponse:
    """
    Export analytics data in various formats.

    Requires EXPORT_ANALYTICS permission.

    Args:
        format: Export format (csv, xlsx, json)
        current_user: The authenticated user with required permissions

    Returns:
        Exported data or download link
    """
    return ExportAnalyticsResponse(
        message="Export analytics endpoint",
        format=format,
        user=current_user.email,
        status="Not implemented",
        download_url=None,
    )


# ===== Observability Candidates Analytics =====


@router.get("/search/candidates/summary", response_model=CandidateSummaryResponse)
async def candidates_summary(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> CandidateSummaryResponse:
    """Get summary statistics for search candidates."""
    summary = await asyncio.to_thread(service.get_candidate_summary, days)

    return CandidateSummaryResponse(
        total_candidates=summary["total_candidates"],
        events_with_candidates=summary["events_with_candidates"],
        avg_candidates_per_event=summary["avg_candidates_per_event"],
        zero_result_events_with_candidates=summary["zero_result_events_with_candidates"],
        source_breakdown=summary["source_breakdown"],
    )


@router.get("/search/candidates/category-trends", response_model=CandidateCategoryTrendsResponse)
async def candidates_category_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> CandidateCategoryTrendsResponse:
    """Get candidate counts by date and category."""
    trends = await asyncio.to_thread(service.get_candidate_category_trends, days)

    return CandidateCategoryTrendsResponse(
        [
            CandidateCategoryTrend(date=t["date"], category=t["category"], count=t["count"])
            for t in trends
        ]
    )


@router.get("/search/candidates/top-services", response_model=CandidateTopServicesResponse)
async def candidates_top_services(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> CandidateTopServicesResponse:
    """Get top services by candidate count."""
    services_data = await asyncio.to_thread(service.get_candidate_top_services, days, limit)

    return CandidateTopServicesResponse(
        [
            CandidateTopService(
                service_catalog_id=s["service_catalog_id"],
                service_name=s["service_name"],
                category_name=s["category_name"],
                candidate_count=s["candidate_count"],
                avg_score=s["avg_score"],
                avg_position=s["avg_position"],
                active_instructors=s["active_instructors"],
                opportunity_score=s["opportunity_score"],
            )
            for s in services_data
        ]
    )


@router.get(
    "/search/candidates/score-distribution", response_model=CandidateScoreDistributionResponse
)
async def candidates_score_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> CandidateScoreDistributionResponse:
    """Get candidate score distribution."""
    distribution = await asyncio.to_thread(service.get_candidate_score_distribution, days)

    return CandidateScoreDistributionResponse(
        gte_0_90=distribution["gte_0_90"],
        gte_0_80_lt_0_90=distribution["gte_0_80_lt_0_90"],
        gte_0_70_lt_0_80=distribution["gte_0_70_lt_0_80"],
        lt_0_70=distribution["lt_0_70"],
    )


@router.get("/search/candidates/queries", response_model=CandidateServiceQueriesResponse)
async def candidate_service_queries(
    service_catalog_id: str,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    analytics_service: SearchAnalyticsService = Depends(get_search_analytics_service),
) -> CandidateServiceQueriesResponse:
    """List queries that produced candidates for a given service (recent first)."""
    queries = await asyncio.to_thread(
        analytics_service.get_candidate_service_queries, service_catalog_id, days, limit
    )

    return CandidateServiceQueriesResponse(
        [
            CandidateServiceQuery(
                searched_at=q["searched_at"],
                search_query=q["search_query"],
                results_count=q["results_count"],
                position=q["position"],
                score=q["score"],
                source=q["source"],
            )
            for q in queries
        ]
    )
