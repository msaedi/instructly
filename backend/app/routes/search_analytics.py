# backend/app/routes/search_analytics.py
"""
Search Analytics API endpoints.

Provides read-only endpoints for search analytics that include
soft-deleted data for comprehensive reporting.

These endpoints are typically restricted to admin/analytics roles.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
    # TODO: Add role check for admin/analytics access
    # if current_user.role not in ["admin", "analytics"]:
    #     raise HTTPException(status_code=403, detail="Access denied")

    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    trends = analytics_service.get_search_trends(
        start_date=start_date, end_date=datetime.utcnow(), include_deleted=include_deleted, search_type=search_type
    )

    return trends


@router.get("/popular-searches")
async def get_popular_searches(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    search_type: Optional[str] = Query(None, description="Filter by search type"),
    include_deleted: bool = Query(True, description="Include soft-deleted searches"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get most popular search queries.

    Returns the most frequently searched terms, including data from
    soft-deleted searches for accurate popularity metrics.

    Args:
        days: Number of days to look back
        limit: Maximum number of results
        search_type: Optional filter by search type
        include_deleted: Whether to include soft-deleted searches
        current_user: Must be authenticated
        db: Database session

    Returns:
        List of popular searches with counts
    """
    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    popular = analytics_service.get_popular_searches(
        start_date=start_date,
        end_date=datetime.utcnow(),
        limit=limit,
        search_type=search_type,
        include_deleted=include_deleted,
    )

    return popular


@router.get("/search-analytics-summary")
async def get_search_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive search analytics summary.

    Includes:
    - Total searches (including soft-deleted)
    - Unique users and guests
    - Search type breakdown
    - Conversion metrics
    - Average searches per user

    Args:
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        Comprehensive analytics summary
    """
    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    summary = analytics_service.get_analytics_summary(start_date=start_date, end_date=datetime.utcnow())

    return summary


@router.get("/user-search-behavior")
async def get_user_search_behavior(
    user_id: Optional[int] = Query(None, description="Specific user ID to analyze"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    include_deleted: bool = Query(False, description="Include deleted searches"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze user search behavior patterns.

    Shows search patterns, frequency, and preferences for a specific user
    or aggregated for all users.

    Args:
        user_id: Optional specific user to analyze
        days: Number of days to analyze
        include_deleted: Whether to include deleted searches
        current_user: Must be authenticated
        db: Database session

    Returns:
        User behavior analytics
    """
    # If analyzing specific user, ensure it's the current user or admin
    if user_id and user_id != current_user.id:
        # TODO: Add admin check
        raise HTTPException(status_code=403, detail="Cannot view other users' data")

    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    behavior = analytics_service.get_user_behavior(
        user_id=user_id or current_user.id,
        start_date=start_date,
        end_date=datetime.utcnow(),
        include_deleted=include_deleted,
    )

    return behavior


@router.get("/conversion-metrics")
async def get_conversion_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get guest-to-user conversion metrics.

    Analyzes how many guest sessions convert to registered users and
    how search behavior changes after conversion.

    Args:
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        Conversion analytics data
    """
    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    metrics = analytics_service.get_conversion_metrics(start_date=start_date, end_date=datetime.utcnow())

    return metrics


@router.get("/search-performance")
async def get_search_performance(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get search performance metrics.

    Analyzes search effectiveness by looking at:
    - Searches with zero results
    - Average results per search
    - Search refinement patterns

    Args:
        days: Number of days to analyze
        current_user: Must be authenticated
        db: Database session

    Returns:
        Search performance metrics
    """
    analytics_service = SearchAnalyticsService(db)

    start_date = datetime.utcnow() - timedelta(days=days)
    performance = analytics_service.get_search_performance(start_date=start_date, end_date=datetime.utcnow())

    return performance
