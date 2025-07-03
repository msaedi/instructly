# backend/app/services/availability_service.py
"""
Availability Service for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

This service has been significantly simplified by removing the concept of
InstructorAvailability entries. Now works directly with AvailabilitySlots
that contain instructor_id and date.

Key changes:
- No more InstructorAvailability model references
- No more is_cleared flag - absence of slots means cleared
- Direct slot queries using instructor_id and date
- Simplified data structures
"""

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.exceptions import ConflictException, DomainException, NotFoundException, RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate
from ..models.instructor import InstructorProfile
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import BlackoutDateCreate, SpecificDateAvailabilityCreate, WeekSpecificScheduleCreate
from ..utils.time_helpers import time_to_string
from .base import BaseService

# TYPE_CHECKING import to avoid circular dependencies
if TYPE_CHECKING:
    from ..repositories.availability_repository import AvailabilityRepository
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


class AvailabilityService(BaseService):
    """
    Service layer for availability operations.

    Works directly with AvailabilitySlot objects in the single-table design.
    """

    def __init__(
        self,
        db: Session,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["AvailabilityRepository"] = None,
    ):
        """Initialize availability service with optional cache and repository."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        self.cache_service = cache_service

        # Initialize repository
        self.repository = repository or RepositoryFactory.create_availability_repository(db)

        if cache_service:
            self.logger.info("AvailabilityService initialized WITH cache service")
        else:
            self.logger.warning("AvailabilityService initialized WITHOUT cache service")

    def get_availability_for_date(self, instructor_id: int, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Get availability for a specific date.

        SIMPLIFIED: Queries slots directly by instructor_id and date.

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
                self.logger.warning(f"Cache error for date availability: {cache_error}. Falling back to database.")

        # Query slots directly
        try:
            slots = self.repository.get_slots_by_date(instructor_id, target_date)
        except RepositoryException as e:
            self.logger.error(f"Repository error getting availability: {e}")
            return None

        if not slots:
            return None

        result = {
            "date": target_date.isoformat(),
            "slots": [
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True,
                }
                for slot in slots
            ],
        }

        # Cache for 1 hour
        if self.cache_service:
            try:
                self.cache_service.set(cache_key, result, tier="warm")
            except Exception as cache_error:
                self.logger.warning(f"Failed to cache date availability: {cache_error}")

        return result

    def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]:
        """
        Get summary of availability (slot counts) for date range.

        SIMPLIFIED: Counts slots directly without InstructorAvailability.

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
            self.logger.error(f"Error getting availability summary: {e}")
            return {}

    def get_week_availability(self, instructor_id: int, start_date: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get availability for a specific week.

        SIMPLIFIED: Returns slots grouped by date, no is_cleared concept.

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
                    self.logger.info(f"CACHE HIT for week availability: instructor={instructor_id}, start={start_date}")
                    return cached_data
                else:
                    self.logger.info(
                        f"CACHE MISS for week availability: instructor={instructor_id}, start={start_date}"
                    )
            except Exception as cache_error:
                self.logger.warning(f"Cache error for week availability: {cache_error}. Falling back to database.")

        # Calculate week dates (Monday to Sunday)
        week_dates = self._calculate_week_dates(start_date)
        end_date = week_dates[-1]

        # Get all slots for the week
        import time as time_module

        start_time = time_module.time()

        try:
            all_slots = self.repository.get_week_availability(instructor_id, start_date, end_date)
        except RepositoryException as e:
            self.logger.error(f"Error getting week availability: {e}")
            return {}

        query_time = (time_module.time() - start_time) * 1000
        self.logger.info(f"Database query took {query_time:.2f}ms")
        self.logger.debug(f"Found {len(all_slots)} slots for the week")

        # Group slots by date
        week_schedule = {}
        for slot in all_slots:
            date_str = slot.date.isoformat()

            if date_str not in week_schedule:
                week_schedule[date_str] = []

            week_schedule[date_str].append(
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True,
                }
            )

        # Cache the result
        if self.cache_service:
            try:
                success = self.cache_service.cache_week_availability(instructor_id, start_date, week_schedule)
                self.logger.info(f"Cached week availability: success={success}")
            except Exception as cache_error:
                self.logger.warning(f"Failed to cache week availability: {cache_error}")

        return week_schedule

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
            # Build query for slots directly
            query = self.db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == instructor_id)

            # Apply date filters if provided
            if start_date:
                query = query.filter(AvailabilitySlot.date >= start_date)
            if end_date:
                query = query.filter(AvailabilitySlot.date <= end_date)

            # Order by date and time
            slots = query.order_by(AvailabilitySlot.date, AvailabilitySlot.start_time).all()

            self.logger.info(f"Retrieved {len(slots)} slots for instructor {instructor_id}")
            return slots

        except Exception as e:
            self.logger.error(f"Error retrieving all availability: {str(e)}")
            raise DomainException(f"Failed to retrieve availability: {str(e)}")

    async def save_week_availability(self, instructor_id: int, week_data: WeekSpecificScheduleCreate) -> Dict[str, Any]:
        """
        Save availability for specific dates in a week.

        SIMPLIFIED: Works directly with slots, no InstructorAvailability entries.

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

        # Determine week dates
        monday = self._determine_week_start(week_data)
        week_dates = self._calculate_week_dates(monday)

        # Group schedule by date
        schedule_by_date = self._group_schedule_by_date(week_data.schedule)

        # Count expected slots
        expected_slot_count = sum(len(slots) for slots in schedule_by_date.values())

        with self.transaction():
            # If clearing existing, delete all slots for the week
            if week_data.clear_existing:
                deleted_count = self.repository.delete_slots_by_dates(instructor_id, week_dates)
                self.logger.info(f"Deleted {deleted_count} existing slots")

            # Process each date with new slots
            slots_created = 0
            for week_date in week_dates:
                # Skip past dates
                if week_date < date.today():
                    continue

                if week_date in schedule_by_date:
                    # Create new slots for this date
                    new_slots = []
                    for slot in schedule_by_date[week_date]:
                        # Check if slot already exists
                        if not self.repository.slot_exists(
                            instructor_id, target_date=week_date, start_time=slot.start_time, end_time=slot.end_time
                        ):
                            new_slots.append(
                                AvailabilitySlot(
                                    instructor_id=instructor_id,
                                    date=week_date,
                                    start_time=slot.start_time,
                                    end_time=slot.end_time,
                                )
                            )

                    if new_slots:
                        self.db.add_all(new_slots)
                        slots_created += len(new_slots)

            self.logger.info(f"Created {slots_created} new slots")

        # Ensure SQLAlchemy session is fresh
        self.db.expire_all()

        # Handle cache warming
        if self.cache_service:
            try:
                from .cache_strategies import CacheWarmingStrategy

                warmer = CacheWarmingStrategy(self.cache_service, self.db)
                updated_availability = await warmer.warm_with_verification(
                    instructor_id, monday, expected_slot_count=expected_slot_count
                )
            except ImportError:
                self.logger.warning("Cache strategies not available, using direct fetch")
                self._invalidate_availability_caches(instructor_id, week_dates)
                updated_availability = self.get_week_availability(instructor_id, monday)
        else:
            updated_availability = self.get_week_availability(instructor_id, monday)

        return updated_availability

    def add_specific_date_availability(
        self, instructor_id: int, availability_data: SpecificDateAvailabilityCreate
    ) -> Dict[str, Any]:
        """
        Add availability for a specific date.

        SIMPLIFIED: Creates slot directly without InstructorAvailability.

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

            # Create new slot - FIXED: Using target_date parameter
            slot = self.repository.create_slot(
                instructor_id=instructor_id,
                target_date=availability_data.specific_date,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time,
            )
            self.db.commit()

            # Invalidate cache
            self._invalidate_availability_caches(instructor_id, [availability_data.specific_date])

            return {
                "id": slot.id,
                "instructor_id": instructor_id,
                "specific_date": slot.date,
                "start_time": time_to_string(slot.start_time),
                "end_time": time_to_string(slot.end_time),
                "is_available": True,
                "is_recurring": False,
            }

    def get_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]:
        """
        Get instructor's future blackout dates.

        NOTE: Blackout dates remain unchanged in single-table design.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of future blackout dates
        """
        try:
            return self.repository.get_future_blackout_dates(instructor_id)
        except RepositoryException as e:
            self.logger.error(f"Error getting blackout dates: {e}")
            return []

    def add_blackout_date(self, instructor_id: int, blackout_data: BlackoutDateCreate) -> BlackoutDate:
        """
        Add a blackout date for an instructor.

        NOTE: Blackout dates remain unchanged in single-table design.

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

        try:
            blackout = self.repository.create_blackout_date(instructor_id, blackout_data.date, blackout_data.reason)
            self.db.commit()
            return blackout
        except RepositoryException as e:
            if "already exists" in str(e):
                raise ConflictException("Blackout date already exists")
            raise

    def delete_blackout_date(self, instructor_id: int, blackout_id: int) -> bool:
        """
        Delete a blackout date.

        NOTE: Blackout dates remain unchanged in single-table design.

        Args:
            instructor_id: The instructor's user ID
            blackout_id: The blackout date ID

        Returns:
            True if deleted successfully
        """
        try:
            success = self.repository.delete_blackout_date(blackout_id, instructor_id)
            if not success:
                raise NotFoundException("Blackout date not found")
            self.db.commit()
            return True
        except RepositoryException as e:
            self.logger.error(f"Error deleting blackout date: {e}")
            raise

    # Private helper methods

    def _get_instructor_profile(self, instructor_id: int) -> InstructorProfile:
        """Get instructor profile or raise exception."""
        profile = self.db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()

        if not profile:
            raise NotFoundException("Instructor profile not found")

        return profile

    def _calculate_week_dates(self, monday: date) -> List[date]:
        """Calculate all dates for a week starting from Monday."""
        return [monday + timedelta(days=i) for i in range(7)]

    def _determine_week_start(self, week_data: WeekSpecificScheduleCreate) -> date:
        """Determine the Monday of the week from schedule data."""
        if week_data.week_start:
            return week_data.week_start
        elif week_data.schedule:
            # Get Monday from the first date in schedule
            first_date = min(slot.date for slot in week_data.schedule)
            return first_date - timedelta(days=first_date.weekday())
        else:
            # Fallback to current week
            today = date.today()
            return today - timedelta(days=today.weekday())

    def _group_schedule_by_date(self, schedule: List[Any]) -> Dict[date, List[Any]]:
        """Group schedule entries by date."""
        schedule_by_date = {}
        for slot in schedule:
            # Skip past dates
            if slot.date < date.today():
                self.logger.warning(f"Skipping past date: {slot.date}")
                continue

            if slot.date not in schedule_by_date:
                schedule_by_date[slot.date] = []
            schedule_by_date[slot.date].append(slot)

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
