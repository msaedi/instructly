# backend/app/services/week_operation_service.py
"""
Week Operation Service for InstaInstru Platform

Handles complex operations that work with entire weeks of availability data
using the single-table design where AvailabilitySlots contain instructor_id
and date directly.

Note: Some methods are async because they perform cache warming operations
that include rate limiting and retry logic with exponential backoff.
"""

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.constants import DAYS_OF_WEEK
from ..repositories.factory import RepositoryFactory
from ..utils.time_helpers import string_to_time
from .base import BaseService

if TYPE_CHECKING:
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.week_operation_repository import WeekOperationRepository
    from .availability_service import AvailabilityService
    from .cache_service import CacheService
    from .conflict_checker import ConflictChecker

logger = logging.getLogger(__name__)


class WeekOperationService(BaseService):
    """
    Service for week-based availability operations.

    Handles complex operations that work with entire weeks
    of availability data using the single-table design.
    """

    def __init__(
        self,
        db: Session,
        availability_service: Optional["AvailabilityService"] = None,
        conflict_checker: Optional["ConflictChecker"] = None,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["WeekOperationRepository"] = None,
        availability_repository: Optional["AvailabilityRepository"] = None,
    ):
        """Initialize week operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)

        # Initialize repositories
        self.repository = repository or RepositoryFactory.create_week_operation_repository(db)
        self.availability_repository = availability_repository or RepositoryFactory.create_availability_repository(db)

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

        Copies slots directly without dealing with InstructorAvailability entries.

        This method is async because it performs cache warming operations that
        include rate limiting and retry logic.

        Args:
            instructor_id: The instructor ID
            from_week_start: Monday of the source week
            to_week_start: Monday of the target week

        Returns:
            Updated target week availability with metadata
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
            deleted_count = self.availability_repository.delete_slots_by_dates(instructor_id, target_week_dates)
            self.logger.debug(f"Deleted {deleted_count} existing slots from target week")

            # Get source week slots
            source_slots = self.repository.get_week_slots(
                instructor_id, from_week_start, from_week_start + timedelta(days=6)
            )

            # Prepare new slots with updated dates
            new_slots = []
            for slot in source_slots:
                # Calculate the day offset
                day_offset = (slot.date - from_week_start).days
                new_date = to_week_start + timedelta(days=day_offset)

                new_slots.append(
                    {
                        "instructor_id": instructor_id,
                        "date": new_date,
                        "start_time": slot.start_time,
                        "end_time": slot.end_time,
                    }
                )

            # Bulk create new slots
            if new_slots:
                created_count = self.repository.bulk_create_slots(new_slots)
                self.logger.info(f"Created {created_count} slots in target week")
            else:
                created_count = 0

        # Ensure SQLAlchemy session is fresh
        self.db.expire_all()

        # Use CacheWarmingStrategy for consistent fresh data
        if self.cache_service:
            from .cache_strategies import CacheWarmingStrategy

            warmer = CacheWarmingStrategy(self.cache_service, self.db)
            # warm_with_verification is async - uses asyncio.sleep for rate limiting
            result = await warmer.warm_with_verification(
                instructor_id,
                to_week_start,
                expected_slot_count=None,
            )
        else:
            result = self.availability_service.get_week_availability(instructor_id, to_week_start)

        # Add metadata
        result["_metadata"] = {
            "operation": "week_copy",
            "slots_created": created_count,
            "message": f"Week copied successfully. {created_count} slots created.",
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

        Works directly with slots, no InstructorAvailability entries.

        This method is async because it performs cache warming operations that
        include rate limiting and retry logic.

        Args:
            instructor_id: The instructor ID
            from_week_start: Monday of source week with pattern
            start_date: Start of range to apply to
            end_date: End of range to apply to

        Returns:
            Operation result with counts
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

        with self.transaction():
            # Get all dates in range
            all_dates = []
            current_date = start_date
            while current_date <= end_date:
                all_dates.append(current_date)
                current_date += timedelta(days=1)

            # Delete ALL existing slots in the date range
            deleted_count = self.availability_repository.delete_slots_by_dates(instructor_id, all_dates)
            self.logger.debug(f"Deleted {deleted_count} existing slots from date range")

            # Prepare new slots based on pattern
            new_slots = []
            dates_with_slots = 0

            current_date = start_date
            while current_date <= end_date:
                day_name = DAYS_OF_WEEK[current_date.weekday()]

                if day_name in week_pattern and week_pattern[day_name]:
                    # Apply pattern for this day
                    dates_with_slots += 1

                    for pattern_slot in week_pattern[day_name]:
                        slot_start = string_to_time(pattern_slot["start_time"])
                        slot_end = string_to_time(pattern_slot["end_time"])

                        new_slots.append(
                            {
                                "instructor_id": instructor_id,
                                "date": current_date,
                                "start_time": slot_start,
                                "end_time": slot_end,
                            }
                        )

                current_date += timedelta(days=1)

            # Bulk create all new slots
            if new_slots:
                created_count = self.repository.bulk_create_slots(new_slots)
                self.logger.info(f"Created {created_count} slots across {dates_with_slots} days")
            else:
                created_count = 0
                self.logger.info("No slots to create - pattern may be empty")

        # Ensure SQLAlchemy session is fresh
        self.db.expire_all()

        message = f"Successfully applied schedule to {len(all_dates)} days"
        self.logger.info(f"Pattern application completed: {created_count} slots created")

        # Cache warming for affected weeks
        if self.cache_service and created_count > 0:
            from .cache_strategies import CacheWarmingStrategy

            warmer = CacheWarmingStrategy(self.cache_service, self.db)

            # Warm cache for ALL affected weeks
            affected_weeks = set()
            current = start_date
            while current <= end_date:
                week_start = current - timedelta(days=current.weekday())
                affected_weeks.add(week_start)
                current += timedelta(days=7)

            for week_start in affected_weeks:
                # warm_with_verification is async - uses asyncio.sleep for rate limiting
                await warmer.warm_with_verification(instructor_id, week_start, expected_slot_count=None)

            self.logger.info(f"Warmed cache for {len(affected_weeks)} affected weeks")

        return {
            "message": message,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "dates_processed": len(all_dates),
            "dates_with_slots": dates_with_slots,
            "slots_created": created_count,
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

    def _extract_week_pattern(
        self, week_availability: Dict[str, List[Dict]], week_start: date
    ) -> Dict[str, List[Dict]]:
        """Extract a reusable pattern from week availability."""
        pattern = {}

        for i in range(7):
            source_date = week_start + timedelta(days=i)
            source_date_str = source_date.isoformat()
            day_name = DAYS_OF_WEEK[i]

            if source_date_str in week_availability and week_availability[source_date_str]:
                pattern[day_name] = week_availability[source_date_str]

        self.logger.debug(f"Extracted pattern with availability for days: {list(pattern.keys())}")
        return pattern
