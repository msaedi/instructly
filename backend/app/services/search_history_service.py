# backend/app/services/search_history_service.py
"""
Search History Service for tracking and retrieving user searches.

Unified implementation that handles both authenticated and guest users
without code duplication.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.search_history import SearchHistory
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

    @BaseService.measure_operation("record_search")
    async def record_search(
        self,
        user_id: Optional[int] = None,
        guest_session_id: Optional[str] = None,
        query: str = None,
        search_type: str = "natural_language",
        results_count: Optional[int] = None,
    ) -> SearchHistory:
        """
        Record a search for any user type (authenticated or guest).

        Args:
            user_id: ID of authenticated user (if applicable)
            guest_session_id: Guest session UUID (if applicable)
            query: The search query string
            search_type: Type of search ('natural_language', 'category', 'filter')
            results_count: Number of results returned (optional)

        Returns:
            The created or updated SearchHistory record
        """
        # Create context
        if user_id:
            context = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            context = SearchUserContext.from_guest(guest_session_id)
        else:
            raise ValueError("Must provide either user_id or guest_session_id")

        try:
            # Check if this exact query already exists (excluding soft-deleted)
            existing = self.repository.find_existing_search(
                user_id=user_id, guest_session_id=guest_session_id, query=query
            )

            if existing:
                # Update timestamp and results count
                existing.created_at = datetime.utcnow()
                existing.results_count = results_count
                self.db.commit()
                self.db.refresh(existing)

                logger.info(f"Updated existing search history for {context.identifier}: {query}")
                return existing

            # Create new search history entry
            search_history = self.repository.create(
                user_id=user_id,
                guest_session_id=guest_session_id,
                search_query=query,
                search_type=search_type,
                results_count=results_count,
            )
            self.db.commit()
            self.db.refresh(search_history)

            logger.info(f"Created new search history for {context.identifier}: {query}")

            # Maintain limit per user/guest
            await self._enforce_search_limit(context)

            return search_history

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error recording search: {str(e)}")
            raise

    @BaseService.measure_operation("get_recent_searches")
    def get_recent_searches(
        self, user_id: Optional[int] = None, guest_session_id: Optional[str] = None, limit: int = 3
    ) -> List[SearchHistory]:
        """
        Get recent searches for any user type.

        Excludes category searches as they are not actual searches but navigation.

        Args:
            user_id: ID of authenticated user (if applicable)
            guest_session_id: Guest session UUID (if applicable)
            limit: Maximum number of searches to return

        Returns:
            List of recent SearchHistory records (excluding categories)
        """
        # Get more searches than limit to account for filtered categories
        searches = self.repository.get_recent_searches(
            user_id=user_id,
            guest_session_id=guest_session_id,
            limit=limit * 2,  # Get extra to ensure we have enough after filtering
        )

        # Filter out category searches
        filtered_searches = [s for s in searches if s.search_type != "category"]

        # Return only the requested limit
        result = filtered_searches[:limit]

        # Create context for logging
        if user_id:
            identifier = f"user_{user_id}"
        elif guest_session_id:
            identifier = f"guest_{guest_session_id}"
        else:
            identifier = "unknown"

        logger.debug(
            f"Retrieved {len(result)} recent searches for {identifier} "
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
            self.db.commit()
            logger.info(f"Soft deleted search history {search_id} for {identifier}")
        else:
            logger.warning(f"Search history {search_id} not found or already deleted for {identifier}")

        return deleted

    async def _enforce_search_limit(self, context: SearchUserContext) -> None:
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

            self.db.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} old searches for {context.identifier} to maintain limit")

    # Guest-to-user conversion (remains as specific operation)
    @BaseService.measure_operation("convert_guest_searches_to_user")
    async def convert_guest_searches_to_user(self, guest_session_id: str, user_id: int) -> int:
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
                        created_at=search.created_at,  # Preserve original timestamp
                        deleted_at=search.deleted_at,  # Preserve deleted status
                    )
                    converted_count += 1

            # Mark all guest searches as converted (even if not copied to avoid re-processing)
            marked_count = self.repository.mark_searches_as_converted(
                guest_session_id=guest_session_id, user_id=user_id
            )

            self.db.commit()

            logger.info(
                f"Converted {converted_count} guest searches to user {user_id}, " f"marked {marked_count} as converted"
            )

            return converted_count

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to convert guest searches: {str(e)}")
            # Don't fail auth if conversion fails
            return 0
