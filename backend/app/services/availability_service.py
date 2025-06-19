# backend/app/services/availability_service.py
"""
Availability Service for InstaInstru Platform

Core service handling instructor availability management including:
- Week-based availability viewing
- Saving and updating availability
- Date-specific availability management
- Coordination with booking system
"""

import logging
from datetime import date, timedelta, datetime, time
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from ..models.availability import InstructorAvailability, AvailabilitySlot, BlackoutDate
from ..models.instructor import InstructorProfile
from ..models.booking import Booking, BookingStatus
from ..models.user import User
from ..schemas.availability_window import (
    WeekSpecificScheduleCreate,
    SpecificDateAvailabilityCreate,
    BlackoutDateCreate
)
from .base import BaseService
from ..core.exceptions import (
    NotFoundException,
    ConflictException
)
from ..utils.time_helpers import time_to_string, string_to_time

# TYPE_CHECKING import to avoid circular dependencies
if TYPE_CHECKING:
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


class AvailabilityService(BaseService):
    """
    Service layer for availability operations.
    
    Centralizes all availability business logic and provides
    clean interfaces for the route handlers.
    """
    
    def __init__(self, db: Session, cache_service: Optional['CacheService'] = None):
        """Initialize availability service with optional cache."""
        # Pass the cache service to BaseService
        # The CacheService has a redis property that matches RedisCache interface
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        self.cache_service = cache_service

        if cache_service:
            self.logger.info("AvailabilityService initialized WITH cache service")
        else:
            self.logger.warning("AvailabilityService initialized WITHOUT cache service")


    def get_availability_for_date(
        self,
        instructor_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """
        Get availability for a specific date (optimized for single day).
        
        Args:
            instructor_id: The instructor ID
            target_date: The specific date
            
        Returns:
            Availability data for the date or None
        """
        # Try cache first
        cache_key = f"availability:day:{instructor_id}:{target_date.isoformat()}"
        if self.cache_service:
            cached = self.cache_service.get(cache_key)
            if cached is not None:
                return cached
        
        # Query only for specific date
        entry = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date == target_date
        ).options(joinedload(InstructorAvailability.time_slots)).first()
        
        if not entry or entry.is_cleared:
            return None
        
        result = {
            "date": entry.date.isoformat(),
            "slots": [
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True
                }
                for slot in entry.time_slots
            ]
        }
        
        # Cache for 1 hour
        if self.cache_service:
            self.cache_service.set(cache_key, result, tier='warm')
        
        return result
    
    def get_availability_summary(
        self,
        instructor_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, int]:
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
        # Use raw SQL for optimal performance
        query = """
            SELECT 
                ia.date,
                COUNT(aslot.id) as slot_count
            FROM instructor_availability ia
            LEFT JOIN availability_slots aslot ON ia.id = aslot.availability_id
            WHERE 
                ia.instructor_id = :instructor_id
                AND ia.date BETWEEN :start_date AND :end_date
                AND ia.is_cleared = false
            GROUP BY ia.date
            ORDER BY ia.date
        """
        
        result = self.db.execute(
            query,
            {
                'instructor_id': instructor_id,
                'start_date': start_date,
                'end_date': end_date
            }
        )
        
        return {
            row.date.isoformat(): row.slot_count
            for row in result
        }
    
    def prefetch_week_availability(
        self,
        instructor_id: int,
        start_date: date
    ) -> None:
        """
        Prefetch and cache a week's availability in one query.
        
        Optimized for initial calendar load.
        """
        week_dates = self._calculate_week_dates(start_date)
        
        # Single query with all data
        entries = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date.in_(week_dates)
        ).options(
            joinedload(InstructorAvailability.time_slots)
        ).all()
        
        # Cache each day individually for granular access
        for entry in entries:
            if not entry.is_cleared and entry.time_slots:
                day_data = {
                    "date": entry.date.isoformat(),
                    "slots": [
                        {
                            "start_time": time_to_string(slot.start_time),
                            "end_time": time_to_string(slot.end_time),
                            "is_available": True
                        }
                        for slot in entry.time_slots
                    ]
                }
                
                cache_key = f"availability:day:{instructor_id}:{entry.date.isoformat()}"
                if self.cache_service:
                    self.cache_service.set(cache_key, day_data, tier='hot')
    
    def get_all_availability(
        self,
        instructor_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
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
        query = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id
        ).options(joinedload(InstructorAvailability.time_slots))
        
        if start_date and end_date:
            query = query.filter(
                InstructorAvailability.date >= start_date,
                InstructorAvailability.date <= end_date
            )
        
        return query.all()
    
    def get_week_availability(
        self,
        instructor_id: int,
        start_date: date
    ) -> Dict[str, List[Dict[str, Any]]]:
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
        self.log_operation(
            "get_week_availability",
            instructor_id=instructor_id,
            start_date=start_date
        )
        
        # Try cache first if available
        if self.cache_service:
            cached_data = self.cache_service.get_week_availability(instructor_id, start_date)
            if cached_data is not None:
                self.logger.info(f"CACHE HIT for week availability: instructor={instructor_id}, start={start_date}")
                return cached_data
            else:
                self.logger.info(f"CACHE MISS for week availability: instructor={instructor_id}, start={start_date}")
        
        # Calculate week dates (Monday to Sunday)
        week_dates = self._calculate_week_dates(start_date)
        
        # Get instructor availability for this week
        import time as time_module
        start_time = time_module.time()
        availability_entries = self.db.query(InstructorAvailability).filter(
            and_(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date.in_(week_dates)
            )
        ).options(joinedload(InstructorAvailability.time_slots)).all()
        
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
                        "is_available": True
                    }
                    for slot in entry.time_slots
                ]
                self.logger.debug(f"Added {len(entry.time_slots)} slots for {date_str}")
        
        # Cache the result if cache is available
        if self.cache_service:
            success = self.cache_service.cache_week_availability(instructor_id, start_date, week_schedule)
            self.logger.info(f"Cached week availability: success={success}")
        
        return week_schedule
    
    async def save_week_availability(
        self,
        instructor_id: int,
        week_data: WeekSpecificScheduleCreate
    ) -> Dict[str, Any]:
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
            schedule_count=len(week_data.schedule)
        )
        
        # Determine week dates
        monday = self._determine_week_start(week_data)
        week_dates = self._calculate_week_dates(monday)
        
        # Group schedule by date
        schedule_by_date = self._group_schedule_by_date(week_data.schedule)
        
        # Process each day with transaction
        with self.transaction():
            result = await self._process_week_days(
                instructor_id=instructor_id,
                week_dates=week_dates,
                schedule_by_date=schedule_by_date,
                clear_existing=week_data.clear_existing
            )
        
        # Force SQLAlchemy to clear its cache
        self.db.expire_all()

        # Invalidate cache AFTER transaction commits
        # This ensures the database has the new data before we clear the cache
        self._invalidate_availability_caches(instructor_id, week_dates)
        
        # Add a small delay to ensure DB replication (if using read replicas)
        import asyncio
        await asyncio.sleep(0.1)  # 100ms delay

        # Get updated availability
        updated_availability = self.get_week_availability(instructor_id, monday)
        
        # Add metadata if dates were skipped
        if result['dates_with_bookings']:
            updated_availability["_metadata"] = {
                "skipped_dates_with_bookings": result['dates_with_bookings'],
                "message": f"Changes saved successfully. {len(result['dates_with_bookings'])} date(s) with existing bookings were not modified."
            }
        
        return updated_availability
    
    def add_specific_date_availability(
        self,
        instructor_id: int,
        availability_data: SpecificDateAvailabilityCreate
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
            # Check for existing entry
            existing = self.db.query(InstructorAvailability).filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == availability_data.specific_date
            ).first()
            
            if existing and not existing.is_cleared:
                # Check for duplicate slot
                duplicate = self._check_duplicate_slot(
                    existing,
                    availability_data.start_time,
                    availability_data.end_time
                )
                if duplicate:
                    raise ConflictException("This time slot already exists")
            
            # Create or update availability entry
            if not existing:
                availability_entry = InstructorAvailability(
                    instructor_id=instructor_id,
                    date=availability_data.specific_date,
                    is_cleared=False
                )
                self.db.add(availability_entry)
                self.db.flush()
            else:
                availability_entry = existing
                if availability_entry.is_cleared:
                    availability_entry.is_cleared = False
            
            # Add time slot
            time_slot = AvailabilitySlot(
                availability_id=availability_entry.id,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time
            )
            self.db.add(time_slot)
            self.db.commit()
            
            # Invalidate cache
            self._invalidate_availability_caches(
                instructor_id, 
                [availability_data.specific_date]
            )
            
            return {
                "id": availability_entry.id,
                "instructor_id": instructor_id,
                "specific_date": availability_entry.date,
                "start_time": time_to_string(availability_data.start_time),
                "end_time": time_to_string(availability_data.end_time),
                "is_available": True,
                "is_recurring": False,
                "is_cleared": False
            }
    
    def get_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]:
        """
        Get instructor's future blackout dates.
        
        Args:
            instructor_id: The instructor's user ID
            
        Returns:
            List of future blackout dates
        """
        return self.db.query(BlackoutDate).filter(
            BlackoutDate.instructor_id == instructor_id,
            BlackoutDate.date >= date.today()
        ).order_by(BlackoutDate.date).all()
    
    def add_blackout_date(
        self,
        instructor_id: int,
        blackout_data: BlackoutDateCreate
    ) -> BlackoutDate:
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
        # Check if already exists
        existing = self.db.query(BlackoutDate).filter(
            BlackoutDate.instructor_id == instructor_id,
            BlackoutDate.date == blackout_data.date
        ).first()
        
        if existing:
            raise ConflictException("Blackout date already exists")
        
        blackout = BlackoutDate(
            instructor_id=instructor_id,
            date=blackout_data.date,
            reason=blackout_data.reason
        )
        
        self.db.add(blackout)
        self.db.commit()
        self.db.refresh(blackout)
        
        return blackout
    
    def delete_blackout_date(
        self,
        instructor_id: int,
        blackout_id: int
    ) -> bool:
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
        blackout = self.db.query(BlackoutDate).filter(
            BlackoutDate.id == blackout_id,
            BlackoutDate.instructor_id == instructor_id
        ).first()
        
        if not blackout:
            raise NotFoundException("Blackout date not found")
        
        self.db.delete(blackout)
        self.db.commit()
        
        return True
    
    # Private helper methods
    
    def _get_instructor_profile(self, instructor_id: int) -> InstructorProfile:
        """Get instructor profile or raise exception."""
        profile = self.db.query(InstructorProfile).filter(
            InstructorProfile.user_id == instructor_id
        ).first()
        
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
    
    def _group_schedule_by_date(
        self, 
        schedule: List[Any]
    ) -> Dict[date, List[Any]]:
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
        clear_existing: bool
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
                    clear_existing=clear_existing
                )
                dates_created += result['dates_created']
                slots_created += result['slots_created']
                if result.get('has_bookings'):
                    dates_with_bookings.append(week_date.strftime("%Y-%m-%d"))
            else:
                # Process date without new slots
                if clear_existing:
                    result = await self._process_date_without_slots(
                        instructor_id=instructor_id,
                        target_date=week_date
                    )
                    dates_created += result['dates_created']
                    if result.get('has_bookings'):
                        dates_with_bookings.append(week_date.strftime("%Y-%m-%d"))
        
        self.logger.info(
            f"Processed week: {dates_created} dates, {slots_created} slots, "
            f"{len(dates_with_bookings)} dates with bookings"
        )
        
        return {
            'dates_created': dates_created,
            'slots_created': slots_created,
            'dates_with_bookings': dates_with_bookings
        }
    
    async def _process_date_with_slots(
        self,
        instructor_id: int,
        target_date: date,
        slots: List[Any],
        clear_existing: bool
    ) -> Dict[str, Any]:
        """Process a date that has new slots."""
        dates_created = 0
        slots_created = 0
        has_bookings = False
        
        # Get existing availability
        existing = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date == target_date
        ).first()
        
        if existing:
            # Handle existing availability with potential bookings
            booked_slots = self._get_booked_slots(existing.id)
            booked_time_ranges = [
                (slot.start_time, slot.end_time) for slot in booked_slots
            ]
            
            if booked_time_ranges:
                has_bookings = True
                self.logger.info(
                    f"Found {len(booked_time_ranges)} booked slots for {target_date}"
                )
            
            if clear_existing:
                # Delete only non-booked slots
                self._delete_non_booked_slots(existing.id, booked_slots)
            
            availability_entry = existing
            availability_entry.is_cleared = False
        else:
            # Create new availability entry
            availability_entry = InstructorAvailability(
                instructor_id=instructor_id,
                date=target_date,
                is_cleared=False
            )
            self.db.add(availability_entry)
            self.db.flush()
            dates_created = 1
            booked_time_ranges = []
        
        # Add new slots that don't conflict with bookings
        for slot in slots:
            if not self._conflicts_with_bookings(
                slot.start_time, 
                slot.end_time, 
                booked_time_ranges
            ):
                if not self._slot_exists(
                    availability_entry.id,
                    slot.start_time,
                    slot.end_time
                ):
                    time_slot = AvailabilitySlot(
                        availability_id=availability_entry.id,
                        start_time=slot.start_time,
                        end_time=slot.end_time
                    )
                    self.db.add(time_slot)
                    slots_created += 1
        
        return {
            'dates_created': dates_created,
            'slots_created': slots_created,
            'has_bookings': has_bookings
        }
    
    async def _process_date_without_slots(
        self,
        instructor_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """Process a date that has no new slots (clearing)."""
        dates_created = 0
        has_bookings = False
        
        # Check for existing bookings
        existing_bookings = self._count_bookings_for_date(instructor_id, target_date)
        
        if existing_bookings > 0:
            has_bookings = True
            self.logger.warning(
                f"Cannot clear {target_date} - has {existing_bookings} bookings"
            )
        else:
            # Safe to delete
            deleted = self.db.query(InstructorAvailability).filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date
            ).delete(synchronize_session=False)
            
            # Create cleared entry if something was deleted
            if deleted > 0 and target_date != date.today():
                availability_entry = InstructorAvailability(
                    instructor_id=instructor_id,
                    date=target_date,
                    is_cleared=True
                )
                self.db.add(availability_entry)
                dates_created = 1
        
        return {
            'dates_created': dates_created,
            'has_bookings': has_bookings
        }
    
    def _get_booked_slots(self, availability_id: int) -> List[AvailabilitySlot]:
        """Get slots that have bookings."""
        return (
            self.db.query(AvailabilitySlot)
            .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
            .filter(
                AvailabilitySlot.availability_id == availability_id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            )
            .all()
        )
    
    def _delete_non_booked_slots(
        self, 
        availability_id: int, 
        booked_slots: List[AvailabilitySlot]
    ) -> int:
        """Delete slots that don't have bookings."""
        booked_slot_ids = [slot.id for slot in booked_slots]
        
        query = self.db.query(AvailabilitySlot).filter(
            AvailabilitySlot.availability_id == availability_id
        )
        
        if booked_slot_ids:
            query = query.filter(~AvailabilitySlot.id.in_(booked_slot_ids))
        
        return query.delete(synchronize_session=False)
    
    def _conflicts_with_bookings(
        self,
        start_time: time,
        end_time: time,
        booked_ranges: List[Tuple[time, time]]
    ) -> bool:
        """Check if a time range conflicts with booked slots."""
        for booked_start, booked_end in booked_ranges:
            if start_time < booked_end and end_time > booked_start:
                return True
        return False
    
    def _slot_exists(
        self,
        availability_id: int,
        start_time: time,
        end_time: time
    ) -> bool:
        """Check if an exact slot already exists."""
        return self.db.query(AvailabilitySlot).filter(
            AvailabilitySlot.availability_id == availability_id,
            AvailabilitySlot.start_time == start_time,
            AvailabilitySlot.end_time == end_time
        ).first() is not None
    
    def _count_bookings_for_date(
        self,
        instructor_id: int,
        target_date: date
    ) -> int:
        """Count bookings for a specific date."""
        return (
            self.db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            )
            .count()
        )
    
    def _check_duplicate_slot(
        self,
        availability: InstructorAvailability,
        start_time: time,
        end_time: time
    ) -> bool:
        """Check if a slot already exists."""
        return self.db.query(AvailabilitySlot).filter(
            AvailabilitySlot.availability_id == availability.id,
            AvailabilitySlot.start_time == start_time,
            AvailabilitySlot.end_time == end_time
        ).first() is not None
    
    def _invalidate_availability_caches(
        self,
        instructor_id: int,
        dates: List[date]
    ) -> None:
        """Invalidate caches for affected dates."""
        # Invalidate instructor-specific caches
        self.invalidate_cache(f"instructor_availability:{instructor_id}")
        
        # Invalidate date-specific caches
        for target_date in dates:
            self.invalidate_cache(
                f"instructor_availability:{instructor_id}:{target_date}"
            )
        
        # Invalidate week caches
        weeks = set()
        for target_date in dates:
            monday = target_date - timedelta(days=target_date.weekday())
            weeks.add(monday)
        
        for week_start in weeks:
            self.invalidate_cache(
                f"week_availability:{instructor_id}:{week_start}"
            )