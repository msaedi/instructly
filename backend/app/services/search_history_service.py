# backend/app/services/search_history_service.py
"""
Search History Service for tracking and retrieving user searches.

Handles:
- Recording new searches with deduplication
- Retrieving recent searches
- Maintaining search history limits per user
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models.search_history import SearchHistory
from .base import BaseService

logger = logging.getLogger(__name__)


class SearchHistoryService(BaseService):
    """
    Service for managing user search history.

    Tracks searches, handles deduplication, and maintains
    a rolling window of recent searches per user.
    """

    MAX_SEARCHES_PER_USER = 10  # Maximum number of searches to keep per user

    def __init__(self, db: Session):
        """Initialize the search history service."""
        super().__init__(db)

    @BaseService.measure_operation("record_search")
    async def record_search(
        self, user_id: int, query: str, search_type: str = "natural_language", results_count: Optional[int] = None
    ) -> SearchHistory:
        """
        Record a user search, updating timestamp if it already exists.

        Args:
            user_id: ID of the user performing the search
            query: The search query string
            search_type: Type of search ('natural_language', 'category', 'filter')
            results_count: Number of results returned (optional)

        Returns:
            The created or updated SearchHistory record
        """
        try:
            # Check if this exact query already exists for the user
            existing = (
                self.db.query(SearchHistory)
                .filter(SearchHistory.user_id == user_id, SearchHistory.search_query == query)
                .first()
            )

            if existing:
                # Update timestamp and results count
                existing.created_at = datetime.utcnow()
                existing.results_count = results_count
                self.db.commit()
                self.db.refresh(existing)

                logger.info(f"Updated existing search history for user {user_id}: {query}")
                return existing

            # Create new search history entry
            search_history = SearchHistory(
                user_id=user_id, search_query=query, search_type=search_type, results_count=results_count
            )

            self.db.add(search_history)
            self.db.commit()
            self.db.refresh(search_history)

            logger.info(f"Created new search history for user {user_id}: {query}")

            # Maintain limit per user
            await self._enforce_search_limit(user_id)

            return search_history

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording search: {str(e)}")
            raise

    @BaseService.measure_operation("get_recent_searches")
    def get_recent_searches(self, user_id: int, limit: int = 3) -> List[SearchHistory]:
        """
        Get the most recent unique searches for a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of searches to return

        Returns:
            List of recent SearchHistory records
        """
        searches = (
            self.db.query(SearchHistory)
            .filter(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.created_at))
            .limit(limit)
            .all()
        )

        logger.debug(f"Retrieved {len(searches)} recent searches for user {user_id}")
        return searches

    @BaseService.measure_operation("delete_search")
    def delete_search(self, user_id: int, search_id: int) -> bool:
        """
        Delete a specific search history entry.

        Args:
            user_id: ID of the user (for authorization)
            search_id: ID of the search history entry

        Returns:
            True if deleted, False if not found or unauthorized
        """
        search = (
            self.db.query(SearchHistory).filter(SearchHistory.id == search_id, SearchHistory.user_id == user_id).first()
        )

        if not search:
            logger.warning(f"Search history {search_id} not found for user {user_id}")
            return False

        self.db.delete(search)
        self.db.commit()

        logger.info(f"Deleted search history {search_id} for user {user_id}")
        return True

    async def _enforce_search_limit(self, user_id: int) -> None:
        """
        Enforce the maximum number of searches per user.

        Deletes oldest searches if limit is exceeded.
        """
        # Count current searches
        search_count = self.db.query(func.count(SearchHistory.id)).filter(SearchHistory.user_id == user_id).scalar()

        if search_count > self.MAX_SEARCHES_PER_USER:
            # Get IDs of searches to keep (most recent)
            keep_searches = (
                self.db.query(SearchHistory.id)
                .filter(SearchHistory.user_id == user_id)
                .order_by(desc(SearchHistory.created_at))
                .limit(self.MAX_SEARCHES_PER_USER)
                .subquery()
            )

            # Delete searches not in the keep list
            deleted = (
                self.db.query(SearchHistory)
                .filter(SearchHistory.user_id == user_id, ~SearchHistory.id.in_(keep_searches))
                .delete(synchronize_session=False)
            )

            self.db.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} old searches for user {user_id} to maintain limit")
