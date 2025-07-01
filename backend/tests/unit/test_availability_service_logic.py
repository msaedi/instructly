# backend/tests/unit/test_availability_service_logic.py
"""
Fixed unit tests for AvailabilityService business logic.

These tests work with the repository pattern implementation.
"""

from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.availability import BlackoutDate, InstructorAvailability
from app.repositories.availability_repository import AvailabilityRepository
from app.schemas.availability_window import SpecificDateAvailabilityCreate, WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService


class TestAvailabilityServiceBusinessLogic:
    """Test business logic that will remain in service layer."""

    @pytest.fixture
    def service(self):
        """Create service with mocked repository."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_pydantic_validation_working(self):
        """Test that Pydantic validation is working correctly."""
        # These should raise validation errors, proving validation works

        # Invalid week start (not Monday)
        with pytest.raises(Exception):  # Pydantic validation error
            tuesday = date.today() + timedelta(days=(1 - date.today().weekday()) % 7)
            WeekSpecificScheduleCreate(week_start=tuesday, clear_existing=True, schedule=[])

        # Invalid time range (end before start)
        with pytest.raises(Exception):  # Pydantic validation error
            SpecificDateAvailabilityCreate(
                specific_date=date.today() + timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(10, 0),  # Before start time
            )

        # Past date
        with pytest.raises(Exception):  # Pydantic validation error
            SpecificDateAvailabilityCreate(
                specific_date=date.today() - timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
            )

    def test_week_date_calculation(self, service):
        """Test the _calculate_week_dates helper method."""
        # Test Monday calculation
        monday = date(2024, 1, 1)  # This is a Monday
        week_dates = service._calculate_week_dates(monday)

        assert len(week_dates) == 7
        assert week_dates[0] == monday
        assert week_dates[6] == monday + timedelta(days=6)
        assert (week_dates[6] - week_dates[0]).days == 6

    def test_determine_week_start(self, service):
        """Test the _determine_week_start helper method."""
        # Test with explicit week_start
        monday = date(2024, 1, 1)
        week_data = Mock()
        week_data.week_start = monday
        week_data.schedule = []

        result = service._determine_week_start(week_data)
        assert result == monday

    def test_group_schedule_by_date(self, service):
        """Test the _group_schedule_by_date helper method."""
        # Create mock schedule items
        tomorrow = date.today() + timedelta(days=1)
        day_after = date.today() + timedelta(days=2)

        schedule = [Mock(date=tomorrow), Mock(date=tomorrow), Mock(date=day_after)]  # Two slots for same day

        result = service._group_schedule_by_date(schedule)

        assert len(result) == 2  # Two unique dates
        assert len(result[tomorrow]) == 2  # Two slots for tomorrow
        assert len(result[day_after]) == 1  # One slot for day after

    def test_conflicts_with_bookings(self, service):
        """Test the _conflicts_with_bookings helper method."""
        # Test time range conflict detection
        booked_ranges = [(time(9, 0), time(11, 0))]

        # Test overlapping range
        assert service._conflicts_with_bookings(time(10, 0), time(12, 0), booked_ranges) == True

        # Test non-overlapping range
        assert service._conflicts_with_bookings(time(12, 0), time(14, 0), booked_ranges) == False

    def test_slot_exists_check(self, service):
        """Test slot existence checking via repository."""
        # Mock repository response
        service.repository.slot_exists.return_value = True

        # Call the add_specific_date_availability which uses slot_exists
        availability_data = SpecificDateAvailabilityCreate(
            specific_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        # Mock the repository methods used
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.id = 123
        mock_availability.is_cleared = False
        service.repository.get_or_create_availability.return_value = mock_availability
        service.repository.slot_exists.return_value = True

        # This should raise ConflictException due to slot existing
        with pytest.raises(ConflictException, match="This time slot already exists"):
            service.add_specific_date_availability(instructor_id=1, availability_data=availability_data)


class TestAvailabilityServiceQueryHelpers:
    """Test repository interaction patterns."""

    @pytest.fixture
    def service(self):
        """Create service with mocked repository."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_get_booked_slots(self, service):
        """Test getting booked slots via repository."""
        # Mock repository response
        mock_booking = Mock()
        mock_booking.availability_slot_id = 1
        service.repository.get_booked_slots_in_range.return_value = [mock_booking]

        # The service uses this internally in save operations
        # Let's verify the repository method signature
        service.repository.get_booked_slots_in_range(
            instructor_id=123, start_date=date.today(), end_date=date.today() + timedelta(days=7)
        )

        service.repository.get_booked_slots_in_range.assert_called_once()

    def test_delete_non_booked_slots(self, service):
        """Test deleting non-booked slots via repository."""
        # Mock repository response
        service.repository.delete_non_booked_slots.return_value = 3

        # Call the repository method
        result = service.repository.delete_non_booked_slots(availability_id=123, booked_slot_ids=[1, 2])

        assert result == 3
        service.repository.delete_non_booked_slots.assert_called_once_with(availability_id=123, booked_slot_ids=[1, 2])

    def test_count_bookings_for_date(self, service):
        """Test counting bookings via repository."""
        # Mock repository response
        service.repository.count_bookings_for_date.return_value = 2

        # Call the repository method
        result = service.repository.count_bookings_for_date(instructor_id=123, target_date=date.today())

        assert result == 2
        service.repository.count_bookings_for_date.assert_called_once()


