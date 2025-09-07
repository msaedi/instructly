# backend/app/services/cache_strategies.py
"""
Cache warming strategies to prevent stale data after updates.

This replaces the band-aid sleep with a proper solution that ensures
data consistency without arbitrary delays.
"""

import asyncio
from datetime import date, timedelta
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheWarmingStrategy:
    """
    Strategy for handling cache warming after invalidation.

    This ensures fresh data is available immediately after updates
    without relying on arbitrary sleep delays.
    """

    def __init__(self, cache_service, db, max_retries: int = 3):
        self.cache_service = cache_service
        self.db = db
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)

    async def warm_with_verification(
        self, instructor_id: str, week_start: date, expected_slot_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Warm cache with verification that data is fresh.

        Instead of arbitrary sleep, we verify the data matches expectations
        and retry if needed.
        """
        if not self.cache_service:
            return {}

        # Import here to avoid circular dependency
        from .availability_service import AvailabilityService

        retry_count = 0
        last_result = None

        while retry_count < self.max_retries:
            # Small exponential backoff: 50ms, 100ms, 200ms
            if retry_count > 0:
                delay = 0.05 * (2 ** (retry_count - 1))
                await asyncio.sleep(delay)
                self.logger.debug(f"Retry {retry_count} after {delay}s delay")

            # Get fresh data directly from DB (bypass cache)
            service = AvailabilityService(self.db, None)  # No cache
            fresh_data = service.get_week_availability(instructor_id, week_start)

            # If we have expected slot count, verify it
            if expected_slot_count is not None:
                actual_count = sum(len(slots) for slots in fresh_data.values())
                if actual_count == expected_slot_count:
                    # Data is fresh! Cache it and return
                    self.cache_service.cache_week_availability(
                        instructor_id, week_start, fresh_data
                    )
                    self.logger.info(f"Cache warmed successfully after {retry_count} retries")
                    return fresh_data
                else:
                    self.logger.debug(f"Expected {expected_slot_count} slots, got {actual_count}")
            else:
                # No verification needed, just cache and return
                self.cache_service.cache_week_availability(instructor_id, week_start, fresh_data)
                return fresh_data

            last_result = fresh_data
            retry_count += 1

        # Max retries reached, log warning but return what we have
        self.logger.warning(f"Cache warming verification failed after {self.max_retries} retries")

        # Cache what we have anyway
        if last_result:
            self.cache_service.cache_week_availability(instructor_id, week_start, last_result)

        return last_result or {}

    async def invalidate_and_warm(
        self,
        instructor_id: str,
        dates: list[date],
        expected_changes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Invalidate caches and immediately warm with fresh data.

        This is the main method to use after any update operation.
        """
        # First, invalidate all affected caches
        if self.cache_service:
            self.cache_service.invalidate_instructor_availability(instructor_id, dates)

        # Group dates by week for efficient warming
        weeks_to_warm = set()
        for d in dates:
            # Get Monday of the week
            week_start = d - timedelta(days=d.weekday())
            weeks_to_warm.add(week_start)

        # Warm each affected week
        for week_start in weeks_to_warm:
            expected_count = None
            if expected_changes and str(week_start) in expected_changes:
                expected_count = expected_changes[str(week_start)]

            await self.warm_with_verification(instructor_id, week_start, expected_count)


class ReadThroughCache:
    """
    Read-through cache pattern that ensures consistency.

    This pattern ensures that cache misses are handled properly
    and that stale data is never served.
    """

    def __init__(self, cache_service, db):
        self.cache_service = cache_service
        self.db = db
        self.logger = logging.getLogger(__name__)

    async def get_week_availability(
        self, instructor_id: str, week_start: date, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get week availability with read-through caching.

        If force_refresh is True, bypasses cache and updates it.
        """
        cache_key = f"week_availability:{instructor_id}:{week_start}"

        # Check cache first (unless forced refresh)
        if not force_refresh and self.cache_service:
            cached_data = self.cache_service.get(cache_key)
            if cached_data is not None:
                self.logger.debug(f"Cache hit for {cache_key}")
                return cached_data

        # Cache miss or forced refresh - get from DB
        from .availability_service import AvailabilityService

        service = AvailabilityService(self.db, None)  # Direct DB access
        fresh_data = service.get_week_availability(instructor_id, week_start)

        # Update cache with fresh data
        if self.cache_service:
            self.cache_service.cache_week_availability(instructor_id, week_start, fresh_data)
            self.logger.debug(f"Cache updated for {cache_key}")

        return fresh_data
