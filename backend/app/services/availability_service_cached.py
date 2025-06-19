# backend/app/services/availability_service_cached.py
"""
Example of how to add caching to the availability service.

This shows the key methods to cache for maximum performance impact.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from .availability_service import AvailabilityService
from .cache_service import CacheService


class CachedAvailabilityService(AvailabilityService):
    """
    Enhanced availability service with caching.

    Inherits from AvailabilityService and adds caching to hot paths.
    """

    def __init__(self, db, cache_service: Optional[CacheService] = None):
        super().__init__(db)
        self.cache = cache_service or CacheService(db)

    def get_week_availability(
        self, instructor_id: int, start_date: date
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get availability for a specific week WITH CACHING.

        This is one of the most frequently called methods.
        """
        # Try cache first
        cached_data = self.cache.get_week_availability(instructor_id, start_date)
        if cached_data is not None:
            self.logger.debug(
                f"Cache hit for week availability: {instructor_id}, {start_date}"
            )
            return cached_data

        # Cache miss - get from database
        self.logger.debug(
            f"Cache miss for week availability: {instructor_id}, {start_date}"
        )
        result = super().get_week_availability(instructor_id, start_date)

        # Cache the result
        self.cache.cache_week_availability(instructor_id, start_date, result)

        return result

    async def save_week_availability(
        self, instructor_id: int, week_data
    ) -> Dict[str, Any]:
        """
        Save week availability and invalidate caches.
        """
        # Perform the save
        result = await super().save_week_availability(instructor_id, week_data)

        # Invalidate all caches for this instructor
        monday = self._determine_week_start(week_data)
        week_dates = self._calculate_week_dates(monday)
        self.cache.invalidate_instructor_availability(instructor_id, week_dates)

        # Pre-warm the cache with the new data
        updated_availability = result.copy()
        if "_metadata" in updated_availability:
            # Remove metadata before caching
            del updated_availability["_metadata"]
        self.cache.cache_week_availability(instructor_id, monday, updated_availability)

        return result

    def add_specific_date_availability(
        self, instructor_id: int, availability_data
    ) -> Dict[str, Any]:
        """
        Add specific date availability and invalidate caches.
        """
        result = super().add_specific_date_availability(
            instructor_id, availability_data
        )

        # Invalidate caches for this date
        self.cache.invalidate_instructor_availability(
            instructor_id, [availability_data.specific_date]
        )

        return result
