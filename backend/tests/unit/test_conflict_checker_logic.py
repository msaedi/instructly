# backend/tests/unit/test_conflict_checker_logic.py
"""
Fixed unit tests for ConflictChecker business logic with proper service fixture.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.services.conflict_checker import ConflictChecker


class TestConflictCheckerDataTransformation:
    """Test data transformation logic that stays in service."""

    def test_booking_conflict_response_formatting(self):
        """Test how booking conflicts are formatted for response."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Mock booking data
        mock_booking = Mock(spec=Booking)
        mock_booking.id = 123
        mock_booking.service_name = "Piano Lessons"
        mock_booking.status = BookingStatus.CONFIRMED

        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.start_time = time(10, 0)
        mock_slot.end_time = time(11, 0)
        mock_booking.availability_slot = mock_slot

        # Mock student
        mock_student = Mock()
        mock_student.full_name = "John Doe"
        mock_booking.student = mock_student

        # Mock query chain
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [mock_booking]

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

    def test_booked_slots_response_formatting(self):
        """Test formatting of booked slots response."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Mock query result (using namedtuple-like object)
        class MockSlotResult:
            def __init__(self):
                self.id = 456
                self.start_time = time(14, 0)
                self.end_time = time(15, 0)
                self.booking_id = 789
                self.student_id = 111
                self.service_name = "Guitar Lessons"
                self.status = BookingStatus.CONFIRMED

        mock_result = MockSlotResult()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [mock_result]

        # Test the formatting
        booked_slots = service.get_booked_slots_for_date(instructor_id=1, target_date=date.today())

        assert len(booked_slots) == 1
        slot = booked_slots[0]
        assert slot["slot_id"] == 456
        assert slot["start_time"] == "14:00:00"
        assert slot["end_time"] == "15:00:00"
        assert slot["booking_id"] == 789
        assert slot["student_id"] == 111
        assert slot["service_name"] == "Guitar Lessons"

    def test_slot_availability_response_formatting(self):
        """Test slot availability response formatting logic."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Mock available slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 123
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.date = date.today() + timedelta(days=1)
        mock_availability.instructor_id = 1
        mock_slot.availability = mock_availability

        db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_slot

        # Mock no booking found (slot is available)
        db.query.return_value.filter.return_value.first.return_value = None

        # Test available slot formatting
        result = service.check_slot_availability(slot_id=123, instructor_id=1)

        assert result["available"] == True
        assert "slot_info" in result
        slot_info = result["slot_info"]
        assert slot_info["date"] == (date.today() + timedelta(days=1)).isoformat()
        assert slot_info["start_time"] == "09:00:00"
        assert slot_info["end_time"] == "10:00:00"
        assert slot_info["instructor_id"] == 1

    def test_conflict_data_formatting(self):
        """Test how conflict data is formatted for response."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Create mock booking with all fields
        mock_booking = Mock(spec=Booking)
        mock_booking.id = 123
        mock_booking.service_name = "Piano Lessons"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.student = Mock(full_name="John Doe")

        mock_slot = Mock()
        mock_slot.start_time = time(10, 0)
        mock_slot.end_time = time(11, 0)
        mock_booking.availability_slot = mock_slot

        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [mock_booking]

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

    def test_week_data_grouping(self):
        """Test how weekly data is grouped by date."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Create mock data for multiple days
        mock_data = []
        base_date = date.today()

        for day_offset in range(3):
            slot_date = base_date + timedelta(days=day_offset)
            for hour in [9, 14]:
                mock_slot = MagicMock()
                mock_slot.date = slot_date
                mock_slot.id = day_offset * 10 + hour
                mock_slot.start_time = time(hour, 0)
                mock_slot.end_time = time(hour + 1, 0)
                mock_slot.booking_id = 100 + mock_slot.id
                mock_slot.student_id = 1
                mock_slot.service_name = "Test Service"
                mock_slot.status = BookingStatus.CONFIRMED
                mock_data.append(mock_slot)

        db.query.return_value.join.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = (
            mock_data
        )

        result = service.get_booked_slots_for_week(instructor_id=1, week_start=base_date)

        # Should be grouped by date
        assert len(result) == 3  # 3 days with bookings

        for date_str, slots in result.items():
            assert isinstance(slots, list)
            assert len(slots) == 2  # 2 slots per day

            # Verify slot format
            for slot in slots:
                assert "slot_id" in slot
                assert "start_time" in slot
                assert "end_time" in slot
                assert "booking_id" in slot

    def test_empty_result_handling(self):
        """Test handling of empty query results."""
        db = Mock(spec=Session)
        service = ConflictChecker(db)

        # Mock empty results for all query chains
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []
        db.query.return_value.join.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )

        # Test empty conflicts
        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )

        assert conflicts == []

        # Test empty week data
        week_data = service.get_booked_slots_for_week(instructor_id=1, week_start=date.today())

        assert week_data == {}


