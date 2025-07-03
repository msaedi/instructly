# backend/tests/unit/test_availability_service_logic.py
"""
Fixed unit tests for AvailabilityService business logic.

UPDATED FOR WORK STREAM #10: Single-table availability design.
These tests work with the repository pattern implementation.
"""

from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.availability import AvailabilitySlot, BlackoutDate
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

    def test_slot_exists_check(self, service):
        """Test slot existence checking via repository."""
        # Mock repository response
        service.repository.slot_exists.return_value = True

        # Call the add_specific_date_availability which uses slot_exists
        availability_data = SpecificDateAvailabilityCreate(
            specific_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        # Mock the repository methods used
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

    def test_get_week_availability(self, service):
        """Test getting week availability with single-table design."""
        # Mock repository response - now returns AvailabilitySlot objects directly
        mock_slot1 = Mock(spec=AvailabilitySlot)
        mock_slot1.date = date.today()
        mock_slot1.start_time = time(9, 0)
        mock_slot1.end_time = time(10, 0)

        mock_slot2 = Mock(spec=AvailabilitySlot)
        mock_slot2.date = date.today()
        mock_slot2.start_time = time(14, 0)
        mock_slot2.end_time = time(15, 0)

        service.repository.get_week_availability.return_value = [mock_slot1, mock_slot2]

        # Call the service method
        result = service.get_week_availability(instructor_id=123, start_date=date.today())

        # Verify the result format
        date_str = date.today().isoformat()
        assert date_str in result
        assert len(result[date_str]) == 2
        assert result[date_str][0]["start_time"] == "09:00:00"
        assert result[date_str][0]["end_time"] == "10:00:00"

    def test_delete_slots_by_dates(self, service):
        """Test deleting slots by dates via repository."""
        # Mock repository response
        service.repository.delete_slots_by_dates.return_value = 3

        # Call the repository method
        result = service.repository.delete_slots_by_dates(
            instructor_id=123, dates=[date.today(), date.today() + timedelta(days=1)]
        )

        assert result == 3
        service.repository.delete_slots_by_dates.assert_called_once()

    def test_count_available_slots(self, service):
        """Test counting available slots via repository."""
        # Mock repository response
        service.repository.count_available_slots.return_value = 5

        # Call the repository method
        result = service.repository.count_available_slots(
            instructor_id=123, start_date=date.today(), end_date=date.today() + timedelta(days=7)
        )

        assert result == 5
        service.repository.count_available_slots.assert_called_once()


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

        # Mock successful repository query - now returns slots directly
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.date = date.today()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        # Repository returns list of slots
        service.repository.get_week_availability.return_value = [mock_slot]

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
        service.repository.slot_exists.return_value = True  # Slot already exists

        availability_data = SpecificDateAvailabilityCreate(
            specific_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        # Should raise ConflictException due to duplicate slot
        with pytest.raises(ConflictException, match="This time slot already exists"):
            service.add_specific_date_availability(instructor_id=123, availability_data=availability_data)
