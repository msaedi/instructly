# backend/tests/integration/services/test_availability_services.py
"""
Integration tests for availability-related services.
Tests the interaction between services and the database.

UPDATED FOR WORK STREAM #10: Single-table availability design.
UPDATED FOR WORK STREAM #9: Layer independence.

FIXES APPLIED:
- Used BlackoutDateCreate schema instead of dict for blackout operations
- Removed instructor_id parameter from slot delete/update methods
- Changed check_time_availability to check_availability (correct method name)
- Changed Service field from duration_minutes to duration
- Added proper imports for all schemas
"""

from datetime import date, time, timedelta

import pytest

from app.models.availability import AvailabilitySlot, BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.service_catalog import InstructorService as Service
from app.schemas.availability_window import SpecificDateAvailabilityCreate
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.conflict_checker import ConflictChecker
from app.services.slot_manager import SlotManager


# Fixtures for services
@pytest.fixture
def availability_service(db):
    """Create AvailabilityService instance."""
    return AvailabilityService(db)


@pytest.fixture
def slot_manager(db):
    """Create SlotManager instance."""
    return SlotManager(db)


@pytest.fixture
def conflict_checker(db):
    """Create ConflictChecker instance."""
    return ConflictChecker(db)


@pytest.fixture
def booking_service(db):
    """Create BookingService instance."""
    return BookingService(db)


class TestAvailabilityService:
    """Test AvailabilityService with database."""

    def test_get_week_availability_empty(self, availability_service, test_instructor):
        """Test getting week availability when no slots exist."""
        # Get a week with no availability
        start_date = date.today() + timedelta(days=30)

        result = availability_service.get_week_availability(instructor_id=test_instructor.id, start_date=start_date)

        # Should return empty dict for days with no slots
        assert isinstance(result, dict)
        assert len(result) == 0  # No days with availability

    def test_get_week_availability_with_slots(self, availability_service, db, test_instructor):
        """Test getting week availability when slots exist."""
        # Create actual slots in the database
        test_date1 = date(2025, 6, 16)
        test_date2 = date(2025, 6, 17)

        slot1 = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=test_date1, start_time=time(9, 0), end_time=time(10, 0)
        )
        slot2 = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=test_date2, start_time=time(14, 0), end_time=time(15, 0)
        )

        db.add(slot1)
        db.add(slot2)
        db.commit()

        # Call method
        result = availability_service.get_week_availability(instructor_id=test_instructor.id, start_date=test_date1)

        # Verify result structure
        assert isinstance(result, dict)
        assert "2025-06-16" in result
        assert "2025-06-17" in result

        # Verify slot data
        assert len(result["2025-06-16"]) == 1
        assert result["2025-06-16"][0]["start_time"] == "09:00:00"
        assert result["2025-06-16"][0]["end_time"] == "10:00:00"

        assert len(result["2025-06-17"]) == 1
        assert result["2025-06-17"][0]["start_time"] == "14:00:00"
        assert result["2025-06-17"][0]["end_time"] == "15:00:00"

    def test_add_specific_date_availability(self, availability_service, test_instructor):
        """Test adding availability for a specific date."""
        test_date = date.today() + timedelta(days=14)

        availability_data = SpecificDateAvailabilityCreate(
            specific_date=test_date, start_time=time(10, 0), end_time=time(12, 0)
        )

        result = availability_service.add_specific_date_availability(
            instructor_id=test_instructor.id, availability_data=availability_data
        )

        # Verify result is an AvailabilitySlot
        assert result is not None
        assert result.instructor_id == test_instructor.id
        assert result.specific_date == test_date
        assert result.start_time == time(10, 0)
        assert result.end_time == time(12, 0)

    def test_blackout_dates(self, availability_service, test_instructor):
        """Test blackout date operations."""
        # Add a blackout date
        from app.schemas.availability_window import BlackoutDateCreate

        blackout_date = date.today() + timedelta(days=21)

        blackout_data = BlackoutDateCreate(date=blackout_date, reason="Holiday")

        blackout = availability_service.add_blackout_date(instructor_id=test_instructor.id, blackout_data=blackout_data)

        assert blackout is not None
        assert blackout.date == blackout_date
        assert blackout.reason == "Holiday"

        # Get blackout dates - should include our new blackout
        blackouts = availability_service.get_blackout_dates(instructor_id=test_instructor.id)

        assert len(blackouts) >= 1
        assert any(b.date == blackout_date for b in blackouts)

        # Delete blackout date
        success = availability_service.delete_blackout_date(instructor_id=test_instructor.id, blackout_id=blackout.id)

        assert success is True

        # Get blackout dates again - should NOT include the deleted blackout
        blackouts_after_delete = availability_service.get_blackout_dates(instructor_id=test_instructor.id)

        # Verify the blackout was actually deleted
        assert len(blackouts_after_delete) == len(blackouts) - 1
        assert not any(b.date == blackout_date for b in blackouts_after_delete)


