# backend/tests/unit/services/test_conflict_checker_logic.py
"""
Updated unit tests for ConflictChecker business logic with repository mocking.

UPDATED FOR CLEAN ARCHITECTURE: Tests now match the current ConflictChecker
implementation which works directly with bookings without slot references.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.availability import BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.repositories.conflict_checker_repository import ConflictCheckerRepository
from app.services.conflict_checker import ConflictChecker


class TestConflictCheckerDataTransformation:
    """Test data transformation logic that stays in service."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        service = ConflictChecker(mock_db)
        service.repository = mock_repository
        return service

    def test_booking_conflict_response_formatting(self, service):
        """Test how booking conflicts are formatted for response."""
        # Create mock booking with proper time values
        mock_booking = Mock(spec=Booking)
        mock_booking.id = 123
        mock_booking.service_name = "Piano Lessons"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.booking_date = date.today()

        # Mock student
        mock_student = Mock()
        mock_student.full_name = "John Doe"
        mock_booking.student = mock_student

        # Mock repository method
        service.repository.get_bookings_for_conflict_check.return_value = [mock_booking]

        # Test the formatting logic
        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=time(9, 30), end_time=time(10, 30)
        )

        # Should format the conflict properly
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict["booking_id"] == 123
        assert conflict["start_time"] == "10:00:00"
        assert conflict["end_time"] == "11:00:00"
        assert conflict["student_name"] == "John Doe"
        assert conflict["service_name"] == "Piano Lessons"

    def test_booked_times_response_formatting(self, service):
        """Test formatting of booked times response."""
        # Create mock bookings with proper fields
        mock_booking = Mock(spec=Booking)
        mock_booking.id = 789
        mock_booking.start_time = time(14, 0)
        mock_booking.end_time = time(15, 0)
        mock_booking.booking_date = date.today()
        mock_booking.student_id = 111
        mock_booking.service_name = "Guitar Lessons"
        mock_booking.status = BookingStatus.CONFIRMED

        service.repository.get_bookings_for_date.return_value = [mock_booking]

        # Test the formatting
        booked_times = service.get_booked_times_for_date(instructor_id=1, target_date=date.today())

        assert len(booked_times) == 1
        time_info = booked_times[0]
        assert time_info["booking_id"] == 789
        assert time_info["start_time"] == "14:00:00"
        assert time_info["end_time"] == "15:00:00"
        assert time_info["student_id"] == 111
        assert time_info["service_name"] == "Guitar Lessons"

    def test_conflict_data_formatting(self, service):
        """Test how conflict data is formatted for response."""
        # Create mock booking with all fields
        mock_booking = Mock(spec=Booking)
        mock_booking.id = 123
        mock_booking.service_name = "Piano Lessons"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.student = Mock(full_name="John Doe")

        service.repository.get_bookings_for_conflict_check.return_value = [mock_booking]

        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=time(9, 30), end_time=time(10, 30)
        )

        # Verify conflict format
        assert len(conflicts) == 1
        conflict = conflicts[0]

        assert conflict["booking_id"] == 123
        assert conflict["start_time"] == "10:00:00"
        assert conflict["end_time"] == "11:00:00"
        assert conflict["student_name"] == "John Doe"
        assert conflict["service_name"] == "Piano Lessons"
        assert conflict["status"] == BookingStatus.CONFIRMED

    def test_week_data_grouping(self, service):
        """Test how weekly data is grouped by date."""
        # Create mock bookings
        mock_bookings = []
        base_date = date.today()

        for day_offset in range(3):
            booking_date = base_date + timedelta(days=day_offset)
            for hour in [9, 14]:
                mock_booking = Mock(spec=Booking)
                mock_booking.id = day_offset * 10 + hour
                mock_booking.booking_date = booking_date
                mock_booking.start_time = time(hour, 0)
                mock_booking.end_time = time(hour + 1, 0)
                mock_booking.student_id = 1
                mock_booking.service_name = "Test Service"
                mock_booking.status = BookingStatus.CONFIRMED
                mock_bookings.append(mock_booking)

        service.repository.get_bookings_for_week.return_value = mock_bookings

        result = service.get_booked_times_for_week(instructor_id=1, week_start=base_date)

        # Should be grouped by date
        assert len(result) == 3  # 3 days with bookings

        for date_str, times in result.items():
            assert isinstance(times, list)
            assert len(times) == 2  # 2 bookings per day

            # Verify time format
            for time_info in times:
                assert "booking_id" in time_info
                assert "start_time" in time_info
                assert "end_time" in time_info

    def test_empty_result_handling(self, service):
        """Test handling of empty query results."""
        # Mock empty results
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_bookings_for_week.return_value = []

        # Test empty conflicts
        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )

        assert conflicts == []

        # Test empty week data
        week_data = service.get_booked_times_for_week(instructor_id=1, week_start=date.today())

        assert week_data == {}


