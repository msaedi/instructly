# backend/app/services/slot_manager.py
"""
Slot Manager Service for InstaInstru Platform

Manages time slot operations including:
- Creating, updating, and deleting slots
- Merging overlapping slots
- Slot validation
- Time slot calculations

This service is now purely focused on availability slot management.
All booking-related logic has been moved to BookingService.
"""

from datetime import date, datetime, time
import logging
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

    Handles all slot-level CRUD operations and ensures data integrity
    when manipulating time slots. Pure availability management without
    any booking concerns.
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
        self.availability_repository = RepositoryFactory.create_availability_repository(db)

    @BaseService.measure_operation("create_slot")
    def create_slot(
        self,
        instructor_id: str,
        target_date: date,
        start_time: time,
        end_time: time,
        auto_merge: bool = True,
    ) -> AvailabilitySlot:
        """
        Create a new availability slot.

        Pure CRUD operation for creating availability slots.
        No booking validation needed.

        Args:
            instructor_id: The instructor ID
            target_date: The date for the slot
            start_time: Start time of the slot
            end_time: End time of the slot
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
        if self.availability_repository.slot_exists(
            instructor_id, target_date, start_time, end_time
        ):
            raise ConflictException("This exact time slot already exists")

        with self.transaction():
            # Create the slot
            new_slot = self.repository.create(
                instructor_id=instructor_id,
                specific_date=target_date,
                start_time=start_time,
                end_time=end_time,
            )

            # Always merge if requested
            if auto_merge:
                self.merge_overlapping_slots(instructor_id, target_date)

            # After merging, the new_slot might have been deleted
            # Try to get the slot by ID first
            final_slot = self.repository.get_slot_by_id(new_slot.id)

            if not final_slot:
                # The slot was merged into another slot
                # Find the slot that now contains our time range
                slots = self.repository.get_slots_by_date_ordered(instructor_id, target_date)
                for slot in slots:
                    # Check if this slot contains our original time range
                    if slot.start_time <= start_time and slot.end_time >= end_time:
                        final_slot = slot
                        break

            if final_slot:
                # repo-pattern-ignore: Refresh after create to get DB-generated values belongs in service layer
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

    @BaseService.measure_operation("update_slot")
    def update_slot(
        self,
        slot_id: str,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
    ) -> AvailabilitySlot:
        """
        Update an existing slot's times.

        Pure CRUD operation for updating slot times.

        Args:
            slot_id: The slot ID to update
            start_time: New start time (optional)
            end_time: New end time (optional)

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

        with self.transaction():
            # Update the slot
            updated_slot = self.repository.update(slot_id, start_time=new_start, end_time=new_end)
            if updated_slot is None:
                raise NotFoundException("Slot not found")

            self.logger.info(f"Updated slot {slot_id}: {new_start}-{new_end}")

            return updated_slot

    @BaseService.measure_operation("delete_slot")
    def delete_slot(self, slot_id: str) -> bool:
        """
        Delete an availability slot.

        Pure CRUD operation - deletes the slot regardless of bookings.
        Bookings are independent and persist after slot deletion.

        Args:
            slot_id: The slot ID to delete

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If slot not found
        """
        # Get the slot
        slot = self.repository.get_slot_by_id(slot_id)

        if not slot:
            raise NotFoundException("Slot not found")

        with self.transaction():
            # Delete the slot
            self.repository.delete(slot_id)

            self.logger.info(f"Deleted slot {slot_id}")
            return True

    @BaseService.measure_operation("merge_slots")
    def merge_overlapping_slots(self, instructor_id: str, target_date: date) -> int:
        """
        Merge overlapping or adjacent slots for a specific date.

        Pure availability operation - merges slots based on time adjacency only.

        Args:
            instructor_id: The instructor ID
            target_date: The date to merge slots on

        Returns:
            Number of slots merged
        """
        # Get all slots ordered by start time
        slots = self.repository.get_slots_by_date_ordered(instructor_id, target_date)

        if len(slots) <= 1:
            return 0

        self.logger.debug(
            f"Merging slots for instructor {instructor_id} on {target_date}: "
            f"{len(slots)} slots found"
        )

        # Merge slots
        merged_count = 0
        merged_slots: list[AvailabilitySlot] = []
        current = slots[0]

        for next_slot in slots[1:]:
            # Check if slots overlap or are adjacent (within 1 minute)
            if self._slots_can_merge(current, next_slot):
                self.logger.debug(
                    f"Merging slots: {current.start_time}-{current.end_time} "
                    f"with {next_slot.start_time}-{next_slot.end_time}"
                )

                new_end = max(current.end_time, next_slot.end_time)

                # Delete the merged slot first to avoid transient overlaps
                self.repository.delete(next_slot.id)

                # Extend current slot after removal
                if new_end != current.end_time:
                    self.repository.update(current.id, end_time=new_end)
                    current.end_time = new_end

                merged_count += 1
            else:
                # Slots are not adjacent
                merged_slots.append(current)
                current = next_slot

        merged_slots.append(current)

        if merged_count > 0:
            # Note: When called from create_slot, we're already in a transaction
            # The BaseService.transaction() context manager handles nested transactions
            self.logger.info(
                f"Merge complete: {len(slots)} slots -> "
                f"{len(merged_slots)} slots ({merged_count} merged)"
            )

        return merged_count

    @BaseService.measure_operation("split_slot")
    def split_slot(
        self, slot_id: str, split_time: time
    ) -> Tuple[AvailabilitySlot, AvailabilitySlot]:
        """
        Split a slot into two at the specified time.

        Pure availability operation.

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

        original_end = slot.end_time

        with self.transaction():
            # Update first slot using repository
            self.repository.update(slot.id, end_time=split_time)
            # Update the local reference for the return value
            slot.end_time = split_time

            # Create second slot after shortening the original slot
            second_slot = self.repository.create(
                instructor_id=slot.instructor_id,
                specific_date=slot.specific_date,
                start_time=split_time,
                end_time=original_end,
            )

            # Get fresh objects from repository
            self.repository.refresh_slots([slot, second_slot])

            self.logger.info(
                f"Split slot {slot_id} at {split_time} into "
                f"{slot.start_time}-{slot.end_time} and "
                f"{second_slot.start_time}-{second_slot.end_time}"
            )

            return (slot, second_slot)

    @BaseService.measure_operation("find_gaps")
    def find_gaps_in_availability(
        self, instructor_id: str, target_date: date, min_gap_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Find gaps in availability that could be filled.

        Pure availability analysis - identifies time gaps between slots.

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

            # Calculate gap duration using reference date (timezone-agnostic)
            start_dt = datetime.combine(date.today(), gap_start)  # reference calculation only
            end_dt = datetime.combine(date.today(), gap_end)  # reference calculation only
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

    @BaseService.measure_operation("get_slots_for_date")
    def get_slots_for_date(self, instructor_id: str, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all availability slots for an instructor on a date.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of availability slots
        """
        return self.repository.get_slots_for_instructor_date(instructor_id, target_date)

    # Private helper methods

    def _slots_can_merge(
        self, slot1: AvailabilitySlot, slot2: AvailabilitySlot, max_gap_minutes: int = 1
    ) -> bool:
        """
        Check if two slots can be merged.

        Only checks time adjacency.
        """
        # Calculate gap between slots
        gap_start = slot1.end_time
        gap_end = slot2.start_time

        # If slot2 starts before slot1 ends, they overlap
        if gap_end <= gap_start:
            return True

        # Calculate gap duration using reference date (timezone-agnostic)
        start_dt = datetime.combine(date.today(), gap_start)  # reference calculation only
        end_dt = datetime.combine(date.today(), gap_end)  # reference calculation only
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
                f"Time {time_value} must align to 15-minute blocks "
                "(e.g., 9:00, 9:15, 9:30, 9:45)"
            )
