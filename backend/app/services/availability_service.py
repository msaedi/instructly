# backend/app/services/availability_service.py
"""
Availability Service for InstaInstru Platform

Core service handling instructor availability management including:
- Week-based availability viewing
- Saving and updating availability
- Date-specific availability management
- Coordination with booking system

REFACTORED: Now uses AvailabilityRepository for all data access
"""

import logging
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import ConflictException, NotFoundException, RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
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

    Centralizes all availability business logic and provides
    clean interfaces for the route handlers.
    """

    def __init__(
        self,
        db: Session,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["AvailabilityRepository"] = None,
    ):
        """Initialize availability service with optional cache and repository."""
        # Pass the cache service to BaseService
        # The CacheService has a redis property that matches RedisCache interface
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
        Get availability for a specific date (optimized for single day).

        Args:
            instructor_id: The instructor ID
            target_date: The specific date

        Returns:
            Availability data for the date or None
        """
        # Try cache first - WITH ERROR HANDLING
        cache_key = f"availability:day:{instructor_id}:{target_date.isoformat()}"
        if self.cache_service:
            try:
                cached = self.cache_service.get(cache_key)
                if cached is not None:
                    return cached
            except Exception as cache_error:
                self.logger.warning(f"Cache error for date availability: {cache_error}. Falling back to database.")

        # Query using repository
        try:
            entry = self.repository.get_availability_by_date(instructor_id, target_date)
        except RepositoryException as e:
            self.logger.error(f"Repository error getting availability: {e}")
            return None

        if not entry or entry.is_cleared:
            return None

        result = {
            "date": entry.date.isoformat(),
            "slots": [
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True,
                }
                for slot in entry.time_slots
            ],
        }

        # Cache for 1 hour - WITH ERROR HANDLING
        if self.cache_service:
            try:
                self.cache_service.set(cache_key, result, tier="warm")
            except Exception as cache_error:
                self.logger.warning(f"Failed to cache date availability: {cache_error}")

        return result

    def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]:
        """
        Get summary of availability (slot counts) for date range.

        Useful for calendar views that just need to show if days have availability.

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

    def prefetch_week_availability(self, instructor_id: int, start_date: date) -> None:
        """
        Prefetch and cache a week's availability in one query.

        Optimized for initial calendar load.
        """
        week_dates = self._calculate_week_dates(start_date)
        end_date = week_dates[-1]

        try:
            # Use repository to get all entries
            entries = self.repository.get_week_availability(instructor_id, start_date, end_date)
        except RepositoryException as e:
            self.logger.error(f"Error prefetching week availability: {e}")
            return

        # Cache each day individually for granular access
        for entry in entries:
            if not entry.is_cleared and entry.time_slots:
                day_data = {
                    "date": entry.date.isoformat(),
                    "slots": [
                        {
                            "start_time": time_to_string(slot.start_time),
                            "end_time": time_to_string(slot.end_time),
                            "is_available": True,
                        }
                        for slot in entry.time_slots
                    ],
                }

                cache_key = f"availability:day:{instructor_id}:{entry.date.isoformat()}"
                if self.cache_service:
                    self.cache_service.set(cache_key, day_data, tier="hot")

    def get_all_availability(
        self,
        instructor_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[InstructorAvailability]:
        """
        Get all availability entries with optional date filtering.

        Args:
            instructor_id: The instructor ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of InstructorAvailability entries with loaded time slots
        """
        try:
            if start_date and end_date:
                return self.repository.get_week_availability(instructor_id, start_date, end_date)
            else:
                # For no date range, use base repository get_all with filter
                # This could be added as a method to AvailabilityRepository if needed
                return self.repository.find_by(instructor_id=instructor_id)
        except RepositoryException as e:
            self.logger.error(f"Error getting all availability: {e}")
            return []

    def get_week_availability(self, instructor_id: int, start_date: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get availability for a specific week.

        Returns a dictionary mapping ISO date strings to lists of time slots.
        Days marked as "cleared" or without entries are not included.

        Args:
            instructor_id: The instructor's user ID
            start_date: Monday of the week to retrieve

        Returns:
            Dict mapping date strings to time slot lists

        Example:
            {
                "2024-06-10": [
                    {"start_time": "09:00:00", "end_time": "12:00:00", "is_available": true}
                ],
                "2024-06-11": []
            }
        """
        self.log_operation("get_week_availability", instructor_id=instructor_id, start_date=start_date)

        # Try cache first if available - WITH ERROR HANDLING
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
                # Log cache error but continue with database query
                self.logger.warning(f"Cache error for week availability: {cache_error}. Falling back to database.")

        # Calculate week dates (Monday to Sunday)
        week_dates = self._calculate_week_dates(start_date)
        end_date = week_dates[-1]

        # Get instructor availability for this week using repository
        import time as time_module

        start_time = time_module.time()

        try:
            availability_entries = self.repository.get_week_availability(instructor_id, start_date, end_date)
        except RepositoryException as e:
            self.logger.error(f"Error getting week availability: {e}")
            return {}

        query_time = (time_module.time() - start_time) * 1000
        self.logger.info(f"Database query took {query_time:.2f}ms")

        self.logger.debug(f"Found {len(availability_entries)} availability entries for the week")

        # Build response
        week_schedule = {}

        for entry in availability_entries:
            date_str = entry.date.isoformat()

            # Skip cleared days
            if entry.is_cleared:
                self.logger.debug(f"Day {date_str} is explicitly cleared")
                continue

            # Add time slots
            if entry.time_slots:
                week_schedule[date_str] = [
                    {
                        "start_time": time_to_string(slot.start_time),
                        "end_time": time_to_string(slot.end_time),
                        "is_available": True,
                    }
                    for slot in entry.time_slots
                ]
                self.logger.debug(f"Added {len(entry.time_slots)} slots for {date_str}")

        # Cache the result if cache is available - WITH ERROR HANDLING
        if self.cache_service:
            try:
                success = self.cache_service.cache_week_availability(instructor_id, start_date, week_schedule)
                self.logger.info(f"Cached week availability: success={success}")
            except Exception as cache_error:
                # Log cache error but don't fail the request
                self.logger.warning(f"Failed to cache week availability: {cache_error}")

        return week_schedule

    async def save_week_availability(self, instructor_id: int, week_data: WeekSpecificScheduleCreate) -> Dict[str, Any]:
        """
        Save availability for specific dates in a week.

        This replaces existing availability while preserving booked slots.
        The operation is atomic - all changes succeed or all are rolled back.

        Args:
            instructor_id: The instructor's user ID
            week_data: The week schedule data

        Returns:
            Updated week availability with metadata about skipped dates

        Raises:
            ValidationException: If validation fails
            BusinessRuleException: If business rules are violated
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

        # Count expected slots for verification
        expected_slot_count = sum(len(slots) for slots in schedule_by_date.values())

        # Process each day with transaction
        with self.transaction():
            result = await self._process_week_days(
                instructor_id=instructor_id,
                week_dates=week_dates,
                schedule_by_date=schedule_by_date,
                clear_existing=week_data.clear_existing,
            )

        # Ensure SQLAlchemy session is fresh after transaction
        self.db.expire_all()

        # Handle cache warming if cache service is available
        if self.cache_service:
            try:
                from .cache_strategies import CacheWarmingStrategy

                warmer = CacheWarmingStrategy(self.cache_service, self.db)

                # Only pass expected_slot_count if no dates were skipped
                expected = expected_slot_count if not result.get("dates_with_bookings") else None

                # Warm cache with verification
                updated_availability = await warmer.warm_with_verification(
                    instructor_id, monday, expected_slot_count=expected
                )
            except ImportError:
                # Fallback if cache_strategies not available yet
                self.logger.warning("Cache strategies not available, using direct fetch")
                self._invalidate_availability_caches(instructor_id, week_dates)
                updated_availability = self.get_week_availability(instructor_id, monday)
        else:
            # No cache, get directly
            updated_availability = self.get_week_availability(instructor_id, monday)

        # Add metadata if dates were skipped
        if result.get("dates_with_bookings"):
            updated_availability["_metadata"] = {
                "skipped_dates_with_bookings": result["dates_with_bookings"],
                "message": f"Changes saved successfully. {len(result['dates_with_bookings'])} date(s) with existing bookings were not modified.",
            }

        return updated_availability

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

        Raises:
            ConflictException: If slot already exists
        """
        with self.transaction():
            # Get or create availability entry using repository
            try:
                availability = self.repository.get_or_create_availability(
                    instructor_id, availability_data.specific_date
                )

                # Check for duplicate slot
                if availability and not availability.is_cleared:
                    if self.repository.slot_exists(
                        availability.id, availability_data.start_time, availability_data.end_time
                    ):
                        raise ConflictException("This time slot already exists")

                # Update cleared status if needed
                if availability.is_cleared:
                    availability.is_cleared = False

                # Add time slot using repository create
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=availability_data.start_time,
                    end_time=availability_data.end_time,
                )
                self.db.add(slot)
                self.db.commit()

            except RepositoryException as e:
                raise ConflictException(f"Failed to add availability: {str(e)}")

            # Invalidate cache
            self._invalidate_availability_caches(instructor_id, [availability_data.specific_date])

            return {
                "id": availability.id,
                "instructor_id": instructor_id,
                "specific_date": availability.date,
                "start_time": time_to_string(availability_data.start_time),
                "end_time": time_to_string(availability_data.end_time),
                "is_available": True,
                "is_recurring": False,
                "is_cleared": False,
            }

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
            self.logger.error(f"Error getting blackout dates: {e}")
            return []

    def add_blackout_date(self, instructor_id: int, blackout_data: BlackoutDateCreate) -> BlackoutDate:
        """
        Add a blackout date for an instructor.

        Args:
            instructor_id: The instructor's user ID
            blackout_data: The blackout date information

        Returns:
            Created blackout date

        Raises:
            ConflictException: If date already exists
        """
        # Check if already exists using repository
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

        Args:
            instructor_id: The instructor's user ID
            blackout_id: The blackout date ID

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If blackout date not found
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

    # Private helper methods (business logic stays in service)

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

    async def _process_week_days(
        self,
        instructor_id: int,
        week_dates: List[date],
        schedule_by_date: Dict[date, List[Any]],
        clear_existing: bool,
    ) -> Dict[str, Any]:
        """Process each day of the week."""
        dates_created = 0
        slots_created = 0
        dates_with_bookings = []

        for week_date in week_dates:
            # Skip past dates
            if week_date < date.today():
                continue

            if week_date in schedule_by_date:
                # Process date with new slots
                result = await self._process_date_with_slots(
                    instructor_id=instructor_id,
                    target_date=week_date,
                    slots=schedule_by_date[week_date],
                    clear_existing=clear_existing,
                )
                dates_created += result["dates_created"]
                slots_created += result["slots_created"]
                if result.get("has_bookings"):
                    dates_with_bookings.append(week_date.strftime("%Y-%m-%d"))
            else:
                # Process date without new slots
                if clear_existing:
                    result = await self._process_date_without_slots(instructor_id=instructor_id, target_date=week_date)
                    dates_created += result["dates_created"]
                    if result.get("has_bookings"):
                        dates_with_bookings.append(week_date.strftime("%Y-%m-%d"))

        self.logger.info(
            f"Processed week: {dates_created} dates, {slots_created} slots, "
            f"{len(dates_with_bookings)} dates with bookings"
        )

        return {
            "dates_created": dates_created,
            "slots_created": slots_created,
            "dates_with_bookings": dates_with_bookings,
        }

    async def _process_date_with_slots(
        self,
        instructor_id: int,
        target_date: date,
        slots: List[Any],
        clear_existing: bool,
    ) -> Dict[str, Any]:
        """Process a date that has new slots."""
        dates_created = 0
        slots_created = 0
        has_bookings = False

        try:
            # Get or create availability using repository
            availability = self.repository.get_or_create_availability(instructor_id, target_date)
            is_new = availability.id is None

            if is_new:
                dates_created = 1

            # Check for existing bookings
            booked_slot_ids = self.repository.get_booked_slot_ids(instructor_id, target_date)
            if booked_slot_ids:
                has_bookings = True
                self.logger.info(f"Found {len(booked_slot_ids)} booked slots for {target_date}")

            if clear_existing and booked_slot_ids:
                # Delete only non-booked slots
                self.repository.delete_non_booked_slots(availability.id, booked_slot_ids)

            # Get booked time ranges for conflict checking
            booked_slots = self.repository.get_slots_by_availability_id(availability.id)
            booked_time_ranges = [
                (slot.start_time, slot.end_time) for slot in booked_slots if slot.id in booked_slot_ids
            ]

            # Set availability as not cleared
            availability.is_cleared = False

            # Add new slots that don't conflict with bookings
            for slot in slots:
                if not self._conflicts_with_bookings(slot.start_time, slot.end_time, booked_time_ranges):
                    if not self.repository.slot_exists(availability.id, slot.start_time, slot.end_time):
                        time_slot = AvailabilitySlot(
                            availability_id=availability.id,
                            start_time=slot.start_time,
                            end_time=slot.end_time,
                        )
                        self.db.add(time_slot)
                        slots_created += 1

        except RepositoryException as e:
            self.logger.error(f"Error processing date with slots: {e}")
            raise

        return {
            "dates_created": dates_created,
            "slots_created": slots_created,
            "has_bookings": has_bookings,
        }

    async def _process_date_without_slots(self, instructor_id: int, target_date: date) -> Dict[str, Any]:
        """Process a date that has no new slots (clearing)."""
        dates_created = 0
        has_bookings = False

        try:
            # Check for existing bookings using repository
            existing_bookings = self.repository.count_bookings_for_date(instructor_id, target_date)

            if existing_bookings > 0:
                has_bookings = True
                self.logger.warning(f"Cannot clear {target_date} - has {existing_bookings} bookings")
            else:
                # Safe to delete - get existing availability
                existing = self.repository.get_availability_by_date(instructor_id, target_date)
                if existing:
                    # Delete the availability entry
                    self.db.delete(existing)

                    # Create cleared entry if not today
                    if target_date != date.today():
                        availability_entry = InstructorAvailability(
                            instructor_id=instructor_id, date=target_date, is_cleared=True
                        )
                        self.db.add(availability_entry)
                        dates_created = 1

        except RepositoryException as e:
            self.logger.error(f"Error processing date without slots: {e}")

        return {"dates_created": dates_created, "has_bookings": has_bookings}

    def _conflicts_with_bookings(
        self, start_time: time, end_time: time, booked_ranges: List[Tuple[time, time]]
    ) -> bool:
        """Check if a time range conflicts with booked slots."""
        for booked_start, booked_end in booked_ranges:
            if start_time < booked_end and end_time > booked_start:
                return True
        return False

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
