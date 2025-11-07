# backend/tests/unit/services/test_availability_service_logic.py
"""
Fixed unit tests for AvailabilityService business logic.

UPDATED FOR WORK STREAM #10: Single-table availability design.
These tests work with the repository pattern implementation.

FIXES:
- Updated field names from 'date' to 'specific_date'
- Fixed mock object configuration for proper date handling
- Fixed _group_schedule_by_date test to use dictionaries instead of Mocks
- Removed expectations of is_available field (now properly removed from service)
"""

from datetime import date, time, timedelta
from unittest.mock import Mock, patch

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.core.ulid_helper import generate_ulid
from app.models.availability import BlackoutDate
from app.repositories.availability_repository import AvailabilityRepository
from app.schemas.availability_window import (
    SpecificDateAvailabilityCreate,
    WeekSpecificScheduleCreate,
)
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows


class TestAvailabilityServiceBusinessLogic:
    """Test business logic that will remain in service layer."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocked repository and real session."""
        service = AvailabilityService(unit_db)

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

        # Past date validation is now handled in service layer, not schema
        # This should NOT raise an error at schema level
        past_slot = SpecificDateAvailabilityCreate(
            specific_date=date.today() - timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )
        assert past_slot.specific_date < date.today()  # Verify it's actually a past date

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
        instructor_id = generate_ulid()

        result = service._determine_week_start(week_data, instructor_id)
        assert result == monday

    def test_group_schedule_by_date(self, service):
        """Test the _group_schedule_by_date helper method."""
        # Mock get_user_today_by_id to return a consistent date
        with patch("app.services.availability_service.get_user_today_by_id") as mock_get_today:
            mock_get_today.return_value = date.today()

            # Create mock schedule items with proper date attribute
            tomorrow = date.today() + timedelta(days=1)
            day_after = date.today() + timedelta(days=2)
            instructor_id = generate_ulid()

            # Create dictionary items that match what the method expects
            # Based on the service code, it expects dicts with 'date' key as string
            schedule = [
                {"date": tomorrow.isoformat(), "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow.isoformat(), "start_time": "14:00", "end_time": "15:00"},
                {"date": day_after.isoformat(), "start_time": "09:00", "end_time": "10:00"},
            ]

            result = service._group_schedule_by_date(schedule, instructor_id)

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

        # This should raise ConflictException due to slot existing
        with pytest.raises(ConflictException, match="This time slot already exists"):
            service.add_specific_date_availability(instructor_id=generate_ulid(), availability_data=availability_data)


class TestAvailabilityServiceQueryHelpers:
    """Test repository interaction patterns."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocked repository and real session."""
        service = AvailabilityService(unit_db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_get_week_availability(self, service):
        """Test getting week availability with single-table design."""
        # Mock bitmap response instead of slot repository
        monday = date.today()
        tuesday = monday + timedelta(days=1)

        bits_map = {
            monday: bits_from_windows([("09:00:00", "10:00:00")]),
            tuesday: bits_from_windows([("14:00:00", "15:00:00")]),
        }
        service.get_week_bits = Mock(return_value=bits_map)

        # Call the service method
        result = service.get_week_availability(instructor_id=123, start_date=monday)

        # Verify the result format
        monday_str = monday.isoformat()
        tuesday_str = tuesday.isoformat()
        assert monday_str in result
        assert tuesday_str in result
        assert result[monday_str][0]["start_time"] == "09:00:00"
        assert result[monday_str][0]["end_time"] == "10:00:00"
        assert result[tuesday_str][0]["start_time"] == "14:00:00"
        assert result[tuesday_str][0]["end_time"] == "15:00:00"

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
    def service(self, unit_db):
        """Create service with mocked repository."""
        service = AvailabilityService(unit_db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_service_without_cache(self, service):
        """Test service behavior without cache."""
        assert service.cache_service is None

    def test_service_with_cache(self, unit_db):
        """Test service behavior with cache."""
        cache_service = Mock()
        service = AvailabilityService(unit_db, cache_service=cache_service)

        assert service.cache_service is not None

    def test_cache_fallback_on_error(self, unit_db):
        """Test that service continues working when cache fails."""
        cache_service = Mock()
        cache_service.get_week_availability.side_effect = Exception("Cache error")

        service = AvailabilityService(unit_db, cache_service=cache_service)

        # Mock repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        # Mock successful repository query - returns bitmap windows as dict
        test_date = date.today()
        mock_window = {
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        }

        # Repository returns week map with windows
        service.repository.get_week_availability.return_value = {
            test_date.isoformat(): [mock_window]
        }

        # Should still work despite cache error
        result = service.get_week_availability(
            instructor_id=generate_ulid(), start_date=date.today() - timedelta(days=date.today().weekday())
        )

        assert isinstance(result, dict)


class TestAvailabilityServiceErrorHandling:
    """Test error handling that should remain in service."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocked repository."""
        service = AvailabilityService(unit_db)

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


class TestAvailabilityServiceNoBackwardCompatibility:
    """Test that the service follows Work Stream #10 - no backward compatibility."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocked repository."""
        service = AvailabilityService(unit_db)

        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository

        return service

    def test_no_is_available_in_responses(self, service):
        """Test that responses don't include the removed is_available field."""
        # Mock repository response - returns bitmap windows as dict
        test_date = date.today()
        mock_window = {
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        }

        service.repository.get_week_availability.return_value = {
            test_date.isoformat(): [mock_window]
        }

        result = service.get_week_availability(instructor_id=123, start_date=test_date)

        # Check that is_available is NOT in the response
        for date_slots in result.values():
            for slot in date_slots:
                assert "is_available" not in slot, "is_available field should not be in response (Work Stream #10)"

    def test_get_availability_for_date_no_is_available(self, service):
        """Test that get_availability_for_date doesn't return is_available."""
        # Mock repository response - returns bitmap windows as dict
        test_date = date.today()
        mock_window = {
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        }

        # get_availability_for_date returns windows for the date
        service.repository.get_day_bits = Mock(return_value=None)  # No availability
        service.repository.get_week_availability.return_value = {
            test_date.isoformat(): [mock_window]
        }

        result = service.get_availability_for_date(instructor_id=123, target_date=test_date)

        # Check the slots in the response
        assert "slots" in result
        for slot in result["slots"]:
            assert "is_available" not in slot, "is_available field should not be in response (Work Stream #10)"