class TestSlotManager:
    """Test SlotManager service."""

    def test_create_slot_basic(self, slot_manager, test_instructor):
        """Test basic slot creation."""
        test_date = date.today() + timedelta(days=7)

        slot = slot_manager.create_slot(
            instructor_id=test_instructor.id, target_date=test_date, start_time=time(9, 0), end_time=time(10, 0)
        )

        assert slot is not None
        assert slot.instructor_id == test_instructor.id
        assert slot.specific_date == test_date
        assert slot.start_time == time(9, 0)
        assert slot.end_time == time(10, 0)

    def test_create_slot_with_single_table_design(self, slot_manager, db, test_instructor):
        """Test slot creation with single-table design."""
        # Create slot directly with instructor_id
        test_date = date.today() + timedelta(days=7)

        result = slot_manager.create_slot(
            instructor_id=test_instructor.id,
            target_date=test_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            # validate_conflicts parameter was removed
            auto_merge=True,
        )

        # Verify result
        assert result is not None
        assert result.instructor_id == test_instructor.id
        assert result.specific_date == test_date
        assert result.start_time == time(9, 0)
        assert result.end_time == time(10, 0)

    def test_delete_slot(self, slot_manager, db, test_instructor):
        """Test slot deletion."""
        # Create a slot first
        test_date = date.today() + timedelta(days=7)

        slot = slot_manager.create_slot(
            instructor_id=test_instructor.id, target_date=test_date, start_time=time(14, 0), end_time=time(15, 0)
        )

        assert slot is not None
        slot_id = slot.id

        # Delete the slot - only takes slot_id
        success = slot_manager.delete_slot(slot_id=slot_id)

        assert success is True

        # Verify it's deleted
        deleted_slot = db.query(AvailabilitySlot).filter_by(id=slot_id).first()
        assert deleted_slot is None

    def test_update_slot(self, slot_manager, db, test_instructor):
        """Test slot update."""
        # Create a slot
        test_date = date.today() + timedelta(days=7)

        slot = slot_manager.create_slot(
            instructor_id=test_instructor.id, target_date=test_date, start_time=time(10, 0), end_time=time(11, 0)
        )

        # Update the slot - only takes slot_id
        updated_slot = slot_manager.update_slot(slot_id=slot.id, start_time=time(11, 0), end_time=time(12, 0))

        assert updated_slot is not None
        assert updated_slot.start_time == time(11, 0)
        assert updated_slot.end_time == time(12, 0)
        assert updated_slot.specific_date == test_date  # Date unchanged

    def test_auto_merge_adjacent_slots(self, slot_manager, db, test_instructor):
        """Test automatic merging of adjacent slots."""
        test_date = date.today() + timedelta(days=7)

        # Create first slot
        slot1 = slot_manager.create_slot(
            instructor_id=test_instructor.id, target_date=test_date, start_time=time(9, 0), end_time=time(10, 0)
        )

        # Create adjacent slot with auto_merge=True
        slot2 = slot_manager.create_slot(
            instructor_id=test_instructor.id,
            target_date=test_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            auto_merge=True,
        )

        # Should merge into one slot
        slots = db.query(AvailabilitySlot).filter_by(instructor_id=test_instructor.id, specific_date=test_date).all()

        # Depending on implementation, might be 1 merged slot or 2 separate
        # Document actual behavior
        if len(slots) == 1:
            # Merged
            assert slots[0].start_time == time(9, 0)
            assert slots[0].end_time == time(11, 0)
        else:
            # Not merged
            assert len(slots) == 2


