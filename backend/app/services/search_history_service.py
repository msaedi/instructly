# backend/app/services/search_history_service.py
"""
Search History Service for tracking and retrieving user searches.

Unified implementation that handles both authenticated and guest users
without code duplication.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.search_history import SearchHistory
from ..repositories.search_event_repository import SearchEventRepository
from ..repositories.search_history_repository import SearchHistoryRepository
from ..schemas.search_context import SearchUserContext
from .base import BaseService

logger = logging.getLogger(__name__)


class SearchHistoryService(BaseService):
    """
    Service for managing search history.

    Unified implementation that works for both authenticated and guest users.
    """

    def __init__(self, db: Session):
        """Initialize the search history service."""
        super().__init__(db)
        self.repository = SearchHistoryRepository(db)
        self.event_repository = SearchEventRepository(db)

    @BaseService.measure_operation("record_search")
    def record_search(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        query: str = None,
        search_type: str = "natural_language",
        results_count: Optional[int] = None,
        context: Optional[SearchUserContext] = None,
        search_data: Optional[dict] = None,
    ) -> SearchHistory:
        """
        Record a search - supports both old and new API.

        Old API: record_search(user_id=1, query="test")
        New API: record_search(context=context, search_data={...})
        """
        # If context is provided, use new API
        if context is not None and search_data is not None:
            return self._record_search_impl(context, search_data)

        # Otherwise use old API parameters
        if user_id:
            ctx = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            ctx = SearchUserContext.from_guest(guest_session_id)
        else:
            raise ValueError("Must provide either user_id or guest_session_id")

        data = {"search_query": query, "search_type": search_type, "results_count": results_count}

        return self._record_search_impl(ctx, data)

    def _record_search_impl(
        self,
        context: SearchUserContext,
        search_data: dict,
    ) -> SearchHistory:
        """
        Internal implementation of search recording.
        """
        try:
            # Check if this exact query already exists (excluding soft-deleted)
            existing = self.repository.find_existing_search_for_update(
                user_id=context.user_id,
                guest_session_id=context.guest_session_id,
                search_query=search_data["search_query"],
            )

            if existing:
                # Update existing record (increment count, update timestamp)
                result = self.repository.increment_search_count(existing.id)
                logger.info(
                    f"Updated existing search history for {context.identifier}: {search_data['search_query']} (count: {result.search_count})"
                )
            else:
                # Create new search history entry with timestamps
                search_history = self.repository.create(
                    user_id=context.user_id,
                    guest_session_id=context.guest_session_id,
                    search_query=search_data["search_query"],
                    search_type=search_data.get("search_type", "natural_language"),
                    results_count=search_data.get("results_count"),
                    first_searched_at=datetime.now(timezone.utc),
                    last_searched_at=datetime.now(timezone.utc),
                    search_count=1,
                )
                result = search_history
                logger.info(f"Created new search history for {context.identifier}: {search_data['search_query']}")

                # Maintain limit per user/guest
                self._enforce_search_limit(context)

            # Always create event for analytics (append-only)
            event_data = {
                "user_id": context.user_id,
                "guest_session_id": context.guest_session_id,
                "search_query": search_data["search_query"],
                "search_type": search_data.get("search_type", "natural_language"),
                "results_count": search_data.get("results_count", 0),
                "session_id": getattr(context, "session_id", None),
                "referrer": search_data.get("referrer"),
                "search_context": search_data.get("context"),
            }
            self.event_repository.create_event(event_data)

            # Use service transaction pattern instead of direct DB operations
            with self.transaction():
                pass  # Transaction commits automatically

            # Refresh through repository
            self.db.refresh(result)

            return result

        except Exception as e:
            logger.error(f"Error recording search: {str(e)}")
            raise

    @BaseService.measure_operation("get_recent_searches")
    def get_recent_searches(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        context: Optional[SearchUserContext] = None,
        limit: int = 10,
    ) -> List[SearchHistory]:
        """
        Get recent searches ordered by last_searched_at.

        Supports both old and new API:
        - Old: get_recent_searches(user_id=1, limit=10)
        - New: get_recent_searches(context=context, limit=10)

        Excludes category searches as they are not actual searches but navigation.

        Args:
            user_id: User ID (old API)
            guest_session_id: Guest session ID (old API)
            context: Search user context (new API)
            limit: Maximum number of searches to return

        Returns:
            List of recent SearchHistory records (excluding categories)
        """
        # Build context from old API if needed
        if context is None:
            if user_id:
                context = SearchUserContext.from_user(user_id)
            elif guest_session_id:
                context = SearchUserContext.from_guest(guest_session_id)
            else:
                raise ValueError("Must provide either user_id, guest_session_id, or context")
        # Use the unified method that works with context
        searches = self.repository.get_recent_searches_unified(
            context, limit=limit * 2, order_by="last_searched_at"  # Get extra to ensure we have enough after filtering
        )

        # Filter out category searches
        filtered_searches = [s for s in searches if s.search_type != "category"]

        # Return only the requested limit
        result = filtered_searches[:limit]

        logger.debug(
            f"Retrieved {len(result)} recent searches for {context.identifier} "
            f"(filtered {len(searches) - len(filtered_searches)} categories)"
        )
        return result

    @BaseService.measure_operation("delete_search")
    def delete_search(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, search_id: int = None
    ) -> bool:
        """
        Soft delete a search for any user type.

        Args:
            user_id: ID of authenticated user (if applicable)
            guest_session_id: Guest session UUID (if applicable)
            search_id: ID of the search history entry

        Returns:
            True if deleted, False if not found or unauthorized
        """
        if not search_id:
            return False

        if user_id:
            deleted = self.repository.soft_delete_by_id(search_id=search_id, user_id=user_id)
            identifier = f"user_{user_id}"
        elif guest_session_id:
            deleted = self.repository.soft_delete_guest_search(search_id=search_id, guest_session_id=guest_session_id)
            identifier = f"guest_{guest_session_id}"
        else:
            return False

        if deleted:
            with self.transaction():
                pass  # Transaction commits automatically
            logger.info(f"Soft deleted search history {search_id} for {identifier}")
        else:
            logger.warning(f"Search history {search_id} not found or already deleted for {identifier}")

        return deleted

    def _enforce_search_limit(self, context: SearchUserContext) -> None:
        """
        Enforce the maximum number of searches per user/guest.

        Deletes oldest searches if limit is exceeded.
        If limit is 0, no limit is enforced.

        Args:
            context: User context (authenticated or guest)
        """
        # Skip if limit is disabled
        if settings.search_history_max_per_user == 0:
            return

        # Count current searches (excluding soft-deleted)
        search_count = self.repository.count_searches(
            user_id=context.user_id, guest_session_id=context.guest_session_id
        )

        if search_count > settings.search_history_max_per_user:
            # Get IDs of searches to keep (most recent, excluding soft-deleted)
            keep_searches = self.repository.get_searches_to_delete(
                user_id=context.user_id,
                guest_session_id=context.guest_session_id,
                keep_count=settings.search_history_max_per_user,
            )

            # Soft delete searches not in the keep list
            deleted = self.repository.soft_delete_old_searches(
                user_id=context.user_id, guest_session_id=context.guest_session_id, keep_ids_subquery=keep_searches
            )

            with self.transaction():
                pass  # Transaction commits automatically

            if deleted > 0:
                logger.info(f"Deleted {deleted} old searches for {context.identifier} to maintain limit")

    # Guest-to-user conversion (remains as specific operation)
    @BaseService.measure_operation("convert_guest_searches_to_user")
    def convert_guest_searches_to_user(self, guest_session_id: str, user_id: int) -> int:
        """
        Convert guest searches to user searches when a guest logs in or signs up.

        This is called when a guest logs in or signs up. It:
        1. Transfers ALL guest searches (including deleted) to the user account
        2. Marks guest searches as converted to prevent double-counting
        3. Preserves original timestamps and deleted status

        Args:
            guest_session_id: Guest session UUID
            user_id: User ID to convert searches to

        Returns:
            Number of searches converted
        """
        try:
            # Get all non-converted guest searches (including deleted ones)
            guest_searches = self.repository.get_guest_searches_for_conversion(guest_session_id)
            converted_count = 0

            for search in guest_searches:
                # Check if user already has this exact search
                # We don't check timestamp to avoid duplicates of same query
                existing = self.repository.find_existing_search(user_id=user_id, query=search.search_query)

                if not existing:
                    # Create new search entry for user, preserving timestamp and deleted status
                    self.repository.create(
                        user_id=user_id,
                        search_query=search.search_query,
                        search_type=search.search_type,
                        results_count=search.results_count,
                        first_searched_at=search.first_searched_at,  # Preserve original timestamp
                        last_searched_at=search.last_searched_at,  # Preserve last search time
                        search_count=search.search_count,  # Preserve search count
                        deleted_at=search.deleted_at,  # Preserve deleted status
                    )
                    converted_count += 1

            # Mark all guest searches as converted (even if not copied to avoid re-processing)
            marked_count = self.repository.mark_searches_as_converted(
                guest_session_id=guest_session_id, user_id=user_id
            )

            with self.transaction():
                pass  # Transaction commits automatically

            logger.info(
                f"Converted {converted_count} guest searches to user {user_id}, " f"marked {marked_count} as converted"
            )

            return converted_count

        except Exception as e:
            logger.error(f"Failed to convert guest searches: {str(e)}")
            # Don't fail auth if conversion fails
            return 0
