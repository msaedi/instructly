# backend/app/repositories/search_history_repository.py
"""
Search History Repository for data access operations.

Unified implementation that handles both authenticated and guest users
without code duplication.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, cast

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import FromClause

from ..models.search_history import SearchHistory
from ..schemas.search_context import SearchUserContext
from .base_repository import BaseRepository


class SearchHistoryRepository(BaseRepository[SearchHistory]):
    """
    Repository for search history data access.

    Provides unified queries that work for both authenticated and guest users.
    """

    def __init__(self, db: Session) -> None:
        """Initialize with SearchHistory model."""
        super().__init__(db, SearchHistory)

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

    def increment_search_count(self, search_id: int) -> Optional[SearchHistory]:
        """
        Increment count and update last_searched_at timestamp.

        Args:
            search_id: ID of the search to update

        Returns:
            Updated SearchHistory or None if not found
        """
        search = self.get_by_id(search_id)
        if search and not search.deleted_at:
            search.search_count += 1
            search.last_searched_at = datetime.now(timezone.utc)
            self.db.flush()
            return search
        return None

    def find_existing_search_for_update(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Optional[SearchHistory]:
        """
        Find existing search for incrementing (not soft-deleted).

        This is used to check if we should increment an existing search
        or create a new one.

        Args:
            user_id: User ID for authenticated searches
            guest_session_id: Guest session ID for anonymous searches
            search_query: The search query to look for

        Returns:
            Existing SearchHistory if found, None otherwise
        """
        if not search_query:
            return None

        # Normalize the query for lookup
        normalized_query = search_query.strip().lower()

        query = self.db.query(SearchHistory).filter(
            SearchHistory.normalized_query == normalized_query, SearchHistory.deleted_at.is_(None)
        )

        if user_id is not None:
            query = query.filter(SearchHistory.user_id == user_id)
        elif guest_session_id:
            query = query.filter(SearchHistory.guest_session_id == guest_session_id)
        else:
            return None

        return cast(Optional[SearchHistory], query.first())

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

    def get_recent_searches(
        self, user_id: Optional[str] = None, guest_session_id: Optional[str] = None, limit: int = 3
    ) -> List[SearchHistory]:
        """
        Get recent searches for a user or guest session.

        Excludes soft-deleted entries and orders by most recent.
        """
        if user_id is not None:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return []

        query = self.db.query(SearchHistory).filter(SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)
        return cast(
            List[SearchHistory],
            query.order_by(desc(SearchHistory.last_searched_at)).limit(limit).all(),
        )

    def count_searches(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        exclude_deleted: bool = True,
    ) -> int:
        """
        Count searches for a user or guest session.
        """
        if user_id is not None:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            return 0

        query = self.db.query(func.count(SearchHistory.id))

        if exclude_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        query = self._add_user_filter(query, context)
        result = query.scalar()
        return int(result or 0)

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

        # Use scalar_subquery() to properly handle the subquery
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

        result: int = int(
            query.update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )

        return result > 0

    def soft_delete_guest_search(self, search_id: int, guest_session_id: str) -> bool:
        """
        Soft delete a specific search entry for a guest.
        """
        context = SearchUserContext.from_guest(guest_session_id)

        query = self.db.query(SearchHistory).filter(
            SearchHistory.id == search_id, SearchHistory.deleted_at.is_(None)
        )

        query = self._add_user_filter(query, context)

        result: int = int(
            query.update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
        )

        return result > 0

    def create(self, **kwargs: Any) -> SearchHistory:
        """
        Create a new search history entry.
        """
        # Handle the new timestamp fields
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

        # Normalize the query for deduplication
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

    # Guest-to-user conversion methods (remain unchanged as they're specific operations)

    def get_guest_searches_for_conversion(self, guest_session_id: str) -> List[SearchHistory]:
        """
        Get all guest searches for conversion to user account, including deleted ones.

        Ordered by first search time, then query to break ties deterministically.
        """
        return cast(
            List[SearchHistory],
            self.db.query(SearchHistory)
            .filter(
                SearchHistory.guest_session_id == guest_session_id,
                SearchHistory.converted_to_user_id.is_(None),
            )
            .order_by(SearchHistory.first_searched_at, SearchHistory.search_query)
            .all(),
        )

    def mark_searches_as_converted(self, guest_session_id: str, user_id: str) -> int:
        """
        Mark guest searches as converted to user account.
        """
        return int(
            self.db.query(SearchHistory)
            .filter(
                SearchHistory.guest_session_id == guest_session_id,
                SearchHistory.converted_to_user_id.is_(None),
            )
            .update(
                {"converted_to_user_id": user_id, "converted_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )

    # Privacy and data management methods

    def get_user_searches(self, user_id: str, exclude_deleted: bool = True) -> List[SearchHistory]:
        """
        Get all searches for a user.

        Used by: PrivacyService for data export

        Args:
            user_id: The user ID
            exclude_deleted: Whether to exclude soft-deleted searches

        Returns:
            List of SearchHistory records
        """
        query = self.db.query(SearchHistory).filter(SearchHistory.user_id == user_id)

        if exclude_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        return cast(
            List[SearchHistory], query.order_by(desc(SearchHistory.first_searched_at)).all()
        )

    def delete_user_searches(self, user_id: str) -> int:
        """
        Delete all searches for a user (hard delete).

        Used by: PrivacyService for right to be forgotten

        Args:
            user_id: The user ID

        Returns:
            Number of deleted records
        """
        return int(
            self.db.query(SearchHistory)
            .filter(SearchHistory.user_id == user_id)
            .delete(synchronize_session=False)
        )

    def count_all_searches(self) -> int:
        """
        Count all search history records.

        Used by: PrivacyService for statistics

        Returns:
            Total count of search history records
        """
        return int(self.db.query(func.count(SearchHistory.id)).scalar() or 0)

    # Analytics methods

    def find_analytics_eligible_searches(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_deleted: bool = True,
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
            query = query.filter(SearchHistory.first_searched_at >= start_date)

        if end_date:
            query = query.filter(SearchHistory.first_searched_at <= end_date)

        # Exclude searches that have been converted (to avoid double counting)
        # We keep the user version, not the guest version
        query = query.filter(
            or_(SearchHistory.converted_to_user_id.is_(None), SearchHistory.user_id.isnot(None))
        )

        return query

    # New methods for SearchHistoryService violations

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

        Args:
            user_id: User ID for authenticated users
            guest_session_id: Session ID for guest users
            search_query: Original search query
            normalized_query: Normalized query for deduplication
            search_type: Type of search
            results_count: Number of results returned

        Returns:
            SearchHistory record (new or updated) if found, otherwise None
        """
        from sqlalchemy.dialects.postgresql import insert

        now = datetime.now(timezone.utc)

        # Prepare values for UPSERT
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

        # Create INSERT statement
        stmt = insert(SearchHistory).values(**values)

        # Define conflict resolution based on user type
        if user_id is not None:
            # For authenticated users
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "normalized_query"],
                set_={
                    "search_count": SearchHistory.search_count + 1,
                    "last_searched_at": now,
                    "results_count": stmt.excluded.results_count,
                    "search_query": stmt.excluded.search_query,  # Update case sensitivity
                },
            )
        else:
            # For guest users
            stmt = stmt.on_conflict_do_update(
                index_elements=["guest_session_id", "normalized_query"],
                set_={
                    "search_count": SearchHistory.search_count + 1,
                    "last_searched_at": now,
                    "results_count": stmt.excluded.results_count,
                    "search_query": stmt.excluded.search_query,  # Update case sensitivity
                },
            )

        # Execute UPSERT
        self.db.execute(stmt)
        self.db.commit()

        # Fetch and return the result
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

        Args:
            user_id: User ID for authenticated users
            guest_session_id: Session ID for guest users
            normalized_query: Normalized search query

        Returns:
            SearchHistory record or None
        """
        from sqlalchemy import and_

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

    def enforce_search_limit(
        self,
        user_id: Optional[str] = None,
        guest_session_id: Optional[str] = None,
        max_searches: int = 10,
    ) -> int:
        """
        Enforce maximum search limit by soft-deleting oldest searches.

        Args:
            user_id: User ID for authenticated users
            guest_session_id: Session ID for guest users
            max_searches: Maximum number of searches to keep

        Returns:
            Number of searches soft-deleted
        """
        # Get IDs to keep (most recent)
        keep_ids_subquery = self.get_searches_to_delete(
            user_id=user_id, guest_session_id=guest_session_id, keep_count=max_searches
        )

        # Soft delete searches not in keep list
        return self.soft_delete_old_searches(
            user_id=user_id, guest_session_id=guest_session_id, keep_ids_subquery=keep_ids_subquery
        )

    def get_previous_search_event(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        before_time: Optional[datetime] = None,
    ) -> None:
        """
        Get previous search event for duplicate detection.

        NOTE: This actually needs to query SearchEvent model, not SearchHistory.
        This is a cross-model query that should be handled by SearchEventRepository.
        We'll return None here and let the service handle it with SearchEventRepository.

        Args:
            user_id: User ID for authenticated users
            guest_session_id: Session ID for guest users
            before_time: Get events before this time

        Returns:
            None (should be handled by SearchEventRepository)
        """
        # This needs to be handled by SearchEventRepository
        # The service should use self.event_repository.get_previous_search_event()
        return None

    def get_search_event_by_id(self, event_id: int) -> None:
        """
        Get search event by ID for validation.

        NOTE: This actually needs to query SearchEvent model, not SearchHistory.
        This is a cross-model query that should be handled by SearchEventRepository.
        We'll return None here and let the service handle it with SearchEventRepository.

        Args:
            event_id: Search event ID

        Returns:
            None (should be handled by SearchEventRepository)
        """
        # This needs to be handled by SearchEventRepository
        # The service should use self.event_repository.get_by_id()
        return None

    # Cleanup methods for SearchHistoryCleanupService

    def hard_delete_old_soft_deleted(self, days_old: int) -> int:
        """
        Permanently delete soft-deleted searches older than specified days.

        Args:
            days_old: Number of days since soft deletion

        Returns:
            Number of records permanently deleted
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        deleted_count_int = int(
            self.db.query(SearchHistory)
            .filter(
                and_(SearchHistory.deleted_at.isnot(None), SearchHistory.deleted_at < cutoff_date)
            )
            .delete(synchronize_session=False)
        )

        return deleted_count_int

    # --------------------
    # Statistics helpers
    # --------------------

    def count_soft_deleted_total(self) -> int:
        """
        Count all soft-deleted search history records.

        Returns:
            Total number of records where deleted_at is not null
        """
        return int(
            self.db.query(SearchHistory).filter(SearchHistory.deleted_at.isnot(None)).count()
        )

    def count_soft_deleted_eligible(self, days_old: int) -> int:
        """
        Count soft-deleted records older than the given number of days.

        Args:
            days_old: Age in days past soft-deletion to be eligible

        Returns:
            Number of eligible soft-deleted records
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.deleted_at.isnot(None),
                    SearchHistory.deleted_at < cutoff_date,
                )
            )
            .count()
        )

    def count_total_guest_sessions(self) -> int:
        """
        Count all guest session records (any record with a guest_session_id).
        """
        return int(
            self.db.query(SearchHistory).filter(SearchHistory.guest_session_id.isnot(None)).count()
        )

    def count_converted_guest_eligible(self, days_old: int) -> int:
        """
        Count converted guest searches older than the purge threshold.

        Args:
            days_old: Days since conversion to be eligible
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    SearchHistory.converted_at < cutoff_date,
                )
            )
            .count()
        )

    def count_expired_guest_eligible(self, days_old: int) -> int:
        """
        Count unconverted guest searches that have passed the expiry+purge window.

        Args:
            days_old: Combined expiry + purge days threshold
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.is_(None),
                    SearchHistory.first_searched_at < cutoff_date,
                )
            )
            .count()
        )

    def delete_converted_guest_searches(self, days_old: int) -> int:
        """
        Delete guest searches that were converted to user more than X days ago.

        Args:
            days_old: Number of days since conversion

        Returns:
            Number of records deleted
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        deleted_count = int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    SearchHistory.converted_at < cutoff_date,
                )
            )
            .delete(synchronize_session=False)
        )

        return deleted_count

    def delete_old_unconverted_guest_searches(self, days_old: int) -> int:
        """
        Hard delete old guest searches that were never converted.

        CRITICAL: This does HARD DELETE (permanent removal) for GDPR compliance.

        Args:
            days_old: Number of days since first search

        Returns:
            Number of records permanently deleted
        """
        from sqlalchemy import and_

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        deleted_count = int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.is_(None),
                    SearchHistory.first_searched_at < cutoff_date,
                )
            )
            .delete(synchronize_session=False)
        )

        return deleted_count
