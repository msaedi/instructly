# backend/app/services/week_operation_service.py
"""
Week Operation Service for InstaInstru Platform

Handles week-based availability operations including:
- Copying availability between weeks
- Applying patterns to date ranges
- Week calculations and pattern extraction
- Bulk week operations
"""

import logging
from datetime import date, timedelta, time
from typing import List, Dict, Optional, Callable, Any, TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from ..models.availability import InstructorAvailability, AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from .base import BaseService
from ..core.constants import DAYS_OF_WEEK
from ..utils.time_helpers import time_to_string, string_to_time

if TYPE_CHECKING:
    from .availability_service import AvailabilityService
    from .conflict_checker import ConflictChecker
    from .cache_service import CacheService

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
        cache_service: Optional['CacheService'] = None
    ):
        """Initialize week operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        
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
        self,
        instructor_id: int,
        from_week_start: date,
        to_week_start: date
    ) -> Dict[str, Any]:
        """
        Copy availability from one week to another while preserving bookings.
        
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
            to_week=to_week_start
        )
        
        # Validate dates are Mondays
        if from_week_start.weekday() != 0:
            self.logger.warning(f"Source week start {from_week_start} is not a Monday")
        if to_week_start.weekday() != 0:
            self.logger.warning(f"Target week start {to_week_start} is not a Monday")
        
        with self.transaction():
            # Get booking information for target week
            booking_info = self._get_target_week_bookings(instructor_id, to_week_start)
            
            # Delete non-booked slots from target week
            self._clear_non_booked_slots(
                instructor_id, 
                to_week_start,
                booking_info['booked_slot_ids'],
                booking_info['availability_with_bookings']
            )
            
            # Get source week availability
            source_week = self.availability_service.get_week_availability(
                instructor_id, 
                from_week_start
            )
            
            # Copy availability day by day
            copy_result = await self._copy_week_slots(
                instructor_id=instructor_id,
                source_week=source_week,
                from_week_start=from_week_start,
                to_week_start=to_week_start,
                booking_info=booking_info
            )
        
        # Get updated availability
        result = self.availability_service.get_week_availability(
            instructor_id,
            to_week_start
        )
        
        # Add metadata
        if copy_result['dates_with_preserved_bookings'] or copy_result['slots_skipped'] > 0:
            result["_metadata"] = {
                "dates_with_preserved_bookings": copy_result['dates_with_preserved_bookings'],
                "slots_skipped": copy_result['slots_skipped'],
                "message": f"Week copied successfully. {len(copy_result['dates_with_preserved_bookings'])} date(s) had bookings preserved."
            }
        
        return result
    
    async def apply_pattern_to_date_range(
        self,
        instructor_id: int,
        from_week_start: date,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Apply a week's pattern to a date range - OPTIMIZED VERSION.
        
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
            date_range=f"{start_date} to {end_date}"
        )
        
        # Get source week availability
        source_week = self.availability_service.get_week_availability(
            instructor_id,
            from_week_start
        )
        
        # Create pattern from source week
        week_pattern = self._extract_week_pattern(source_week, from_week_start)
        
        # OPTIMIZATION 1: Bulk fetch all data upfront
        # Get ALL existing availability entries in date range
        existing_availability = (
            self.db.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date >= start_date,
                InstructorAvailability.date <= end_date
            )
            .all()
        )
        
        # Create lookup dict for O(1) access
        existing_by_date = {entry.date: entry for entry in existing_availability}
        
        # Get ALL bookings in range at once
        bookings_in_range = self._get_bookings_in_range(
            instructor_id,
            start_date,
            end_date
        )
        
        # OPTIMIZATION 2: Use single transaction
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
            dates_skipped = 0
            slots_created = 0
            slots_skipped = 0
            
            while current_date <= end_date:
                day_name = DAYS_OF_WEEK[current_date.weekday()]
                current_date_str = current_date.isoformat()
                
                # Check if date has bookings
                date_has_bookings = current_date_str in bookings_in_range['bookings_by_date']
                booked_slots = bookings_in_range['bookings_by_date'].get(current_date_str, [])
                
                # Get existing availability for this date
                existing = existing_by_date.get(current_date)
                
                if day_name in week_pattern and week_pattern[day_name]:
                    # Process pattern for this day
                    if existing:
                        # Mark for update
                        existing.is_cleared = False
                        availability_to_update.append(existing)
                        availability_id = existing.id
                        dates_modified += 1
                        
                        # Mark non-booked slots for deletion
                        if date_has_bookings:
                            booked_ids = [s['slot_id'] for s in booked_slots]
                            for slot in existing.time_slots:
                                if slot.id not in booked_ids:
                                    slots_to_delete.append(slot.id)
                        else:
                            # No bookings - delete all slots
                            slots_to_delete.extend([s.id for s in existing.time_slots])
                    else:
                        # Create new availability entry
                        new_entry = InstructorAvailability(
                            instructor_id=instructor_id,
                            date=current_date,
                            is_cleared=False
                        )
                        new_availability_entries.append(new_entry)
                        dates_created += 1
                    
                    # Prepare new slots
                    for pattern_slot in week_pattern[day_name]:
                        slot_start = string_to_time(pattern_slot['start_time'])
                        slot_end = string_to_time(pattern_slot['end_time'])
                        
                        # Check conflicts with bookings
                        conflicts = False
                        for booked_slot in booked_slots:
                            if (slot_start < booked_slot['end_time'] and 
                                slot_end > booked_slot['start_time']):
                                conflicts = True
                                slots_skipped += 1
                                break
                        
                        if not conflicts:
                            new_slots.append({
                                'date': current_date,
                                'start_time': slot_start,
                                'end_time': slot_end,
                                'existing_availability': existing
                            })
                            slots_created += 1
                else:
                    # No pattern for this day
                    if date_has_bookings:
                        dates_skipped += 1
                    elif existing and not existing.is_cleared:
                        # Clear the day
                        existing.is_cleared = True
                        availability_to_update.append(existing)
                        slots_to_delete.extend([s.id for s in existing.time_slots])
                        dates_modified += 1
                
                current_date += timedelta(days=1)
            
            # OPTIMIZATION 3: Bulk operations
            # Bulk insert new availability entries
            if new_availability_entries:
                self.db.bulk_save_objects(new_availability_entries, return_defaults=True)
                self.db.flush()  # Get IDs for new entries
            
            # Bulk delete slots
            if slots_to_delete:
                self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.id.in_(slots_to_delete)
                ).delete(synchronize_session=False)
            
            # Bulk insert new slots
            if new_slots:
                # Create AvailabilitySlot objects with proper availability_id
                slot_objects = []
                for slot_data in new_slots:
                    if slot_data['existing_availability']:
                        availability_id = slot_data['existing_availability'].id
                    else:
                        # Find the newly created entry for this date
                        for new_entry in new_availability_entries:
                            if new_entry.date == slot_data['date']:
                                availability_id = new_entry.id
                                break
                    
                    slot_objects.append(AvailabilitySlot(
                        availability_id=availability_id,
                        start_time=slot_data['start_time'],
                        end_time=slot_data['end_time']
                    ))
                
                self.db.bulk_save_objects(slot_objects)
            
            # Update modified availability entries
            if availability_to_update:
                self.db.bulk_update_mappings(
                    InstructorAvailability,
                    [{'id': a.id, 'is_cleared': a.is_cleared} for a in availability_to_update]
                )
        
        message = f"Successfully applied schedule to {dates_created + dates_modified} days"
        if dates_skipped > 0 or slots_skipped > 0:
            message += f" ({dates_skipped} days preserved, {slots_skipped} slots skipped due to bookings)"
        
        # Just log without timing for now
        self.logger.info(
            f"Optimized apply_pattern completed: {dates_created} created, "
            f"{dates_modified} modified, {slots_created} slots"
        )
        
        if self.cache_service and (dates_created > 0 or dates_modified > 0):
            # Calculate all affected dates
            affected_dates = []
            current = start_date
            while current <= end_date:
                affected_dates.append(current)
                current += timedelta(days=1)
            
            # Invalidate cache for all affected dates
            self.cache_service.invalidate_instructor_availability(
                instructor_id,
                affected_dates
            )
            self.logger.info(f"Invalidated cache for {len(affected_dates)} dates after apply_pattern")

        return {
            "message": message,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            'dates_created': dates_created,
            'dates_modified': dates_modified,
            'dates_skipped': dates_skipped,
            'slots_created': slots_created,
            'slots_skipped': slots_skipped,
            'total_bookings_preserved': bookings_in_range['total_bookings']
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
    
    def get_week_pattern(
        self,
        instructor_id: int,
        week_start: date
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract the availability pattern for a week.
        
        Args:
            instructor_id: The instructor ID
            week_start: Monday of the week
            
        Returns:
            Pattern indexed by day name (Monday, Tuesday, etc.)
        """
        week_availability = self.availability_service.get_week_availability(
            instructor_id,
            week_start
        )
        
        return self._extract_week_pattern(week_availability, week_start)
    
    # Private helper methods
    
    def _get_target_week_bookings(
        self,
        instructor_id: int,
        week_start: date
    ) -> Dict[str, Any]:
        """Get booking information for target week."""
        target_week_dates = self.calculate_week_dates(week_start)
        
        bookings = (
            self.db.query(
                Booking.booking_date,
                AvailabilitySlot.id.label("slot_id"),
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
                InstructorAvailability.id.label("availability_id")
            )
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                Booking.booking_date.in_(target_week_dates),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            )
            .all()
        )
        
        # Process booking information
        booked_slot_ids = set()
        booked_availability_ids = set()
        booked_time_ranges_by_date = {}
        
        for booking in bookings:
            booked_slot_ids.add(booking.slot_id)
            booked_availability_ids.add(booking.availability_id)
            
            date_str = booking.booking_date.isoformat()
            if date_str not in booked_time_ranges_by_date:
                booked_time_ranges_by_date[date_str] = []
            booked_time_ranges_by_date[date_str].append({
                'start_time': booking.start_time,
                'end_time': booking.end_time
            })
        
        self.logger.info(f"Found {len(bookings)} booked slots in target week")
        
        return {
            'booked_slot_ids': booked_slot_ids,
            'availability_with_bookings': booked_availability_ids,
            'booked_time_ranges_by_date': booked_time_ranges_by_date,
            'total_bookings': len(bookings)
        }
    
    def _clear_non_booked_slots(
        self,
        instructor_id: int,
        week_start: date,
        booked_slot_ids: set,
        availability_with_bookings: set
    ) -> None:
        """Clear non-booked slots from target week."""
        target_week_dates = self.calculate_week_dates(week_start)
        
        if booked_slot_ids:
            # Delete slots that are NOT booked
            deleted_slots = self.db.query(AvailabilitySlot).filter(
                AvailabilitySlot.availability_id.in_(
                    self.db.query(InstructorAvailability.id).filter(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date.in_(target_week_dates)
                    )
                ),
                ~AvailabilitySlot.id.in_(booked_slot_ids)
            ).delete(synchronize_session=False)
            
            # Delete availability entries with no remaining slots
            remaining_availability_ids = self.db.query(
                AvailabilitySlot.availability_id
            ).filter(
                AvailabilitySlot.availability_id.in_(
                    self.db.query(InstructorAvailability.id).filter(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date.in_(target_week_dates)
                    )
                )
            ).distinct().all()
            
            remaining_ids = [r[0] for r in remaining_availability_ids]
            
            deleted_availabilities = self.db.query(InstructorAvailability).filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date.in_(target_week_dates),
                ~InstructorAvailability.id.in_(remaining_ids)
            ).delete(synchronize_session=False)
            
            self.logger.debug(
                f"Deleted {deleted_slots} non-booked slots and "
                f"{deleted_availabilities} empty availability entries"
            )
        else:
            # No bookings - safe to delete all
            deleted = self.db.query(InstructorAvailability).filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date.in_(target_week_dates)
            ).delete(synchronize_session=False)
            self.logger.debug(f"Deleted {deleted} entries (no bookings)")
    
    async def _copy_week_slots(
        self,
        instructor_id: int,
        source_week: Dict[str, List[Dict]],
        from_week_start: date,
        to_week_start: date,
        booking_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Copy slots from source to target week."""
        dates_created = 0
        slots_created = 0
        slots_skipped = 0
        dates_with_preserved_bookings = []
        
        for i in range(7):
            source_date = from_week_start + timedelta(days=i)
            target_date = to_week_start + timedelta(days=i)
            source_date.isoformat()
            target_date_str = target_date.isoformat()
            
            # Check if target date has bookings
            has_bookings = target_date_str in booking_info['booked_time_ranges_by_date']
            
            # Get ALL slots from source date (including booked ones)
            source_slots = await self._get_all_slots_for_date(instructor_id, source_date)
            
            if source_slots:
                # Copy ALL slots (booked become available)
                result = await self._copy_day_slots(
                    instructor_id=instructor_id,
                    source_slots=source_slots,
                    target_date=target_date,
                    has_bookings=has_bookings,
                    booked_ranges=booking_info['booked_time_ranges_by_date'].get(
                        target_date_str, []
                    )
                )
                
                dates_created += result['dates_created']
                slots_created += result['slots_created']
                slots_skipped += result['slots_skipped']
                
                if has_bookings:
                    dates_with_preserved_bookings.append(target_date_str)
            else:
                # Source day has no slots
                if has_bookings:
                    # Preserve booked slots
                    self.logger.info(
                        f"Preserving booked slots on {target_date} "
                        "(source day was empty)"
                    )
                    dates_with_preserved_bookings.append(target_date_str)
                else:
                    # Create cleared entry
                    availability_entry = InstructorAvailability(
                        instructor_id=instructor_id,
                        date=target_date,
                        is_cleared=True
                    )
                    self.db.add(availability_entry)
                    dates_created += 1
        
        self.logger.info(
            f"Week copy complete: {dates_created} dates, "
            f"{slots_created} slots, {slots_skipped} slots skipped"
        )
        
        return {
            'dates_created': dates_created,
            'slots_created': slots_created,
            'slots_skipped': slots_skipped,
            'dates_with_preserved_bookings': dates_with_preserved_bookings
        }
    
    async def _copy_day_slots(
        self,
        instructor_id: int,
        source_slots: List[Dict],
        target_date: date,
        has_bookings: bool,
        booked_ranges: List[Dict]
    ) -> Dict[str, Any]:
        """Copy slots for a single day."""
        dates_created = 0
        slots_created = 0
        slots_skipped = 0
        
        # Get or create availability entry
        existing_availability = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date == target_date
        ).first()
        
        if existing_availability:
            availability_entry = existing_availability
            availability_entry.is_cleared = False
        else:
            availability_entry = InstructorAvailability(
                instructor_id=instructor_id,
                date=target_date,
                is_cleared=False
            )
            self.db.add(availability_entry)
            self.db.flush()
            dates_created = 1
        
        # Copy slots that don't conflict
        for slot in source_slots:
            slot_start = string_to_time(slot['start_time'])
            slot_end = string_to_time(slot['end_time'])
            
            # Check conflicts
            conflicts = False
            if has_bookings:
                for booked_range in booked_ranges:
                    if (slot_start < booked_range['end_time'] and 
                        slot_end > booked_range['start_time']):
                        conflicts = True
                        slots_skipped += 1
                        self.logger.debug(
                            f"Skipping slot {slot['start_time']}-{slot['end_time']} "
                            f"on {target_date} due to booking conflict"
                        )
                        break
            
            if not conflicts:
                # Check if slot already exists
                existing_slot = self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.availability_id == availability_entry.id,
                    AvailabilitySlot.start_time == slot_start,
                    AvailabilitySlot.end_time == slot_end
                ).first()
                
                if not existing_slot:
                    time_slot = AvailabilitySlot(
                        availability_id=availability_entry.id,
                        start_time=slot_start,
                        end_time=slot_end
                    )
                    self.db.add(time_slot)
                    slots_created += 1
        
        return {
            'dates_created': dates_created,
            'slots_created': slots_created,
            'slots_skipped': slots_skipped
        }
    
    def _extract_week_pattern(
        self,
        week_availability: Dict[str, List[Dict]],
        week_start: date
    ) -> Dict[str, List[Dict]]:
        """Extract a reusable pattern from week availability."""
        pattern = {}
        
        for i in range(7):
            source_date = week_start + timedelta(days=i)
            source_date_str = source_date.isoformat()
            day_name = DAYS_OF_WEEK[i]
            
            if source_date_str in week_availability:
                pattern[day_name] = week_availability[source_date_str]
        
        self.logger.debug(
            f"Extracted pattern with availability for days: {list(pattern.keys())}"
        )
        
        return pattern
    
    def _get_bookings_in_range(
        self,
        instructor_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Get all bookings in a date range."""
        bookings = (
            self.db.query(
                Booking.booking_date,
                AvailabilitySlot.id.label("slot_id"),
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
                InstructorAvailability.id.label("availability_id")
            )
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            )
            .all()
        )
        
        # Organize booking information
        bookings_by_date = {}
        booked_slot_ids = set()
        
        for booking in bookings:
            date_str = booking.booking_date.isoformat()
            if date_str not in bookings_by_date:
                bookings_by_date[date_str] = []
            
            bookings_by_date[date_str].append({
                'slot_id': booking.slot_id,
                'start_time': booking.start_time,
                'end_time': booking.end_time
            })
            booked_slot_ids.add(booking.slot_id)
        
        self.logger.info(
            f"Found {len(bookings)} bookings across {len(bookings_by_date)} dates"
        )
        
        return {
            'bookings_by_date': bookings_by_date,
            'booked_slot_ids': booked_slot_ids,
            'total_bookings': len(bookings)
        }
    
    async def _apply_pattern_to_range(
        self,
        instructor_id: int,
        week_pattern: Dict[str, List[Dict]],
        start_date: date,
        end_date: date,
        bookings_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply a weekly pattern to a date range."""
        dates_created = 0
        dates_modified = 0
        dates_skipped = 0
        slots_created = 0
        slots_skipped = 0
        
        current_date = start_date
        
        while current_date <= end_date:
            self.logger.info(f"Processing date: {current_date}")
            day_name = DAYS_OF_WEEK[current_date.weekday()]
            current_date_str = current_date.isoformat()
            
            # Check if date has bookings
            date_has_bookings = current_date_str in bookings_info['bookings_by_date']
            
            if day_name in week_pattern and week_pattern[day_name]:
                # Apply pattern for this day
                result = await self._apply_pattern_to_date(
                    instructor_id=instructor_id,
                    target_date=current_date,
                    pattern_slots=week_pattern[day_name],
                    has_bookings=date_has_bookings,
                    booked_slots=bookings_info['bookings_by_date'].get(
                        current_date_str, []
                    )
                )
                
                dates_created += result['dates_created']
                dates_modified += result['dates_modified']
                slots_created += result['slots_created']
                slots_skipped += result['slots_skipped']
                
                if result.get('skipped'):
                    dates_skipped += 1
            else:
                # Pattern has no slots for this day
                if date_has_bookings:
                    # Preserve existing availability
                    dates_skipped += 1
                else:
                    # Clear or create cleared entry
                    result = self._clear_date_availability(instructor_id, current_date)
                    dates_created += result['dates_created']
                    dates_modified += result['dates_modified']
            current_date += timedelta(days=1)
        
        return {
            'dates_created': dates_created,
            'dates_modified': dates_modified,
            'dates_skipped': dates_skipped,
            'slots_created': slots_created,
            'slots_skipped': slots_skipped,
            'total_bookings_preserved': bookings_info['total_bookings']
        }
            
    async def _get_all_slots_for_date(
        self,
        instructor_id: int,
        target_date: date
    ) -> List[Dict[str, Any]]:
        """Get ALL slots for a date (including booked ones)."""
        slots = (
            self.db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date
            )
            .all()
        )
        
        # Convert to dict format
        return [
            {
                'start_time': slot.start_time.isoformat(),
                'end_time': slot.end_time.isoformat(),
                'is_booked': slot.booking_id is not None
            }
            for slot in slots
        ]
    
    async def _apply_pattern_to_date(
        self,
        instructor_id: int,
        target_date: date,
        pattern_slots: List[Dict],
        has_bookings: bool,
        booked_slots: List[Dict]
    ) -> Dict[str, Any]:
        """Apply pattern to a single date."""
        dates_created = 0
        dates_modified = 0
        slots_created = 0
        slots_skipped = 0
        skipped = False
        
        # Get existing availability
        existing = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date == target_date
        ).first()
        
        if existing:
            # Update existing
            availability_entry = existing
            availability_entry.is_cleared = False
            
            # Delete non-booked slots
            if has_bookings:
                booked_ids = [s['slot_id'] for s in booked_slots]
                deleted = self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.availability_id == availability_entry.id,
                    ~AvailabilitySlot.id.in_(booked_ids)
                ).delete(synchronize_session=False)
            else:
                # No bookings - delete all
                deleted = self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.availability_id == availability_entry.id
                ).delete(synchronize_session=False)
            
            dates_modified = 1
        else:
            # Create new
            availability_entry = InstructorAvailability(
                instructor_id=instructor_id,
                date=target_date,
                is_cleared=False
            )
            self.db.add(availability_entry)
            self.db.flush()
            dates_created = 1
        
        # Add pattern slots
        for pattern_slot in pattern_slots:
            slot_start = string_to_time(pattern_slot['start_time'])
            slot_end = string_to_time(pattern_slot['end_time'])
            
            # Check conflicts
            conflicts = False
            if has_bookings:
                for booked_slot in booked_slots:
                    if (slot_start < booked_slot['end_time'] and 
                        slot_end > booked_slot['start_time']):
                        conflicts = True
                        slots_skipped += 1
                        break
            
            if not conflicts:
                # Check if slot exists
                existing_slot = self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.availability_id == availability_entry.id,
                    AvailabilitySlot.start_time == slot_start,
                    AvailabilitySlot.end_time == slot_end
                ).first()
                
                if not existing_slot:
                    time_slot = AvailabilitySlot(
                        availability_id=availability_entry.id,
                        start_time=slot_start,
                        end_time=slot_end
                    )
                    self.db.add(time_slot)
                    slots_created += 1
        
        return {
            'dates_created': dates_created,
            'dates_modified': dates_modified,
            'slots_created': slots_created,
            'slots_skipped': slots_skipped,
            'skipped': skipped
        }
    
    def _clear_date_availability(
        self,
        instructor_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """Clear availability for a date."""
        dates_created = 0
        dates_modified = 0
        
        existing = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date == target_date
        ).first()
        
        if existing:
            if not existing.is_cleared:
                # Delete all slots
                self.db.query(AvailabilitySlot).filter(
                    AvailabilitySlot.availability_id == existing.id
                ).delete(synchronize_session=False)
                
                existing.is_cleared = True
                dates_modified = 1
        else:
            # Create cleared entry
            availability_entry = InstructorAvailability(
                instructor_id=instructor_id,
                date=target_date,
                is_cleared=True
            )
            self.db.add(availability_entry)
            dates_created = 1
        
        return {
            'dates_created': dates_created,
            'dates_modified': dates_modified
        }
    
    # Add these methods to the end of WeekOperationService class:

    def _bulk_create_slots(self, slots_data: List[Dict[str, Any]]) -> int:
        """
        Efficiently bulk create slots using batch operations for maximum performance.
        
        Args:
            slots_data: List of slot dictionaries with availability_id, start_time, end_time
            
        Returns:
            Number of slots created
        """
        if not slots_data:
            return 0
        
        # Prepare data for bulk insert
        values = []
        for slot in slots_data:
            values.append({
                'availability_id': slot['availability_id'],
                'start_time': slot['start_time'],
                'end_time': slot['end_time']
            })
        
        # Use bulk_insert_mappings for best performance
        self.db.bulk_insert_mappings(AvailabilitySlot, values)
        
        return len(values)
    
    def get_cached_week_pattern(
        self,
        instructor_id: int,
        week_start: date,
        cache_ttl: int = 3600
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
        start_time = time.time()
        
        cache_key = f"week_pattern:{instructor_id}:{week_start.isoformat()}"
        
        # Try cache first
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                self.logger.debug(f"Week pattern cache hit for {week_start}")
                # Record metric
                elapsed = time.time() - start_time
                self._record_metric("pattern_extraction", elapsed, success=True)
                return cached
        
        # Get fresh data
        week_availability = self.availability_service.get_week_availability(
            instructor_id,
            week_start
        )
        pattern = self._extract_week_pattern(week_availability, week_start)
        
        # Cache the result
        if self.cache:
            self.cache.set(cache_key, pattern, ttl=cache_ttl)
        
        # Record metric
        elapsed = time.time() - start_time
        self._record_metric("pattern_extraction", elapsed, success=True)
        
        return pattern
    
    def add_performance_logging(self) -> None:
        """Add detailed performance logging to track slow operations."""
        # This is automatically handled by @measure_performance decorator
        # but we can add custom metrics here
        metrics = self.get_metrics()
        
        for operation, data in metrics.items():
            if data['avg_time'] > 1.0:  # Operations taking > 1 second
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
        progress_callback: Optional[Callable[[int, int], None]] = None
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
            result = await self.apply_pattern_to_date_range(
                instructor_id,
                from_week_start,
                start_date,
                end_date
            )
            return result
        finally:
            # Restore original method
            self._apply_pattern_to_date = original_method