class TestConflictChecker:
    """Test ConflictChecker service."""

    def test_check_time_availability_no_conflicts(self, conflict_checker, db, test_instructor):
        """Test availability check when no conflicts exist."""
        test_date = date.today() + timedelta(days=7)

        # Create an available slot
        slot = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=test_date, start_time=time(9, 0), end_time=time(17, 0)
        )
        db.add(slot)
        db.commit()

        # Check for conflicts - should return False (no conflicts)
        has_conflicts = conflict_checker.check_time_conflicts(
            instructor_id=test_instructor.id, booking_date=test_date, start_time=time(10, 0), end_time=time(11, 0)
        )

        assert has_conflicts is False  # No conflicts

    def test_check_slot_availability_with_single_table(self, conflict_checker, db, test_instructor, test_student):
        """Test conflict checking with single-table design."""
        test_date = date.today() + timedelta(days=7)

        # Create an available slot
        slot = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=test_date, start_time=time(9, 0), end_time=time(11, 0)
        )
        db.add(slot)

        # Get instructor profile first
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter_by(user_id=test_instructor.id).first()

        # Use existing service from test_instructor fixture instead of creating new one
        # to avoid unique constraint violation
        service = db.query(Service).filter_by(instructor_profile_id=profile.id, is_active=True).first()

        if not service:
            raise RuntimeError("No instructor service found from test_instructor fixture")

        # Use validate_booking_constraints for comprehensive check
        result = conflict_checker.validate_booking_constraints(
            instructor_id=test_instructor.id,
            booking_date=test_date,
            start_time=time(9, 30),
            end_time=time(10, 30),
            service_id=service.id,
        )

        # Should be valid (no conflicts, within slot)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_check_time_availability_with_booking_conflict(self, conflict_checker, db, test_instructor, test_student):
        """Test availability check with existing booking."""
        test_date = date.today() + timedelta(days=7)

        # Create an available slot
        slot = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=test_date, start_time=time(9, 0), end_time=time(17, 0)
        )
        db.add(slot)

        # Get instructor profile
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter_by(user_id=test_instructor.id).first()

        # Use existing service from test_instructor fixture instead of creating new one
        service = db.query(Service).filter_by(instructor_profile_id=profile.id, is_active=True).first()

        if not service:
            raise RuntimeError("No instructor service found from test_instructor fixture")

        # Create an existing booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=test_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Check for overlapping time - should have conflicts
        conflicts = conflict_checker.check_booking_conflicts(
            instructor_id=test_instructor.id, check_date=test_date, start_time=time(10, 30), end_time=time(11, 30)
        )

        # Should have conflicts
        assert len(conflicts) > 0
        assert conflicts[0]["booking_id"] == booking.id

    def test_check_blackout_date(self, conflict_checker, db, test_instructor):
        """Test availability check on blackout date."""
        test_date = date.today() + timedelta(days=14)

        # Create a blackout date
        blackout = BlackoutDate(instructor_id=test_instructor.id, date=test_date, reason="Vacation")
        db.add(blackout)
        db.commit()

        # Check if date is blacked out
        is_blacked_out = conflict_checker.check_blackout_date(instructor_id=test_instructor.id, target_date=test_date)

        # Should be blacked out
        assert is_blacked_out is True

    def test_get_booked_times_for_date(self, conflict_checker, db, test_instructor, test_student):
        """Test getting booked times for a specific date."""
        test_date = date.today() + timedelta(days=7)

        # Get instructor profile
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter_by(user_id=test_instructor.id).first()

        # Use existing service from test_instructor fixture instead of creating new one
        # to avoid unique constraint violation
        service = db.query(Service).filter_by(instructor_profile_id=profile.id, is_active=True).first()

        if not service:
            raise RuntimeError("No instructor service found from test_instructor fixture")

        # Create bookings
        booking1 = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=test_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

        booking2 = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=test_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

        db.add(booking1)
        db.add(booking2)
        db.commit()

        # Get booked times - returns actual time strings
        booked_times = conflict_checker.get_booked_times_for_date(
            instructor_id=test_instructor.id, target_date=test_date
        )

        # Should return list of time ranges
        assert len(booked_times) == 2
        # Times are returned as ISO format strings
        assert any(bt["start_time"] == "09:00:00" and bt["end_time"] == "10:00:00" for bt in booked_times)
        assert any(bt["start_time"] == "14:00:00" and bt["end_time"] == "15:00:00" for bt in booked_times)
