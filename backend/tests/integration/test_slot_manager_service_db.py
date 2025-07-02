# backend/tests/integration/test_slot_manager_service_db.py
"""
Integration tests for SlotManager database operations.

These tests document transaction boundaries and database interaction patterns
that will need to be maintained during repository pattern implementation.

UPDATED: Fixed tests to match Work Stream #9 - Availability operations no longer
check for bookings (layer independence).
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.user import User
from app.services.conflict_checker import ConflictChecker
from app.services.slot_manager import SlotManager


class TestSlotManagerDatabaseOperations:
    """Test all database operations in SlotManager service."""

    def test_create_slot_success(self, db: Session, test_instructor_with_availability: User):
        """Test successful slot creation."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Get an availability entry
        availability = (
            db.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == test_instructor_with_availability.id,
                InstructorAvailability.is_cleared == False,
            )
            .first()
        )

        if availability:
            # Create a new slot
            new_slot = service.create_slot(
                availability_id=availability.id,
                start_time=time(15, 0),
                end_time=time(16, 0),
                validate_conflicts=True,
                auto_merge=False,
            )

            assert new_slot.id is not None
            assert new_slot.start_time == time(15, 0)
            assert new_slot.end_time == time(16, 0)
            assert new_slot.availability_id == availability.id

            # Verify it's in the database
            saved_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == new_slot.id).first()

            assert saved_slot is not None
            assert saved_slot.start_time == time(15, 0)

    def test_create_slot_with_invalid_time_alignment(self, db: Session, test_instructor_with_availability: User):
        """Test slot creation with invalid time alignment."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            # Try to create slot with invalid time (not 15-minute aligned)
            with pytest.raises(ValidationException) as exc_info:
                service.create_slot(
                    availability_id=availability.id, start_time=time(15, 7), end_time=time(16, 0)  # Invalid alignment
                )

            assert "must align to 15-minute blocks" in str(exc_info.value)

    def test_create_slot_with_conflict(self, db: Session, test_instructor_with_availability: User, test_booking):
        """Test slot creation that would have conflicted with existing booking in old system.

        FIXED: With layer independence, we can create slots even if bookings exist.
        This is correct behavior - availability and bookings are independent layers.
        """
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Get the availability that has the booking
        slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == test_booking.availability_slot_id).first()
        if slot:
            availability_id = slot.availability_id

            # In the old system, we couldn't create ANY slot when a booking existed
            # Now we can. Create a slot at a different time to avoid duplicate error.
            # Since booking is typically at 11:00-12:00, create one at 13:00-14:00
            new_slot = service.create_slot(
                availability_id=availability_id,
                start_time=time(13, 0),
                end_time=time(14, 0),
                validate_conflicts=True,  # Deprecated parameter, ignored
                # auto_merge defaults to True - test real behavior
            )

            assert new_slot is not None
            # The slot might have been merged with adjacent slots, which is fine
            # The key point is that creation succeeded
            assert new_slot.start_time <= time(13, 0)
            assert new_slot.end_time >= time(14, 0)

            # The key point: we successfully created a slot on a date that has bookings
            # This demonstrates layer independence - in the old system this would have
            # raised ConflictException

    def test_create_duplicate_slot(self, db: Session, test_instructor_with_availability: User):
        """Test creating a duplicate slot."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability and availability.time_slots:
            existing_slot = availability.time_slots[0]

            # Try to create exact duplicate
            with pytest.raises(ConflictException) as exc_info:
                service.create_slot(
                    availability_id=availability.id,
                    start_time=existing_slot.start_time,
                    end_time=existing_slot.end_time,
                )

            assert "already exists" in str(exc_info.value)

    def test_update_slot_success(self, db: Session, test_instructor_with_availability: User):
        """Test successful slot update."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create a slot first
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            new_slot = service.create_slot(
                availability_id=availability.id, start_time=time(17, 0), end_time=time(18, 0), auto_merge=False
            )

            # Update the slot
            updated_slot = service.update_slot(slot_id=new_slot.id, start_time=time(17, 30), end_time=time(18, 30))

            assert updated_slot.start_time == time(17, 30)
            assert updated_slot.end_time == time(18, 30)

            # Verify in database
            db_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == new_slot.id).first()

            assert db_slot.start_time == time(17, 30)
            assert db_slot.end_time == time(18, 30)

    def test_update_slot_with_booking(self, db: Session, test_booking):
        """Test updating a slot that has a booking.

        FIXED: With layer independence, we can update slots even if they have bookings.
        This is correct behavior - availability changes don't affect existing bookings.
        """
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Store the original booking end time
        original_booking_end = test_booking.end_time

        # Update slot to a different time than the booking currently has
        # If booking ends at 12:00, update slot to end at 13:00
        new_end_time = time(13, 0) if original_booking_end == time(12, 0) else time(12, 0)

        # Update should now SUCCEED - bookings don't prevent slot updates
        updated_slot = service.update_slot(slot_id=test_booking.availability_slot_id, end_time=new_end_time)

        assert updated_slot is not None
        assert updated_slot.end_time == new_end_time

        # The booking remains unchanged (independent layer)
        db.refresh(test_booking)
        assert test_booking.end_time == original_booking_end  # Booking keeps its original time

    def test_delete_slot_success(self, db: Session, test_instructor_with_availability: User):
        """Test successful slot deletion."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create a slot to delete
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            new_slot = service.create_slot(
                availability_id=availability.id, start_time=time(19, 0), end_time=time(20, 0), auto_merge=False
            )

            slot_id = new_slot.id

            # Delete the slot
            result = service.delete_slot(slot_id)

            assert result == True

            # Verify it's gone from database
            deleted_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot_id).first()

            assert deleted_slot is None

    def test_delete_slot_with_booking_no_force(self, db: Session, test_booking):
        """Test deleting a booked slot without force.

        FIXED: With layer independence, we can delete slots even if they have bookings.
        The 'force' parameter is deprecated. Bookings persist independently.
        """
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        slot_id = test_booking.availability_slot_id

        # Delete should now SUCCEED - bookings don't prevent slot deletion
        result = service.delete_slot(slot_id, force=False)

        assert result == True

        # Verify slot is deleted
        deleted_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot_id).first()
        assert deleted_slot is None

        # Verify booking still exists (independent layer)
        db.refresh(test_booking)
        assert test_booking.id is not None
        assert test_booking.status == BookingStatus.CONFIRMED

    def test_delete_slot_with_booking_force(self, db: Session, test_instructor_with_availability: User):
        """Test force deleting a booked slot.

        FIXED: With FK constraint removed, slots can be deleted even with bookings.
        No RepositoryException is raised. This is correct behavior - bookings
        persist independently of availability slots.
        """
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create a slot and book it
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            slot = service.create_slot(
                availability_id=availability.id, start_time=time(20, 0), end_time=time(21, 0), auto_merge=False
            )

            # Create a booking for this slot
            service_obj = (
                db.query(Service)
                .filter(Service.instructor_profile_id == test_instructor_with_availability.instructor_profile.id)
                .first()
            )

            booking = Booking(
                student_id=test_instructor_with_availability.id,
                instructor_id=test_instructor_with_availability.id,
                service_id=service_obj.id,
                availability_slot_id=slot.id,
                booking_date=availability.date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                service_name="Test Service",
                hourly_rate=50.00,
                total_price=50.00,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
                location_type="student_home",
            )
            db.add(booking)
            db.commit()

            # Delete should SUCCEED now - FK constraint is removed
            result = service.delete_slot(slot.id, force=True)

            assert result == True

            # Verify slot is deleted
            deleted_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot.id).first()
            assert deleted_slot is None

            # Verify booking still exists with its availability_slot_id pointing to deleted slot
            db.refresh(booking)
            assert booking.id is not None
            assert booking.availability_slot_id == slot.id  # Still points to deleted slot
            assert booking.status == BookingStatus.CONFIRMED

    def test_merge_overlapping_slots(self, db: Session, test_instructor_with_availability: User):
        """Test merging overlapping/adjacent slots."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create a new availability for clean test
        new_availability = InstructorAvailability(
            instructor_id=test_instructor_with_availability.id, date=date.today() + timedelta(days=10), is_cleared=False
        )
        db.add(new_availability)
        db.commit()

        # Create adjacent slots
        slot1 = service.create_slot(
            availability_id=new_availability.id, start_time=time(9, 0), end_time=time(10, 0), auto_merge=False
        )

        slot2 = service.create_slot(
            availability_id=new_availability.id, start_time=time(10, 0), end_time=time(11, 0), auto_merge=False
        )

        slot3 = service.create_slot(
            availability_id=new_availability.id, start_time=time(11, 0), end_time=time(12, 0), auto_merge=False
        )

        # Merge slots
        merged_count = service.merge_overlapping_slots(new_availability.id)

        assert merged_count == 2  # Two slots were merged

        # Check result - should have one slot from 9-12
        remaining_slots = (
            db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == new_availability.id).all()
        )

        assert len(remaining_slots) == 1
        assert remaining_slots[0].start_time == time(9, 0)
        assert remaining_slots[0].end_time == time(12, 0)

    def test_merge_with_booked_slots_preserved(self, db: Session, test_instructor_with_availability: User):
        """Test merge with booked slots.

        FIXED: The preserve_booked parameter is deprecated. Slots are merged
        regardless of bookings (layer independence).
        """
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Use existing availability with booking
        availability_id = test_instructor_with_availability.availability[0].id

        # Count initial slots
        initial_slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).all()

        # Try to merge - should merge adjacent slots regardless of bookings
        merged_count = service.merge_overlapping_slots(availability_id, preserve_booked=True)

        # Merging may or may not happen depending on whether slots are adjacent
        # The key is that it doesn't fail due to bookings
        assert merged_count >= 0

        # Verify we still have slots (might be fewer due to merging)
        final_slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).count()
        assert final_slots > 0

    def test_split_slot_success(self, db: Session, test_instructor_with_availability: User):
        """Test successful slot splitting."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create a large slot to split
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            large_slot = service.create_slot(
                availability_id=availability.id, start_time=time(14, 0), end_time=time(16, 0), auto_merge=False
            )

            # Split at 15:00
            slot1, slot2 = service.split_slot(large_slot.id, time(15, 0))

            assert slot1.start_time == time(14, 0)
            assert slot1.end_time == time(15, 0)
            assert slot2.start_time == time(15, 0)
            assert slot2.end_time == time(16, 0)

            # Verify both in database
            db_slots = (
                db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.availability_id == availability.id,
                    AvailabilitySlot.start_time >= time(14, 0),
                    AvailabilitySlot.end_time <= time(16, 0),
                )
                .all()
            )

            assert len(db_slots) == 2

    def test_find_gaps_in_availability(self, db: Session, test_instructor_with_availability: User):
        """Test finding gaps between slots."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create availability with gaps
        new_availability = InstructorAvailability(
            instructor_id=test_instructor_with_availability.id, date=date.today() + timedelta(days=15), is_cleared=False
        )
        db.add(new_availability)
        db.commit()

        # Create slots with gaps
        service.create_slot(
            availability_id=new_availability.id, start_time=time(9, 0), end_time=time(10, 0), auto_merge=False
        )

        service.create_slot(
            availability_id=new_availability.id,
            start_time=time(11, 0),  # 1 hour gap
            end_time=time(12, 0),
            auto_merge=False,
        )

        service.create_slot(
            availability_id=new_availability.id,
            start_time=time(14, 0),  # 2 hour gap
            end_time=time(15, 0),
            auto_merge=False,
        )

        # Find gaps
        gaps = service.find_gaps_in_availability(
            instructor_id=test_instructor_with_availability.id, target_date=new_availability.date, min_gap_minutes=30
        )

        assert len(gaps) == 2
        assert gaps[0]["duration_minutes"] == 60  # 10-11
        assert gaps[1]["duration_minutes"] == 120  # 12-14

    def test_optimize_availability(self, db: Session, test_instructor_with_availability: User):
        """Test availability optimization suggestions."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create large slot for optimization
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            # Clear existing slots for clean test
            for slot in availability.time_slots:
                if (
                    not db.query(Booking)
                    .filter(
                        Booking.availability_slot_id == slot.id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                    .first()
                ):
                    db.delete(slot)
            db.commit()

            # Create large slot
            large_slot = service.create_slot(
                availability_id=availability.id,
                start_time=time(9, 0),
                end_time=time(12, 0),  # 3 hours
                auto_merge=False,
            )

            # Get optimization suggestions for 60-minute sessions
            suggestions = service.optimize_availability(availability_id=availability.id, target_duration_minutes=60)

            assert len(suggestions) == 3  # 3 one-hour slots
            assert suggestions[0]["start_time"] == "09:00:00"
            assert suggestions[0]["end_time"] == "10:00:00"
            assert suggestions[1]["start_time"] == "10:00:00"
            assert suggestions[1]["end_time"] == "11:00:00"
            assert suggestions[2]["start_time"] == "11:00:00"
            assert suggestions[2]["end_time"] == "12:00:00"


class TestSlotManagerTransactionBehavior:
    """Test transaction handling in SlotManager operations."""

    def test_create_slot_rollback_on_error(self, db: Session, test_instructor_with_availability: User):
        """Test that slot creation rolls back on error."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Get slot count before
        initial_count = db.query(AvailabilitySlot).count()

        # Try to create slot with invalid availability ID
        with pytest.raises(NotFoundException):
            service.create_slot(availability_id=99999, start_time=time(10, 0), end_time=time(11, 0))  # Non-existent

        # Verify no slot was created
        final_count = db.query(AvailabilitySlot).count()
        assert final_count == initial_count

    def test_delete_last_slot_updates_availability(self, db: Session, test_instructor_with_availability: User):
        """Test that deleting last slot marks availability as cleared."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Create new availability with one slot
        new_availability = InstructorAvailability(
            instructor_id=test_instructor_with_availability.id, date=date.today() + timedelta(days=20), is_cleared=False
        )
        db.add(new_availability)
        db.commit()

        slot = service.create_slot(
            availability_id=new_availability.id, start_time=time(10, 0), end_time=time(11, 0), auto_merge=False
        )

        # Verify availability is not cleared
        assert new_availability.is_cleared == False

        # Delete the only slot
        service.delete_slot(slot.id)

        # Verify availability is now cleared
        db.refresh(new_availability)
        assert new_availability.is_cleared == True


class TestSlotManagerErrorConditions:
    """Test error conditions and edge cases."""

    def test_nonexistent_slot_operations(self, db: Session):
        """Test operations on non-existent slots."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Test update non-existent slot
        with pytest.raises(NotFoundException) as exc_info:
            service.update_slot(99999, end_time=time(12, 0))
        assert "Slot not found" in str(exc_info.value)

        # Test delete non-existent slot
        with pytest.raises(NotFoundException) as exc_info:
            service.delete_slot(99999)
        assert "Slot not found" in str(exc_info.value)

        # Test split non-existent slot
        with pytest.raises(NotFoundException) as exc_info:
            service.split_slot(99999, time(10, 30))
        assert "Slot not found" in str(exc_info.value)

    def test_invalid_time_range_operations(self, db: Session, test_instructor_with_availability: User):
        """Test operations with invalid time ranges."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability:
            # Test create with end before start
            with pytest.raises(ValidationException):
                service.create_slot(
                    availability_id=availability.id, start_time=time(10, 0), end_time=time(9, 0)  # Before start
                )

            # Create slot for split test
            slot = service.create_slot(
                availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0), auto_merge=False
            )

            # Test split outside slot range
            with pytest.raises(ValidationException) as exc_info:
                service.split_slot(slot.id, time(9, 30))  # Before start
            assert "between slot start and end times" in str(exc_info.value)

            with pytest.raises(ValidationException) as exc_info:
                service.split_slot(slot.id, time(11, 30))  # After end
            assert "between slot start and end times" in str(exc_info.value)
