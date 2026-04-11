"""Soft-delete and search-limit lifecycle helpers for search history."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.sql import FromClause

from ...models.search_history import SearchHistory
from ...schemas.search_context import SearchUserContext
from .mixin_base import SearchHistoryRepositoryMixinBase


class LifecycleMixin(SearchHistoryRepositoryMixinBase):
    """Lifecycle policies for SearchHistory rows."""

    def get_searches_to_delete(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        keep_count: int = 10,
    ) -> FromClause:
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
        return query.order_by(desc(SearchHistory.first_searched_at)).limit(keep_count).subquery()

    def soft_delete_old_searches(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        keep_ids_subquery: Optional[FromClause] = None,
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

        from sqlalchemy import select

        query = self.db.query(SearchHistory).filter(
            ~SearchHistory.id.in_(select(keep_ids_subquery)), SearchHistory.deleted_at.is_(None)
        )
        query = self._add_user_filter(query, context)
        return int(
            query.update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )

    def soft_delete_by_id(self, search_id: str, user_id: str) -> bool:
        """
        Soft delete a specific search entry for an authenticated user.
        """
        context = SearchUserContext.from_user(user_id)

        query = self.db.query(SearchHistory).filter(
            SearchHistory.id == search_id, SearchHistory.deleted_at.is_(None)
        )
        query = self._add_user_filter(query, context)

        result = int(
            query.update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )
        return result > 0

    def soft_delete_guest_search(self, search_id: str, guest_session_id: str) -> bool:
        """
        Soft delete a specific search entry for a guest.
        """
        context = SearchUserContext.from_guest(guest_session_id)

        query = self.db.query(SearchHistory).filter(
            SearchHistory.id == search_id, SearchHistory.deleted_at.is_(None)
        )
        query = self._add_user_filter(query, context)

        result = int(
            query.update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )
        return result > 0

    def enforce_search_limit(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        max_searches: int = 10,
    ) -> int:
        """
        Enforce maximum search limit by soft-deleting oldest searches.
        """
        keep_ids_subquery = self.get_searches_to_delete(
            user_id=user_id, guest_session_id=guest_session_id, keep_count=max_searches
        )
        return self.soft_delete_old_searches(
            user_id=user_id, guest_session_id=guest_session_id, keep_ids_subquery=keep_ids_subquery
        )
