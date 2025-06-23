# backend/tests/integration/test_slot_manager_service_db.py
"""
Integration tests for SlotManager database operations.

These tests document transaction boundaries and database interaction patterns
that will need to be maintained during repository pattern implementation.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
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
        """Test slot creation that conflicts with existing booking."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Try to create a slot that overlaps with test_booking
        availability_id = test_booking.availability_slot.availability_id

        with pytest.raises(ConflictException) as exc_info:
            service.create_slot(
                availability_id=availability_id,
                start_time=test_booking.start_time,
                end_time=test_booking.end_time,
                validate_conflicts=True,
            )

        assert "conflicts with" in str(exc_info.value)
        assert "existing bookings" in str(exc_info.value)

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
        """Test updating a slot that has a booking."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Try to update a booked slot
        with pytest.raises(BusinessRuleException) as exc_info:
            service.update_slot(slot_id=test_booking.availability_slot_id, end_time=time(12, 0))

        assert "Cannot update slot that has a booking" in str(exc_info.value)

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
        """Test deleting a booked slot without force."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Try to delete a booked slot
        with pytest.raises(BusinessRuleException) as exc_info:
            service.delete_slot(test_booking.availability_slot_id, force=False)

        assert "Cannot delete slot with" in str(exc_info.value)
        assert "booking" in str(exc_info.value)

    def test_delete_slot_with_booking_force(self, db: Session, test_instructor_with_availability: User):
        """Test that force deleting a booked slot still respects foreign key constraints."""
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

            # The test should expect failure when trying to force delete a booked slot
            from sqlalchemy.exc import IntegrityError

            with pytest.raises(IntegrityError):
                service.delete_slot(slot.id, force=True)

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
        """Test merge preserves booked slots."""
        conflict_checker = ConflictChecker(db)
        service = SlotManager(db, conflict_checker)

        # Use existing availability with booking
        availability_id = test_instructor_with_availability.availability[0].id

        # Count initial slots
        initial_slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).count()

        # Try to merge - should preserve booked slots
        merged_count = service.merge_overlapping_slots(availability_id, preserve_booked=True)

        # With bookings present, no merging should happen
        assert merged_count == 0

        # Verify slot count unchanged
        final_slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).count()

        assert final_slots == initial_slots

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
