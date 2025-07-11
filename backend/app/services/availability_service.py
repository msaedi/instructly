# backend/app/services/availability_service.py
"""
Availability Service for InstaInstru Platform

This service handles all availability-related business logic.

"""

import logging
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypedDict

from sqlalchemy.orm import Session

from ..core.exceptions import ConflictException, NotFoundException, RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import BlackoutDateCreate, SpecificDateAvailabilityCreate, WeekSpecificScheduleCreate
from ..utils.time_helpers import time_to_string
from .base import BaseService

# TYPE_CHECKING import to avoid circular dependencies
if TYPE_CHECKING:
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.bulk_operation_repository import BulkOperationRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


# Type definitions for better type safety
class ScheduleSlotInput(TypedDict):
    """Input format for schedule slots from API."""

    date: str
    start_time: str
    end_time: str


class ProcessedSlot(TypedDict):
    """Internal format after processing schedule slots."""

    start_time: time
    end_time: time


class TimeSlotResponse(TypedDict):
    """Response format for time slots."""

    start_time: str
    end_time: str


class AvailabilityService(BaseService):
    """
    Service layer for availability operations.

    Works directly with AvailabilitySlot objects.
    """

    def __init__(
        self,
        db: Session,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["AvailabilityRepository"] = None,
        bulk_repository: Optional["BulkOperationRepository"] = None,
        conflict_repository: Optional["ConflictCheckerRepository"] = None,
    ):
        """Initialize availability service with optional cache and repositories."""
        super().__init__(db, cache=cache_service)
        self.cache_service = cache_service

        # Initialize repositories
        self.repository = repository or RepositoryFactory.create_availability_repository(db)
        self.bulk_repository = bulk_repository or RepositoryFactory.create_bulk_operation_repository(db)
        self.conflict_repository = conflict_repository or RepositoryFactory.create_conflict_checker_repository(db)

    @BaseService.measure_operation("get_availability_for_date")
    def get_availability_for_date(self, instructor_id: int, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Get availability for a specific date.

        Args:
            instructor_id: The instructor ID
            target_date: The specific date

        Returns:
            Availability data for the date or None if no slots
        """
        # Try cache first
        cache_key = f"availability:day:{instructor_id}:{target_date.isoformat()}"
        if self.cache_service:
            try:
                cached = self.cache_service.get(cache_key)
                if cached is not None:
                    return cached
            except Exception as cache_error:
                logger.warning(f"Cache error for date availability: {cache_error}")

        # Query slots directly
        try:
            slots = self.repository.get_slots_by_date(instructor_id, target_date)
        except RepositoryException as e:
            logger.error(f"Repository error getting availability: {e}")
            return None

        if not slots:
            return None

        result = {
            "date": target_date.isoformat(),
            "slots": [
                TimeSlotResponse(
                    start_time=time_to_string(slot.start_time),
                    end_time=time_to_string(slot.end_time),
                )
                for slot in slots
            ],
        }

        # Cache for 1 hour
        if self.cache_service:
            try:
                self.cache_service.set(cache_key, result, tier="warm")
            except Exception as cache_error:
                logger.warning(f"Failed to cache date availability: {cache_error}")

        return result

    @BaseService.measure_operation("get_availability_summary")
    def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]:
        """
        Get summary of availability (slot counts) for date range.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            Dict mapping date strings to slot counts
        """
        try:
            return self.repository.get_availability_summary(instructor_id, start_date, end_date)
        except RepositoryException as e:
            logger.error(f"Error getting availability summary: {e}")
            return {}

    @BaseService.measure_operation("get_week_availability")
    def get_week_availability(self, instructor_id: int, start_date: date) -> Dict[str, List[TimeSlotResponse]]:
        """
        Get availability for a specific week.

        Args:
            instructor_id: The instructor's user ID
            start_date: Monday of the week to retrieve

        Returns:
            Dict mapping date strings to time slot lists
        """
        self.log_operation("get_week_availability", instructor_id=instructor_id, start_date=start_date)

        # Try cache first
        if self.cache_service:
            try:
                cached_data = self.cache_service.get_week_availability(instructor_id, start_date)
                if cached_data is not None:
                    return cached_data
            except Exception as cache_error:
                logger.warning(f"Cache error for week availability: {cache_error}")

        # Calculate week dates (Monday to Sunday)
        week_dates = self._calculate_week_dates(start_date)
        end_date = week_dates[-1]

        # Get all slots for the week
        try:
            all_slots = self.repository.get_week_availability(instructor_id, start_date, end_date)
        except RepositoryException as e:
            logger.error(f"Error getting week availability: {e}")
            return {}

        # Group slots by date
        week_schedule: Dict[str, List[TimeSlotResponse]] = {}
        for slot in all_slots:
            date_str = slot.specific_date.isoformat()

            if date_str not in week_schedule:
                week_schedule[date_str] = []

            week_schedule[date_str].append(
                TimeSlotResponse(
                    start_time=time_to_string(slot.start_time),
                    end_time=time_to_string(slot.end_time),
                )
            )

        # Cache the result
        if self.cache_service:
            try:
                self.cache_service.cache_week_availability(instructor_id, start_date, week_schedule)
            except Exception as cache_error:
                logger.warning(f"Failed to cache week availability: {cache_error}")

        return week_schedule

    @BaseService.measure_operation("get_all_availability")
    def get_all_instructor_availability(
        self, instructor_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[AvailabilitySlot]:
        """
        Get all availability slots for an instructor with optional date filtering.

        Args:
            instructor_id: The instructor's ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of availability slots ordered by date and time
        """
        self.log_operation(
            "get_all_instructor_availability",
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            # Use repository method for date range queries
            # If no dates provided, use a large range
            if not start_date:
                start_date = date.today()
            if not end_date:
                end_date = date.today() + timedelta(days=365)  # One year ahead

            slots = self.repository.get_week_availability(instructor_id, start_date, end_date)
            return slots

        except RepositoryException as e:
            logger.error(f"Error retrieving all availability: {str(e)}")
            raise

    def _validate_and_parse_week_data(
        self, week_data: WeekSpecificScheduleCreate
    ) -> Tuple[date, List[date], Dict[date, List[ProcessedSlot]]]:
        """
        Validate week data and parse into organized structure.

        Args:
            week_data: The week schedule data to validate and parse

        Returns:
            Tuple of (monday, week_dates, schedule_by_date)
        """
        # Determine week dates
        monday = self._determine_week_start(week_data)
        week_dates = self._calculate_week_dates(monday)

        # Group schedule by date
        schedule_by_date = self._group_schedule_by_date(week_data.schedule)

        return monday, week_dates, schedule_by_date

    def _prepare_slots_for_creation(
        self, instructor_id: int, week_dates: List[date], schedule_by_date: Dict[date, List[ProcessedSlot]]
    ) -> List[Dict[str, Any]]:
        """
        Convert time slots to database-ready format.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            schedule_by_date: Schedule data grouped by date

        Returns:
            List of slot dictionaries ready for creation
        """
        slots_to_create = []

        for week_date in week_dates:
            # Skip past dates
            if week_date < date.today():
                continue

            if week_date in schedule_by_date:
                # Prepare slots for bulk creation
                for slot in schedule_by_date[week_date]:
                    # Check if slot already exists
                    if not self.repository.slot_exists(
                        instructor_id,
                        target_date=week_date,
                        start_time=slot["start_time"],
                        end_time=slot["end_time"],
                    ):
                        slots_to_create.append(
                            {
                                "instructor_id": instructor_id,
                                "specific_date": week_date,
                                "start_time": slot["start_time"],
                                "end_time": slot["end_time"],
                            }
                        )

        return slots_to_create

    async def _save_week_slots_transaction(
        self,
        instructor_id: int,
        week_data: WeekSpecificScheduleCreate,
        week_dates: List[date],
        slots_to_create: List[Dict[str, Any]],
    ) -> int:
        """
        Execute the database transaction to save slots.

        Args:
            instructor_id: The instructor ID
            week_data: Original week data for clear_existing flag
            week_dates: List of dates in the week
            slots_to_create: Prepared slots for creation

        Returns:
            Number of slots created

        Raises:
            RepositoryException: If database operation fails
        """
        try:
            with self.transaction():
                # If clearing existing, delete all slots for the week
                if week_data.clear_existing:
                    deleted_count = self.repository.delete_slots_by_dates(instructor_id, week_dates)
                    logger.info(f"Deleted {deleted_count} existing slots for instructor {instructor_id}")

                # Bulk create all slots at once
                if slots_to_create:
                    created_slots = self.bulk_repository.bulk_create_slots(slots_to_create)
                    logger.info(f"Created {len(created_slots)} new slots for instructor {instructor_id}")
                    return len(created_slots)

                return 0
        except RepositoryException as e:
            logger.error(f"Database error saving week availability for instructor {instructor_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving week availability for instructor {instructor_id}: {e}")
            raise

    async def _warm_cache_after_save(
        self, instructor_id: int, monday: date, week_dates: List[date], slot_count: int
    ) -> Dict[str, List[TimeSlotResponse]]:
        """
        Warm cache with new availability data.

        Args:
            instructor_id: The instructor ID
            monday: Monday of the week
            week_dates: List of dates affected
            slot_count: Number of slots created

        Returns:
            Updated availability data

        Note:
            Cache failures do not prevent the operation from succeeding
        """
        # Expire all cached objects to ensure fresh data for the final query
        # This is necessary after bulk operations to prevent stale data issues
        self.db.expire_all()

        # Handle cache warming
        if self.cache_service:
            try:
                from .cache_strategies import CacheWarmingStrategy

                warmer = CacheWarmingStrategy(self.cache_service, self.db)
                updated_availability = await warmer.warm_with_verification(
                    instructor_id, monday, expected_slot_count=slot_count
                )
                logger.debug(f"Cache warmed successfully for instructor {instructor_id}, week {monday}")
                return updated_availability
            except ImportError:
                logger.warning("Cache strategies not available, using direct fetch")
                self._invalidate_availability_caches(instructor_id, week_dates)
                return self.get_week_availability(instructor_id, monday)
            except Exception as cache_error:
                logger.warning(f"Cache warming failed for instructor {instructor_id}: {cache_error}")
                self._invalidate_availability_caches(instructor_id, week_dates)
                return self.get_week_availability(instructor_id, monday)
        else:
            logger.debug(f"No cache service available, fetching availability directly for instructor {instructor_id}")
            return self.get_week_availability(instructor_id, monday)

    @BaseService.measure_operation("save_week_availability")
    async def save_week_availability(self, instructor_id: int, week_data: WeekSpecificScheduleCreate) -> Dict[str, Any]:
        """
        Save availability for specific dates in a week - NOW UNDER 50 LINES!

        Args:
            instructor_id: The instructor's user ID
            week_data: The week schedule data

        Returns:
            Updated week availability
        """
        self.log_operation(
            "save_week_availability",
            instructor_id=instructor_id,
            clear_existing=week_data.clear_existing,
            schedule_count=len(week_data.schedule),
        )

        # 1. Validate and parse
        monday, week_dates, schedule_by_date = self._validate_and_parse_week_data(week_data)

        # 2. Prepare slots for creation
        slots_to_create = self._prepare_slots_for_creation(instructor_id, week_dates, schedule_by_date)

        # 3. Save to database
        slot_count = await self._save_week_slots_transaction(instructor_id, week_data, week_dates, slots_to_create)

        # 4. Warm cache and return response
        updated_availability = await self._warm_cache_after_save(instructor_id, monday, week_dates, slot_count)

        return updated_availability

    @BaseService.measure_operation("add_specific_date")
    def add_specific_date_availability(
        self, instructor_id: int, availability_data: SpecificDateAvailabilityCreate
    ) -> Dict[str, Any]:
        """
        Add availability for a specific date.

        Args:
            instructor_id: The instructor's user ID
            availability_data: The specific date and time slot

        Returns:
            Created availability slot information
        """
        with self.transaction():
            # Check for duplicate slot
            if self.repository.slot_exists(
                instructor_id,
                target_date=availability_data.specific_date,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time,
            ):
                raise ConflictException("This time slot already exists")

            # Create new slot
            slot = self.repository.create_slot(
                instructor_id=instructor_id,
                target_date=availability_data.specific_date,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time,
            )

            # Invalidate cache
            self._invalidate_availability_caches(instructor_id, [availability_data.specific_date])

            return slot  # Just return the model object

    @BaseService.measure_operation("get_blackout_dates")
    def get_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]:
        """
        Get instructor's future blackout dates.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of future blackout dates
        """
        try:
            return self.repository.get_future_blackout_dates(instructor_id)
        except RepositoryException as e:
            logger.error(f"Error getting blackout dates: {e}")
            return []

    @BaseService.measure_operation("add_blackout_date")
    def add_blackout_date(self, instructor_id: int, blackout_data: BlackoutDateCreate) -> BlackoutDate:
        """
        Add a blackout date for an instructor.

        Args:
            instructor_id: The instructor's user ID
            blackout_data: The blackout date information

        Returns:
            Created blackout date
        """
        # Check if already exists
        existing_blackouts = self.repository.get_future_blackout_dates(instructor_id)
        if any(b.date == blackout_data.date for b in existing_blackouts):
            raise ConflictException("Blackout date already exists")

        with self.transaction():
            try:
                blackout = self.repository.create_blackout_date(instructor_id, blackout_data.date, blackout_data.reason)
                return blackout
            except RepositoryException as e:
                if "already exists" in str(e):
                    raise ConflictException("Blackout date already exists")
                raise

    @BaseService.measure_operation("delete_blackout_date")
    def delete_blackout_date(self, instructor_id: int, blackout_id: int) -> bool:
        """
        Delete a blackout date.

        Args:
            instructor_id: The instructor's user ID
            blackout_id: The blackout date ID

        Returns:
            True if deleted successfully
        """
        with self.transaction():
            try:
                success = self.repository.delete_blackout_date(blackout_id, instructor_id)
                if not success:
                    raise NotFoundException("Blackout date not found")
                return True
            except RepositoryException as e:
                logger.error(f"Error deleting blackout date: {e}")
                raise

    # Private helper methods

    def _calculate_week_dates(self, monday: date) -> List[date]:
        """Calculate all dates for a week starting from Monday."""
        return [monday + timedelta(days=i) for i in range(7)]

    def _determine_week_start(self, week_data: WeekSpecificScheduleCreate) -> date:
        """Determine the Monday of the week from schedule data."""
        if week_data.week_start:
            return week_data.week_start
        elif week_data.schedule:
            # Get Monday from the first date in schedule
            first_date = min(slot.specific_date for slot in week_data.schedule)
            return first_date - timedelta(days=first_date.weekday())
        else:
            # Fallback to current week
            today = date.today()
            return today - timedelta(days=today.weekday())

    def _group_schedule_by_date(self, schedule: List[Dict[str, str]]) -> Dict[date, List[ProcessedSlot]]:
        """
        Group schedule entries by date.

        Args:
            schedule: List of schedule slot dictionaries with date, start_time, end_time as strings

        Returns:
            Dictionary mapping dates to lists of ProcessedSlot dictionaries
        """
        schedule_by_date: Dict[date, List[ProcessedSlot]] = {}

        for slot in schedule:
            # Skip past dates
            slot_date = date.fromisoformat(slot["date"])
            if slot_date < date.today():
                logger.warning(f"Skipping past date: {slot_date}")
                continue

            if slot_date not in schedule_by_date:
                schedule_by_date[slot_date] = []

            # Convert string times to time objects
            from datetime import time as dt_time

            schedule_by_date[slot_date].append(
                ProcessedSlot(
                    start_time=dt_time.fromisoformat(slot["start_time"]),
                    end_time=dt_time.fromisoformat(slot["end_time"]),
                )
            )

        return schedule_by_date

    def _invalidate_availability_caches(self, instructor_id: int, dates: List[date]) -> None:
        """Invalidate caches for affected dates."""
        # Invalidate instructor-specific caches
        self.invalidate_cache(f"instructor_availability:{instructor_id}")

        # Invalidate date-specific caches
        for target_date in dates:
            self.invalidate_cache(f"instructor_availability:{instructor_id}:{target_date}")

        # Invalidate week caches
        weeks = set()
        for target_date in dates:
            monday = target_date - timedelta(days=target_date.weekday())
            weeks.add(monday)

        for week_start in weeks:
            self.invalidate_cache(f"week_availability:{instructor_id}:{week_start}")
