# backend/app/routes/search_analytics.py
"""
Search Analytics API endpoints.

Provides analytics endpoints for search patterns, user journeys,
and search effectiveness using the append-only search_events table.

These endpoints are typically restricted to admin/analytics roles.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..database import get_db
from ..models.user import User
from ..services.search_analytics_service import SearchAnalyticsService

router = APIRouter()


@router.get("/search-trends")
async def get_search_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    include_deleted: bool = Query(True, description="Include soft-deleted searches"),
    search_type: Optional[str] = Query(None, description="Filter by search type"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get search trends over time.

    Returns aggregated search data by day, including soft-deleted searches
    for accurate analytics.

    Args:
        days: Number of days to look back (1-365)
        include_deleted: Whether to include soft-deleted searches
        search_type: Optional filter by search type
        current_user: Must be authenticated
        db: Database session

    Returns:
        Daily search counts and trends
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_search_trends(days=days, search_type=search_type, include_deleted=include_deleted)


@router.get("/popular-searches")
async def get_popular_searches(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    search_type: Optional[str] = Query(None, description="Filter by search type"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get most popular search queries.

    Returns the most frequently searched terms based on the search_events table.

    Args:
        days: Number of days to look back
        limit: Maximum number of results
        search_type: Optional filter by search type
        current_user: Must be authenticated
        db: Database session

    Returns:
        List of popular searches with counts and unique users
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_popular_searches(days=days, limit=limit, search_type=search_type)


@router.get("/referrers")
async def get_referrer_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze which pages generate the most searches.

    Shows referrer statistics to understand which pages drive search traffic.

    Args:
        days: Number of days to look back
        current_user: Must be authenticated
        db: Database session

    Returns:
        List of pages with search counts and unique sessions
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_referrer_stats(days=days)


@router.get("/zero-results")
async def get_zero_result_searches(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Find searches that returned no results.

    Helps identify missing content or services that users are looking for.

    Args:
        days: Number of days to look back
        current_user: Must be authenticated
        db: Database session

    Returns:
        List of searches with no results and attempt counts
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_zero_result_searches(days=days)


@router.get("/session/{session_id}")
async def get_session_funnel(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get search journey for a specific session.

    Shows the complete search path for a browser session to understand user behavior.

    Args:
        session_id: Browser session ID
        current_user: Must be authenticated
        db: Database session

    Returns:
        List of searches in chronological order
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_search_funnel(session_id)


@router.get("/service-pill-performance")
async def get_service_pill_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze service pill click performance by page.

    Shows which service pills get clicked most and from which pages.

    Args:
        days: Number of days to look back
        current_user: Must be authenticated
        db: Database session

    Returns:
        Service pill performance statistics grouped by origin page
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_service_pill_performance(days=days)


@router.get("/session-conversion-rate")
async def get_session_conversion(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    min_searches: int = Query(2, ge=1, le=10, description="Minimum searches to consider a session"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze how many search sessions lead to finding what users want.

    A "successful" session is one where users stop searching after finding results.

    Args:
        days: Number of days to analyze
        min_searches: Minimum searches to consider a session
        current_user: Must be authenticated
        db: Database session

    Returns:
        Conversion metrics including success rate
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_session_conversion_rate(days=days, min_searches=min_searches)


@router.get("/search-analytics-summary")
async def get_search_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    search_type: Optional[str] = Query(None, description="Filter by search type"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive search analytics summary.

    Provides an overview of search behavior including totals, user metrics,
    search types breakdown, and performance indicators.

    Args:
        days: Number of days to analyze
        search_type: Optional filter by search type
        current_user: Must be authenticated
        db: Database session

    Returns:
        Comprehensive analytics summary with multiple metrics
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_analytics_summary(days=days, search_type=search_type)


@router.get("/user-search-behavior")
async def get_user_search_behavior(
    user_id: Optional[int] = Query(None, description="User ID to analyze (admin only)"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze search behavior patterns for a specific user.

    Shows search patterns, effectiveness, and preferences for a user.
    Non-admin users can only view their own behavior.

    Args:
        user_id: Optional user ID (admin only, defaults to current user)
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        User search behavior analytics
    """
    # Non-admin users can only view their own behavior
    if user_id and user_id != current_user.id:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Cannot view other users' behavior")

    # Use current user if no user_id specified
    target_user_id = user_id or current_user.id

    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_user_behavior(user_id=target_user_id, days=days)


@router.get("/conversion-metrics")
async def get_conversion_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get guest-to-user conversion metrics.

    Analyzes how many guest users convert to registered users and their
    search behavior before and after conversion.

    Args:
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        Conversion metrics and behavior analysis
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_conversion_metrics(days=days)


@router.get("/search-performance")
async def get_search_performance(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze search effectiveness and performance.

    Provides insights into search result quality, zero-result queries,
    and overall search effectiveness.

    Args:
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        Search performance metrics
    """
    analytics_service = SearchAnalyticsService(db)
    return analytics_service.get_search_performance(days=days)
