# backend/app/routes/analytics.py
"""
Analytics routes for the InstaInstru platform.

These routes provide access to analytics dashboards and data exports,
protected by RBAC permissions.
"""

from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import literal

from ..core.enums import PermissionName
from ..database import get_db
from ..dependencies.permissions import require_permission
from ..models.search_event import SearchEvent, SearchEventCandidate
from ..models.search_history import SearchHistory
from ..models.user import User
from ..schemas.analytics_responses import (
    CandidateCategoryTrend,
    CandidateCategoryTrendsResponse,
    CandidateScoreDistributionResponse,
    CandidateServiceQueriesResponse,
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

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.get("/search/search-trends", response_model=SearchTrendsResponse)
async def get_search_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> SearchTrendsResponse:
    """
    Get search trends over time.

    Returns daily search counts, unique users, and unique guests.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    # Query search events grouped by date
    search_trends = (
        db.query(
            func.date(SearchEvent.searched_at).label("date"),
            func.count(SearchEvent.id).label("total_searches"),
            func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
            func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
        )
        .filter(
            and_(
                func.date(SearchEvent.searched_at) >= start_date,
                func.date(SearchEvent.searched_at) <= end_date,
            )
        )
        .group_by(func.date(SearchEvent.searched_at))
        .order_by(func.date(SearchEvent.searched_at))
        .all()
    )

    return SearchTrendsResponse(
        [
            DailySearchTrend(
                date=trend.date.isoformat(),
                total_searches=trend.total_searches,
                unique_users=trend.unique_users or 0,
                unique_guests=trend.unique_guests or 0,
            )
            for trend in search_trends
        ]
    )


@router.get("/search/popular-searches", response_model=PopularSearchesResponse)
async def get_popular_searches(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> PopularSearchesResponse:
    """
    Get most popular search queries.

    Returns search queries ordered by frequency with user counts and average results.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    # Query popular searches from search events
    popular_searches = (
        db.query(
            SearchEvent.search_query,
            func.count(SearchEvent.id).label("search_count"),
            func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
            func.avg(SearchEvent.results_count).label("average_results"),
        )
        .filter(
            and_(
                func.date(SearchEvent.searched_at) >= start_date,
                func.date(SearchEvent.searched_at) <= end_date,
                SearchEvent.search_query.isnot(None),
                SearchEvent.search_query != "",
            )
        )
        .group_by(SearchEvent.search_query)
        .order_by(desc("search_count"))
        .limit(limit)
        .all()
    )

    return PopularSearchesResponse(
        [
            PopularSearch(
                query=search.search_query,
                search_count=search.search_count,
                unique_users=search.unique_users or 0,
                average_results=round(search.average_results or 0, 2),
            )
            for search in popular_searches
        ]
    )


@router.get("/search/referrers", response_model=SearchReferrersResponse)
async def get_search_referrers(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> SearchReferrersResponse:
    """
    Get pages that drive searches (referrers).

    Returns referrer pages with search counts and unique sessions.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    # Query referrers
    referrers = (
        db.query(
            SearchEvent.referrer,
            func.count(SearchEvent.id).label("search_count"),
            func.count(func.distinct(SearchEvent.session_id)).label("unique_sessions"),
            # Skip search_types aggregation for database compatibility
        )
        .filter(
            and_(
                func.date(SearchEvent.searched_at) >= start_date,
                func.date(SearchEvent.searched_at) <= end_date,
                SearchEvent.referrer.isnot(None),
                SearchEvent.referrer != "",
            )
        )
        .group_by(SearchEvent.referrer)
        .order_by(desc("search_count"))
        .all()
    )

    return SearchReferrersResponse(
        [
            SearchReferrer(
                page=referrer.referrer,
                search_count=referrer.search_count,
                unique_sessions=referrer.unique_sessions or 0,
                search_types=[],  # Simplified for database compatibility
            )
            for referrer in referrers
        ]
    )


@router.get("/search/search-analytics-summary", response_model=SearchAnalyticsSummaryResponse)
async def get_search_analytics_summary(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> SearchAnalyticsSummaryResponse:
    """
    Get comprehensive search analytics summary.

    Returns totals, user breakdown, search types, conversions, and performance metrics.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    # Base filter for date range
    date_filter = and_(
        func.date(SearchEvent.searched_at) >= start_date,
        func.date(SearchEvent.searched_at) <= end_date,
    )

    # Total searches and users
    totals = (
        db.query(
            func.count(SearchEvent.id).label("total_searches"),
            func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
            func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
            func.avg(SearchEvent.results_count).label("avg_results"),
        )
        .filter(date_filter)
        .first()
    )

    # Search types breakdown
    search_types_query = (
        db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
        .filter(date_filter)
        .group_by(SearchEvent.search_type)
        .all()
    )

    total_searches = totals.total_searches or 0
    search_types = {}
    for st in search_types_query:
        search_types[st.search_type] = {
            "count": st.count,
            "percentage": round((st.count / total_searches * 100) if total_searches > 0 else 0, 2),
        }

    # Deleted searches from search history
    deleted_searches = (
        db.query(func.count(SearchHistory.id))
        .filter(
            and_(
                SearchHistory.deleted_at.isnot(None),
                func.date(SearchHistory.deleted_at) >= start_date,
                func.date(SearchHistory.deleted_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    # Guest conversions
    guest_sessions = (
        db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    converted_guests = (
        db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                SearchHistory.converted_to_user_id.isnot(None),
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    # Zero result rate
    zero_results = (
        db.query(func.count(SearchEvent.id))
        .filter(and_(date_filter, SearchEvent.results_count == 0))
        .scalar()
        or 0
    )

    # Most effective search type
    most_effective = (
        db.query(SearchEvent.search_type, func.avg(SearchEvent.results_count).label("avg_results"))
        .filter(and_(date_filter, SearchEvent.results_count.isnot(None)))
        .group_by(SearchEvent.search_type)
        .order_by(desc("avg_results"))
        .first()
    )

    unique_users = totals.unique_users or 0
    unique_guests = totals.unique_guests or 0
    total_users = unique_users + unique_guests

    return SearchAnalyticsSummaryResponse(
        date_range={"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
        totals={
            "total_searches": total_searches,
            "unique_users": unique_users,
            "unique_guests": unique_guests,
            "total_users": total_users,
            "deleted_searches": deleted_searches,
            "deletion_rate": round(
                (deleted_searches / total_searches * 100) if total_searches > 0 else 0, 2
            ),
        },
        users={
            "authenticated": unique_users,
            "guests": unique_guests,
            "converted_guests": converted_guests,
            "user_percentage": round(
                (unique_users / total_users * 100) if total_users > 0 else 0, 2
            ),
            "guest_percentage": round(
                (unique_guests / total_users * 100) if total_users > 0 else 0, 2
            ),
        },
        search_types=search_types,
        conversions={
            "guest_sessions": {
                "total": guest_sessions,
                "converted": converted_guests,
                "conversion_rate": round(
                    (converted_guests / guest_sessions * 100) if guest_sessions > 0 else 0, 2
                ),
            },
            "conversion_behavior": {
                "avg_searches_before_conversion": 0,  # Would need more complex query
                "avg_days_to_conversion": 0,  # Would need more complex query
                "most_common_first_search": "",  # Would need more complex query
            },
        },
        performance={
            "avg_results_per_search": round(totals.avg_results or 0, 2),
            "zero_result_rate": round(
                (zero_results / total_searches * 100) if total_searches > 0 else 0, 2
            ),
            "most_effective_type": most_effective.search_type if most_effective else "",
        },
    )


@router.get("/search/conversion-metrics", response_model=ConversionMetricsResponse)
async def get_conversion_metrics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> ConversionMetricsResponse:
    """
    Get guest-to-user conversion metrics.

    Returns conversion rates and guest engagement data.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    # Guest sessions and conversions
    guest_sessions = (
        db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    converted_guests = (
        db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                SearchHistory.converted_to_user_id.isnot(None),
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    # Guest engagement (sessions with multiple searches)
    engaged_sessions = (
        db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                SearchHistory.search_count > 1,
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    # Average searches per guest session
    avg_searches = (
        db.query(func.avg(SearchHistory.search_count))
        .filter(
            and_(
                SearchHistory.guest_session_id.isnot(None),
                func.date(SearchHistory.first_searched_at) >= start_date,
                func.date(SearchHistory.first_searched_at) <= end_date,
            )
        )
        .scalar()
        or 0
    )

    return ConversionMetricsResponse(
        period={"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
        guest_sessions={
            "total": guest_sessions,
            "converted": converted_guests,
            "conversion_rate": round(
                (converted_guests / guest_sessions * 100) if guest_sessions > 0 else 0, 2
            ),
        },
        conversion_behavior={
            "avg_searches_before_conversion": 0,  # Would need more complex query
            "avg_days_to_conversion": 0,  # Would need more complex query
            "most_common_first_search": "",  # Would need more complex query
        },
        guest_engagement={
            "avg_searches_per_session": round(avg_searches, 2),
            "engaged_sessions": engaged_sessions,
            "engagement_rate": round(
                (engaged_sessions / guest_sessions * 100) if guest_sessions > 0 else 0, 2
            ),
        },
    )


@router.get("/search/search-performance", response_model=SearchPerformanceResponse)
async def get_search_performance(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> SearchPerformanceResponse:
    """
    Get search performance metrics.

    Returns result distribution, effectiveness metrics, and problematic queries.
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    date_filter = and_(
        func.date(SearchEvent.searched_at) >= start_date,
        func.date(SearchEvent.searched_at) <= end_date,
        SearchEvent.results_count.isnot(None),
    )

    # Result distribution
    zero_results = (
        db.query(func.count(SearchEvent.id))
        .filter(date_filter, SearchEvent.results_count == 0)
        .scalar()
        or 0
    )

    one_to_five = (
        db.query(func.count(SearchEvent.id))
        .filter(date_filter, SearchEvent.results_count.between(1, 5))
        .scalar()
        or 0
    )

    six_to_ten = (
        db.query(func.count(SearchEvent.id))
        .filter(date_filter, SearchEvent.results_count.between(6, 10))
        .scalar()
        or 0
    )

    over_ten = (
        db.query(func.count(SearchEvent.id))
        .filter(date_filter, SearchEvent.results_count > 10)
        .scalar()
        or 0
    )

    # Effectiveness metrics
    effectiveness = (
        db.query(
            func.avg(SearchEvent.results_count).label("avg_results"),
            func.count(SearchEvent.id).label("total_searches"),
        )
        .filter(date_filter)
        .first()
    )

    searches_with_results = (
        db.query(func.count(SearchEvent.id))
        .filter(date_filter, SearchEvent.results_count > 0)
        .scalar()
        or 0
    )

    # Median results (approximation using avg as fallback)
    # Note: Using avg as approximation since median is database-specific
    median_results = effectiveness.avg_results or 0

    # Problematic queries (low average results)
    problematic_queries = (
        db.query(
            SearchEvent.search_query,
            func.count(SearchEvent.id).label("count"),
            func.avg(SearchEvent.results_count).label("avg_results"),
        )
        .filter(
            and_(date_filter, SearchEvent.search_query.isnot(None), SearchEvent.search_query != "")
        )
        .group_by(SearchEvent.search_query)
        .having(func.count(SearchEvent.id) >= 5)  # Only queries with at least 5 searches
        .order_by(func.avg(SearchEvent.results_count))
        .limit(10)
        .all()
    )

    total_searches = effectiveness.total_searches or 0

    return SearchPerformanceResponse(
        result_distribution={
            "zero_results": zero_results,
            "1_5_results": one_to_five,
            "6_10_results": six_to_ten,
            "over_10_results": over_ten,
        },
        effectiveness={
            "avg_results_per_search": round(effectiveness.avg_results or 0, 2),
            "median_results": round(median_results, 2),
            "searches_with_results": searches_with_results,
            "zero_result_rate": round(
                (zero_results / total_searches * 100) if total_searches > 0 else 0, 2
            ),
        },
        problematic_queries=[
            {
                "query": query.search_query,
                "count": query.count,
                "avg_results": round(query.avg_results or 0, 2),
            }
            for query in problematic_queries
        ],
    )


@router.post("/export", response_model=ExportAnalyticsResponse)
async def export_analytics(
    format: str = "csv",
    current_user: User = Depends(require_permission(PermissionName.EXPORT_ANALYTICS)),
    db: Session = Depends(get_db),
) -> ExportAnalyticsResponse:
    """
    Export analytics data in various formats.

    Requires EXPORT_ANALYTICS permission.

    Args:
        format: Export format (csv, xlsx, json)
        current_user: The authenticated user with required permissions
        db: Database session

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
    db: Session = Depends(get_db),
) -> CandidateSummaryResponse:
    from sqlalchemy import and_, func

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    total_candidates = (
        db.query(func.count(SearchEventCandidate.id))
        .filter(
            and_(
                SearchEventCandidate.created_at >= start_date,
                SearchEventCandidate.created_at <= end_date,
            )
        )
        .scalar()
        or 0
    )

    events_with_candidates = (
        db.query(func.count(func.distinct(SearchEventCandidate.search_event_id)))
        .filter(
            and_(
                SearchEventCandidate.created_at >= start_date,
                SearchEventCandidate.created_at <= end_date,
            )
        )
        .scalar()
        or 0
    )

    avg_candidates_per_event = 0.0
    if events_with_candidates > 0:
        avg_candidates_per_event = round(total_candidates / float(events_with_candidates), 2)

    zero_result_events_with_candidates = (
        db.query(func.count(func.distinct(SearchEventCandidate.search_event_id)))
        .join(SearchEvent, SearchEvent.id == SearchEventCandidate.search_event_id)
        .filter(
            and_(
                SearchEventCandidate.created_at >= start_date,
                SearchEventCandidate.created_at <= end_date,
                SearchEvent.results_count == 0,
            )
        )
        .scalar()
        or 0
    )

    # Source breakdown
    rows = (
        db.query(SearchEventCandidate.source, func.count(SearchEventCandidate.id))
        .filter(
            and_(
                SearchEventCandidate.created_at >= start_date,
                SearchEventCandidate.created_at <= end_date,
            )
        )
        .group_by(SearchEventCandidate.source)
        .all()
    )
    source_breakdown = {r[0] or "unknown": r[1] for r in rows}

    return CandidateSummaryResponse(
        total_candidates=total_candidates,
        events_with_candidates=events_with_candidates,
        avg_candidates_per_event=avg_candidates_per_event,
        zero_result_events_with_candidates=zero_result_events_with_candidates,
        source_breakdown=source_breakdown,
    )


@router.get("/search/candidates/category-trends", response_model=CandidateCategoryTrendsResponse)
async def candidates_category_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> CandidateCategoryTrendsResponse:
    from sqlalchemy import and_, func

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Count candidates per day per category via join to service_catalog -> service_categories
    from ..models.service_catalog import ServiceCatalog, ServiceCategory

    date_expr = func.date(SearchEventCandidate.created_at)
    category_expr = func.coalesce(ServiceCategory.name, literal("unknown"))

    try:
        rows = (
            db.query(
                date_expr.label("date"),
                category_expr.label("category"),
                func.count(SearchEventCandidate.id).label("count"),
            )
            .select_from(SearchEventCandidate)
            .outerjoin(ServiceCatalog, ServiceCatalog.id == SearchEventCandidate.service_catalog_id)
            .outerjoin(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
            .filter(
                and_(
                    SearchEventCandidate.created_at >= start_date,
                    SearchEventCandidate.created_at <= end_date,
                )
            )
            .group_by(date_expr, category_expr)
            .order_by(date_expr)
            .all()
        )
    except Exception as e:
        logger.error(f"candidates_category_trends query failed: {e}", exc_info=True)
        rows = []

    # Fallback simple by day without category if query failed or returned no rows
    if not rows:
        rows = (
            db.query(
                func.date(SearchEventCandidate.created_at).label("date"),
                literal("unknown").label("category"),
                func.count(SearchEventCandidate.id).label("count"),
            )
            .filter(
                and_(
                    SearchEventCandidate.created_at >= start_date,
                    SearchEventCandidate.created_at <= end_date,
                )
            )
            .group_by(func.date(SearchEventCandidate.created_at))
            .order_by(func.date(SearchEventCandidate.created_at))
            .all()
        )

    return CandidateCategoryTrendsResponse(
        [CandidateCategoryTrend(date=str(r.date), category=r.category, count=r.count) for r in rows]
    )


@router.get("/search/candidates/top-services", response_model=CandidateTopServicesResponse)
async def candidates_top_services(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> CandidateTopServicesResponse:
    from sqlalchemy import and_, func

    from ..models.service_catalog import ServiceCatalog, ServiceCategory

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    rows = (
        db.query(
            SearchEventCandidate.service_catalog_id,
            ServiceCatalog.name.label("service_name"),
            ServiceCategory.name.label("category_name"),
            func.count(SearchEventCandidate.id).label("candidate_count"),
            func.avg(func.coalesce(SearchEventCandidate.score, 0)).label("avg_score"),
            func.avg(SearchEventCandidate.position).label("avg_position"),
        )
        .join(ServiceCatalog, ServiceCatalog.id == SearchEventCandidate.service_catalog_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
        .filter(
            and_(
                SearchEventCandidate.created_at >= start_date,
                SearchEventCandidate.created_at <= end_date,
            )
        )
        .group_by(
            SearchEventCandidate.service_catalog_id, ServiceCatalog.name, ServiceCategory.name
        )
        .order_by(func.count(SearchEventCandidate.id).desc())
        .limit(limit)
        .all()
    )

    # Supply: active instructor count per service
    service_ids = [r.service_catalog_id for r in rows]
    supply_map = {}
    if service_ids:
        from ..models.service_catalog import InstructorService

        supply_rows = (
            db.query(InstructorService.service_catalog_id, func.count(InstructorService.id))
            .filter(
                InstructorService.service_catalog_id.in_(service_ids),
                InstructorService.is_active == True,
            )
            .group_by(InstructorService.service_catalog_id)
            .all()
        )
        supply_map = {sid: cnt for sid, cnt in supply_rows}

    items = []
    for r in rows:
        active_instructors = int(supply_map.get(r.service_catalog_id, 0))
        opportunity = float(r.candidate_count) / max(1, active_instructors)
        items.append(
            CandidateTopService(
                service_catalog_id=r.service_catalog_id,
                service_name=r.service_name,
                category_name=r.category_name,
                candidate_count=r.candidate_count,
                avg_score=float(r.avg_score or 0),
                avg_position=float(r.avg_position or 0),
                active_instructors=active_instructors,
                opportunity_score=round(opportunity, 2),
            )
        )

    return CandidateTopServicesResponse(items)


@router.get(
    "/search/candidates/score-distribution", response_model=CandidateScoreDistributionResponse
)
async def candidates_score_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> CandidateScoreDistributionResponse:
    from sqlalchemy import and_, func

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    def count_where(condition: ColumnElement[bool]) -> int:
        result = (
            db.query(func.count(SearchEventCandidate.id))
            .filter(
                and_(
                    SearchEventCandidate.created_at >= start_date,
                    SearchEventCandidate.created_at <= end_date,
                )
            )
            .filter(condition)
            .scalar()
        )
        return int(result or 0)

    gte_0_90 = count_where(SearchEventCandidate.score >= 0.9)
    gte_0_80_lt_0_90 = count_where(
        and_(SearchEventCandidate.score >= 0.8, SearchEventCandidate.score < 0.9)
    )
    gte_0_70_lt_0_80 = count_where(
        and_(SearchEventCandidate.score >= 0.7, SearchEventCandidate.score < 0.8)
    )
    lt_0_70 = count_where(SearchEventCandidate.score < 0.7)

    return CandidateScoreDistributionResponse(
        gte_0_90=gte_0_90,
        gte_0_80_lt_0_90=gte_0_80_lt_0_90,
        gte_0_70_lt_0_80=gte_0_70_lt_0_80,
        lt_0_70=lt_0_70,
    )


@router.get("/search/candidates/queries", response_model=CandidateServiceQueriesResponse)
async def candidate_service_queries(
    service_catalog_id: str,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
    db: Session = Depends(get_db),
) -> CandidateServiceQueriesResponse:
    """List queries that produced candidates for a given service (recent first)."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    rows = (
        db.query(
            SearchEvent.searched_at,
            SearchEvent.search_query,
            SearchEvent.results_count,
            SearchEventCandidate.position,
            SearchEventCandidate.score,
            SearchEventCandidate.source,
        )
        .join(SearchEvent, SearchEvent.id == SearchEventCandidate.search_event_id)
        .filter(
            SearchEventCandidate.service_catalog_id == service_catalog_id,
            SearchEventCandidate.created_at >= start_date,
            SearchEventCandidate.created_at <= end_date,
        )
        .order_by(SearchEvent.searched_at.desc(), SearchEventCandidate.position.asc())
        .limit(limit)
        .all()
    )

    return CandidateServiceQueriesResponse(
        [
            {
                "searched_at": r.searched_at.isoformat() if r.searched_at else "",
                "search_query": r.search_query or "",
                "results_count": r.results_count,
                "position": r.position,
                "score": float(r.score) if r.score is not None else None,
                "source": r.source,
            }
            for r in rows
        ]
    )
