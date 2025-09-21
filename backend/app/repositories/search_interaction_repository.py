# backend/app/repositories/search_interaction_repository.py
"""
Repository for search interaction data access.

Handles all database operations for search interactions including
clicks, hovers, bookmarks, and other user engagement metrics.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..models.search_interaction import SearchInteraction
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SearchInteractionRepository(BaseRepository[SearchInteraction]):
    """Repository for search interaction operations."""

    def __init__(self, db: Session):
        """Initialize the repository."""
        super().__init__(db, SearchInteraction)

    def create_interaction(self, interaction_data: Dict[str, Any]) -> SearchInteraction:
        """
        Create a new search interaction record.

        Args:
            interaction_data: Dictionary containing interaction details

        Returns:
            Created SearchInteraction instance
        """
        interaction = SearchInteraction(**interaction_data)
        self.db.add(interaction)
        return interaction

    def get_interactions_by_search_event(
        self, search_event_id: int, limit: int = 100
    ) -> List[SearchInteraction]:
        """
        Get all interactions for a specific search event.

        Args:
            search_event_id: ID of the search event
            limit: Maximum number of interactions to return

        Returns:
            List of SearchInteraction instances
        """
        return cast(
            List[SearchInteraction],
            self.db.query(SearchInteraction)
            .filter(SearchInteraction.search_event_id == search_event_id)
            .order_by(SearchInteraction.created_at.desc())
            .limit(limit)
            .all(),
        )

    def get_interactions_by_instructor(
        self, instructor_id: int, days: int = 30, limit: int = 100
    ) -> List[SearchInteraction]:
        """
        Get recent interactions for a specific instructor.

        Args:
            instructor_id: ID of the instructor
            days: Number of days to look back
            limit: Maximum number of interactions to return

        Returns:
            List of SearchInteraction instances
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        return cast(
            List[SearchInteraction],
            self.db.query(SearchInteraction)
            .filter(
                and_(
                    SearchInteraction.instructor_id == instructor_id,
                    SearchInteraction.created_at >= cutoff_date,
                )
            )
            .order_by(SearchInteraction.created_at.desc())
            .limit(limit)
            .all(),
        )

    def get_click_through_rate(self, search_event_ids: Sequence[int]) -> Dict[str, float | int]:
        """
        Calculate click-through rate for given search events.

        Args:
            search_event_ids: List of search event IDs to analyze

        Returns:
            Dictionary with CTR metrics
        """
        if not search_event_ids:
            return {"ctr": 0.0, "total_searches": 0, "total_clicks": 0}

        # Count clicks for these search events
        click_count = int(
            self.db.query(func.count(SearchInteraction.id))
            .filter(
                and_(
                    SearchInteraction.search_event_id.in_(search_event_ids),
                    SearchInteraction.interaction_type == "click",
                )
            )
            .scalar()
            or 0
        )

        total_searches = len(search_event_ids)
        ctr = (click_count / total_searches * 100) if total_searches > 0 else 0.0

        return {"ctr": round(ctr, 2), "total_searches": total_searches, "total_clicks": click_count}

    def get_average_position_clicked(self, instructor_id: int, days: int = 30) -> Optional[float]:
        """
        Get average position clicked for an instructor.

        Args:
            instructor_id: ID of the instructor
            days: Number of days to analyze

        Returns:
            Average position or None if no clicks
        """
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        avg_position = (
            self.db.query(func.avg(SearchInteraction.result_position))
            .filter(
                and_(
                    SearchInteraction.instructor_id == instructor_id,
                    SearchInteraction.interaction_type == "click",
                    SearchInteraction.created_at >= cutoff_date,
                    SearchInteraction.result_position.isnot(None),
                )
            )
            .scalar()
        )

        return float(avg_position) if avg_position else None

    def get_interaction_funnel(self, search_event_id: int) -> Dict[str, int]:
        """
        Get interaction funnel for a search event.

        Shows progression: view -> hover -> click -> contact/book

        Args:
            search_event_id: ID of the search event

        Returns:
            Dictionary with funnel metrics
        """
        interactions = cast(
            List[Tuple[str, int]],
            self.db.query(
                SearchInteraction.interaction_type, func.count(SearchInteraction.id).label("count")
            )
            .filter(SearchInteraction.search_event_id == search_event_id)
            .group_by(SearchInteraction.interaction_type)
            .all(),
        )

        funnel: Dict[str, int] = {
            "view": 0,
            "hover": 0,
            "click": 0,
            "view_profile": 0,
            "contact": 0,
            "book": 0,
        }

        for interaction_type, count in interactions:
            if interaction_type in funnel:
                funnel[interaction_type] = count

        return funnel

    def get_time_to_first_click(
        self, search_event_ids: Sequence[int]
    ) -> Dict[str, Optional[float] | int]:
        """
        Calculate average time to first click for search events.

        Args:
            search_event_ids: List of search event IDs

        Returns:
            Dictionary with timing metrics
        """
        if not search_event_ids:
            return {"avg_time_seconds": None, "median_time_seconds": None}

        # Get first clicks for each search event
        first_clicks = cast(
            List[Tuple[int, float]],
            self.db.query(
                SearchInteraction.search_event_id,
                func.min(SearchInteraction.time_to_interaction).label("first_click_time"),
            )
            .filter(
                and_(
                    SearchInteraction.search_event_id.in_(search_event_ids),
                    SearchInteraction.interaction_type == "click",
                    SearchInteraction.time_to_interaction.isnot(None),
                )
            )
            .group_by(SearchInteraction.search_event_id)
            .all(),
        )

        if not first_clicks:
            return {"avg_time_seconds": None, "median_time_seconds": None}

        times = [click_time for _, click_time in first_clicks]
        avg_time = sum(times) / len(times)

        # Calculate median
        sorted_times = sorted(times)
        n = len(sorted_times)
        median_time = (
            sorted_times[n // 2]
            if n % 2 == 1
            else (sorted_times[n // 2 - 1] + sorted_times[n // 2]) / 2
        )

        return {
            "avg_time_seconds": round(avg_time, 2),
            "median_time_seconds": round(median_time, 2),
            "sample_size": len(first_clicks),
        }

    def get_popular_instructors_from_clicks(
        self, days: int = 7, limit: int = 10
    ) -> List[Dict[str, Optional[float] | int]]:
        """
        Get most clicked instructors in recent searches.

        Args:
            days: Number of days to analyze
            limit: Number of instructors to return

        Returns:
            List of dictionaries with instructor click data
        """
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        results = cast(
            List[Tuple[int, int, Optional[float]]],
            self.db.query(
                SearchInteraction.instructor_id,
                func.count(SearchInteraction.id).label("click_count"),
                func.avg(SearchInteraction.result_position).label("avg_position"),
            )
            .filter(
                and_(
                    SearchInteraction.interaction_type == "click",
                    SearchInteraction.created_at >= cutoff_date,
                    SearchInteraction.instructor_id.isnot(None),
                )
            )
            .group_by(SearchInteraction.instructor_id)
            .order_by(func.count(SearchInteraction.id).desc())
            .limit(limit)
            .all(),
        )

        return [
            {
                "instructor_id": instructor_id,
                "click_count": click_count,
                "avg_position": round(float(avg_pos), 1) if avg_pos else None,
            }
            for instructor_id, click_count, avg_pos in results
        ]
