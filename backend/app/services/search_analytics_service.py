# backend/app/services/search_analytics_service.py
"""
Search Analytics Service for analyzing search patterns and behaviors.

This service provides insights into search patterns, user journeys,
and search effectiveness using the append-only search_events table.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.search_event import SearchEvent
from ..repositories.search_event_repository import SearchEventRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class SearchAnalyticsService(BaseService):
    """
    Service for analyzing search patterns and generating insights.

    Uses the search_events table which contains all search activity
    without deduplication, perfect for analytics.
    """

    def __init__(self, db: Session):
        """Initialize the search analytics service."""
        super().__init__(db)
        self.event_repository = SearchEventRepository(db)

    @BaseService.measure_operation("get_popular_searches")
    def get_popular_searches(
        self, days: int = 7, limit: int = 20, search_type: Optional[str] = None, include_deleted: bool = True
    ) -> List[Dict]:
        """
        Get most popular search queries.

        Returns the most frequently searched terms with counts and average results.

        Args:
            days: Number of days to look back
            limit: Maximum number of results
            search_type: Filter by search type (optional)
            include_deleted: Whether to include soft-deleted searches

        Returns:
            List of popular searches with structure:
            [{
                "query": "piano lessons",
                "search_count": 25,
                "average_results": 12.5
            }, ...]
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Query search events for popularity metrics
        query = self.db.query(
            SearchEvent.search_query,
            func.count(SearchEvent.id).label("search_count"),
            func.avg(SearchEvent.results_count).label("average_results"),
            func.count(
                func.distinct(func.coalesce(func.cast(SearchEvent.user_id, sa.String), SearchEvent.guest_session_id))
            ).label("unique_users"),
        ).filter(SearchEvent.searched_at >= cutoff_date)

        # Apply search type filter if provided
        if search_type:
            query = query.filter(SearchEvent.search_type == search_type)

        # Group by query and order by popularity
        results = (
            query.group_by(SearchEvent.search_query).order_by(func.count(SearchEvent.id).desc()).limit(limit).all()
        )

        return [
            {
                "query": r.search_query,  # Route tests expect "query" key
                "search_count": r.search_count,
                "average_results": round(float(r.average_results), 2) if r.average_results else 0.0,
                "unique_users": r.unique_users,
            }
            for r in results
        ]

    @BaseService.measure_operation("get_search_funnel")
    def get_search_funnel(self, session_id: str) -> List[Dict]:
        """
        Get search journey for a specific session.

        Args:
            session_id: Browser session ID

        Returns:
            List of searches in chronological order for the session
        """
        # Delegate to repository
        return self.event_repository.get_user_journey(session_id)

    @BaseService.measure_operation("get_referrer_stats")
    def get_referrer_stats(self, days: int = 7) -> List[Dict]:
        """
        Analyze which pages generate the most searches.

        Args:
            days: Number of days to look back

        Returns:
            List of pages with search counts and unique sessions
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = (
            self.db.query(
                SearchEvent.referrer,
                func.count(SearchEvent.id).label("search_count"),
                func.count(func.distinct(SearchEvent.session_id)).label("unique_sessions"),
                # Most common search type from each page
                func.array_agg(func.distinct(SearchEvent.search_type)).label("search_types"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date, SearchEvent.referrer.isnot(None))
            .group_by(SearchEvent.referrer)
            .order_by(func.count(SearchEvent.id).desc())
            .all()
        )

        return [
            {
                "page": r.referrer or "unknown",
                "search_count": r.search_count,
                "unique_sessions": r.unique_sessions,
                "search_types": list(r.search_types) if r.search_types else [],
            }
            for r in results
        ]

    @BaseService.measure_operation("get_zero_result_searches")
    def get_zero_result_searches(self, days: int = 7) -> List[Dict]:
        """
        Find searches that returned no results.

        Args:
            days: Number of days to look back

        Returns:
            List of searches with no results and attempt counts
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("attempt_count"),
                func.count(
                    func.distinct(
                        func.coalesce(func.cast(SearchEvent.user_id, sa.String), SearchEvent.guest_session_id)
                    )
                ).label("unique_users"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date, SearchEvent.results_count == 0)
            .group_by(SearchEvent.search_query)
            .order_by(func.count(SearchEvent.id).desc())
            .limit(50)
            .all()
        )

        return [
            {"search_query": r.search_query, "attempt_count": r.attempt_count, "unique_users": r.unique_users}
            for r in results
        ]

    @BaseService.measure_operation("get_service_pill_performance")
    def get_service_pill_performance(self, days: int = 7) -> List[Dict]:
        """
        Analyze service pill click performance by page.

        Args:
            days: Number of days to look back

        Returns:
            List of service pills with click counts grouped by origin page
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = (
            self.db.query(
                SearchEvent.search_query,
                SearchEvent.referrer,
                func.count(SearchEvent.id).label("click_count"),
                func.count(func.distinct(SearchEvent.session_id)).label("unique_sessions"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date, SearchEvent.search_type == "service_pill")
            .group_by(SearchEvent.search_query, SearchEvent.referrer)
            .order_by(SearchEvent.search_query, func.count(SearchEvent.id).desc())
            .all()
        )

        # Group by service for better presentation
        service_stats = {}
        for r in results:
            service = r.search_query
            if service not in service_stats:
                service_stats[service] = {"service": service, "total_clicks": 0, "by_page": []}

            service_stats[service]["total_clicks"] += r.click_count
            service_stats[service]["by_page"].append(
                {"page": r.referrer or "unknown", "clicks": r.click_count, "unique_sessions": r.unique_sessions}
            )

        # Sort by total clicks
        return sorted(list(service_stats.values()), key=lambda x: x["total_clicks"], reverse=True)

    @BaseService.measure_operation("get_search_velocity")
    def get_search_velocity(self, search_query: str, hours: int = 24) -> Dict:
        """
        Analyze search frequency over recent time period.

        Args:
            search_query: Query to analyze
            hours: Number of hours to look back

        Returns:
            Velocity metrics including trend
        """
        return self.event_repository.get_search_velocity(search_query, hours)

    @BaseService.measure_operation("get_session_conversion_rate")
    def get_session_conversion_rate(self, days: int = 7, min_searches: int = 2) -> Dict:
        """
        Analyze how many search sessions lead to finding what users want.

        A "successful" session is one where users stop searching after finding results.

        Args:
            days: Number of days to analyze
            min_searches: Minimum searches to consider a session

        Returns:
            Conversion metrics
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get all sessions with multiple searches
        sessions = (
            self.db.query(
                SearchEvent.session_id,
                func.count(SearchEvent.id).label("search_count"),
                func.max(SearchEvent.results_count).label("max_results"),
                func.min(SearchEvent.results_count).label("min_results"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date, SearchEvent.session_id.isnot(None))
            .group_by(SearchEvent.session_id)
            .having(func.count(SearchEvent.id) >= min_searches)
            .all()
        )

        total_sessions = len(sessions)
        if total_sessions == 0:
            return {"total_sessions": 0, "successful_sessions": 0, "conversion_rate": 0}

        # Sessions that ended with results (likely found what they wanted)
        successful = sum(1 for s in sessions if s.max_results > 0)

        return {
            "total_sessions": total_sessions,
            "successful_sessions": successful,
            "conversion_rate": round(successful / total_sessions * 100, 2),
            "avg_searches_per_session": round(sum(s.search_count for s in sessions) / total_sessions, 2),
        }

    @BaseService.measure_operation("get_search_trends")
    def get_search_trends(
        self, days: int = 30, search_type: Optional[str] = None, include_deleted: bool = True
    ) -> List[Dict]:
        """
        Get daily search trends over time.

        Returns daily search counts with unique user/guest breakdowns.

        Args:
            days: Number of days to analyze
            search_type: Optional filter by search type
            include_deleted: Whether to include soft-deleted searches

        Returns:
            List of daily search counts with structure:
            [{
                "date": "2024-01-01",
                "total_searches": 10,
                "unique_users": 5,
                "unique_guests": 3
            }, ...]
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Base query on search_events for real-time analytics
        query = self.db.query(
            func.date(SearchEvent.searched_at).label("date"),
            func.count(SearchEvent.id).label("total_searches"),
            func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
            func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
        ).filter(SearchEvent.searched_at >= cutoff_date)

        # Apply search type filter if provided
        if search_type:
            query = query.filter(SearchEvent.search_type == search_type)

        # Group by date and order chronologically
        results = query.group_by(func.date(SearchEvent.searched_at)).order_by(func.date(SearchEvent.searched_at)).all()

        return [
            {
                "date": r.date.isoformat() if r.date else None,
                "total_searches": r.total_searches,
                "unique_users": r.unique_users,
                "unique_guests": r.unique_guests,
            }
            for r in results
        ]

    @BaseService.measure_operation("get_analytics_summary")
    def get_analytics_summary(self, days: int = 30, search_type: Optional[str] = None) -> Dict:
        """
        Get comprehensive search analytics summary.

        Args:
            days: Number of days to analyze
            search_type: Optional filter by search type

        Returns:
            Comprehensive analytics summary
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Base query with optional search type filter
        base_query = self.db.query(SearchEvent).filter(SearchEvent.searched_at >= cutoff_date)
        if search_type:
            base_query = base_query.filter(SearchEvent.search_type == search_type)

        # Get total metrics
        total_searches = base_query.count()
        unique_users = base_query.with_entities(
            func.count(
                func.distinct(func.coalesce(func.cast(SearchEvent.user_id, sa.String), SearchEvent.guest_session_id))
            )
        ).scalar()

        # Get deleted searches (from search_history table)
        from ..models.search_history import SearchHistory

        deleted_searches = (
            self.db.query(func.count(SearchHistory.id))
            .filter(SearchHistory.deleted_at.isnot(None), SearchHistory.last_searched_at >= cutoff_date)
            .scalar()
        )

        # Search type breakdown
        search_types = (
            base_query.with_entities(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
            .group_by(SearchEvent.search_type)
            .all()
        )

        # Guest vs User breakdown
        guest_searches = base_query.filter(SearchEvent.user_id.is_(None)).count()
        user_searches = base_query.filter(SearchEvent.user_id.isnot(None)).count()

        # Conversion metrics
        converted_guests = (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(SearchHistory.converted_to_user_id.isnot(None), SearchHistory.converted_at >= cutoff_date)
            .scalar()
        )

        # Zero results
        zero_results = base_query.filter(SearchEvent.results_count == 0).count()

        return {
            "date_range": {
                "start": cutoff_date.isoformat(),
                "end": datetime.now(timezone.utc).isoformat(),
                "days": days,
            },
            "totals": {
                "total_searches": total_searches,
                "unique_users": unique_users,
                "deleted_searches": deleted_searches,
                "deletion_rate": round(deleted_searches / total_searches * 100, 2) if total_searches > 0 else 0,
            },
            "users": {
                "guest_searches": guest_searches,
                "user_searches": user_searches,
                "guest_percentage": round(guest_searches / total_searches * 100, 2) if total_searches > 0 else 0,
            },
            "search_types": {st.search_type: st.count for st in search_types},
            "conversions": {
                "converted_guests": converted_guests,
                "conversion_rate": round(converted_guests / unique_users * 100, 2) if unique_users > 0 else 0,
            },
            "performance": {
                "zero_results_count": zero_results,
                "zero_results_rate": round(zero_results / total_searches * 100, 2) if total_searches > 0 else 0,
            },
        }

    @BaseService.measure_operation("get_user_behavior")
    def get_user_behavior(self, user_id: int, days: int = 30) -> Dict:
        """
        Analyze search behavior patterns for a specific user.

        Args:
            user_id: User ID to analyze
            days: Number of days to analyze

        Returns:
            User search behavior analytics
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get user's searches from events
        user_searches = (
            self.db.query(SearchEvent)
            .filter(SearchEvent.user_id == user_id, SearchEvent.searched_at >= cutoff_date)
            .all()
        )

        if not user_searches:
            return {
                "message": "No searches found for this user in the specified period",
                "user_id": user_id,
                "total_searches": 0,
            }

        # Search patterns
        search_types = {}
        hourly_pattern = {str(i): 0 for i in range(24)}
        daily_pattern = {}
        top_searches = {}

        for search in user_searches:
            # Count by type
            search_types[search.search_type] = search_types.get(search.search_type, 0) + 1

            # Hourly pattern
            hour = search.searched_at.hour
            hourly_pattern[str(hour)] += 1

            # Daily pattern
            day = search.searched_at.strftime("%A")
            daily_pattern[day] = daily_pattern.get(day, 0) + 1

            # Top searches
            top_searches[search.search_query] = top_searches.get(search.search_query, 0) + 1

        # Search effectiveness
        total = len(user_searches)
        with_results = sum(1 for s in user_searches if s.results_count > 0)
        avg_results = sum(s.results_count for s in user_searches) / total if total > 0 else 0

        # Sort top searches
        sorted_searches = sorted(top_searches.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "user_id": user_id,
            "total_searches": total,
            "search_patterns": {
                "by_type": search_types,
                "most_common_type": max(search_types, key=search_types.get) if search_types else None,
            },
            "top_searches": [{"query": q, "count": c} for q, c in sorted_searches],
            "time_patterns": {
                "hourly": hourly_pattern,
                "daily": daily_pattern,
                "peak_hour": max(hourly_pattern, key=hourly_pattern.get) if hourly_pattern else None,
            },
            "search_effectiveness": {
                "searches_with_results": with_results,
                "success_rate": round(with_results / total * 100, 2) if total > 0 else 0,
                "avg_results_per_search": round(avg_results, 2),
            },
        }

    @BaseService.measure_operation("get_conversion_metrics")
    def get_conversion_metrics(self, days: int = 30) -> Dict:
        """
        Get guest-to-user conversion metrics.

        Args:
            days: Number of days to analyze

        Returns:
            Conversion metrics and behavior analysis
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Import here to avoid circular dependency
        from ..models.search_history import SearchHistory

        # Get converted guests
        converted_guests = (
            self.db.query(SearchHistory)
            .filter(SearchHistory.converted_to_user_id.isnot(None), SearchHistory.converted_at >= cutoff_date)
            .all()
        )

        # Get total guest sessions
        total_guests = (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(SearchHistory.guest_session_id.isnot(None), SearchHistory.first_searched_at >= cutoff_date)
            .scalar()
        )

        # Analyze conversion behavior
        conversion_times = []
        pre_conversion_searches = {}
        post_conversion_activity = {}

        for guest in converted_guests:
            # Time to conversion
            if guest.first_searched_at and guest.converted_at:
                time_to_convert = (guest.converted_at - guest.first_searched_at).total_seconds() / 3600
                conversion_times.append(time_to_convert)

            # Count searches before conversion
            session_id = guest.guest_session_id
            if session_id not in pre_conversion_searches:
                pre_conversion_searches[session_id] = (
                    self.db.query(func.count(SearchHistory.id))
                    .filter(SearchHistory.guest_session_id == session_id)
                    .scalar()
                )

            # Track post-conversion activity
            user_id = guest.converted_to_user_id
            if user_id not in post_conversion_activity:
                post_conversion_activity[user_id] = (
                    self.db.query(func.count(SearchEvent.id))
                    .filter(SearchEvent.user_id == user_id, SearchEvent.searched_at >= guest.converted_at)
                    .scalar()
                )

        # Calculate metrics
        num_converted = len(set(g.guest_session_id for g in converted_guests))
        avg_time_to_convert = sum(conversion_times) / len(conversion_times) if conversion_times else 0
        avg_pre_searches = (
            sum(pre_conversion_searches.values()) / len(pre_conversion_searches) if pre_conversion_searches else 0
        )

        # Guest engagement (from events)
        guest_events = (
            self.db.query(SearchEvent.guest_session_id, func.count(SearchEvent.id).label("search_count"))
            .filter(SearchEvent.guest_session_id.isnot(None), SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.guest_session_id)
            .all()
        )

        engaged_guests = sum(1 for g in guest_events if g.search_count > 1)

        return {
            "guest_sessions": {
                "total": total_guests,
                "converted": num_converted,
                "conversion_rate": round(num_converted / total_guests * 100, 2) if total_guests > 0 else 0,
            },
            "conversion_behavior": {
                "avg_time_to_convert_hours": round(avg_time_to_convert, 2),
                "avg_searches_before_conversion": round(avg_pre_searches, 2),
                "retained_users": sum(1 for count in post_conversion_activity.values() if count > 0),
                "retention_rate": round(
                    sum(1 for count in post_conversion_activity.values() if count > 0)
                    / len(post_conversion_activity)
                    * 100,
                    2,
                )
                if post_conversion_activity
                else 0,
            },
            "guest_engagement": {
                "total_guest_sessions": len(guest_events),
                "engaged_sessions": engaged_guests,
                "engagement_rate": round(engaged_guests / len(guest_events) * 100, 2) if guest_events else 0,
            },
        }

    @BaseService.measure_operation("get_search_performance")
    def get_search_performance(self, days: int = 30) -> Dict:
        """
        Analyze search effectiveness and performance.

        Args:
            days: Number of days to analyze

        Returns:
            Search performance metrics
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get all searches
        searches = self.db.query(SearchEvent).filter(SearchEvent.searched_at >= cutoff_date).all()

        if not searches:
            return {"message": "No searches found in the specified period", "days": days}

        # Result distribution
        distribution = {"zero_results": 0, "1_5_results": 0, "6_10_results": 0, "over_10_results": 0}

        # Problematic queries tracking
        zero_result_queries = {}
        low_result_queries = {}

        for search in searches:
            count = search.results_count

            if count == 0:
                distribution["zero_results"] += 1
                zero_result_queries[search.search_query] = zero_result_queries.get(search.search_query, 0) + 1
            elif count <= 5:
                distribution["1_5_results"] += 1
                if count <= 2:
                    low_result_queries[search.search_query] = low_result_queries.get(search.search_query, 0) + 1
            elif count <= 10:
                distribution["6_10_results"] += 1
            else:
                distribution["over_10_results"] += 1

        total_searches = len(searches)

        # Sort problematic queries
        top_zero_results = sorted(zero_result_queries.items(), key=lambda x: x[1], reverse=True)[:10]

        top_low_results = sorted(low_result_queries.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "result_distribution": distribution,
            "effectiveness": {
                "total_searches": total_searches,
                "searches_with_results": total_searches - distribution["zero_results"],
                "success_rate": round((total_searches - distribution["zero_results"]) / total_searches * 100, 2)
                if total_searches > 0
                else 0,
                "avg_results": round(sum(s.results_count for s in searches) / total_searches, 2)
                if total_searches > 0
                else 0,
            },
            "problematic_queries": {
                "zero_results": [{"query": q, "count": c} for q, c in top_zero_results],
                "low_results": [{"query": q, "count": c} for q, c in top_low_results],
            },
        }
