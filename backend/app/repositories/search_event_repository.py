# backend/app/repositories/search_event_repository.py
"""
Repository for SearchEvent model - analytics tracking for search events.

This repository handles the append-only event log for search analytics,
recording every single search event without deduplication.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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

        return [{"search_query": result[0], "frequency": result[1], "last_searched": result[2]} for result in results]

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
            "daily_counts": [{"date": str(dc[0]), "count": dc[1]} for dc in daily_counts],
            "type_distribution": [{"type": td[0], "count": td[1]} for td in type_distribution],
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
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
            )
            .filter(SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.search_query)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return [
            {
                "search_query": result[0],  # search_query
                "search_count": result[1],  # search_count
                "unique_users": result[2],  # unique_users
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
            first_half = sum(hc[1] for hc in hourly_counts[: len(hourly_counts) // 2])
            second_half = sum(hc[1] for hc in hourly_counts[len(hourly_counts) // 2 :])
            trend = "increasing" if second_half > first_half else "decreasing" if second_half < first_half else "stable"
        else:
            trend = "insufficient_data"

        return {
            "query": search_query,
            "period_hours": hours,
            "total_searches": sum(hc[1] for hc in hourly_counts),
            "hourly_breakdown": [{"hour": str(hc[0]), "count": hc[1]} for hc in hourly_counts],
            "trend": trend,
        }

    def get_popular_searches_with_avg_results(self, hours: int = 24, limit: int = 20) -> List[Dict]:
        """
        Get popular searches with average result counts.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of results

        Returns:
            List of popular searches with counts and average results
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        results = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("count"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(SearchEvent.searched_at >= cutoff_time)
            .group_by(SearchEvent.search_query)
            .order_by(func.count(SearchEvent.id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "query": result[0],  # search_query
                "count": result[1],  # count
                "avg_results": float(result[2]) if result[2] else 0,  # avg_results
            }
            for result in results
        ]

    def get_search_type_distribution(self, hours: int = 24) -> Dict[str, int]:
        """
        Get distribution of search types.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary mapping search type to count
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        results = (
            self.db.query(
                SearchEvent.search_type,
                func.count(SearchEvent.id).label("count"),
            )
            .filter(SearchEvent.searched_at >= cutoff_time)
            .group_by(SearchEvent.search_type)
            .all()
        )

        return {result[0]: result[1] for result in results}  # search_type: count

    def count_searches_since(self, cutoff_time: datetime) -> int:
        """
        Count total searches since a given time.

        Args:
            cutoff_time: Time to count from

        Returns:
            Total search count
        """
        return self.db.query(SearchEvent).filter(SearchEvent.searched_at >= cutoff_time).count()

    def count_searches_with_interactions(self, cutoff_time: datetime) -> int:
        """
        Count searches that have associated interactions.

        Args:
            cutoff_time: Time to count from

        Returns:
            Count of searches with interactions
        """
        from ..models.search_interaction import SearchInteraction

        return (
            self.db.query(SearchEvent)
            .join(SearchInteraction)
            .filter(SearchEvent.searched_at >= cutoff_time)
            .distinct()
            .count()
        )

    def get_hourly_search_counts(self, cutoff_time: datetime, limit: int = 5) -> List[Dict]:
        """
        Get search counts by hour.

        Args:
            cutoff_time: Time to count from
            limit: Maximum number of hours to return

        Returns:
            List of hours with search counts
        """
        hourly_counts = (
            self.db.query(
                func.extract("hour", SearchEvent.searched_at).label("hour"),
                func.count(SearchEvent.id).label("count"),
            )
            .filter(SearchEvent.searched_at >= cutoff_time)
            .group_by(func.extract("hour", SearchEvent.searched_at))
            .order_by(func.count(SearchEvent.id).desc())
            .limit(limit)
            .all()
        )

        return [{"hour": int(result[0]), "search_count": result[1]} for result in hourly_counts]

    def calculate_search_quality_score(self, event_id: int) -> float:
        """
        Calculate quality score for a search event.

        Args:
            event_id: ID of the search event

        Returns:
            Quality score between 0 and 100
        """
        event = self.get_by_id(event_id)
        if not event:
            return 0.0

        score = 50.0  # Base score

        # Factor 1: Results count (penalize too many or too few)
        if event.results_count == 0:
            score -= 30
        elif event.results_count > 50:
            score -= 10
        elif 5 <= event.results_count <= 20:
            score += 10

        # Factor 2: Has interactions (good signal)
        from ..models.search_interaction import SearchInteraction

        has_interactions = (
            self.db.query(SearchInteraction).filter(SearchInteraction.search_event_id == event.id).first() is not None
        )

        if has_interactions:
            score += 20

        # Factor 3: Search type (some types are more targeted)
        if event.search_type in ["service_pill", "category"]:
            score += 5

        return max(0, min(100, score))