class TestConflictCheckerValidationRules:
    """Test validation rules and business constraints."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        service = ConflictChecker(mock_db)
        service.repository = mock_repository
        return service

    def test_past_date_validation_rules(self, service):
        """Test business rules for past date validation."""
        # Mock repository methods to return valid data
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_blackout_date.return_value = None

        # Mock profile with 2 hour advance requirement
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile

        # Test past date
        result = service.validate_booking_constraints(
            instructor_id=1, booking_date=date.today() - timedelta(days=1), start_time=time(14, 0), end_time=time(15, 0)
        )

        assert result["valid"] == False
        assert any("past" in error.lower() for error in result["errors"])

    def test_service_duration_validation_rules(self, service):
        """Test service-specific duration validation."""
        # Mock service with duration options
        mock_service = Mock(spec=Service)
        mock_service.duration_options = [60, 90, 120]  # Multiple duration options
        mock_service.is_active = True
        service.repository.get_active_service.return_value = mock_service

        # Mock other validations to pass
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_blackout_date.return_value = None

        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile

        # Test service duration mismatch - use a duration not in the options
        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(14, 45),  # 45 minutes - not in the options [60, 90, 120]
            service_id=1,
        )

        assert result["valid"] == True  # Valid but with warning
        assert len(result["warnings"]) >= 1
        assert any("[60, 90, 120] minutes" in warning for warning in result["warnings"])

    def test_blackout_date_priority_rules(self, service):
        """Test that blackout dates take priority over other validations."""
        # Mock blackout date exists
        service.repository.get_blackout_date.return_value = Mock(spec=BlackoutDate)

        # Mock other validations to pass
        service.repository.get_bookings_for_conflict_check.return_value = []
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile

        result = service.validate_booking_constraints(
            instructor_id=1, booking_date=date.today() + timedelta(days=1), start_time=time(14, 0), end_time=time(15, 0)
        )

        assert result["valid"] == False
        assert any("not available" in error for error in result["errors"])
        assert result["details"]["has_blackout"] == True

    def test_time_overlap_detection_logic(self, service):
        """Test the time overlap detection algorithm."""
        # Test data - these times should overlap
        check_start = time(10, 0)
        check_end = time(12, 0)

        # Create mock bookings with different time ranges
        mock_bookings = []

        # Overlapping cases
        overlapping_times = [
            (time(9, 0), time(11, 0)),  # Overlaps at start
            (time(11, 0), time(13, 0)),  # Overlaps at end
            (time(10, 30), time(11, 30)),  # Contained within
            (time(9, 0), time(13, 0)),  # Contains check range
        ]

        # Non-overlapping cases
        non_overlapping_times = [
            (time(8, 0), time(9, 30)),  # Before
            (time(12, 30), time(14, 0)),  # After
        ]

        booking_id = 1
        for start, end in overlapping_times + non_overlapping_times:
            mock_booking = self._create_mock_booking(booking_id, start, end)
            mock_bookings.append(mock_booking)
            booking_id += 1

        # Mock the repository method
        service.repository.get_bookings_for_conflict_check.return_value = mock_bookings

        # Call the method
        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=check_start, end_time=check_end
        )

        # Should detect exactly 4 conflicts
        assert len(conflicts) == 4

        # Verify conflict details
        assert all("booking_id" in conflict for conflict in conflicts)
        assert all("start_time" in conflict for conflict in conflicts)
        assert all("end_time" in conflict for conflict in conflicts)

    def test_time_overlap_edge_cases(self, service):
        """Test edge cases in time overlap detection."""
        # Test exact boundary conditions
        check_start = time(10, 0)
        check_end = time(11, 0)

        mock_bookings = []

        # Edge cases
        boundary_times = [
            (1, time(9, 0), time(10, 0)),  # Ends exactly at start
            (2, time(11, 0), time(12, 0)),  # Starts exactly at end
            (3, time(10, 0), time(11, 0)),  # Exact same time
        ]

        for booking_id, start, end in boundary_times:
            mock_booking = self._create_mock_booking(booking_id, start, end)
            mock_bookings.append(mock_booking)

        service.repository.get_bookings_for_conflict_check.return_value = mock_bookings

        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=check_start, end_time=check_end
        )

        # Adjacent slots should not conflict, only exact overlap
        assert len(conflicts) == 1
        assert conflicts[0]["booking_id"] == 3

    def test_validate_time_range_business_rules(self, service):
        """Test time range validation business logic."""
        # Test valid range
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(10, 30), min_duration_minutes=30)

        assert result["valid"] == True
        assert result["duration_minutes"] == 90

        # Test invalid: end before start
        result = service.validate_time_range(start_time=time(10, 0), end_time=time(9, 0))

        assert result["valid"] == False
        assert "after start time" in result["reason"]

        # Test invalid: too short
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(9, 15), min_duration_minutes=30)

        assert result["valid"] == False
        assert "at least 30 minutes" in result["reason"]
        assert result["duration_minutes"] == 15

        # Test invalid: too long
        result = service.validate_time_range(
            start_time=time(9, 0), end_time=time(18, 0), max_duration_minutes=480  # 8 hours
        )

        assert result["valid"] == False
        assert "cannot exceed 480 minutes" in result["reason"]
        assert result["duration_minutes"] == 540  # 9 hours

    def test_minimum_advance_booking_calculation(self, service):
        """Test advance booking time calculation logic."""
        # Mock instructor profile
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 24
        service.repository.get_instructor_profile.return_value = mock_profile

        # Test booking exactly 24 hours in advance
        booking_datetime = datetime.now() + timedelta(hours=24, minutes=1)
        result = service.check_minimum_advance_booking(
            instructor_id=1, booking_date=booking_datetime.date(), booking_time=booking_datetime.time()
        )

        assert result["valid"] == True
        assert result["min_advance_hours"] == 24

        # Test booking too soon (23 hours)
        booking_datetime = datetime.now() + timedelta(hours=23)
        result = service.check_minimum_advance_booking(
            instructor_id=1, booking_date=booking_datetime.date(), booking_time=booking_datetime.time()
        )

        assert result["valid"] == False
        assert "at least 24 hours in advance" in result["reason"]

    def test_find_next_available_time_logic(self, service):
        """Test finding next available time slot."""
        # Create existing bookings
        existing_bookings = [
            self._create_mock_booking(1, time(9, 0), time(10, 0)),
            self._create_mock_booking(2, time(11, 0), time(12, 0)),
            self._create_mock_booking(3, time(14, 0), time(15, 0)),
        ]

        service.repository.get_bookings_for_date.return_value = existing_bookings

        # Find 60-minute slot
        result = service.find_next_available_time(
            instructor_id=1,
            target_date=date.today(),
            duration_minutes=60,
            earliest_time=time(9, 0),
            latest_time=time(17, 0),
        )

        assert result is not None
        assert result["start_time"] == "10:00:00"
        assert result["end_time"] == "11:00:00"
        assert result["available"] == True

    def test_repository_method_usage(self, service):
        """Test that service uses repository methods correctly."""
        # Test check_booking_conflicts uses repository
        service.repository.get_bookings_for_conflict_check.return_value = []

        service.check_booking_conflicts(1, date.today(), time(10, 0), time(11, 0))

        service.repository.get_bookings_for_conflict_check.assert_called_once_with(1, date.today(), None)

        # Test get_booked_times_for_date uses correct repository method
        service.repository.get_bookings_for_date.return_value = []

        service.get_booked_times_for_date(1, date.today())

        service.repository.get_bookings_for_date.assert_called_once_with(1, date.today())

    # Helper methods
    def _create_mock_booking(self, booking_id: int, start: time, end: time) -> Mock:
        """Create a mock booking with proper time values."""
        booking = Mock(spec=Booking)
        booking.id = booking_id
        booking.start_time = start
        booking.end_time = end
        booking.booking_date = date.today()
        booking.student = Mock(full_name="Test Student")
        booking.service_name = "Test Service"
        booking.status = BookingStatus.CONFIRMED

        return booking


class TestConflictCheckerEdgeCases:
    """Test edge cases and error conditions in business logic."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        service = ConflictChecker(mock_db)
        service.repository = mock_repository
        return service

    def test_midnight_boundary_handling(self, service):
        """Test handling of times near midnight."""
        # Test late night booking
        result = service.validate_time_range(start_time=time(23, 30), end_time=time(0, 30))  # After midnight

        # Should be invalid as it crosses midnight
        assert result["valid"] == False

    def test_zero_duration_handling(self, service):
        """Test handling of zero-duration slots."""
        result = service.validate_time_range(start_time=time(10, 0), end_time=time(10, 0))

        assert result["valid"] == False
        assert "after start time" in result["reason"]

    def test_maximum_duration_boundary(self, service):
        """Test maximum duration validation."""
        # Test exactly at limit (8 hours)
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(17, 0), max_duration_minutes=480)

        assert result["valid"] == True
        assert result["duration_minutes"] == 480

        # Test 1 minute over limit
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(17, 1), max_duration_minutes=480)

        assert result["valid"] == False
        assert result["duration_minutes"] == 481

    def test_none_handling_in_validation(self, service):
        """Test handling of None values in validation."""
        # Mock profile not found
        service.repository.get_instructor_profile.return_value = None

        result = service.check_minimum_advance_booking(
            instructor_id=999, booking_date=date.today() + timedelta(days=1), booking_time=time(10, 0)
        )

        assert result["valid"] == False
        assert "not found" in result["reason"]

    def test_inactive_service_validation(self, service):
        """Test validation with inactive service."""
        # Repository returns None for inactive service
        service.repository.get_active_service.return_value = None

        # Mock other validations to pass
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_blackout_date.return_value = None

        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile

        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_id=1,
        )

        assert result["valid"] == False
        assert any("not found or no longer available" in error for error in result["errors"])