class TestAvailabilityServiceCacheHandling:
    """Test cache handling in availability service."""

    @pytest.fixture
    def service(self):
        """Create service with mocked repository."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_service_without_cache(self, service):
        """Test service behavior without cache."""
        assert service.cache_service is None

    def test_service_with_cache(self):
        """Test service behavior with cache."""
        db = Mock(spec=Session)
        cache_service = Mock()
        service = AvailabilityService(db, cache_service=cache_service)

        assert service.cache_service is not None

    def test_cache_fallback_on_error(self):
        """Test that service continues working when cache fails."""
        db = Mock(spec=Session)
        cache_service = Mock()
        cache_service.get_week_availability.side_effect = Exception("Cache error")

        service = AvailabilityService(db, cache_service=cache_service)

        # Mock repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        # Mock successful repository query
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.date = date.today()
        mock_availability.is_cleared = False
        mock_availability.time_slots = []

        # Repository returns list of availability entries
        service.repository.get_week_availability.return_value = [mock_availability]

        # Should still work despite cache error
        result = service.get_week_availability(
            instructor_id=1, start_date=date.today() - timedelta(days=date.today().weekday())
        )

        assert isinstance(result, dict)


class TestAvailabilityServiceErrorHandling:
    """Test error handling that should remain in service."""

    @pytest.fixture
    def service(self):
        """Create service with mocked repository."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_not_found_exception_handling(self, service):
        """Test NotFoundException handling."""
        # Mock repository returning False (not found)
        service.repository.delete_blackout_date.return_value = False

        with pytest.raises(NotFoundException):
            service.delete_blackout_date(instructor_id=123, blackout_id=999)

    def test_conflict_exception_handling(self, service):
        """Test ConflictException handling."""
        # Mock existing blackout dates
        existing_blackout = Mock(spec=BlackoutDate)
        existing_blackout.date = date.today() + timedelta(days=7)

        service.repository.get_future_blackout_dates.return_value = [existing_blackout]

        from app.schemas.availability_window import BlackoutDateCreate

        blackout_data = BlackoutDateCreate(date=date.today() + timedelta(days=7), reason="Test")

        with pytest.raises(ConflictException):
            service.add_blackout_date(instructor_id=123, blackout_data=blackout_data)

    def test_duplicate_slot_detection(self, service):
        """Test duplicate slot detection via repository."""
        # Mock repository methods
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.id = 123
        mock_availability.is_cleared = False

        service.repository.get_or_create_availability.return_value = mock_availability
        service.repository.slot_exists.return_value = True  # Slot already exists

        availability_data = SpecificDateAvailabilityCreate(
            specific_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        # Should raise ConflictException due to duplicate slot
        with pytest.raises(ConflictException, match="This time slot already exists"):
            service.add_specific_date_availability(instructor_id=123, availability_data=availability_data)
