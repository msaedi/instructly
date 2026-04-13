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

from app.auth import get_password_hash
from app.core.ulid_helper import generate_ulid
from app.models.availability import BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.booking_payment import BookingPayment
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.services.conflict_checker import ConflictChecker

try:  # pragma: no cover - allow repo root or backend/ test execution
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_secondary_student(db: Session, test_password: str) -> User:
    student = User(
        email=f"secondary.student.{generate_ulid().lower()}@example.com",
        hashed_password=get_password_hash(test_password),
        first_name="Second",
        last_name="Student",
        phone="+12125550001",
        zip_code="10001",
        is_active=True,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


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

    def test_cancelled_booking_does_not_block_same_slot(
        self,
        db: Session,
        test_student: User,
        test_instructor_with_availability: User,
        test_booking: Booking,
    ):
        booking_date = date.today() + timedelta(days=5)
        cancelled_booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=booking_date,
            start_time=time(13, 0),
            end_time=time(14, 0),
            status=BookingStatus.CANCELLED,
            service_name="Cancelled lesson",
            hourly_rate=80.0,
            total_price=80.0,
            duration_minutes=60,
            location_type="online",
            meeting_location="Zoom",
            service_area="Manhattan",
            instructor_timezone="America/New_York",
        )
        db.commit()

        service = ConflictChecker(db)
        conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=booking_date,
            start_time=time(13, 0),
            end_time=time(14, 0),
            new_location_type="online",
        )

        assert cancelled_booking.cancelled_at is not None
        assert conflicts == []

    def test_pending_auth_from_different_student_blocks_slot(
        self,
        db: Session,
        test_password: str,
        test_student: User,
        test_instructor_with_availability: User,
        test_booking: Booking,
    ):
        requester_student = _create_secondary_student(db, test_password)
        booking_date = date.today() + timedelta(days=6)
        pending_booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=booking_date,
            start_time=time(15, 0),
            end_time=time(16, 0),
            status=BookingStatus.PENDING,
            service_name="Pending auth lesson",
            hourly_rate=80.0,
            total_price=80.0,
            duration_minutes=60,
            location_type="online",
            meeting_location="Zoom",
            service_area="Manhattan",
            instructor_timezone="America/New_York",
        )
        db.add(
            BookingPayment(
                booking_id=pending_booking.id,
                payment_status="scheduled",
                auth_failure_count=0,
            )
        )
        db.commit()

        service = ConflictChecker(db)
        instructor_conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=booking_date,
            start_time=time(15, 0),
            end_time=time(16, 0),
            new_location_type="online",
        )
        requester_student_conflicts = service.check_student_booking_conflicts(
            student_id=requester_student.id,
            check_date=booking_date,
            start_time=time(15, 0),
            end_time=time(16, 0),
        )

        assert [conflict["booking_id"] for conflict in instructor_conflicts] == [
            pending_booking.id
        ]
        assert instructor_conflicts[0]["status"] == BookingStatus.PENDING
        assert requester_student_conflicts == []

    def test_spring_forward_day_back_to_back_boundary_is_not_conflict(
        self,
        db: Session,
        test_student: User,
        test_instructor_with_availability: User,
        test_booking: Booking,
    ):
        booking_date = date(2026, 3, 8)
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        assert profile is not None
        profile.non_travel_buffer_minutes = 0
        profile.travel_buffer_minutes = 0
        db.commit()

        dst_booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=booking_date,
            start_time=time(1, 30),
            end_time=time(3, 0),
            status=BookingStatus.CONFIRMED,
            service_name="Spring-forward lesson",
            hourly_rate=120.0,
            total_price=180.0,
            duration_minutes=90,
            location_type="online",
            meeting_location="Zoom",
            service_area="Manhattan",
            instructor_timezone="America/New_York",
        )
        db.commit()

        service = ConflictChecker(db)
        conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=booking_date,
            start_time=time(3, 0),
            end_time=time(4, 0),
            new_location_type="online",
        )

        assert dst_booking.booking_start_utc.isoformat() == "2026-03-08T06:30:00+00:00"
        assert dst_booking.booking_end_utc.isoformat() == "2026-03-08T07:00:00+00:00"
        assert conflicts == []

    def test_fall_back_day_back_to_back_boundary_is_not_conflict(
        self,
        db: Session,
        test_student: User,
        test_instructor_with_availability: User,
        test_booking: Booking,
    ):
        booking_date = date(2026, 11, 1)
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        assert profile is not None
        profile.non_travel_buffer_minutes = 0
        profile.travel_buffer_minutes = 0
        db.commit()

        dst_booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=booking_date,
            start_time=time(1, 0),
            end_time=time(2, 0),
            status=BookingStatus.CONFIRMED,
            service_name="Fall-back lesson",
            hourly_rate=80.0,
            total_price=80.0,
            duration_minutes=60,
            location_type="online",
            meeting_location="Zoom",
            service_area="Manhattan",
            instructor_timezone="America/New_York",
            is_dst_for_ambiguous=True,
        )
        db.commit()

        service = ConflictChecker(db)
        conflicts = service.check_booking_conflicts(
            instructor_id=test_instructor_with_availability.id,
            check_date=booking_date,
            start_time=time(2, 0),
            end_time=time(3, 0),
            new_location_type="online",
        )

        assert dst_booking.booking_start_utc.isoformat() == "2026-11-01T05:00:00+00:00"
        assert dst_booking.booking_end_utc.isoformat() == "2026-11-01T07:00:00+00:00"
        assert conflicts == []

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
        # Availability is stored in bitmap format (availability_days table), not slots

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

        assert final_booking_count == initial_booking_count


class TestConflictCheckerErrorConditions:
    """Test error conditions and edge cases."""

    def test_nonexistent_instructor_handling(self, db: Session):
        """Test handling of nonexistent instructor IDs."""
        service = ConflictChecker(db)

        # Test with nonexistent instructor
        conflicts = service.check_booking_conflicts(
            instructor_id=generate_ulid(),
            check_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),  # Nonexistent
        )

        # Should return empty list, not crash
        assert conflicts == []

        # Test minimum advance booking with nonexistent instructor
        advance_result = service.check_minimum_advance_booking(
            instructor_id=generate_ulid(), booking_date=date.today() + timedelta(days=1), booking_time=time(9, 0)
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