class TestConflictCheckerValidationRules:
    """Test validation rules and business constraints."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock database."""
        mock_db = Mock(spec=Session)
        return ConflictChecker(mock_db)

    def test_past_date_validation_rules(self, service):
        """Test business rules for past date validation."""
        # Mock other validations to pass
        with patch.object(service, "validate_time_range") as mock_time_val, patch.object(
            service, "check_minimum_advance_booking"
        ) as mock_advance, patch.object(service, "check_blackout_date") as mock_blackout, patch.object(
            service, "check_booking_conflicts"
        ) as mock_conflicts:
            mock_time_val.return_value = {"valid": True, "duration_minutes": 60}
            mock_advance.return_value = {"valid": True}
            mock_blackout.return_value = False
            mock_conflicts.return_value = []

            # Test past date
            result = service.validate_booking_constraints(
                instructor_id=1,
                booking_date=date.today() - timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(15, 0),
            )

            assert result["valid"] == False
            assert any("past" in error.lower() for error in result["errors"])

            # Test today with past time
            result = service.validate_booking_constraints(
                instructor_id=1,
                booking_date=date.today(),
                start_time=time(8, 0),  # Assuming it's after 8 AM when test runs
                end_time=time(9, 0),
            )

            # This might be valid or invalid depending on current time
            # The business rule is documented in the assertion
            if datetime.now().time() > time(8, 0):
                assert result["valid"] == False
                assert any("past" in error.lower() for error in result["errors"])

    def test_service_duration_validation_rules(self, service):
        """Test service-specific duration validation."""
        # Mock service with duration override
        mock_service = Mock(spec=Service)
        mock_service.duration_override = 90  # 90 minutes required
        mock_service.is_active = True

        service.db.query.return_value.filter.return_value.first.return_value = mock_service

        # Mock other validations
        with patch.object(service, "validate_time_range") as mock_time_val, patch.object(
            service, "check_minimum_advance_booking"
        ) as mock_advance, patch.object(service, "check_blackout_date") as mock_blackout, patch.object(
            service, "check_booking_conflicts"
        ) as mock_conflicts:
            mock_time_val.return_value = {"valid": True, "duration_minutes": 60}  # Only 60 minutes
            mock_advance.return_value = {"valid": True}
            mock_blackout.return_value = False
            mock_conflicts.return_value = []

            # Test service duration mismatch
            result = service.validate_booking_constraints(
                instructor_id=1,
                booking_date=date.today() + timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(15, 0),  # 60 minutes but service needs 90
                service_id=1,
            )

            assert result["valid"] == True  # Valid but with warning
            assert len(result["warnings"]) >= 1
            assert any("90 minutes" in warning for warning in result["warnings"])

    def test_blackout_date_priority_rules(self, service):
        """Test that blackout dates take priority over other validations."""
        # Mock blackout date exists
        with patch.object(service, "validate_time_range") as mock_time_val, patch.object(
            service, "check_minimum_advance_booking"
        ) as mock_advance, patch.object(service, "check_blackout_date") as mock_blackout, patch.object(
            service, "check_booking_conflicts"
        ) as mock_conflicts:
            mock_time_val.return_value = {"valid": True, "duration_minutes": 60}
            mock_advance.return_value = {"valid": True}
            mock_blackout.return_value = True  # Blackout date
            mock_conflicts.return_value = []

            result = service.validate_booking_constraints(
                instructor_id=1,
                booking_date=date.today() + timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(15, 0),
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
        mock_bookings = [
            # Overlapping cases
            self._create_mock_booking(time(9, 0), time(11, 0)),  # Overlaps at start
            self._create_mock_booking(time(11, 0), time(13, 0)),  # Overlaps at end
            self._create_mock_booking(time(10, 30), time(11, 30)),  # Contained within
            self._create_mock_booking(time(9, 0), time(13, 0)),  # Contains check range
            # Non-overlapping cases
            self._create_mock_booking(time(8, 0), time(9, 30)),  # Before
            self._create_mock_booking(time(12, 30), time(14, 0)),  # After
        ]

        # Mock the database query
        service.db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = (
            mock_bookings
        )

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

        mock_bookings = [
            # Edge cases
            self._create_mock_booking(time(9, 0), time(10, 0)),  # Ends exactly at start
            self._create_mock_booking(time(11, 0), time(12, 0)),  # Starts exactly at end
            self._create_mock_booking(time(10, 0), time(11, 0)),  # Exact same time
        ]

        service.db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = (
            mock_bookings
        )

        conflicts = service.check_booking_conflicts(
            instructor_id=1, check_date=date.today(), start_time=check_start, end_time=check_end
        )

        # Adjacent slots should not conflict, only exact overlap
        assert len(conflicts) == 1
        assert conflicts[0]["start_time"] == "10:00:00"
        assert conflicts[0]["end_time"] == "11:00:00"

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

        service.db.query.return_value.filter.return_value.first.return_value = mock_profile

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
        assert result["hours_until_booking"] >= 0

    def test_past_booking_validation(self, service):
        """Test validation for past dates/times."""
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2

        service.db.query.return_value.filter.return_value.first.return_value = mock_profile

        # Test past date
        yesterday = date.today() - timedelta(days=1)
        result = service.check_minimum_advance_booking(
            instructor_id=1, booking_date=yesterday, booking_time=time(10, 0)
        )

        # Even with low advance requirement, past dates should fail
        assert result["valid"] == False

    def test_slot_availability_logic_without_database(self, service):
        """Test slot availability checking logic."""
        # Create mock slot with availability
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(10, 0)
        mock_slot.end_time = time(11, 0)

        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.instructor_id = 1
        mock_availability.date = date.today() + timedelta(days=1)
        mock_slot.availability = mock_availability

        service.db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_slot

        # Mock no booking found (available)
        service.db.query.return_value.filter.return_value.first.return_value = None

        # Test available slot
        result = service.check_slot_availability(slot_id=1, instructor_id=1)

        assert result["available"] == True
        assert "slot_info" in result

    def test_past_slot_validation(self, service):
        """Test that past slots cannot be booked."""
        # Create mock slot in the past
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(10, 0)

        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.instructor_id = 1
        mock_availability.date = date.today() - timedelta(days=1)  # Yesterday
        mock_slot.availability = mock_availability

        # First mock call returns the slot
        service.db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_slot

        # Second mock call (for booking check) returns None - no booking exists
        booking_query_mock = Mock()
        booking_query_mock.first.return_value = None

        # Set up the mock to handle the two different query chains
        def side_effect(*args):
            if args[0] == AvailabilitySlot:
                # First query for slot
                mock_chain = Mock()
                mock_chain.options.return_value.filter.return_value.first.return_value = mock_slot
                return mock_chain
            elif args[0] == Booking:
                # Second query for booking
                mock_chain = Mock()
                mock_chain.filter.return_value.first.return_value = None  # No booking
                return mock_chain
            return Mock()

        service.db.query.side_effect = side_effect

        result = service.check_slot_availability(slot_id=1)

        assert result["available"] == False
        assert "past" in result["reason"]

    def test_comprehensive_validation_aggregation(self, service):
        """Test how multiple validation errors are aggregated."""
        # Mock profile
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.db.query.return_value.filter.return_value.first.return_value = mock_profile

        # Mock no conflicts
        service.db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

        # Mock service query to return None (service not found)
        def query_side_effect(*args):
            if len(args) > 0 and args[0] == Service:
                # Service query
                mock_chain = Mock()
                mock_chain.filter.return_value.first.return_value = None  # Service not found
                return mock_chain
            else:
                # Default mock chain for other queries
                mock_chain = Mock()
                mock_chain.filter.return_value.first.return_value = mock_profile
                mock_chain.join.return_value.join.return_value.filter.return_value.all.return_value = []
                return mock_chain

        service.db.query.side_effect = query_side_effect

        # Past date with invalid time range
        past_date = date.today() - timedelta(days=1)

        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=past_date,
            start_time=time(10, 0),
            end_time=time(9, 0),  # Invalid time range
            service_id=999,
        )

        assert result["valid"] == False
        assert len(result["errors"]) >= 2  # At least time range and past date errors
        assert any("past" in error.lower() for error in result["errors"])
        assert any("after start time" in error for error in result["errors"])

    def test_blackout_date_checking(self, service):
        """Test blackout date validation logic."""
        # Mock blackout date exists
        mock_blackout = Mock(spec=BlackoutDate)
        service.db.query.return_value.filter.return_value.first.return_value = mock_blackout

        # Check blackout date
        is_blackout = service.check_blackout_date(instructor_id=1, target_date=date.today() + timedelta(days=5))

        assert is_blackout == True

        # Mock no blackout
        service.db.query.return_value.filter.return_value.first.return_value = None

        is_blackout = service.check_blackout_date(instructor_id=1, target_date=date.today() + timedelta(days=5))

        assert is_blackout == False

    def test_service_duration_validation(self, service):
        """Test service-specific duration validation."""
        # Mock service with duration override
        mock_service = Mock(spec=Service)
        mock_service.duration_override = 90  # 90 minutes required
        mock_service.is_active = True

        service.db.query.return_value.filter.return_value.first.return_value = mock_service

        # Mock other validations to pass
        service.validate_time_range = Mock(return_value={"valid": True, "duration_minutes": 60})
        service.check_minimum_advance_booking = Mock(return_value={"valid": True})
        service.check_blackout_date = Mock(return_value=False)
        service.check_booking_conflicts = Mock(return_value=[])

        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),  # Only 60 minutes
            service_id=1,
        )

        assert result["valid"] == True  # Valid but with warning
        assert len(result["warnings"]) == 1
        assert "requires 90 minutes" in result["warnings"][0]

    def test_find_overlapping_slots_algorithm(self, service):
        """Test the algorithm for finding overlapping slots."""
        # Create mock slots
        mock_slots = [
            self._create_mock_slot(1, time(9, 0), time(10, 0)),
            self._create_mock_slot(2, time(10, 0), time(11, 0)),
            self._create_mock_slot(3, time(11, 0), time(12, 0)),
            self._create_mock_slot(4, time(14, 0), time(15, 0)),
        ]

        service.db.query.return_value.join.return_value.filter.return_value.all.return_value = mock_slots

        # Mock bookings query for checking booked status
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Check for overlaps with 9:30-11:30
        overlapping = service.find_overlapping_slots(
            instructor_id=1, target_date=date.today(), start_time=time(9, 30), end_time=time(11, 30)
        )

        # Should find slots 1, 2, and 3
        assert len(overlapping) == 3
        assert overlapping[0]["slot_id"] == 1
        assert overlapping[1]["slot_id"] == 2
        assert overlapping[2]["slot_id"] == 3

    def test_error_message_formatting(self, service):
        """Test that error messages are properly formatted."""
        # Mock profile
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.db.query.return_value.filter.return_value.first.return_value = mock_profile

        # Mock empty bookings
        service.db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

        # Test with multiple validation failures
        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=date.today() - timedelta(days=1),  # Past
            start_time=time(14, 0),
            end_time=time(14, 0),  # Same time
            service_id=None,
        )

        assert result["valid"] == False
        # Check error messages are clear and actionable
        assert all(isinstance(error, str) for error in result["errors"])
        assert all(len(error) > 10 for error in result["errors"])  # Not empty messages

    def test_query_efficiency_indicators(self, service):
        """Test that methods indicate what data they need (for repository pattern)."""
        # This helps document what each method needs from the database

        # Mock the query chain to return empty list
        service.db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

        # check_booking_conflicts needs: Booking + AvailabilitySlot + InstructorAvailability
        service.check_booking_conflicts(1, date.today(), time(10, 0), time(11, 0))

        # Verify it queries Booking model
        service.db.query.assert_called_with(Booking)

        # Reset for next test
        service.db.reset_mock()

        # check_slot_availability needs: AvailabilitySlot with joinedload
        service.db.query.return_value.options.return_value.filter.return_value.first.return_value = None
        service.check_slot_availability(1)
        service.db.query.assert_called_with(AvailabilitySlot)

    # Helper methods
    def _create_mock_booking(self, start: time, end: time) -> Mock:
        """Create a mock booking with slot."""
        booking = Mock(spec=Booking)
        booking.id = 1
        booking.student = Mock(full_name="Test Student")
        booking.service_name = "Test Service"
        booking.status = BookingStatus.CONFIRMED

        slot = Mock(spec=AvailabilitySlot)
        slot.start_time = start
        slot.end_time = end
        booking.availability_slot = slot

        return booking

    def _create_mock_slot(self, slot_id: int, start: time, end: time) -> Mock:
        """Create a mock availability slot."""
        slot = Mock(spec=AvailabilitySlot)
        slot.id = slot_id
        slot.start_time = start
        slot.end_time = end
        # Don't set booking_id - it doesn't exist!
        return slot


class TestConflictCheckerEdgeCases:
    """Test edge cases and error conditions in business logic."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock database."""
        mock_db = Mock(spec=Session)
        return ConflictChecker(mock_db)

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
        service.db.query.return_value.filter.return_value.first.return_value = None

        result = service.check_minimum_advance_booking(
            instructor_id=999, booking_date=date.today() + timedelta(days=1), booking_time=time(10, 0)
        )

        assert result["valid"] == False
        assert "not found" in result["reason"]

    def test_inactive_service_validation(self, service):
        """Test validation with inactive service."""
        # Mock inactive service
        mock_service = Mock(spec=Service)
        mock_service.is_active = False

        # Query returns nothing because we filter by is_active=True
        service.db.query.return_value.filter.return_value.first.return_value = None

        # Mock other validations
        service.validate_time_range = Mock(return_value={"valid": True, "duration_minutes": 60})
        service.check_minimum_advance_booking = Mock(return_value={"valid": True})
        service.check_blackout_date = Mock(return_value=False)
        service.check_booking_conflicts = Mock(return_value=[])

        result = service.validate_booking_constraints(
            instructor_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_id=1,
        )

        assert result["valid"] == False
        assert any("not found or no longer available" in error for error in result["errors"])
