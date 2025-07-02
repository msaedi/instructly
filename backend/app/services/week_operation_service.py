# backend/app/services/week_operation_service.py
"""
Week Operation Service for InstaInstru Platform

FIXED: Implements proper separation between availability and booking layers.
Availability operations no longer check for booking conflicts.

Handles week-based availability operations including:
- Copying availability between weeks
- Applying patterns to date ranges
- Week calculations and pattern extraction
- Bulk week operations

Updated to use WeekOperationRepository for all data access.
"""

import logging
import time as time_module
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.constants import DAYS_OF_WEEK
from ..repositories.factory import RepositoryFactory
from ..utils.time_helpers import string_to_time
from .base import BaseService

if TYPE_CHECKING:
    from ..repositories.week_operation_repository import WeekOperationRepository
    from .availability_service import AvailabilityService
    from .cache_service import CacheService
    from .conflict_checker import ConflictChecker

logger = logging.getLogger(__name__)


class WeekOperationService(BaseService):
    """
    Service for week-based availability operations.

    Handles complex operations that work with entire weeks
    of availability data.
    """

    def __init__(
        self,
        db: Session,
        availability_service: Optional["AvailabilityService"] = None,
        conflict_checker: Optional["ConflictChecker"] = None,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["WeekOperationRepository"] = None,
    ):
        """Initialize week operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)

        # Initialize repository
        self.repository = repository or RepositoryFactory.create_week_operation_repository(db)

        # Lazy import to avoid circular dependencies
        if availability_service is None:
            from .availability_service import AvailabilityService

            availability_service = AvailabilityService(db)

        if conflict_checker is None:
            from .conflict_checker import ConflictChecker

            conflict_checker = ConflictChecker(db)

        self.availability_service = availability_service
        self.conflict_checker = conflict_checker
        self.cache_service = cache_service

    async def copy_week_availability(
        self, instructor_id: int, from_week_start: date, to_week_start: date
    ) -> Dict[str, Any]:
        """
        Copy availability from one week to another.

        Note: This creates the same availability pattern. Existing bookings
        in the target week remain unaffected (they are an independent layer).

        Args:
            instructor_id: The instructor ID
            from_week_start: Monday of the source week
            to_week_start: Monday of the target week

        Returns:
            Updated target week availability with metadata

        Raises:
            ValidationException: If dates are not Mondays
        """
        self.log_operation(
            "copy_week_availability",
            instructor_id=instructor_id,
            from_week=from_week_start,
            to_week=to_week_start,
        )

        # Validate dates are Mondays
        if from_week_start.weekday() != 0:
            self.logger.warning(f"Source week start {from_week_start} is not a Monday")
        if to_week_start.weekday() != 0:
            self.logger.warning(f"Target week start {to_week_start} is not a Monday")

        with self.transaction():
            # Get target week dates
            target_week_dates = self.calculate_week_dates(to_week_start)

            # Clear ALL existing slots from target week
            self._clear_all_slots(instructor_id, target_week_dates)

            # Get source week availability
            source_week = self.availability_service.get_week_availability(instructor_id, from_week_start)

            # Copy availability day by day
            copy_result = await self._copy_week_slots(
                instructor_id=instructor_id,
                source_week=source_week,
                from_week_start=from_week_start,
                to_week_start=to_week_start,
            )

        # Ensure SQLAlchemy session is fresh
        self.db.expire_all()

        # Use CacheWarmingStrategy for consistent fresh data
        if self.cache_service:
            from .cache_strategies import CacheWarmingStrategy

            warmer = CacheWarmingStrategy(self.cache_service, self.db)

            # Warm cache with fresh data
            result = await warmer.warm_with_verification(
                instructor_id,
                to_week_start,
                expected_slot_count=None,
            )
        else:
            # No cache, get directly
            result = self.availability_service.get_week_availability(instructor_id, to_week_start)

        # Add metadata if useful
        if copy_result.get("dates_created", 0) > 0 or copy_result.get("slots_created", 0) > 0:
            result["_metadata"] = {
                "operation": "week_copy",
                "dates_created": copy_result["dates_created"],
                "slots_created": copy_result["slots_created"],
                "message": f"Week copied successfully. {copy_result['slots_created']} slots created.",
            }

        return result

    async def apply_pattern_to_date_range(
        self,
        instructor_id: int,
        from_week_start: date,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Apply a week's pattern to a date range.

        This creates availability slots based on the pattern. Existing bookings
        are unaffected as they are an independent layer.

        Key optimizations:
        1. Bulk fetch all existing data upfront
        2. Batch all inserts/updates
        3. Single transaction for entire operation
        4. Minimize database round trips
        """
        self.log_operation(
            "apply_pattern_to_date_range",
            instructor_id=instructor_id,
            from_week=from_week_start,
            date_range=f"{start_date} to {end_date}",
        )

        # Get source week availability
        source_week = self.availability_service.get_week_availability(instructor_id, from_week_start)

        # Create pattern from source week
        week_pattern = self._extract_week_pattern(source_week, from_week_start)

        # OPTIMIZATION: Bulk fetch all data upfront using repository
        existing_availability = self.repository.get_availability_in_range(instructor_id, start_date, end_date)

        # Create lookup dict for O(1) access
        existing_by_date = {entry.date: entry for entry in existing_availability}

        with self.transaction():
            # Prepare bulk operations
            new_availability_entries = []
            new_slots = []
            slots_to_delete = []
            availability_to_update = []

            # Process each date
            current_date = start_date
            dates_created = 0
            dates_modified = 0
            slots_created = 0

            while current_date <= end_date:
                day_name = DAYS_OF_WEEK[current_date.weekday()]

                # Get existing availability for this date
                existing = existing_by_date.get(current_date)

                if day_name in week_pattern and week_pattern[day_name]:
                    # Process pattern for this day
                    if existing:
                        # Mark for update
                        existing.is_cleared = False
                        availability_to_update.append({"id": existing.id, "is_cleared": False})
                        availability_id = existing.id
                        dates_modified += 1

                        # Delete ALL existing slots (no booking checks!)
                        slots_to_delete.extend([s.id for s in existing.time_slots])
                    else:
                        # Create new availability entry
                        new_entry = {
                            "instructor_id": instructor_id,
                            "date": current_date,
                            "is_cleared": False,
                        }
                        new_availability_entries.append(new_entry)
                        dates_created += 1

                    # Prepare new slots - ALL of them, no conflict checking!
                    for pattern_slot in week_pattern[day_name]:
                        slot_start = string_to_time(pattern_slot["start_time"])
                        slot_end = string_to_time(pattern_slot["end_time"])

                        new_slots.append(
                            {
                                "date": current_date,
                                "start_time": slot_start,
                                "end_time": slot_end,
                                "existing_availability": existing,
                            }
                        )
                        slots_created += 1
                else:
                    # No pattern for this day - clear it
                    if existing and not existing.is_cleared:
                        # Clear the day
                        availability_to_update.append({"id": existing.id, "is_cleared": True})
                        slots_to_delete.extend([s.id for s in existing.time_slots])
                        dates_modified += 1

                current_date += timedelta(days=1)

            # OPTIMIZATION: Bulk operations using repository
            # Bulk insert new availability entries
            created_entries = []
            if new_availability_entries:
                created_entries = self.repository.bulk_create_availability(new_availability_entries)

            # Bulk delete slots
            if slots_to_delete:
                self.repository.bulk_delete_slots(slots_to_delete)

            # Bulk insert new slots
            if new_slots:
                # Create slot mappings with proper availability_id
                slot_mappings = []
                for slot_data in new_slots:
                    availability_id = None
                    if slot_data["existing_availability"]:
                        availability_id = slot_data["existing_availability"].id
                    else:
                        # Find the newly created entry for this date
                        for new_entry in created_entries:
                            if new_entry.date == slot_data["date"]:
                                availability_id = new_entry.id
                                break
                        if availability_id is None:
                            # This shouldn't happen, but handle it gracefully
                            self.logger.error(
                                f"No availability found for slot on {slot_data['date']}. "
                                "This indicates a logic error in the service."
                            )
                            continue

                    slot_mappings.append(
                        {
                            "availability_id": availability_id,
                            "start_time": slot_data["start_time"],
                            "end_time": slot_data["end_time"],
                        }
                    )

                self.repository.bulk_create_slots(slot_mappings)

            # Update modified availability entries
            if availability_to_update:
                self.repository.bulk_update_availability(availability_to_update)

        # Ensure SQLAlchemy session is fresh
        self.db.expire_all()

        message = f"Successfully applied schedule to {dates_created + dates_modified} days"
        self.logger.info(
            f"Pattern application completed: {dates_created} created, "
            f"{dates_modified} modified, {slots_created} slots"
        )

        # Cache warming for affected weeks
        if self.cache_service and (dates_created > 0 or dates_modified > 0):
            from .cache_strategies import CacheWarmingStrategy

            warmer = CacheWarmingStrategy(self.cache_service, self.db)

            # We need to warm cache for ALL affected weeks
            affected_weeks = set()
            current = start_date
            while current <= end_date:
                week_start = current - timedelta(days=current.weekday())
                affected_weeks.add(week_start)
                current += timedelta(days=7)

            # Warm all affected weeks
            for week_start in affected_weeks:
                await warmer.warm_with_verification(instructor_id, week_start, expected_slot_count=None)

            self.logger.info(f"Warmed cache for {len(affected_weeks)} affected weeks")

        return {
            "message": message,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "dates_created": dates_created,
            "dates_modified": dates_modified,
            "slots_created": slots_created,
        }

    def calculate_week_dates(self, monday: date) -> List[date]:
        """
        Calculate all dates for a week starting from Monday.

        Args:
            monday: The Monday of the week

        Returns:
            List of 7 dates (Monday through Sunday)
        """
        return [monday + timedelta(days=i) for i in range(7)]

    def get_week_pattern(self, instructor_id: int, week_start: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract the availability pattern for a week.

        Args:
            instructor_id: The instructor ID
            week_start: Monday of the week

        Returns:
            Pattern indexed by day name (Monday, Tuesday, etc.)
        """
        week_availability = self.availability_service.get_week_availability(instructor_id, week_start)
        return self._extract_week_pattern(week_availability, week_start)

    # Private helper methods

    def _clear_all_slots(self, instructor_id: int, week_dates: List[date]) -> None:
        """Clear ALL slots from the given dates."""
        # Delete all slots for the week
        deleted_slots = self.repository.delete_non_booked_slots(
            instructor_id, week_dates, set()  # Empty set means delete all
        )

        # Delete availability entries with no remaining slots
        deleted_availabilities = self.repository.delete_empty_availability_entries(instructor_id, week_dates)

        self.logger.debug(f"Deleted {deleted_slots} slots and " f"{deleted_availabilities} empty availability entries")

    async def _copy_week_slots(
        self,
        instructor_id: int,
        source_week: Dict[str, List[Dict]],
        from_week_start: date,
        to_week_start: date,
    ) -> Dict[str, Any]:
        """Copy slots from source to target week."""
        dates_created = 0
        slots_created = 0

        for i in range(7):
            source_date = from_week_start + timedelta(days=i)
            target_date = to_week_start + timedelta(days=i)

            # Get ALL slots from source date
            source_slots = self.repository.get_slots_with_booking_status(instructor_id, source_date)

            if source_slots:
                # Copy ALL slots
                result = await self._copy_day_slots(
                    instructor_id=instructor_id,
                    source_slots=source_slots,
                    target_date=target_date,
                )

                dates_created += result["dates_created"]
                slots_created += result["slots_created"]
            else:
                # Source day has no slots - create cleared entry
                availability_entry = self.repository.get_or_create_availability(
                    instructor_id, target_date, is_cleared=True
                )
                if availability_entry:
                    dates_created += 1

        self.logger.info(f"Week copy complete: {dates_created} dates, {slots_created} slots created")

        return {
            "dates_created": dates_created,
            "slots_created": slots_created,
        }

    async def _copy_day_slots(
        self,
        instructor_id: int,
        source_slots: List[Dict],
        target_date: date,
    ) -> Dict[str, Any]:
        """
        Copy slots for a single day.

        This method copies ALL slots from source to target without
        checking for booking conflicts. Bookings are an independent layer.
        """
        dates_created = 0
        slots_created = 0

        # Get or create availability entry using repository
        existing_availability = self.repository.get_or_create_availability(instructor_id, target_date, is_cleared=False)

        if existing_availability:
            availability_entry = existing_availability
            if hasattr(availability_entry, "id"):
                availability_id = availability_entry.id
            else:
                # New entry, need to flush to get ID
                self.db.flush()
                availability_id = availability_entry.id
                dates_created = 1
        else:
            # Should not happen with get_or_create
            raise Exception("Failed to get or create availability")

        # Collect slots to create in bulk
        slots_to_create = []

        # Copy ALL slots - no conflict checking!
        for slot in source_slots:
            slot_start = slot.get("start_time")
            slot_end = slot.get("end_time")

            # Convert to time objects if needed
            if isinstance(slot_start, str):
                slot_start = string_to_time(slot_start)
            if isinstance(slot_end, str):
                slot_end = string_to_time(slot_end)

            # Only check if slot already exists to avoid duplicates
            if not self.repository.slot_exists(availability_id, slot_start, slot_end):
                slots_to_create.append(
                    {
                        "availability_id": availability_id,
                        "start_time": slot_start,
                        "end_time": slot_end,
                    }
                )
                slots_created += 1

        # Bulk create slots if any
        if slots_to_create:
            self.repository.bulk_create_slots(slots_to_create)

        return {
            "dates_created": dates_created,
            "slots_created": slots_created,
            "slots_skipped": 0,  # Always 0 - we don't skip slots anymore
        }

    def _extract_week_pattern(
        self, week_availability: Dict[str, List[Dict]], week_start: date
    ) -> Dict[str, List[Dict]]:
        """Extract a reusable pattern from week availability."""
        pattern = {}

        for i in range(7):
            source_date = week_start + timedelta(days=i)
            source_date_str = source_date.isoformat()
            day_name = DAYS_OF_WEEK[i]

            if source_date_str in week_availability:
                pattern[day_name] = week_availability[source_date_str]

        self.logger.debug(f"Extracted pattern with availability for days: {list(pattern.keys())}")

        return pattern

    async def _apply_pattern_to_date(
        self,
        instructor_id: int,
        target_date: date,
        pattern_slots: List[Dict],
    ) -> Dict[str, Any]:
        """
        Apply pattern to a single date.

        This method applies ALL pattern slots without checking for
        booking conflicts. Existing slots are replaced with the pattern.
        """
        dates_created = 0
        dates_modified = 0
        slots_created = 0

        # Get or create availability using repository
        availability_entry = self.repository.get_or_create_availability(instructor_id, target_date, is_cleared=False)

        # Check if it's a new entry
        if availability_entry.date == target_date and not hasattr(availability_entry, "_sa_instance_state"):
            dates_created = 1
        else:
            dates_modified = 1
            # Delete ALL existing slots
            if hasattr(availability_entry, "time_slots") and availability_entry.time_slots:
                slot_ids = [slot.id for slot in availability_entry.time_slots]
                if slot_ids:
                    self.repository.bulk_delete_slots(slot_ids)

        # Collect slots to create
        slots_to_create = []

        # Add ALL pattern slots - no conflict checking!
        for pattern_slot in pattern_slots:
            slot_start = string_to_time(pattern_slot["start_time"])
            slot_end = string_to_time(pattern_slot["end_time"])

            # Only check if slot exists to avoid duplicates
            if not self.repository.slot_exists(availability_entry.id, slot_start, slot_end):
                slots_to_create.append(
                    {
                        "availability_id": availability_entry.id,
                        "start_time": slot_start,
                        "end_time": slot_end,
                    }
                )
                slots_created += 1

        # Bulk create slots
        if slots_to_create:
            self.repository.bulk_create_slots(slots_to_create)

        return {
            "dates_created": dates_created,
            "dates_modified": dates_modified,
            "slots_created": slots_created,
            "slots_skipped": 0,  # Always 0 - we don't skip anymore
            "skipped": False,  # Never skip entire date
        }

    def _clear_date_availability(self, instructor_id: int, target_date: date) -> Dict[str, Any]:
        """Clear availability for a date using repository."""
        dates_created = 0
        dates_modified = 0

        # Get or create availability
        availability = self.repository.get_or_create_availability(instructor_id, target_date, is_cleared=True)

        # Check if we modified existing
        if hasattr(availability, "_sa_instance_state"):
            if not availability.is_cleared:
                # Delete all slots
                if hasattr(availability, "time_slots"):
                    slot_ids = [s.id for s in availability.time_slots]
                    if slot_ids:
                        self.repository.bulk_delete_slots(slot_ids)

                # Update to cleared
                self.repository.bulk_update_availability([{"id": availability.id, "is_cleared": True}])
                dates_modified = 1
        else:
            dates_created = 1

        return {"dates_created": dates_created, "dates_modified": dates_modified}

    # Keep these methods unchanged as requested
    def _bulk_create_slots(self, slots_data: List[Dict[str, Any]]) -> int:
        """
        Efficiently bulk create slots using repository.

        Args:
            slots_data: List of slot dictionaries with availability_id, start_time, end_time

        Returns:
            Number of slots created
        """
        return self.repository.bulk_create_slots(slots_data)

    def get_cached_week_pattern(
        self, instructor_id: int, week_start: date, cache_ttl: int = 3600
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get week pattern with caching support.

        Args:
            instructor_id: The instructor ID
            week_start: Monday of the week
            cache_ttl: Cache time-to-live in seconds

        Returns:
            Cached or fresh week pattern
        """
        # Start performance measurement
        start_time = time_module.time()

        cache_key = f"week_pattern:{instructor_id}:{week_start.isoformat()}"

        # Try cache first
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                self.logger.debug(f"Week pattern cache hit for {week_start}")
                # Record metric
                elapsed = time_module.time() - start_time
                self._record_metric("pattern_extraction", elapsed, success=True)
                return cached

        # Get fresh data
        week_availability = self.availability_service.get_week_availability(instructor_id, week_start)
        pattern = self._extract_week_pattern(week_availability, week_start)

        # Cache the result
        if self.cache:
            self.cache.set(cache_key, pattern, ttl=cache_ttl)

        # Record metric
        elapsed = time_module.time() - start_time
        self._record_metric("pattern_extraction", elapsed, success=True)

        return pattern

    def add_performance_logging(self) -> None:
        """Add detailed performance logging to track slow operations."""
        # This is automatically handled by @measure_performance decorator
        # but we can add custom metrics here
        metrics = self.get_metrics()

        for operation, data in metrics.items():
            if data["avg_time"] > 1.0:  # Operations taking > 1 second
                self.logger.warning(
                    f"Slow operation detected: {operation} "
                    f"avg_time={data['avg_time']:.2f}s "
                    f"count={data['count']}"
                )

    async def apply_pattern_with_progress(
        self,
        instructor_id: int,
        from_week_start: date,
        start_date: date,
        end_date: date,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Apply pattern with progress callback for UI updates.

        Args:
            instructor_id: The instructor ID
            from_week_start: Source week Monday
            start_date: Start of range
            end_date: End of range
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Operation result
        """
        total_days = (end_date - start_date).days + 1

        # Wrapper to track progress
        original_method = self._apply_pattern_to_date
        current_day = [0]  # Use list to make it mutable in closure

        async def wrapped_apply(*args, **kwargs):
            result = await original_method(*args, **kwargs)
            current_day[0] += 1
            if progress_callback:
                progress_callback(current_day[0], total_days)
            return result

        # Temporarily replace method
        self._apply_pattern_to_date = wrapped_apply

        try:
            # Call the main method
            result = await self.apply_pattern_to_date_range(instructor_id, from_week_start, start_date, end_date)
            return result
        finally:
            # Restore original method
            self._apply_pattern_to_date = original_method
