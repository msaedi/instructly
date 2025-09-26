# backend/app/services/search_history_service.py
"""
Search History Service for tracking and retrieving user searches.

Unified implementation that handles both authenticated and guest users
without code duplication.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import math
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.search_history import SearchHistory
from ..models.search_interaction import SearchInteraction
from ..repositories.search_event_repository import SearchEventRepository
from ..repositories.search_history_repository import SearchHistoryRepository
from ..repositories.search_interaction_repository import SearchInteractionRepository
from ..schemas.search_context import SearchUserContext
from .base import BaseService
from .device_tracking_service import DeviceTrackingService
from .geolocation_service import GeolocationService

logger = logging.getLogger(__name__)


class SearchHistoryService(BaseService):
    """
    Service for managing search history.

    Unified implementation that works for both authenticated and guest users.
    """

    def __init__(
        self,
        db: Session,
        geolocation_service: Optional[GeolocationService] = None,
        device_tracking_service: Optional[DeviceTrackingService] = None,
    ):
        """Initialize the search history service with analytics capabilities."""
        super().__init__(db)
        self.repository = SearchHistoryRepository(db)
        self.event_repository = SearchEventRepository(db)
        self.interaction_repository = SearchInteractionRepository(db)
        self.geolocation_service = geolocation_service or GeolocationService(db)
        self.device_tracking_service = device_tracking_service or DeviceTrackingService(db)

    @BaseService.measure_operation("record_search")
    async def record_search(
        self,
        user_id: str | None = None,
        guest_session_id: str | None = None,
        query: str | None = None,
        search_type: str = "natural_language",
        results_count: int | None = None,
        context: SearchUserContext | None = None,
        search_data: dict[str, Any] | None = None,
        request_ip: str | None = None,
        user_agent: str | None = None,
        device_context: dict[str, Any] | None = None,
        observability_candidates: list[dict[str, Any]] | None = None,
    ) -> SearchHistory:
        """
        Record a search - supports both old and new API.

        Old API: record_search(user_id=1, query="test")
        New API: record_search(context=context, search_data={...})
        """
        # If context is provided, use new API
        if context is not None and search_data is not None:
            return await self._record_search_impl(
                context,
                search_data,
                request_ip,
                user_agent,
                device_context,
                observability_candidates=observability_candidates,
            )

        # Otherwise use old API parameters
        if user_id:
            ctx = SearchUserContext.from_user(user_id)
        elif guest_session_id:
            ctx = SearchUserContext.from_guest(guest_session_id)
        else:
            raise ValueError("Must provide either user_id or guest_session_id")

        data = {"search_query": query, "search_type": search_type, "results_count": results_count}

        return await self._record_search_impl(
            ctx,
            data,
            request_ip,
            user_agent,
            device_context,
            observability_candidates=observability_candidates,
        )

    def normalize_search_query(self, query: str) -> str:  # no-metrics
        """Normalize a search query for deduplication."""
        if not query:
            return ""
        return query.strip().lower()

    async def _record_search_impl(
        self,
        context: SearchUserContext,
        search_data: dict[str, Any],
        request_ip: str | None = None,
        user_agent: str | None = None,
        device_context: dict[str, Any] | None = None,
        observability_candidates: list[dict[str, Any]] | None = None,
    ) -> SearchHistory:
        """
        Internal implementation of search recording using PostgreSQL UPSERT.
        This is atomic and handles race conditions perfectly.
        """
        try:
            query = search_data["search_query"]
            normalized_query = self.normalize_search_query(query)
            _now = datetime.now(timezone.utc)

            # Use repository for atomic UPSERT operation
            result = cast(
                SearchHistory,
                self.repository.upsert_search(
                    user_id=context.user_id,
                    guest_session_id=context.guest_session_id,
                    search_query=query,
                    normalized_query=normalized_query,
                    search_type=search_data.get("search_type", "natural_language"),
                    results_count=search_data.get("results_count"),
                ),
            )

            # Log what happened
            if result.search_count == 1:
                logger.info(f"Created new search history for {context.identifier}: {query}")
            else:
                logger.info(
                    f"Updated search history for {context.identifier}: {query} (count: {result.search_count})"
                )

            # Maintain limit per user/guest
            self._enforce_search_limit(context)

            # Process analytics data
            ip_hash: str | None = None
            geo_data: dict[str, Any] | None = None
            browser_info: dict[str, Any] | None = None

            # Hash IP address for privacy
            if request_ip:
                ip_hash = hashlib.sha256(request_ip.encode()).hexdigest()

                # Get geolocation data
                try:
                    geo_data = await self.geolocation_service.get_location_from_ip(request_ip)
                except Exception as e:
                    logger.warning(f"Failed to get geolocation: {str(e)}")

            # Parse device/browser info
            if user_agent:
                device_info = self.device_tracking_service.parse_user_agent(user_agent)
                browser_info = self.device_tracking_service.format_for_analytics(device_info)

            # Merge with frontend device context
            if device_context and browser_info:
                browser_info.update(
                    {
                        "device": {
                            **browser_info.get("device", {}),
                            "type": device_context.get(
                                "device_type", browser_info.get("device", {}).get("type")
                            ),
                        },
                        "viewport": device_context.get("viewport_size"),
                        "screen": device_context.get("screen_resolution"),
                        "connection": {
                            "type": device_context.get("connection_type"),
                            "effective_type": device_context.get("connection_effective_type"),
                        },
                    }
                )

            # Check if returning user
            is_returning = False
            if context.user_id:
                # Check if user has searched before
                previous_search = self.event_repository.get_previous_search_event(
                    user_id=cast(Any, context.user_id),
                    before_time=datetime.now(timezone.utc),
                )
                is_returning = previous_search is not None
            elif context.guest_session_id:
                # Check guest session history (with 30 minute offset)
                previous_search = self.event_repository.get_previous_search_event(
                    guest_session_id=context.guest_session_id,
                    before_time=datetime.now(timezone.utc) - timedelta(minutes=30),
                )
                is_returning = previous_search is not None

            # Always create event for analytics (append-only) with enhanced data
            event_data = {
                "user_id": context.user_id,
                "guest_session_id": context.guest_session_id,
                "search_query": search_data["search_query"],
                "search_type": search_data.get("search_type", "natural_language"),
                "results_count": search_data.get("results_count", 0),
                "session_id": getattr(context, "session_id", None),
                "referrer": search_data.get("referrer"),
                "search_context": search_data.get("context"),
                # Enhanced analytics fields
                "ip_address": None,  # Never store raw IP
                "ip_address_hash": ip_hash,
                "geo_data": geo_data,
                "device_type": device_context.get("device_type") if device_context else None,
                "browser_info": browser_info,
                "connection_type": device_context.get("connection_type")
                if device_context
                else None,
                "is_returning_user": is_returning,
                "page_view_count": search_data.get("context", {}).get("page_view_count")
                if search_data.get("context")
                else None,
                "session_duration": search_data.get("context", {}).get("session_duration")
                if search_data.get("context")
                else None,
                "consent_given": True,  # Default for now
                "consent_type": "analytics",  # Default for now
            }
            event = self.event_repository.create_event(event_data)

            # Persist observability top-N candidates if provided
            try:
                if observability_candidates:
                    # Normalize candidate payload keys
                    normalized = []
                    for idx, c in enumerate(observability_candidates):
                        normalized.append(
                            {
                                "position": int(c.get("position", idx + 1)),
                                "service_catalog_id": c.get("service_catalog_id") or c.get("id"),
                                "score": c.get("score"),
                                "vector_score": c.get("vector_score"),
                                "lexical_score": c.get("lexical_score"),
                                "source": c.get("source", "hybrid"),
                            }
                        )
                    self.event_repository.bulk_insert_candidates(event.id, normalized)
            except Exception as e:
                logger.warning(
                    f"Failed to persist observability candidates for event {event.id}: {e}"
                )

            # Use service transaction pattern instead of direct DB operations
            with self.transaction():
                pass  # Transaction commits automatically

            # Refresh through repository
            # repo-pattern-ignore: Refresh after upsert to get updated values belongs in service layer
            self.db.refresh(result)

            # Store the event ID on the result for frontend use
            result.search_event_id = event.id

            return result

        except Exception as e:
            logger.error(f"Error recording search: {str(e)}")
            raise

    @BaseService.measure_operation("get_recent_searches")
    def get_recent_searches(
        self,
        user_id: str | None = None,
        guest_session_id: str | None = None,
        context: SearchUserContext | None = None,
        limit: int = 10,
    ) -> list[SearchHistory]:
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
            context,
            limit=limit * 2,
            order_by="last_searched_at",  # Get extra to ensure we have enough after filtering
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
        self,
        user_id: str | None = None,
        guest_session_id: str | None = None,
        search_id: str | None = None,
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
            deleted = self.repository.soft_delete_guest_search(
                search_id=cast(Any, search_id),  # repository accepts ULIDs; annotation is outdated
                guest_session_id=guest_session_id,
            )
            identifier = f"guest_{guest_session_id}"
        else:
            return False

        if deleted:
            with self.transaction():
                pass  # Transaction commits automatically
            logger.info(f"Soft deleted search history {search_id} for {identifier}")
        else:
            logger.warning(
                f"Search history {search_id} not found or already deleted for {identifier}"
            )

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

        # Use repository method for enforcing search limit
        deleted = self.repository.enforce_search_limit(
            user_id=context.user_id,
            guest_session_id=context.guest_session_id,
            max_searches=settings.search_history_max_per_user,
        )

        if deleted > 0:
            with self.transaction():
                pass  # Transaction commits automatically
            logger.info(
                f"Deleted {deleted} old searches for {context.identifier} to maintain limit"
            )

    # Guest-to-user conversion (remains as specific operation)
    @BaseService.measure_operation("convert_guest_searches_to_user")
    def convert_guest_searches_to_user(self, guest_session_id: str, user_id: str) -> int:
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
                existing = self.repository.find_existing_search(
                    user_id=user_id, query=search.search_query
                )

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
                f"Converted {converted_count} guest searches to user {user_id}, "
                f"marked {marked_count} as converted"
            )

            return converted_count

        except Exception as e:
            logger.error(f"Failed to convert guest searches: {str(e)}")
            # Don't fail auth if conversion fails
            return 0

    @BaseService.measure_operation("track_interaction")
    def track_interaction(
        self,
        search_event_id: int,
        interaction_type: str,
        instructor_id: Optional[str] = None,
        result_position: Optional[int] = None,
        time_to_interaction: Optional[float] = None,
        session_id: Optional[str] = None,
        interaction_duration: Optional[float] = None,
    ) -> SearchInteraction:
        """
        Track user interaction with search results.

        Args:
            search_event_id: ID of the search event
            interaction_type: Type of interaction (click, hover, bookmark, view_profile, contact, book)
            instructor_id: ID of the instructor interacted with
            result_position: Position in search results (1-based)
            time_to_interaction: Seconds from search to interaction
            session_id: Browser session ID for tracking
            interaction_duration: Duration of interaction in seconds (e.g., hover time)

        Returns:
            Created SearchInteraction instance
        """
        try:
            logger.info(f"Looking for search event {search_event_id}")

            # Validate search event exists
            search_event = self.event_repository.get_search_event_by_id(search_event_id)
            if not search_event:
                raise ValueError(f"Search event {search_event_id} not found")

            logger.info(f"Found search event {search_event_id}")

            normalized_time = time_to_interaction
            if normalized_time is not None:
                latest_recorded = self.interaction_repository.get_latest_time_to_interaction(
                    search_event_id
                )
                if latest_recorded is not None and normalized_time <= latest_recorded:
                    # Guarantee strictly increasing values even if the client clock jitters.
                    normalized_time = math.nextafter(latest_recorded, math.inf)

            # Create interaction record
            interaction_data = {
                "search_event_id": search_event_id,
                "session_id": session_id or getattr(search_event, "session_id", None),
                "interaction_type": interaction_type,
                "instructor_id": instructor_id,
                "result_position": result_position,
                "time_to_interaction": normalized_time,
                "interaction_duration": interaction_duration,
            }

            interaction = self.interaction_repository.create_interaction(interaction_data)

            with self.transaction():
                pass  # Transaction commits automatically

            logger.info(
                f"Tracked {interaction_type} interaction for search event {search_event_id}"
                + (f" on instructor {instructor_id}" if instructor_id else "")
            )

            return interaction

        except Exception as e:
            logger.error(f"Failed to track interaction: {str(e)}")
            raise
