# backend/tests/integration/services/test_conflict_checker_service_db.py
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
from app.models.booking import Booking
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

    def test_get_booked_times_for_date_integration(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Test getting booked slots for a specific date."""
        service = ConflictChecker(db)

        booked_times = service.get_booked_times_for_date(
            instructor_id=test_instructor_with_availability.id, target_date=test_booking.booking_date
        )

        # Should find our test booking
        assert len(booked_times) == 1
        assert booked_times[0]["booking_id"] == test_booking.id
        assert booked_times[0]["student_id"] == test_booking.student_id
        assert booked_times[0]["service_name"] == test_booking.service_name

        # Test date with no bookings
        empty_date = date.today() + timedelta(days=30)
        empty_times = service.get_booked_times_for_date(
            instructor_id=test_instructor_with_availability.id, target_date=empty_date
        )

        assert len(empty_times) == 0

    def test_get_booked_times_for_week_integration(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Test getting booked slots for a week."""
        service = ConflictChecker(db)

        # Get week containing the test booking
        booking_date = test_booking.booking_date
        week_start = booking_date - timedelta(days=booking_date.weekday())

        week_times = service.get_booked_times_for_week(
            instructor_id=test_instructor_with_availability.id, week_start=week_start
        )

        # Should have data for the booking date
        booking_date_str = booking_date.isoformat()
        assert booking_date_str in week_times
        assert len(week_times[booking_date_str]) == 1
        assert week_times[booking_date_str][0]["booking_id"] == test_booking.id

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

        service.get_booked_times_for_week(
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
