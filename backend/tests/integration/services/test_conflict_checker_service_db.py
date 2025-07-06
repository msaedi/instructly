# backend/tests/integration/test_conflict_checker_service_db.py
"""
Fixed integration tests for ConflictChecker database operations.

UPDATED FOR WORK STREAM #10: Single-table availability design.
- All InstructorAvailability references removed
- Slots created directly with instructor_id and date
- No more is_cleared checks
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.user import User
from app.services.conflict_checker import ConflictChecker


class TestConflictCheckerDatabaseOperations:
    """Test all database operations in ConflictChecker service."""

    def test_check_booking_conflicts_integration(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Test conflict checking with real database data."""
        service = ConflictChecker(db)

        # Test conflict detection with existing booking
        conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=test_booking.booking_date,
            start_time=test_booking.start_time,
            end_time=test_booking.end_time,
        )

        # Should find the existing booking as a conflict
        assert len(conflicts) == 1
        assert conflicts[0]["booking_id"] == test_booking.id
        assert conflicts[0]["service_name"] == test_booking.service_name

        # Test no conflict with different time
        no_conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=test_booking.booking_date,
            start_time=time(20, 0),  # Different time
            end_time=time(22, 0),
        )

        assert len(no_conflicts) == 0

    def test_check_slot_availability_integration(self, db: Session, test_instructor_with_availability: User):
        """Test slot availability checking with real data."""
        service = ConflictChecker(db)

        # Create a new slot in the future to ensure it's not in the past
        future_date = date.today() + timedelta(days=7)

        # Create slot directly (single-table design)
        available_slot = AvailabilitySlot(
            instructor_id=test_instructor_with_availability.id,
            date=future_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db.add(available_slot)
        db.commit()

        # Test 1: Available slot should be available
        result = service.check_slot_availability(
            slot_id=available_slot.id, instructor_id=test_instructor_with_availability.id
        )

        assert result["available"] == True
        assert "slot_info" in result
        assert result["slot_info"]["instructor_id"] == test_instructor_with_availability.id
        assert result["slot_info"]["date"] == future_date.isoformat()

        # Test 2: Wrong instructor should fail
        wrong_instructor_result = service.check_slot_availability(
            slot_id=available_slot.id, instructor_id=999  # Non-existent instructor
        )

        assert wrong_instructor_result["available"] == False
        assert "different instructor" in wrong_instructor_result["reason"]

        # Test 3: Create a booked slot and verify it's not available
        booked_slot = AvailabilitySlot(
            instructor_id=test_instructor_with_availability.id,
            date=future_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        db.add(booked_slot)
        db.commit()

        # Create a booking for this slot
        booking = Booking(
            student_id=test_instructor_with_availability.id,  # Using instructor as student for test
            instructor_id=test_instructor_with_availability.id,
            service_id=db.query(Service)
            .filter(Service.instructor_profile_id == test_instructor_with_availability.instructor_profile.id)
            .first()
            .id,
            availability_slot_id=booked_slot.id,
            booking_date=future_date,
            start_time=booked_slot.start_time,
            end_time=booked_slot.end_time,
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="student_home",
        )
        db.add(booking)
        db.commit()

        # Test that booked slot is not available
        booked_result = service.check_slot_availability(
            slot_id=booked_slot.id, instructor_id=test_instructor_with_availability.id
        )

        assert booked_result["available"] == False
        assert "already booked" in booked_result["reason"]
        assert booked_result["booking_status"] == BookingStatus.CONFIRMED

        # Test 4: Non-existent slot
        non_existent_result = service.check_slot_availability(
            slot_id=99999, instructor_id=test_instructor_with_availability.id
        )

        assert non_existent_result["available"] == False
        assert "not found" in non_existent_result["reason"]

    def test_get_booked_slots_for_date_integration(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Test getting booked slots for a specific date."""
        service = ConflictChecker(db)

        booked_slots = service.get_booked_slots_for_date(
            instructor_id=test_instructor_with_availability.id, target_date=test_booking.booking_date
        )

        # Should find our test booking
        assert len(booked_slots) == 1
        assert booked_slots[0]["booking_id"] == test_booking.id
        assert booked_slots[0]["student_id"] == test_booking.student_id
        assert booked_slots[0]["service_name"] == test_booking.service_name

        # Test date with no bookings
        empty_date = date.today() + timedelta(days=30)
        empty_slots = service.get_booked_slots_for_date(
            instructor_id=test_instructor_with_availability.id, target_date=empty_date
        )

        assert len(empty_slots) == 0

    def test_get_booked_slots_for_week_integration(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Test getting booked slots for a week."""
        service = ConflictChecker(db)

        # Get week containing the test booking
        booking_date = test_booking.booking_date
        week_start = booking_date - timedelta(days=booking_date.weekday())

        week_slots = service.get_booked_slots_for_week(
            instructor_id=test_instructor_with_availability.id, week_start=week_start
        )

        # Should have data for the booking date
        booking_date_str = booking_date.isoformat()
        assert booking_date_str in week_slots
        assert len(week_slots[booking_date_str]) == 1
        assert week_slots[booking_date_str][0]["booking_id"] == test_booking.id

    def test_validate_time_range_integration(self, db: Session):
        """Test time range validation logic."""
        service = ConflictChecker(db)

        # Test valid time range
        valid_result = service.validate_time_range(
            start_time=time(9, 0), end_time=time(10, 30), min_duration_minutes=30
        )

        assert valid_result["valid"] == True
        assert valid_result["duration_minutes"] == 90

        # Test invalid time range (end before start)
        invalid_result = service.validate_time_range(start_time=time(10, 0), end_time=time(9, 0))

        assert invalid_result["valid"] == False
        assert "after start time" in invalid_result["reason"]

        # Test too short duration
        short_result = service.validate_time_range(start_time=time(9, 0), end_time=time(9, 15), min_duration_minutes=30)

        assert short_result["valid"] == False
        assert "at least 30 minutes" in short_result["reason"]

    def test_check_minimum_advance_booking_integration(self, db: Session, test_instructor: User):
        """Test minimum advance booking validation with real profile data."""
        service = ConflictChecker(db)

        # Test booking too soon
        tomorrow = date.today() + timedelta(days=1)
        too_soon_result = service.check_minimum_advance_booking(
            instructor_id=test_instructor.id, booking_date=tomorrow, booking_time=time(9, 0)
        )

        # With default 2-hour advance requirement, tomorrow should be valid
        assert too_soon_result["valid"] == True

        # Test booking in the past
        yesterday = date.today() - timedelta(days=1)
        past_result = service.check_minimum_advance_booking(
            instructor_id=test_instructor.id, booking_date=yesterday, booking_time=time(9, 0)
        )

        # Past bookings should be invalid due to being in the past
        assert past_result["valid"] == False

    def test_find_overlapping_slots_integration(self, db: Session, test_instructor_with_availability: User):
        """Test finding overlapping slots with real data."""
        service = ConflictChecker(db)

        # Get a date with availability - direct query on slots
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        if slot:
            target_date = slot.date

            # Test overlapping with existing slot
            overlapping = service.find_overlapping_slots(
                instructor_id=test_instructor_with_availability.id,
                target_date=target_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )

            # Should find the overlapping slot
            assert len(overlapping) >= 1
            found_slot = next((s for s in overlapping if s["slot_id"] == slot.id), None)
            assert found_slot is not None

            # Test non-overlapping time
            non_overlapping = service.find_overlapping_slots(
                instructor_id=test_instructor_with_availability.id,
                target_date=target_date,
                start_time=time(23, 0),
                end_time=time(23, 30),
            )

            # Should find no overlaps with late night time
            overlapping_ids = [s["slot_id"] for s in non_overlapping]
            assert slot.id not in overlapping_ids

    def test_check_blackout_date_integration(self, db: Session, test_instructor: User):
        """Test blackout date checking with real data."""
        service = ConflictChecker(db)

        # Add a blackout date
        blackout_date = date.today() + timedelta(days=15)
        blackout = BlackoutDate(instructor_id=test_instructor.id, date=blackout_date, reason="Integration test")
        db.add(blackout)
        db.commit()

        # Test blackout date detection
        is_blackout = service.check_blackout_date(test_instructor.id, blackout_date)
        assert is_blackout == True

        # Test non-blackout date
        normal_date = date.today() + timedelta(days=20)
        is_normal = service.check_blackout_date(test_instructor.id, normal_date)
        assert is_normal == False

    def test_validate_booking_constraints_comprehensive(self, db: Session, test_instructor_with_availability: User):
        """Test comprehensive booking validation with real data."""
        service = ConflictChecker(db)

        # Get a valid future date
        future_date = date.today() + timedelta(days=7)

        # Test valid booking constraints
        valid_result = service.validate_booking_constraints(
            instructor_id=test_instructor_with_availability.id,
            booking_date=future_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        assert valid_result["valid"] == True
        assert len(valid_result["errors"]) == 0
        assert "time_validation" in valid_result["details"]
        assert "advance_booking" in valid_result["details"]

        # Test invalid booking (past date)
        past_result = service.validate_booking_constraints(
            instructor_id=test_instructor_with_availability.id,
            booking_date=date.today() - timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        assert past_result["valid"] == False
        assert len(past_result["errors"]) > 0
        assert any("past" in error.lower() for error in past_result["errors"])


class TestConflictCheckerTransactionBoundaries:
    """Test transaction handling in ConflictChecker operations."""

    def test_database_query_isolation(self, db: Session, test_instructor_with_availability: User):
        """Test that queries are properly isolated."""
        service = ConflictChecker(db)

        # Test that queries don't interfere with each other
        conflicts1 = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        conflicts2 = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        # Each query should be independent
        assert isinstance(conflicts1, list)
        assert isinstance(conflicts2, list)

    def test_read_only_operations_safety(self, db: Session, test_instructor_with_availability: User):
        """Test that read operations don't modify data."""
        service = ConflictChecker(db)

        # Count initial bookings
        initial_booking_count = db.query(Booking).count()
        initial_slot_count = db.query(AvailabilitySlot).count()

        # Perform various read operations
        service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        service.get_booked_slots_for_week(
            instructor_id=test_instructor_with_availability.id,
            week_start=date.today() - timedelta(days=date.today().weekday()),
        )

        service.validate_booking_constraints(
            instructor_id=test_instructor_with_availability.id,
            booking_date=date.today() + timedelta(days=7),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        # Verify no data was modified
        final_booking_count = db.query(Booking).count()
        final_slot_count = db.query(AvailabilitySlot).count()

        assert final_booking_count == initial_booking_count
        assert final_slot_count == initial_slot_count


class TestConflictCheckerErrorConditions:
    """Test error conditions and edge cases."""

    def test_nonexistent_instructor_handling(self, db: Session):
        """Test handling of nonexistent instructor IDs."""
        service = ConflictChecker(db)

        # Test with nonexistent instructor
        conflicts = service.check_booking_conflicts(
            instructor_id=99999, check_date=date.today(), start_time=time(9, 0), end_time=time(10, 0)  # Nonexistent
        )

        # Should return empty list, not crash
        assert conflicts == []

        # Test minimum advance booking with nonexistent instructor
        advance_result = service.check_minimum_advance_booking(
            instructor_id=99999, booking_date=date.today() + timedelta(days=1), booking_time=time(9, 0)
        )

        assert advance_result["valid"] == False
        assert "not found" in advance_result["reason"]

    def test_nonexistent_slot_handling(self, db: Session):
        """Test handling of nonexistent slot IDs."""
        service = ConflictChecker(db)

        # Test with nonexistent slot
        availability_result = service.check_slot_availability(slot_id=99999, instructor_id=1)  # Nonexistent

        assert availability_result["available"] == False
        assert "not found" in availability_result["reason"]

    def test_edge_case_time_ranges(self, db: Session):
        """Test edge cases in time range validation."""
        service = ConflictChecker(db)

        # Test midnight crossing
        midnight_result = service.validate_time_range(start_time=time(23, 30), end_time=time(0, 30))  # Next day

        # This should be invalid as it crosses midnight
        assert midnight_result["valid"] == False

        # Test same start and end time
        same_time_result = service.validate_time_range(start_time=time(10, 0), end_time=time(10, 0))

        assert same_time_result["valid"] == False

        # Test maximum duration edge case
        max_duration_result = service.validate_time_range(
            start_time=time(9, 0), end_time=time(17, 0), max_duration_minutes=480  # 8 hours exactly
        )

        assert max_duration_result["valid"] == True
        assert max_duration_result["duration_minutes"] == 480
