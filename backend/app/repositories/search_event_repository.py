# backend/app/repositories/search_event_repository.py
"""
Repository for SearchEvent model - analytics tracking for search events.

This repository handles the append-only event log for search analytics,
recording every single search event without deduplication.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models.search_event import SearchEvent
from .base_repository import BaseRepository


class SearchEventRepository(BaseRepository[SearchEvent]):
    """Repository for managing search event analytics."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        super().__init__(db, SearchEvent)

    def create_event(self, event_data: dict) -> SearchEvent:
        """
        Create a new search event for analytics.

        Args:
            event_data: Dictionary containing event details

        Returns:
            Created SearchEvent instance
        """
        return self.create(**event_data)

    def get_user_search_frequency(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, days: int = 30
    ) -> List[Dict]:
        """
        Get search frequency analytics for a user or guest.

        Args:
            user_id: User ID to analyze
            guest_session_id: Guest session ID to analyze
            days: Number of days to look back

        Returns:
            List of search queries with frequency counts
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = self.db.query(
            SearchEvent.search_query,
            func.count(SearchEvent.id).label("frequency"),
            func.max(SearchEvent.searched_at).label("last_searched"),
        ).filter(SearchEvent.searched_at >= cutoff_date)

        if user_id:
            query = query.filter(SearchEvent.user_id == user_id)
        elif guest_session_id:
            query = query.filter(SearchEvent.guest_session_id == guest_session_id)
        else:
            return []

        results = query.group_by(SearchEvent.search_query).order_by(desc("frequency")).all()

        return [
            {"search_query": result.search_query, "frequency": result.frequency, "last_searched": result.last_searched}
            for result in results
        ]

    def get_search_patterns(self, search_query: str, days: int = 30) -> Dict:
        """
        Analyze patterns for a specific search query.

        Args:
            search_query: Query to analyze
            days: Number of days to look back

        Returns:
            Dictionary with pattern analysis
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get daily search counts
        daily_counts = (
            self.db.query(func.date(SearchEvent.searched_at).label("date"), func.count(SearchEvent.id).label("count"))
            .filter(SearchEvent.search_query == search_query, SearchEvent.searched_at >= cutoff_date)
            .group_by(func.date(SearchEvent.searched_at))
            .all()
        )

        # Get search type distribution
        type_distribution = (
            self.db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
            .filter(SearchEvent.search_query == search_query, SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.search_type)
            .all()
        )

        # Get average results count
        avg_results = (
            self.db.query(func.avg(SearchEvent.results_count))
            .filter(
                SearchEvent.search_query == search_query,
                SearchEvent.searched_at >= cutoff_date,
                SearchEvent.results_count.isnot(None),
            )
            .scalar()
        )

        return {
            "query": search_query,
            "daily_counts": [{"date": str(dc.date), "count": dc.count} for dc in daily_counts],
            "type_distribution": [{"type": td.search_type, "count": td.count} for td in type_distribution],
            "average_results": float(avg_results) if avg_results else 0,
        }

    def get_user_journey(self, session_id: str) -> List[Dict]:
        """
        Get sequence of searches in a session.

        Args:
            session_id: Browser session ID

        Returns:
            List of search events in chronological order
        """
        events = (
            self.db.query(SearchEvent)
            .filter(SearchEvent.session_id == session_id)
            .order_by(SearchEvent.searched_at)
            .all()
        )

        return [
            {
                "search_query": e.search_query,
                "search_type": e.search_type,
                "timestamp": e.searched_at.isoformat(),
                "results_count": e.results_count,
                "referrer": e.referrer,
            }
            for e in events
        ]

    def get_popular_searches(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """
        Get most popular searches across all users.

        Args:
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of popular searches with counts
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("search_count"),
                func.count(
                    func.distinct(
                        func.concat(
                            func.coalesce(func.cast(SearchEvent.user_id, sa.String), ""),
                            func.coalesce(SearchEvent.guest_session_id, ""),
                        )
                    )
                ).label("unique_users"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.search_query)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return [
            {
                "search_query": result.search_query,
                "search_count": result.search_count,
                "unique_users": result.unique_users,
            }
            for result in results
        ]

    def get_search_velocity(self, search_query: str, hours: int = 24) -> Dict:
        """
        Analyze search frequency over recent time period.

        Args:
            search_query: Query to analyze
            hours: Number of hours to look back

        Returns:
            Velocity metrics
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Get hourly counts
        hourly_counts = (
            self.db.query(
                func.date_trunc("hour", SearchEvent.searched_at).label("hour"),
                func.count(SearchEvent.id).label("count"),
            )
            .filter(SearchEvent.search_query == search_query, SearchEvent.searched_at >= cutoff_time)
            .group_by(func.date_trunc("hour", SearchEvent.searched_at))
            .order_by("hour")
            .all()
        )

        # Calculate velocity trend
        if len(hourly_counts) >= 2:
            first_half = sum(hc.count for hc in hourly_counts[: len(hourly_counts) // 2])
            second_half = sum(hc.count for hc in hourly_counts[len(hourly_counts) // 2 :])
            trend = "increasing" if second_half > first_half else "decreasing" if second_half < first_half else "stable"
        else:
            trend = "insufficient_data"

        return {
            "query": search_query,
            "period_hours": hours,
            "total_searches": sum(hc.count for hc in hourly_counts),
            "hourly_breakdown": [{"hour": str(hc.hour), "count": hc.count} for hc in hourly_counts],
            "trend": trend,
        }
