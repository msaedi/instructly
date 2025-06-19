# backend/app/services/slot_manager.py
"""
Slot Manager Service for InstaInstru Platform

Manages time slot operations including:
- Creating, updating, and deleting slots
- Merging overlapping slots
- Slot validation and optimization
- Time slot calculations
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import (
    BusinessRuleException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from .base import BaseService
from .conflict_checker import ConflictChecker

logger = logging.getLogger(__name__)


class SlotManager(BaseService):
    """
    Service for managing availability time slots.

    Handles all slot-level operations and ensures data integrity
    when manipulating time slots.
    """

    def __init__(self, db: Session, conflict_checker: Optional[ConflictChecker] = None):
        """Initialize slot manager service."""
        super().__init__(db)
        self.logger = logging.getLogger(__name__)
        self.conflict_checker = conflict_checker or ConflictChecker(db)

    def create_slot(
        self,
        availability_id: int,
        start_time: time,
        end_time: time,
        validate_conflicts: bool = True,
        auto_merge: bool = True,
    ) -> AvailabilitySlot:
        """
        Create a new availability slot.

        Args:
            availability_id: The instructor availability entry ID
            start_time: Start time of the slot
            end_time: End time of the slot
            validate_conflicts: Whether to check for booking conflicts
            auto_merge: Whether to merge with adjacent slots

        Returns:
            Created availability slot

        Raises:
            ValidationException: If validation fails
            ConflictException: If conflicts detected
        """
        # Get availability entry
        availability = (
            self.db.query(InstructorAvailability)
            .filter(InstructorAvailability.id == availability_id)
            .first()
        )

        if not availability:
            raise NotFoundException("Availability entry not found")

        # Validate time alignment (15-minute blocks)
        self._validate_time_alignment(start_time)
        self._validate_time_alignment(end_time)

        # Validate time range
        validation = self.conflict_checker.validate_time_range(start_time, end_time)
        if not validation["valid"]:
            raise ValidationException(validation["reason"])

        # Check for conflicts if requested
        if validate_conflicts:
            conflicts = self.conflict_checker.check_booking_conflicts(
                instructor_id=availability.instructor_id,
                check_date=availability.date,
                start_time=start_time,
                end_time=end_time,
            )
            if conflicts:
                raise ConflictException(
                    f"Time slot conflicts with {len(conflicts)} existing bookings"
                )

        # Check for duplicate slot
        if self._slot_exists(availability_id, start_time, end_time):
            raise ConflictException("This exact time slot already exists")

        # Create the slot
        new_slot = AvailabilitySlot(
            availability_id=availability_id, start_time=start_time, end_time=end_time
        )

        self.db.add(new_slot)
        self.db.flush()

        # Auto merge if requested and no bookings exist
        if auto_merge and not self._has_bookings_on_date(availability):
            self.merge_overlapping_slots(availability_id)

        self.db.commit()
        self.db.refresh(new_slot)

        self.logger.info(
            f"Created slot {new_slot.id} for availability {availability_id}: "
            f"{start_time}-{end_time}"
        )

        return new_slot

    def update_slot(
        self,
        slot_id: int,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
        validate_conflicts: bool = True,
    ) -> AvailabilitySlot:
        """
        Update an existing slot's times.

        Args:
            slot_id: The slot ID to update
            start_time: New start time (optional)
            end_time: New end time (optional)
            validate_conflicts: Whether to check for conflicts

        Returns:
            Updated slot

        Raises:
            NotFoundException: If slot not found
            BusinessRuleException: If slot has booking
            ConflictException: If new times conflict
        """
        # Get the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.id == slot_id)
            .first()
        )

        if not slot:
            raise NotFoundException("Slot not found")

        # Check if slot has booking
        if slot.booking_id:
            raise BusinessRuleException("Cannot update slot that has a booking")

        # Determine new times
        new_start = start_time if start_time is not None else slot.start_time
        new_end = end_time if end_time is not None else slot.end_time

        # Validate new time range
        validation = self.conflict_checker.validate_time_range(new_start, new_end)
        if not validation["valid"]:
            raise ValidationException(validation["reason"])

        # Check for conflicts if requested
        if validate_conflicts:
            availability = slot.availability
            conflicts = self.conflict_checker.check_booking_conflicts(
                instructor_id=availability.instructor_id,
                check_date=availability.date,
                start_time=new_start,
                end_time=new_end,
                exclude_slot_id=slot_id,
            )
            if conflicts:
                raise ConflictException(
                    f"New time range conflicts with {len(conflicts)} bookings"
                )

        # Update the slot
        slot.start_time = new_start
        slot.end_time = new_end

        self.db.commit()
        self.db.refresh(slot)

        self.logger.info(f"Updated slot {slot_id}: {new_start}-{new_end}")

        return slot

    def delete_slot(self, slot_id: int, force: bool = False) -> bool:
        """
        Delete an availability slot.

        Args:
            slot_id: The slot ID to delete
            force: Force deletion even if booked (dangerous!)

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If slot not found
            BusinessRuleException: If slot has booking and not forced
        """
        # Get the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.id == slot_id)
            .first()
        )

        if not slot:
            raise NotFoundException("Slot not found")

        # Check if slot has booking
        if slot.booking_id and not force:
            booking = (
                self.db.query(Booking).filter(Booking.id == slot.booking_id).first()
            )
            if booking and booking.status in [
                BookingStatus.CONFIRMED,
                BookingStatus.COMPLETED,
            ]:
                raise BusinessRuleException(
                    f"Cannot delete slot with {booking.status} booking"
                )

        availability_id = slot.availability_id

        # Delete the slot
        self.db.delete(slot)
        self.db.flush()

        # Check if this was the last slot for the availability
        remaining_slots = (
            self.db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.availability_id == availability_id)
            .count()
        )

        if remaining_slots == 0:
            # Mark availability as cleared or delete it
            availability = (
                self.db.query(InstructorAvailability)
                .filter(InstructorAvailability.id == availability_id)
                .first()
            )
            if availability:
                availability.is_cleared = True

        self.db.commit()

        self.logger.info(f"Deleted slot {slot_id}")
        return True

    def merge_overlapping_slots(
        self, availability_id: int, preserve_booked: bool = True
    ) -> int:
        """
        Merge overlapping or adjacent slots for an availability entry.

        Args:
            availability_id: The availability entry ID
            preserve_booked: Whether to preserve booked slots

        Returns:
            Number of slots merged
        """
        # Get all slots ordered by start time
        slots = (
            self.db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.availability_id == availability_id)
            .order_by(AvailabilitySlot.start_time)
            .all()
        )

        if len(slots) <= 1:
            return 0

        self.logger.debug(
            f"Merging slots for availability_id {availability_id}: "
            f"{len(slots)} slots found"
        )

        # Separate booked and non-booked slots
        if preserve_booked:
            booked_slots = [s for s in slots if s.booking_id]
            non_booked_slots = [s for s in slots if not s.booking_id]

            if booked_slots:
                self.logger.info(f"Preserving {len(booked_slots)} booked slots")
                # Don't merge if any booked slots exist
                return 0
        else:
            non_booked_slots = slots

        # Merge non-booked slots
        merged_count = 0
        merged_slots = []
        current = non_booked_slots[0]

        for next_slot in non_booked_slots[1:]:
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
                self.db.delete(next_slot)
                merged_count += 1
            else:
                # Slots are not adjacent
                merged_slots.append(current)
                current = next_slot

        merged_slots.append(current)

        if merged_count > 0:
            self.db.commit()
            self.logger.info(
                f"Merge complete: {len(slots)} slots -> "
                f"{len(merged_slots)} slots ({merged_count} merged)"
            )

        return merged_count

    def split_slot(
        self, slot_id: int, split_time: time
    ) -> Tuple[AvailabilitySlot, AvailabilitySlot]:
        """
        Split a slot into two at the specified time.

        Args:
            slot_id: The slot ID to split
            split_time: Time to split at

        Returns:
            Tuple of (first_slot, second_slot)

        Raises:
            NotFoundException: If slot not found
            ValidationException: If split time invalid
            BusinessRuleException: If slot has booking
        """
        # Get the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.id == slot_id)
            .first()
        )

        if not slot:
            raise NotFoundException("Slot not found")

        # Check if slot has booking
        if slot.booking_id:
            raise BusinessRuleException("Cannot split slot that has a booking")

        # Validate split time
        if split_time <= slot.start_time or split_time >= slot.end_time:
            raise ValidationException(
                "Split time must be between slot start and end times"
            )

        # Create second slot
        second_slot = AvailabilitySlot(
            availability_id=slot.availability_id,
            start_time=split_time,
            end_time=slot.end_time,
        )

        # Update first slot
        slot.end_time = split_time

        self.db.add(second_slot)
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

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            min_gap_minutes: Minimum gap size to report

        Returns:
            List of gaps with start/end times
        """
        # Get all slots for the date
        slots = (
            self.db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date,
            )
            .order_by(AvailabilitySlot.start_time)
            .all()
        )

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
        self, availability_id: int, target_duration_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Suggest optimal slot arrangements for a given duration.

        Args:
            availability_id: The availability entry ID
            target_duration_minutes: Desired booking duration

        Returns:
            List of suggested time slots
        """
        # Get all non-booked slots
        slots = (
            self.db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.availability_id == availability_id,
                AvailabilitySlot.booking_id.is_(None),
            )
            .order_by(AvailabilitySlot.start_time)
            .all()
        )

        suggestions = []

        for slot in slots:
            # Calculate slot duration
            start_dt = datetime.combine(date.today(), slot.start_time)
            end_dt = datetime.combine(date.today(), slot.end_time)
            slot_minutes = int((end_dt - start_dt).total_seconds() / 60)

            # If slot is large enough, suggest divisions
            if slot_minutes >= target_duration_minutes:
                num_divisions = slot_minutes // target_duration_minutes

                for i in range(num_divisions):
                    suggested_start = start_dt + timedelta(
                        minutes=i * target_duration_minutes
                    )
                    suggested_end = suggested_start + timedelta(
                        minutes=target_duration_minutes
                    )

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

    def _slot_exists(
        self, availability_id: int, start_time: time, end_time: time
    ) -> bool:
        """Check if an exact slot already exists."""
        return (
            self.db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.availability_id == availability_id,
                AvailabilitySlot.start_time == start_time,
                AvailabilitySlot.end_time == end_time,
            )
            .first()
            is not None
        )

    def _has_bookings_on_date(self, availability: InstructorAvailability) -> bool:
        """Check if any slots for this availability have bookings."""
        return (
            self.db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .filter(
                AvailabilitySlot.availability_id == availability.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
            > 0
        )

    def _slots_can_merge(
        self, slot1: AvailabilitySlot, slot2: AvailabilitySlot, max_gap_minutes: int = 1
    ) -> bool:
        """Check if two slots can be merged."""
        # Check if either has booking
        if slot1.booking_id or slot2.booking_id:
            return False

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
                f"Time {time_value} must align to 15-minute blocks "
                f"(e.g., 9:00, 9:15, 9:30, 9:45)"
            )
