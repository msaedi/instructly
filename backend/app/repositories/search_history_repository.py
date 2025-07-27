# backend/app/repositories/search_history_repository.py
"""
Search History Repository for data access operations.

Unified implementation that handles both authenticated and guest users
without code duplication.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Query

from ..models.search_history import SearchHistory
from ..schemas.search_context import SearchUserContext
from .base_repository import BaseRepository


class SearchHistoryRepository(BaseRepository[SearchHistory]):
    """
    Repository for search history data access.

    Provides unified queries that work for both authenticated and guest users.
    """

    def __init__(self, db):
        """Initialize with SearchHistory model."""
        super().__init__(db, SearchHistory)

    def _add_user_filter(self, query: Query, context: SearchUserContext) -> Query:
        """
        Add user-specific filters to a query.

        Helper method to consistently filter by user_id or guest_session_id.
        """
        if context.user_id:
            return query.filter(SearchHistory.user_id == context.user_id)
        elif context.guest_session_id:
            return query.filter(SearchHistory.guest_session_id == context.guest_session_id)
        else:
            raise ValueError("SearchUserContext must have either user_id or guest_session_id")

    def find_existing_search(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, query: str = None
    ) -> Optional[SearchHistory]:
        """
        Find an existing search entry for a user or guest.

        Excludes soft-deleted entries.
        """
        if not query:
            return None

        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return None

        search_query = self.db.query(SearchHistory).filter(
            SearchHistory.deleted_at.is_(None), SearchHistory.search_query == query
        )

        search_query = self._add_user_filter(search_query, context)
        return search_query.first()

    def get_recent_searches(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, limit: int = 3
    ) -> List[SearchHistory]:
        """
        Get recent searches for a user or guest session.

        Excludes soft-deleted entries and orders by most recent.
        """
        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return []

        query = self.db.query(SearchHistory).filter(SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)
        return query.order_by(desc(SearchHistory.created_at)).limit(limit).all()

    def count_searches(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, exclude_deleted: bool = True
    ) -> int:
        """
        Count searches for a user or guest session.
        """
        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return 0

        query = self.db.query(func.count(SearchHistory.id))

        if exclude_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)
        return query.scalar() or 0

    def get_searches_to_delete(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, keep_count: int = 10
    ) -> Query:
        """
        Get IDs of searches to keep (most recent).

        Returns a subquery that can be used to identify searches to delete.
        """
        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return self.db.query(SearchHistory.id).filter(False).subquery()

        query = self.db.query(SearchHistory.id).filter(SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)
        return query.order_by(desc(SearchHistory.created_at)).limit(keep_count).subquery()

    def soft_delete_old_searches(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, keep_ids_subquery: Query = None
    ) -> int:
        """
        Soft delete searches not in the keep list.
        """
        if keep_ids_subquery is None:
            return 0

        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return 0

        # Use scalar_subquery() to properly handle the subquery
        from sqlalchemy import select

        query = self.db.query(SearchHistory).filter(
            ~SearchHistory.id.in_(select(keep_ids_subquery)), SearchHistory.deleted_at.is_(None)
        )

        query = self._add_user_filter(query, context)

        return query.update({"deleted_at": datetime.utcnow()}, synchronize_session=False)

    def soft_delete_by_id(self, search_id: int, user_id: int) -> bool:
        """
        Soft delete a specific search entry for an authenticated user.
        """
        context = SearchUserContext.from_user(user_id)

        query = self.db.query(SearchHistory).filter(SearchHistory.id == search_id, SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)

        result = query.update({"deleted_at": datetime.utcnow()}, synchronize_session=False)

        return result > 0

    def soft_delete_guest_search(self, search_id: int, guest_session_id: str) -> bool:
        """
        Soft delete a specific search entry for a guest.
        """
        context = SearchUserContext.from_guest(guest_session_id)

        query = self.db.query(SearchHistory).filter(SearchHistory.id == search_id, SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)

        result = query.update({"deleted_at": datetime.utcnow()}, synchronize_session=False)

        return result > 0

    def create(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        search_query: str = None,
        search_type: str = "natural_language",
        results_count: Optional[int] = None,
        created_at: Optional[datetime] = None,
        deleted_at: Optional[datetime] = None,
        **kwargs,
    ) -> SearchHistory:
        """
        Create a new search history entry.
        """
        search_history = SearchHistory(
            user_id=user_id,
            guest_session_id=guest_session_id,
            search_query=search_query,
            search_type=search_type,
            results_count=results_count,
            created_at=created_at or datetime.utcnow(),
            deleted_at=deleted_at,
        )

        self.db.add(search_history)
        self.db.flush()
        return search_history

    # Guest-to-user conversion methods (remain unchanged as they're specific operations)

    def get_guest_searches_for_conversion(self, guest_session_id: str) -> List[SearchHistory]:
        """
        Get all guest searches for conversion to user account, including deleted ones.
        """
        return (
            self.db.query(SearchHistory)
            .filter(SearchHistory.guest_session_id == guest_session_id, SearchHistory.converted_to_user_id.is_(None))
            .order_by(SearchHistory.created_at)
            .all()
        )

    def mark_searches_as_converted(self, guest_session_id: str, user_id: int) -> int:
        """
        Mark guest searches as converted to user account.
        """
        return (
            self.db.query(SearchHistory)
            .filter(SearchHistory.guest_session_id == guest_session_id, SearchHistory.converted_to_user_id.is_(None))
            .update({"converted_to_user_id": user_id, "converted_at": datetime.utcnow()}, synchronize_session=False)
        )

    # Analytics methods

    def find_analytics_eligible_searches(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, include_deleted: bool = True
    ) -> Query:
        """
        Get searches eligible for analytics.

        This includes soft-deleted searches but excludes duplicates
        from guest-to-user conversions.
        """
        query = self.db.query(SearchHistory)

        if not include_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        if start_date:
            query = query.filter(SearchHistory.created_at >= start_date)

        if end_date:
            query = query.filter(SearchHistory.created_at <= end_date)

        # Exclude searches that have been converted (to avoid double counting)
        # We keep the user version, not the guest version
        query = query.filter(or_(SearchHistory.converted_to_user_id.is_(None), SearchHistory.user_id.isnot(None)))

        return query
