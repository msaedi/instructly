# backend/app/repositories/search_event_repository.py
"""
Search Event Repository for InstaInstru Platform.

Handles data access for individual search events used in analytics.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.search_event import SearchEvent, SearchEventCandidate
from .base_repository import BaseRepository


class SearchEventRepository(BaseRepository[SearchEvent]):
    """Repository for search event data access."""

    def __init__(self, db: Session):
        """Initialize with SearchEvent model."""
        super().__init__(db, SearchEvent)

    def get_user_events(self, user_id: str) -> List[SearchEvent]:
        """
        Get all search events for a user.

        Used by: PrivacyService for data export

        Args:
            user_id: The user ID

        Returns:
            List of SearchEvent records
        """
        return (
            self.db.query(SearchEvent)
            .filter(SearchEvent.user_id == user_id)
            .order_by(SearchEvent.searched_at.desc())
            .all()
        )

    def delete_user_events(self, user_id: str) -> int:
        """
        Delete all search events for a user.

        Used by: PrivacyService for right to be forgotten

        Args:
            user_id: The user ID

        Returns:
            Number of deleted records
        """
        return self.db.query(SearchEvent).filter(SearchEvent.user_id == user_id).delete(synchronize_session=False)

    def delete_old_events(self, cutoff_date: datetime) -> int:
        """
        Delete search events older than a cutoff date.

        Used by: PrivacyService for retention policies

        Args:
            cutoff_date: Delete events before this date

        Returns:
            Number of deleted records
        """
        return (
            self.db.query(SearchEvent).filter(SearchEvent.searched_at < cutoff_date).delete(synchronize_session=False)
        )

    def count_old_events(self, cutoff_date: datetime) -> int:
        """
        Count search events older than a cutoff date.

        Used by: PrivacyService for retention statistics

        Args:
            cutoff_date: Count events before this date

        Returns:
            Count of old events
        """
        return self.db.query(func.count(SearchEvent.id)).filter(SearchEvent.searched_at < cutoff_date).scalar() or 0

    def count_all_events(self) -> int:
        """
        Count all search event records.

        Used by: PrivacyService for statistics

        Returns:
            Total count of search event records
        """
        return self.db.query(func.count(SearchEvent.id)).scalar() or 0

    def create_event(self, event_data: Optional[Dict] = None, **kwargs) -> SearchEvent:
        """
        Create a new search event for analytics tracking.

        This is the primary method for creating search events, used by
        SearchHistoryService for tracking all search interactions.

        Args:
            event_data: Optional dictionary of event data
            **kwargs: Additional keyword arguments

        Returns:
            Created SearchEvent
        """
        # If event_data is provided as a dict, use it
        if event_data:
            return self.create(**event_data)
        # Otherwise use kwargs
        return self.create(**kwargs)

    def bulk_insert_candidates(
        self,
        search_event_id: str,
        candidates: List[Dict],
    ) -> int:
        """
        Persist top-N candidates for a search event.

        Args:
            search_event_id: Parent event id
            candidates: List of dicts with keys: position, service_catalog_id, score, vector_score, lexical_score, source

        Returns:
            Number of rows inserted
        """
        if not candidates:
            return 0

        objects = [
            SearchEventCandidate(
                search_event_id=search_event_id,
                position=c.get("position"),
                service_catalog_id=c.get("service_catalog_id"),
                score=c.get("score"),
                vector_score=c.get("vector_score"),
                lexical_score=c.get("lexical_score"),
                source=c.get("source"),
            )
            for c in candidates
        ]

        self.db.bulk_save_objects(objects)
        # Flush so event id can be used immediately by callers if needed
        self.db.flush()
        return len(objects)

    def get_popular_searches(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """
        Get popular search queries within a time period.

        Returns list of dicts with query and count.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = (
            self.db.query(SearchEvent.search_query, func.count(SearchEvent.id).label("count"))
            .filter(SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.search_query)
            .order_by(func.count(SearchEvent.id).desc())
            .limit(limit)
            .all()
        )

        return [{"query": query, "count": count} for query, count in results]

    def calculate_search_quality_score(self, event_id: int) -> float:
        """
        Calculate quality score for a search event.

        Score based on:
        - Results returned (more is better to a point)
        - Too many results is bad (overwhelming)
        - Interactions boost the score
        """
        from ..models.search_interaction import SearchInteraction

        event = self.get_by_id(event_id)
        if not event:
            return 0.0

        score = 0.0

        # Base score from result count
        if event.results_count:
            if event.results_count == 0:
                # No results is bad
                score = 0.0
            elif event.results_count <= 10:
                # Optimal range: 1-10 results
                score = event.results_count * 5  # Max 50 points
            elif event.results_count <= 50:
                # Still good but diminishing returns
                score = 50.0  # Cap at 50 for reasonable results
            else:
                # Too many results (overwhelming)
                score = 50.0 - (event.results_count - 50) * 0.2  # Penalty for too many
                score = max(30.0, score)  # Don't go below 30

        # Check for interactions (clicks, bookings, etc.)
        interaction = self.db.query(SearchInteraction).filter(SearchInteraction.search_event_id == event_id).first()

        if interaction:
            # Interaction bonus (adds 20-30 points)
            score += 25.0

        return min(100.0, score)  # Cap at 100

    def get_popular_searches_with_avg_results(self, limit: int = 10, hours: Optional[int] = None) -> List[Dict]:
        """
        Get popular searches with their average result counts.

        Useful for understanding which searches are most effective.

        Args:
            limit: Maximum number of results to return
            hours: Optional time window in hours (if not specified, gets all time)
        """
        query = self.db.query(
            SearchEvent.search_query,
            func.count(SearchEvent.id).label("search_count"),
            func.avg(SearchEvent.results_count).label("avg_results"),
        )

        # Apply time filter if hours specified
        if hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.filter(SearchEvent.searched_at >= cutoff_time)

        results = (
            query.group_by(SearchEvent.search_query).order_by(func.count(SearchEvent.id).desc()).limit(limit).all()
        )

        return [
            {"query": query, "search_count": search_count, "avg_results": float(avg_results) if avg_results else 0.0}
            for query, search_count, avg_results in results
        ]

    def count_searches_since(self, since: datetime) -> int:
        """
        Count total searches since a given datetime.

        Used for analytics and rate limiting.
        """
        return self.db.query(func.count(SearchEvent.id)).filter(SearchEvent.searched_at >= since).scalar() or 0

    def get_searches_by_user(self, user_id: str, limit: Optional[int] = None) -> List[SearchEvent]:
        """
        Get search events for a specific user.

        Used for user history and personalization.
        """
        query = (
            self.db.query(SearchEvent).filter(SearchEvent.user_id == user_id).order_by(SearchEvent.searched_at.desc())
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_searches_by_session(self, session_id: str) -> List[SearchEvent]:
        """
        Get search events for a guest session.

        Used for guest search history.
        """
        return (
            self.db.query(SearchEvent)
            .filter(SearchEvent.session_id == session_id)
            .order_by(SearchEvent.searched_at.desc())
            .all()
        )

    def count_searches_with_interactions(self, since: datetime) -> int:
        """
        Count searches that have interactions since a given time.

        Args:
            since: Count searches with interactions since this time

        Returns:
            Number of searches with interactions
        """
        from ..models.search_interaction import SearchInteraction

        # Subquery to get search event IDs with interactions
        interaction_subquery = (
            self.db.query(SearchInteraction.search_event_id)
            .filter(SearchInteraction.search_event_id.isnot(None))
            .subquery()
        )

        return (
            self.db.query(func.count(SearchEvent.id))
            .filter(SearchEvent.searched_at >= since, SearchEvent.id.in_(interaction_subquery))
            .scalar()
            or 0
        )

    def get_search_type_distribution(self, hours: Optional[int] = None) -> Dict[str, int]:
        """
        Get distribution of search types.

        Args:
            hours: Optional time window in hours

        Returns:
            Dictionary mapping search types to counts
        """
        query = self.db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))

        if hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.filter(SearchEvent.searched_at >= cutoff_time)

        results = query.group_by(SearchEvent.search_type).all()

        return {search_type: count for search_type, count in results}

    def get_search_patterns(self, query: str, days: int = 30) -> Dict:
        """
        Get search patterns for a specific query.

        Returns analytics about how this query is being searched.
        """
        from sqlalchemy import Date, cast

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get count of this search
        count = (
            self.db.query(func.count(SearchEvent.id))
            .filter(SearchEvent.search_query == query, SearchEvent.searched_at >= cutoff_date)
            .scalar()
            or 0
        )

        # Get average results for this query
        avg_results = (
            self.db.query(func.avg(SearchEvent.results_count))
            .filter(SearchEvent.search_query == query, SearchEvent.searched_at >= cutoff_date)
            .scalar()
            or 0.0
        )

        # Get daily counts
        daily_counts_query = (
            self.db.query(cast(SearchEvent.searched_at, Date).label("date"), func.count(SearchEvent.id).label("count"))
            .filter(SearchEvent.search_query == query, SearchEvent.searched_at >= cutoff_date)
            .group_by(cast(SearchEvent.searched_at, Date))
            .order_by(cast(SearchEvent.searched_at, Date))
            .all()
        )

        daily_counts = [{"date": str(date), "count": count} for date, count in daily_counts_query]

        # Get type distribution
        type_distribution_query = (
            self.db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
            .filter(SearchEvent.search_query == query, SearchEvent.searched_at >= cutoff_date)
            .group_by(SearchEvent.search_type)
            .all()
        )

        type_distribution = {search_type: count for search_type, count in type_distribution_query}

        return {
            "query": query,
            "count": count,
            "avg_results": float(avg_results) if avg_results else 0.0,
            "average_results": float(avg_results) if avg_results else 0.0,  # Alias for compatibility
            "period_days": days,
            "daily_counts": daily_counts,
            "type_distribution": type_distribution,
        }

    def get_previous_search_event(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        before_time: Optional[datetime] = None,
    ) -> Optional[SearchEvent]:
        """
        Get previous search event for duplicate detection.

        Used to check if a user has searched before (returning user detection).

        Args:
            user_id: User ID for authenticated users
            guest_session_id: Session ID for guest users
            before_time: Get events before this time (defaults to now)

        Returns:
            Previous SearchEvent or None if this is the first search
        """
        if before_time is None:
            before_time = datetime.now(timezone.utc)

        query = self.db.query(SearchEvent).filter(SearchEvent.searched_at < before_time)

        if user_id:
            query = query.filter(SearchEvent.user_id == user_id)
        elif guest_session_id:
            query = query.filter(SearchEvent.guest_session_id == guest_session_id)
        else:
            return None

        return query.order_by(SearchEvent.searched_at.desc()).first()

    def get_search_event_by_id(self, event_id: int) -> Optional[SearchEvent]:
        """
        Get search event by ID for validation.

        Simple wrapper around get_by_id for clarity.

        Args:
            event_id: Search event ID

        Returns:
            SearchEvent or None if not found
        """
        return self.get_by_id(event_id)
