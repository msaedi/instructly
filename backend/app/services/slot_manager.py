# backend/app/services/slot_manager.py
"""
Slot Manager Service for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

Manages time slot operations including:
- Creating, updating, and deleting slots
- Merging overlapping slots
- Slot validation and optimization
- Time slot calculations

All methods now use instructor_id + date instead of availability_id.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import ConflictException, NotFoundException, ValidationException
from ..models.availability import AvailabilitySlot
from ..repositories import RepositoryFactory
from ..repositories.slot_manager_repository import SlotManagerRepository
from .base import BaseService
from .conflict_checker import ConflictChecker

logger = logging.getLogger(__name__)


class SlotManager(BaseService):
    """
    Service for managing availability time slots.

    Handles all slot-level operations and ensures data integrity
    when manipulating time slots.
    """

    def __init__(
        self,
        db: Session,
        conflict_checker: Optional[ConflictChecker] = None,
        repository: Optional[SlotManagerRepository] = None,
    ):
        """Initialize slot manager service."""
        super().__init__(db)
        self.logger = logging.getLogger(__name__)
        self.conflict_checker = conflict_checker or ConflictChecker(db)
        # Add repository - either use provided or create new
        self.repository = repository or RepositoryFactory.create_slot_manager_repository(db)

    def create_slot(
        self,
        instructor_id: int,
        target_date: date,
        start_time: time,
        end_time: time,
        validate_conflicts: bool = True,  # DEPRECATED - kept for backward compatibility
        auto_merge: bool = True,
    ) -> AvailabilitySlot:
        """
        Create a new availability slot.

        UPDATED: Now uses instructor_id and date instead of availability_id.
        No longer checks for booking conflicts (layer independence).

        Args:
            instructor_id: The instructor ID
            target_date: The date for the slot
            start_time: Start time of the slot
            end_time: End time of the slot
            validate_conflicts: DEPRECATED - ignored for layer independence
            auto_merge: Whether to merge with adjacent slots

        Returns:
            Created availability slot

        Raises:
            ValidationException: If validation fails
        """
        # Validate time alignment (15-minute blocks)
        self._validate_time_alignment(start_time)
        self._validate_time_alignment(end_time)

        # Validate time range
        validation = self.conflict_checker.validate_time_range(start_time, end_time)
        if not validation["valid"]:
            raise ValidationException(validation["reason"])

        # Check for duplicate slot
        if self.repository.slot_exists(instructor_id, target_date, start_time, end_time):
            raise ConflictException("This exact time slot already exists")

        # Create the slot
        new_slot = self.repository.create(
            instructor_id=instructor_id, date=target_date, start_time=start_time, end_time=end_time
        )

        # Always merge if requested - don't check for bookings
        if auto_merge:
            self.merge_overlapping_slots(instructor_id, target_date)

        self.db.commit()

        # After merging, the new_slot might have been deleted
        # Try to get the slot by ID first
        final_slot = self.repository.get_slot_by_id(new_slot.id)

        if not final_slot:
            # The slot was merged into another slot
            # Find the slot that now contains our time range
            slots = self.repository.get_slots_for_date_ordered(instructor_id, target_date)
            for slot in slots:
                # Check if this slot contains our original time range
                if slot.start_time <= start_time and slot.end_time >= end_time:
                    final_slot = slot
                    break

        if final_slot:
            self.db.refresh(final_slot)
            self.logger.info(
                f"Created slot {new_slot.id} for instructor {instructor_id} on {target_date}: "
                f"{start_time}-{end_time}"
            )
            return final_slot
        else:
            # This shouldn't happen, but return the original slot info
            self.logger.info(
                f"Created slot {new_slot.id} for instructor {instructor_id} on {target_date}: "
                f"{start_time}-{end_time}"
            )
            return new_slot

    def update_slot(
        self,
        slot_id: int,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
        validate_conflicts: bool = True,  # DEPRECATED - kept for backward compatibility
    ) -> AvailabilitySlot:
        """
        Update an existing slot's times.

        No longer checks for booking conflicts (layer independence).

        Args:
            slot_id: The slot ID to update
            start_time: New start time (optional)
            end_time: New end time (optional)
            validate_conflicts: DEPRECATED - ignored for layer independence

        Returns:
            Updated slot

        Raises:
            NotFoundException: If slot not found
            ValidationException: If new times invalid
        """
        # Get the slot
        slot = self.repository.get_slot_by_id(slot_id)

        if not slot:
            raise NotFoundException("Slot not found")

        # Determine new times
        new_start = start_time if start_time is not None else slot.start_time
        new_end = end_time if end_time is not None else slot.end_time

        # Validate new time range
        validation = self.conflict_checker.validate_time_range(new_start, new_end)
        if not validation["valid"]:
            raise ValidationException(validation["reason"])

        # Update the slot
        updated_slot = self.repository.update(slot_id, start_time=new_start, end_time=new_end)

        self.db.commit()
        self.logger.info(f"Updated slot {slot_id}: {new_start}-{new_end}")

        return updated_slot

    def delete_slot(self, slot_id: int, force: bool = False) -> bool:
        """
        Delete an availability slot.

        UPDATED: Always allows deletion regardless of bookings.
        Removed is_cleared logic since InstructorAvailability no longer exists.

        Args:
            slot_id: The slot ID to delete
            force: DEPRECATED - all deletions allowed for layer independence

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If slot not found
        """
        # Get the slot
        slot = self.repository.get_slot_by_id(slot_id)

        if not slot:
            raise NotFoundException("Slot not found")

        # Delete the slot
        self.repository.delete(slot_id)
        self.db.commit()

        self.logger.info(f"Deleted slot {slot_id}")
        return True

    def merge_overlapping_slots(self, instructor_id: int, target_date: date, preserve_booked: bool = True) -> int:
        """
        Merge overlapping or adjacent slots for a specific date.

        UPDATED: Now uses instructor_id and date instead of availability_id.
        Always merges overlapping slots regardless of bookings.

        Args:
            instructor_id: The instructor ID
            target_date: The date to merge slots on
            preserve_booked: DEPRECATED - ignored for layer independence

        Returns:
            Number of slots merged
        """
        # Get all slots ordered by start time
        slots = self.repository.get_slots_for_date_ordered(instructor_id, target_date)

        if len(slots) <= 1:
            return 0

        self.logger.debug(
            f"Merging slots for instructor {instructor_id} on {target_date}: " f"{len(slots)} slots found"
        )

        # Merge slots
        merged_count = 0
        merged_slots = []
        current = slots[0]

        for next_slot in slots[1:]:
            # Check if slots overlap or are adjacent (within 1 minute)
            if self._slots_can_merge(current, next_slot):
                self.logger.debug(
                    f"Merging slots: {current.start_time}-{current.end_time} "
                    f"with {next_slot.start_time}-{next_slot.end_time}"
                )

                # Extend current slot
                if next_slot.end_time > current.end_time:
                    current.end_time = next_slot.end_time

                # Delete the merged slot
                self.repository.delete(next_slot.id)
                merged_count += 1
            else:
                # Slots are not adjacent
                merged_slots.append(current)
                current = next_slot

        merged_slots.append(current)

        if merged_count > 0:
            self.db.commit()
            self.logger.info(
                f"Merge complete: {len(slots)} slots -> " f"{len(merged_slots)} slots ({merged_count} merged)"
            )

        return merged_count

    def split_slot(self, slot_id: int, split_time: time) -> Tuple[AvailabilitySlot, AvailabilitySlot]:
        """
        Split a slot into two at the specified time.

        Allows splitting regardless of bookings.

        Args:
            slot_id: The slot ID to split
            split_time: Time to split at

        Returns:
            Tuple of (first_slot, second_slot)

        Raises:
            NotFoundException: If slot not found
            ValidationException: If split time invalid
        """
        # Get the slot
        slot = self.repository.get_slot_by_id(slot_id)

        if not slot:
            raise NotFoundException("Slot not found")

        # Validate split time
        if split_time <= slot.start_time or split_time >= slot.end_time:
            raise ValidationException("Split time must be between slot start and end times")

        # Create second slot
        second_slot = self.repository.create(
            instructor_id=slot.instructor_id,
            date=slot.date,
            start_time=split_time,
            end_time=slot.end_time,
        )

        # Update first slot
        slot.end_time = split_time

        self.db.commit()
        self.db.refresh(slot)
        self.db.refresh(second_slot)

        self.logger.info(
            f"Split slot {slot_id} at {split_time} into "
            f"{slot.start_time}-{slot.end_time} and "
            f"{second_slot.start_time}-{second_slot.end_time}"
        )

        return (slot, second_slot)

    def find_gaps_in_availability(
        self, instructor_id: int, target_date: date, min_gap_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Find gaps in availability that could be filled.

        UPDATED: Method signature already uses instructor_id and date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            min_gap_minutes: Minimum gap size to report

        Returns:
            List of gaps with start/end times
        """
        # Get all slots for the date
        slots = self.repository.get_slots_for_instructor_date(instructor_id, target_date)

        if not slots:
            return []

        gaps = []

        # Check gaps between consecutive slots
        for i in range(len(slots) - 1):
            current_slot = slots[i]
            next_slot = slots[i + 1]

            # Calculate gap
            gap_start = current_slot.end_time
            gap_end = next_slot.start_time

            # Calculate gap duration
            start_dt = datetime.combine(date.today(), gap_start)
            end_dt = datetime.combine(date.today(), gap_end)
            gap_minutes = int((end_dt - start_dt).total_seconds() / 60)

            if gap_minutes >= min_gap_minutes:
                gaps.append(
                    {
                        "start_time": gap_start.isoformat(),
                        "end_time": gap_end.isoformat(),
                        "duration_minutes": gap_minutes,
                        "after_slot_id": current_slot.id,
                        "before_slot_id": next_slot.id,
                    }
                )

        return gaps

    def optimize_availability(
        self, instructor_id: int, target_date: date, target_duration_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Suggest optimal slot arrangements for a given duration.

        UPDATED: Now uses instructor_id and date instead of availability_id.

        This method finds FREE time slots that can accommodate bookings of the
        specified duration. It MUST check existing bookings to avoid suggesting
        already-booked times.

        NOTE: This is NOT an availability CRUD operation. This is a booking
        helper that needs to respect existing bookings.

        Args:
            instructor_id: The instructor ID
            target_date: The date to optimize
            target_duration_minutes: Desired booking duration

        Returns:
            List of suggested time slots that are FREE for booking
        """
        # Get all slots with their booking status
        slots_with_status = self.repository.get_slots_with_booking_status_for_date(instructor_id, target_date)

        # Filter out booked slots - we only want to suggest FREE times
        non_booked_slots = [slot for slot, status in slots_with_status if status is None]

        suggestions = []

        for slot in non_booked_slots:
            # Calculate slot duration
            start_dt = datetime.combine(date.today(), slot.start_time)
            end_dt = datetime.combine(date.today(), slot.end_time)
            slot_minutes = int((end_dt - start_dt).total_seconds() / 60)

            # If slot is large enough, suggest divisions
            if slot_minutes >= target_duration_minutes:
                num_divisions = slot_minutes // target_duration_minutes

                for i in range(num_divisions):
                    suggested_start = start_dt + timedelta(minutes=i * target_duration_minutes)
                    suggested_end = suggested_start + timedelta(minutes=target_duration_minutes)

                    suggestions.append(
                        {
                            "start_time": suggested_start.time().isoformat(),
                            "end_time": suggested_end.time().isoformat(),
                            "duration_minutes": target_duration_minutes,
                            "fits_in_slot_id": slot.id,
                        }
                    )

        return suggestions

    # Private helper methods

    def _slots_can_merge(self, slot1: AvailabilitySlot, slot2: AvailabilitySlot, max_gap_minutes: int = 1) -> bool:
        """
        Check if two slots can be merged.

        Only checks time adjacency, not bookings.
        """
        # Calculate gap between slots
        gap_start = slot1.end_time
        gap_end = slot2.start_time

        # If slot2 starts before slot1 ends, they overlap
        if gap_end <= gap_start:
            return True

        # Calculate gap duration
        start_dt = datetime.combine(date.today(), gap_start)
        end_dt = datetime.combine(date.today(), gap_end)
        gap_minutes = int((end_dt - start_dt).total_seconds() / 60)

        # Slots can merge if gap is small enough
        return gap_minutes <= max_gap_minutes

    def _validate_time_alignment(self, time_value: time) -> None:
        """
        Ensure time aligns to 15-minute blocks.

        Args:
            time_value: Time to validate

        Raises:
            ValidationException: If time doesn't align to 15-minute blocks
        """
        if time_value.minute % 15 != 0 or time_value.second != 0:
            raise ValidationException(
                f"Time {time_value} must align to 15-minute blocks " "(e.g., 9:00, 9:15, 9:30, 9:45)"
            )
