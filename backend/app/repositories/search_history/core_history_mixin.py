"""Core read/write operations for deduplicated search history."""

from datetime import datetime, timezone
from typing import Any, List, Optional, cast

from sqlalchemy import and_, desc
from sqlalchemy.orm import Query

from ...models.search_history import SearchHistory
from ...schemas.search_context import SearchUserContext
from .mixin_base import SearchHistoryRepositoryMixinBase


class CoreHistoryMixin(SearchHistoryRepositoryMixinBase):
    """Primary SearchHistory access and write helpers."""

    def _add_user_filter(self, query: Query[Any], context: SearchUserContext) -> Query[Any]:
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
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Optional[SearchHistory]:
        """
        Find an existing search entry for a user or guest.

        Excludes soft-deleted entries.
        """
        if not query:
            return None

        if user_id is not None:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return None

        search_query = self.db.query(SearchHistory).filter(
            SearchHistory.deleted_at.is_(None), SearchHistory.search_query == query
        )

        search_query = self._add_user_filter(search_query, context)
        return cast(Optional[SearchHistory], search_query.first())

    def get_recent_searches_unified(
        self, context: SearchUserContext, limit: int = 10, order_by: str = "last_searched_at"
    ) -> List[SearchHistory]:
        """
        Get recent searches using SearchUserContext, ordered by specified field.

        Args:
            context: Search user context with user_id or guest_session_id
            limit: Maximum number of results
            order_by: Field to order by (last_searched_at or first_searched_at)

        Returns:
            List of recent searches
        """
        query = self.db.query(SearchHistory).filter(SearchHistory.deleted_at.is_(None))
        query = self._add_user_filter(query, context)

        if order_by == "last_searched_at":
            query = query.order_by(desc(SearchHistory.last_searched_at))
        elif order_by == "first_searched_at":
            query = query.order_by(desc(SearchHistory.first_searched_at))
        else:
            query = query.order_by(desc(SearchHistory.last_searched_at))

        return cast(List[SearchHistory], query.limit(limit).all())

    def create(self, **kwargs: Any) -> SearchHistory:
        """
        Create a new search history entry.
        """
        now = datetime.now(timezone.utc)
        user_id = cast(Optional[str], kwargs.get("user_id"))
        guest_session_id = cast(Optional[str], kwargs.get("guest_session_id"))
        search_query = cast(Optional[str], kwargs.get("search_query"))
        search_type = cast(str, kwargs.get("search_type", "natural_language"))
        results_count = cast(Optional[int], kwargs.get("results_count"))
        deleted_at = cast(Optional[datetime], kwargs.get("deleted_at"))
        first_searched_at = cast(datetime, kwargs.get("first_searched_at", now))
        last_searched_at = cast(datetime, kwargs.get("last_searched_at", now))
        search_count = cast(int, kwargs.get("search_count", 1))

        normalized_query = cast(Optional[str], kwargs.get("normalized_query"))
        if not normalized_query and search_query:
            normalized_query = search_query.strip().lower()

        search_history = SearchHistory(
            user_id=user_id,
            guest_session_id=guest_session_id,
            search_query=search_query,
            normalized_query=normalized_query,
            search_type=search_type,
            results_count=results_count,
            first_searched_at=first_searched_at,
            last_searched_at=last_searched_at,
            search_count=search_count,
            deleted_at=deleted_at,
        )

        self.db.add(search_history)
        self.db.flush()
        return search_history

    def upsert_search(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        search_query: Optional[str] = None,
        normalized_query: Optional[str] = None,
        search_type: str = "natural_language",
        results_count: Optional[int] = None,
    ) -> Optional[SearchHistory]:
        """
        Atomic UPSERT operation for search history.

        Implements PostgreSQL INSERT...ON CONFLICT UPDATE pattern.
        This eliminates race conditions completely.
        """
        from sqlalchemy.dialects.postgresql import insert

        now = datetime.now(timezone.utc)

        values = {
            "user_id": user_id,
            "guest_session_id": guest_session_id,
            "search_query": search_query,
            "normalized_query": normalized_query,
            "search_type": search_type,
            "results_count": results_count,
            "search_count": 1,
            "first_searched_at": now,
            "last_searched_at": now,
        }

        stmt = insert(SearchHistory).values(**values)

        if user_id is not None:
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "normalized_query"],
                set_={
                    "search_count": SearchHistory.search_count + 1,
                    "last_searched_at": now,
                    "results_count": stmt.excluded.results_count,
                    "search_query": stmt.excluded.search_query,
                },
            )
        else:
            stmt = stmt.on_conflict_do_update(
                index_elements=["guest_session_id", "normalized_query"],
                set_={
                    "search_count": SearchHistory.search_count + 1,
                    "last_searched_at": now,
                    "results_count": stmt.excluded.results_count,
                    "search_query": stmt.excluded.search_query,
                },
            )

        self.db.execute(stmt)
        self.db.commit()

        return self.get_search_by_user_and_query(
            user_id=user_id, guest_session_id=guest_session_id, normalized_query=normalized_query
        )

    def get_search_by_user_and_query(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        normalized_query: Optional[str] = None,
    ) -> Optional[SearchHistory]:
        """
        Get search history by user/guest and normalized query.

        Used after UPSERT to fetch the updated record.
        """
        if user_id is not None:
            return cast(
                Optional[SearchHistory],
                self.db.query(SearchHistory)
                .populate_existing()
                .filter(
                    and_(
                        SearchHistory.user_id == user_id,
                        SearchHistory.normalized_query == normalized_query,
                        SearchHistory.deleted_at.is_(None),
                    )
                )
                .first(),
            )
        elif guest_session_id:
            return cast(
                Optional[SearchHistory],
                self.db.query(SearchHistory)
                .populate_existing()
                .filter(
                    and_(
                        SearchHistory.guest_session_id == guest_session_id,
                        SearchHistory.normalized_query == normalized_query,
                        SearchHistory.deleted_at.is_(None),
                    )
                )
                .first(),
            )
        return None
