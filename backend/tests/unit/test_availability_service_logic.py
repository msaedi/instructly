# backend/tests/unit/test_availability_service_logic.py
"""
Fixed unit tests for AvailabilityService business logic.

These tests work with the actual service implementation.
"""

from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.schemas.availability_window import SpecificDateAvailabilityCreate, WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService


class TestAvailabilityServiceBusinessLogic:
    """Test business logic that will remain in service layer."""

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

    def test_week_date_calculation(self):
        """Test the _calculate_week_dates helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Test Monday calculation
        monday = date(2024, 1, 1)  # This is a Monday
        week_dates = service._calculate_week_dates(monday)

        assert len(week_dates) == 7
        assert week_dates[0] == monday
        assert week_dates[6] == monday + timedelta(days=6)
        assert (week_dates[6] - week_dates[0]).days == 6

    def test_determine_week_start(self):
        """Test the _determine_week_start helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Test with explicit week_start
        monday = date(2024, 1, 1)
        week_data = Mock()
        week_data.week_start = monday
        week_data.schedule = []

        result = service._determine_week_start(week_data)
        assert result == monday

    def test_group_schedule_by_date(self):
        """Test the _group_schedule_by_date helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Create mock schedule items
        tomorrow = date.today() + timedelta(days=1)
        day_after = date.today() + timedelta(days=2)

        schedule = [Mock(date=tomorrow), Mock(date=tomorrow), Mock(date=day_after)]  # Two slots for same day

        result = service._group_schedule_by_date(schedule)

        assert len(result) == 2  # Two unique dates
        assert len(result[tomorrow]) == 2  # Two slots for tomorrow
        assert len(result[day_after]) == 1  # One slot for day after

    def test_conflicts_with_bookings(self):
        """Test the _conflicts_with_bookings helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Test time range conflict detection
        booked_ranges = [(time(9, 0), time(11, 0))]

        # Test overlapping range
        assert service._conflicts_with_bookings(time(10, 0), time(12, 0), booked_ranges) == True

        # Test non-overlapping range
        assert service._conflicts_with_bookings(time(12, 0), time(14, 0), booked_ranges) == False

    def test_slot_exists_check(self):
        """Test the _slot_exists helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the query chain
        db.query.return_value.filter.return_value.first.return_value = Mock()

        result = service._slot_exists(availability_id=123, start_time=time(9, 0), end_time=time(10, 0))

        assert result == True

        # Test when slot doesn't exist
        db.query.return_value.filter.return_value.first.return_value = None

        result = service._slot_exists(availability_id=123, start_time=time(11, 0), end_time=time(12, 0))

        assert result == False


class TestAvailabilityServiceQueryHelpers:
    """Test query helper methods."""

    def test_get_booked_slots(self):
        """Test the _get_booked_slots helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the query result
        mock_slot = Mock(spec=AvailabilitySlot)
        db.query.return_value.join.return_value.filter.return_value.all.return_value = [mock_slot]

        result = service._get_booked_slots(availability_id=123)

        assert result == [mock_slot]

    def test_delete_non_booked_slots(self):
        """Test the _delete_non_booked_slots helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock booked slots
        booked_slots = [Mock(id=1), Mock(id=2)]

        # Mock the delete query
        mock_query = Mock()
        db.query.return_value.filter.return_value = mock_query
        mock_query.filter.return_value.delete.return_value = 3  # 3 slots deleted

        result = service._delete_non_booked_slots(availability_id=123, booked_slots=booked_slots)

        assert result == 3

    def test_count_bookings_for_date(self):
        """Test the _count_bookings_for_date helper method."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock the query chain
        db.query.return_value.join.return_value.join.return_value.filter.return_value.count.return_value = 2

        result = service._count_bookings_for_date(instructor_id=123, target_date=date.today())

        assert result == 2


class TestAvailabilityServiceCacheHandling:
    """Test cache handling in availability service."""

    def test_service_without_cache(self):
        """Test service behavior without cache."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)  # No cache service

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

        # Mock successful database query
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.date = date.today()
        mock_availability.is_cleared = False
        mock_availability.time_slots = []

        db.query.return_value.filter.return_value.options.return_value.all.return_value = [mock_availability]

        # Should still work despite cache error
        result = service.get_week_availability(
            instructor_id=1, start_date=date.today() - timedelta(days=date.today().weekday())
        )

        assert isinstance(result, dict)


class TestAvailabilityServiceErrorHandling:
    """Test error handling that should remain in service."""

    def test_not_found_exception_handling(self):
        """Test NotFoundException handling."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock not found scenario
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundException):
            service.delete_blackout_date(instructor_id=123, blackout_id=999)  # Non-existent ID

    def test_conflict_exception_handling(self):
        """Test ConflictException handling."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock existing blackout date
        existing_blackout = Mock()
        db.query.return_value.filter.return_value.first.return_value = existing_blackout

        from app.schemas.availability_window import BlackoutDateCreate

        blackout_data = BlackoutDateCreate(date=date.today() + timedelta(days=7), reason="Test")

        with pytest.raises(ConflictException):
            service.add_blackout_date(instructor_id=123, blackout_data=blackout_data)

    def test_duplicate_slot_detection(self):
        """Test duplicate slot detection."""
        db = Mock(spec=Session)
        service = AvailabilityService(db)

        # Mock existing availability with duplicate slot
        existing_availability = Mock(spec=InstructorAvailability)
        existing_availability.is_cleared = False

        # Mock duplicate slot found
        db.query.return_value.filter.return_value.first.return_value = Mock()

        result = service._check_duplicate_slot(
            availability=existing_availability, start_time=time(9, 0), end_time=time(10, 0)
        )

        assert result == True
