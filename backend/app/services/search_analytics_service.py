# backend/app/services/search_analytics_service.py
"""
Search Analytics Service.

Provides analytics and reporting functionality for search history data,
including soft-deleted records for comprehensive insights.
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models.search_history import SearchHistory
from ..repositories.search_history_repository import SearchHistoryRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class SearchAnalyticsService(BaseService):
    """
    Service for generating search analytics and insights.

    Unlike the regular SearchHistoryService, this service includes
    soft-deleted data in its queries for accurate analytics.
    """

    def __init__(self, db: Session):
        """Initialize the analytics service."""
        super().__init__(db)
        self.repository = SearchHistoryRepository(db)

    @BaseService.measure_operation("get_search_trends")
    def get_search_trends(
        self, start_date: datetime, end_date: datetime, include_deleted: bool = True, search_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get daily search trends over a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_deleted: Whether to include soft-deleted searches
            search_type: Optional filter by search type

        Returns:
            List of daily search counts
        """
        query = self.repository.find_analytics_eligible_searches(
            start_date=start_date, end_date=end_date, include_deleted=include_deleted
        )

        if search_type:
            query = query.filter(SearchHistory.search_type == search_type)

        # Group by date and count
        daily_counts = (
            query.with_entities(
                func.date(SearchHistory.created_at).label("date"),
                func.count(SearchHistory.id).label("count"),
                func.count(func.distinct(SearchHistory.user_id)).label("unique_users"),
                func.count(func.distinct(SearchHistory.guest_session_id)).label("unique_guests"),
            )
            .group_by(func.date(SearchHistory.created_at))
            .order_by(func.date(SearchHistory.created_at))
            .all()
        )

        # Format results
        trends = []
        for row in daily_counts:
            trends.append(
                {
                    "date": row.date.isoformat() if row.date else None,
                    "total_searches": row.count,
                    "unique_users": row.unique_users,
                    "unique_guests": row.unique_guests,
                }
            )

        return trends

    @BaseService.measure_operation("get_popular_searches")
    def get_popular_searches(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 20,
        search_type: Optional[str] = None,
        include_deleted: bool = True,
    ) -> List[Dict]:
        """
        Get most popular search queries.

        Args:
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of results
            search_type: Optional filter by search type
            include_deleted: Whether to include soft-deleted searches

        Returns:
            List of popular searches with counts
        """
        query = self.repository.find_analytics_eligible_searches(
            start_date=start_date, end_date=end_date, include_deleted=include_deleted
        )

        if search_type:
            query = query.filter(SearchHistory.search_type == search_type)

        # Group by search query and count
        popular = (
            query.with_entities(
                SearchHistory.search_query,
                func.count(SearchHistory.id).label("count"),
                func.avg(SearchHistory.results_count).label("avg_results"),
            )
            .group_by(SearchHistory.search_query)
            .order_by(func.count(SearchHistory.id).desc())
            .limit(limit)
            .all()
        )

        # Format results
        results = []
        for row in popular:
            results.append(
                {
                    "query": row.search_query,
                    "search_count": row.count,
                    "average_results": float(row.avg_results) if row.avg_results else 0.0,
                }
            )

        return results

    @BaseService.measure_operation("get_analytics_summary")
    def get_analytics_summary(self, start_date: datetime, end_date: datetime) -> Dict:
        """
        Get comprehensive analytics summary.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dictionary with analytics summary
        """
        # Base query including soft-deleted
        base_query = self.repository.find_analytics_eligible_searches(
            start_date=start_date, end_date=end_date, include_deleted=True
        )

        # Total searches
        total_searches = base_query.count()

        # Active (non-deleted) searches
        active_searches = base_query.filter(SearchHistory.deleted_at.is_(None)).count()

        # Unique users
        unique_users = base_query.filter(SearchHistory.user_id.isnot(None)).distinct(SearchHistory.user_id).count()

        # Unique guests
        unique_guests = (
            base_query.filter(SearchHistory.guest_session_id.isnot(None))
            .distinct(SearchHistory.guest_session_id)
            .count()
        )

        # Search type breakdown
        type_breakdown = (
            base_query.with_entities(SearchHistory.search_type, func.count(SearchHistory.id).label("count"))
            .group_by(SearchHistory.search_type)
            .all()
        )

        # Conversion metrics
        converted_guests = (
            base_query.filter(SearchHistory.converted_to_user_id.isnot(None))
            .distinct(SearchHistory.guest_session_id)
            .count()
        )

        # Zero results searches
        zero_results = base_query.filter(
            or_(SearchHistory.results_count == 0, SearchHistory.results_count.is_(None))
        ).count()

        # Format summary
        summary = {
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
            "totals": {
                "total_searches": total_searches,
                "active_searches": active_searches,
                "deleted_searches": total_searches - active_searches,
                "deletion_rate": ((total_searches - active_searches) / total_searches * 100)
                if total_searches > 0
                else 0,
            },
            "users": {
                "unique_users": unique_users,
                "unique_guests": unique_guests,
                "total_unique_searchers": unique_users + unique_guests,
                "avg_searches_per_user": (total_searches / unique_users) if unique_users > 0 else 0,
            },
            "search_types": {row.search_type: row.count for row in type_breakdown},
            "conversions": {
                "converted_guests": converted_guests,
                "conversion_rate": (converted_guests / unique_guests * 100) if unique_guests > 0 else 0,
            },
            "performance": {
                "searches_with_results": total_searches - zero_results,
                "zero_result_searches": zero_results,
                "zero_result_rate": (zero_results / total_searches * 100) if total_searches > 0 else 0,
            },
        }

        return summary

    @BaseService.measure_operation("get_user_behavior")
    def get_user_behavior(
        self, user_id: int, start_date: datetime, end_date: datetime, include_deleted: bool = False
    ) -> Dict:
        """
        Analyze search behavior for a specific user.

        Args:
            user_id: User ID to analyze
            start_date: Start of date range
            end_date: End of date range
            include_deleted: Whether to include deleted searches

        Returns:
            User behavior analytics
        """
        # Get user's searches
        query = self.db.query(SearchHistory).filter(
            SearchHistory.user_id == user_id,
            SearchHistory.created_at >= start_date,
            SearchHistory.created_at <= end_date,
        )

        if not include_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        searches = query.all()

        if not searches:
            return {
                "user_id": user_id,
                "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_searches": 0,
                "message": "No searches found for this user in the specified period",
            }

        # Analyze behavior
        search_queries = [s.search_query for s in searches]
        query_counter = Counter(search_queries)

        # Time-based patterns
        hour_distribution = defaultdict(int)
        day_distribution = defaultdict(int)

        for search in searches:
            hour_distribution[search.created_at.hour] += 1
            day_distribution[search.created_at.strftime("%A")] += 1

        # Search effectiveness
        total_results = sum(s.results_count or 0 for s in searches)
        searches_with_results = sum(1 for s in searches if s.results_count and s.results_count > 0)

        behavior = {
            "user_id": user_id,
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "search_patterns": {
                "total_searches": len(searches),
                "unique_queries": len(set(search_queries)),
                "repeat_search_rate": (1 - len(set(search_queries)) / len(searches)) * 100 if searches else 0,
                "deleted_searches": sum(1 for s in searches if s.deleted_at is not None),
            },
            "top_searches": [{"query": query, "count": count} for query, count in query_counter.most_common(10)],
            "time_patterns": {
                "by_hour": dict(hour_distribution),
                "by_day": dict(day_distribution),
                "most_active_hour": max(hour_distribution.items(), key=lambda x: x[1])[0]
                if hour_distribution
                else None,
                "most_active_day": max(day_distribution.items(), key=lambda x: x[1])[0] if day_distribution else None,
            },
            "search_effectiveness": {
                "average_results_per_search": total_results / len(searches) if searches else 0,
                "searches_with_results": searches_with_results,
                "success_rate": (searches_with_results / len(searches) * 100) if searches else 0,
            },
        }

        return behavior

    @BaseService.measure_operation("get_conversion_metrics")
    def get_conversion_metrics(self, start_date: datetime, end_date: datetime) -> Dict:
        """
        Analyze guest-to-user conversion metrics.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Conversion metrics
        """
        # Get all guest sessions in period
        guest_sessions = (
            self.db.query(
                SearchHistory.guest_session_id,
                func.min(SearchHistory.created_at).label("first_search"),
                func.max(SearchHistory.created_at).label("last_search"),
                func.count(SearchHistory.id).label("search_count"),
            )
            .filter(
                SearchHistory.guest_session_id.isnot(None),
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date,
            )
            .group_by(SearchHistory.guest_session_id)
            .all()
        )

        total_guests = len(guest_sessions)

        # Get converted sessions
        converted_sessions = (
            self.db.query(
                SearchHistory.guest_session_id,
                SearchHistory.converted_to_user_id,
                SearchHistory.converted_at,
                func.count(SearchHistory.id).label("searches_before_conversion"),
            )
            .filter(
                SearchHistory.guest_session_id.isnot(None),
                SearchHistory.converted_to_user_id.isnot(None),
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date,
            )
            .group_by(SearchHistory.guest_session_id, SearchHistory.converted_to_user_id, SearchHistory.converted_at)
            .all()
        )

        # Calculate conversion time
        conversion_times = []
        for session in converted_sessions:
            # Find first search time for this session
            first_search = next((g for g in guest_sessions if g.guest_session_id == session.guest_session_id), None)
            if first_search and session.converted_at:
                time_to_convert = (session.converted_at - first_search.first_search).total_seconds() / 3600  # hours
                conversion_times.append(time_to_convert)

        metrics = {
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "guest_sessions": {
                "total": total_guests,
                "converted": len(converted_sessions),
                "conversion_rate": (len(converted_sessions) / total_guests * 100) if total_guests > 0 else 0,
            },
            "conversion_behavior": {
                "average_searches_before_conversion": (
                    sum(s.searches_before_conversion for s in converted_sessions) / len(converted_sessions)
                )
                if converted_sessions
                else 0,
                "average_time_to_convert_hours": (sum(conversion_times) / len(conversion_times))
                if conversion_times
                else 0,
                "median_time_to_convert_hours": (sorted(conversion_times)[len(conversion_times) // 2])
                if conversion_times
                else 0,
            },
            "guest_engagement": {
                "average_searches_per_guest": (sum(g.search_count for g in guest_sessions) / len(guest_sessions))
                if guest_sessions
                else 0,
                "single_search_guests": sum(1 for g in guest_sessions if g.search_count == 1),
                "multi_search_guests": sum(1 for g in guest_sessions if g.search_count > 1),
            },
        }

        return metrics

    @BaseService.measure_operation("get_search_performance")
    def get_search_performance(self, start_date: datetime, end_date: datetime) -> Dict:
        """
        Analyze search performance metrics.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Search performance metrics
        """
        # Base query
        base_query = self.repository.find_analytics_eligible_searches(
            start_date=start_date, end_date=end_date, include_deleted=True
        )

        # Searches by result count ranges
        result_ranges = {
            "zero_results": base_query.filter(
                or_(SearchHistory.results_count == 0, SearchHistory.results_count.is_(None))
            ).count(),
            "1_5_results": base_query.filter(SearchHistory.results_count.between(1, 5)).count(),
            "6_10_results": base_query.filter(SearchHistory.results_count.between(6, 10)).count(),
            "over_10_results": base_query.filter(SearchHistory.results_count > 10).count(),
        }

        # Refinement patterns (users who search multiple times in short period)
        # This is a simplified version - in production you might want more sophisticated analysis
        total_searches = base_query.count()

        # Zero result queries
        zero_result_queries = (
            base_query.filter(or_(SearchHistory.results_count == 0, SearchHistory.results_count.is_(None)))
            .with_entities(SearchHistory.search_query, func.count(SearchHistory.id).label("count"))
            .group_by(SearchHistory.search_query)
            .order_by(func.count(SearchHistory.id).desc())
            .limit(10)
            .all()
        )

        performance = {
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "result_distribution": result_ranges,
            "effectiveness": {
                "total_searches": total_searches,
                "successful_searches": total_searches - result_ranges["zero_results"],
                "success_rate": ((total_searches - result_ranges["zero_results"]) / total_searches * 100)
                if total_searches > 0
                else 0,
                "average_results": base_query.with_entities(func.avg(SearchHistory.results_count)).scalar() or 0,
            },
            "problematic_queries": [
                {
                    "query": query,
                    "failed_count": count,
                    "impact": (count / result_ranges["zero_results"] * 100) if result_ranges["zero_results"] > 0 else 0,
                }
                for query, count in zero_result_queries
            ],
        }

        return performance
