# backend/tests/services/test_availability_services.py
"""
Basic test suite for availability services.

UPDATED FOR WORK STREAM #10: Single-table availability design.

Run with: pytest backend/tests/services/test_availability_services.py -v
"""

from datetime import date, time
from unittest.mock import MagicMock, Mock

import pytest

from app.core.exceptions import ValidationException
from app.models.availability import AvailabilitySlot
from app.repositories.availability_repository import AvailabilityRepository
from app.services.availability_service import AvailabilityService
from app.services.conflict_checker import ConflictChecker
from app.services.slot_manager import SlotManager
from app.services.week_operation_service import WeekOperationService


class TestAvailabilityService:
    """Test AvailabilityService core functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance with mock DB and repository."""
        service = AvailabilityService(mock_db)
        # Mock the repository
        mock_repository = Mock(spec=AvailabilityRepository)
        service.repository = mock_repository
        return service

    def test_get_week_availability_empty(self, service, mock_db):
        """Test getting empty week availability."""
        # Setup - mock repository instead of database
        service.repository.get_week_availability.return_value = []

        # Execute
        result = service.get_week_availability(instructor_id=1, start_date=date(2025, 6, 16))  # Monday

        # Assert
        assert result == {}
        # Verify repository was called
        service.repository.get_week_availability.assert_called_once()

    def test_get_week_availability_with_slots(self, service, mock_db):
        """Test getting week with availability slots."""
        # Setup mock data - now using single-table design
        mock_slot1 = Mock(spec=AvailabilitySlot)
        mock_slot1.date = date(2025, 6, 16)
        mock_slot1.start_time = time(9, 0)
        mock_slot1.end_time = time(10, 0)

        mock_slot2 = Mock(spec=AvailabilitySlot)
        mock_slot2.date = date(2025, 6, 16)
        mock_slot2.start_time = time(14, 0)
        mock_slot2.end_time = time(15, 0)

        # Mock repository response - returns list of slots directly
        service.repository.get_week_availability.return_value = [mock_slot1, mock_slot2]

        # Execute
        result = service.get_week_availability(instructor_id=1, start_date=date(2025, 6, 16))

        # Assert
        assert "2025-06-16" in result
        assert len(result["2025-06-16"]) == 2
        assert result["2025-06-16"][0]["start_time"] == "09:00:00"
        assert result["2025-06-16"][0]["end_time"] == "10:00:00"
        assert result["2025-06-16"][0]["is_available"] is True
        assert result["2025-06-16"][1]["start_time"] == "14:00:00"
        assert result["2025-06-16"][1]["end_time"] == "15:00:00"


class TestSlotManager:
    """Test SlotManager functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        # Setup transaction context
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=None)
        return db

    @pytest.fixture
    def mock_conflict_checker(self):
        """Create mock conflict checker."""
        return MagicMock(spec=ConflictChecker)

    @pytest.fixture
    def service(self, mock_db, mock_conflict_checker):
        """Create service instance."""
        service = SlotManager(mock_db, mock_conflict_checker)
        # Add mocked repositories
        service.repository = Mock()
        service.availability_repository = Mock()
        return service

    def test_validate_time_alignment_valid(self, service):
        """Test time alignment validation with valid time."""
        # Should not raise exception
        service._validate_time_alignment(time(9, 0))
        service._validate_time_alignment(time(9, 15))
        service._validate_time_alignment(time(9, 30))
        service._validate_time_alignment(time(9, 45))

    def test_validate_time_alignment_invalid(self, service):
        """Test time alignment validation with invalid time."""
        with pytest.raises(ValidationException) as exc_info:
            service._validate_time_alignment(time(9, 17))

        assert "must align to 15-minute blocks" in str(exc_info.value)

    def test_create_slot_with_single_table_design(self, service, mock_db, mock_conflict_checker):
        """Test slot creation with single-table design."""
        # Setup
        instructor_id = 1
        target_date = date(2025, 6, 20)

        mock_conflict_checker.validate_time_range.return_value = {"valid": True}
        service.availability_repository.slot_exists.return_value = False

        # Mock the slot creation
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 123
        mock_slot.instructor_id = instructor_id
        mock_slot.date = target_date
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        service.repository.create.return_value = mock_slot
        service.repository.get_slot_by_id.return_value = mock_slot

        # Mock get_slots_for_date_ordered to return empty list (for merge check)
        service.repository.get_slots_for_date_ordered.return_value = []

        # Execute
        result = service.create_slot(
            instructor_id=instructor_id,
            target_date=target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            validate_conflicts=False,  # Layer independence
            auto_merge=False,  # Disable auto merge to avoid the len() issue
        )

        # Assert
        assert result.id == 123
        assert result.instructor_id == instructor_id
        assert result.date == target_date


class TestWeekOperationService:
    """Test WeekOperationService functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        db.flush = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance."""
        mock_availability_service = MagicMock()
        mock_conflict_checker = MagicMock()
        return WeekOperationService(mock_db, mock_availability_service, mock_conflict_checker)

    def test_calculate_week_dates(self, service):
        """Test week date calculation."""
        monday = date(2025, 6, 16)
        dates = service.calculate_week_dates(monday)

        assert len(dates) == 7
        assert dates[0] == monday
        assert dates[6] == date(2025, 6, 22)  # Sunday

    def test_extract_week_pattern(self, service):
        """Test pattern extraction from week availability."""
        week_availability = {
            "2025-06-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}],
            "2025-06-17": [{"start_time": "14:00:00", "end_time": "16:00:00"}],
        }

        pattern = service._extract_week_pattern(week_availability, date(2025, 6, 16))

        # Use proper day names
        assert "Monday" in pattern
        assert "Tuesday" in pattern
        assert pattern["Monday"] == week_availability["2025-06-16"]
        assert pattern["Tuesday"] == week_availability["2025-06-17"]


class TestConflictChecker:
    """Test ConflictChecker functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance."""
        service = ConflictChecker(mock_db)
        # Add mock repository
        service.repository = Mock()
        return service

    def test_validate_time_range_valid(self, service):
        """Test valid time range validation."""
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(10, 0))

        assert result["valid"] is True
        assert result["duration_minutes"] == 60

    def test_validate_time_range_invalid_order(self, service):
        """Test invalid time range (end before start)."""
        result = service.validate_time_range(start_time=time(10, 0), end_time=time(9, 0))

        assert result["valid"] is False
        assert "End time must be after start time" in result["reason"]

    def test_validate_time_range_too_short(self, service):
        """Test time range that's too short."""
        result = service.validate_time_range(start_time=time(9, 0), end_time=time(9, 15), min_duration_minutes=30)

        assert result["valid"] is False
        assert "at least 30 minutes" in result["reason"]

    def test_check_slot_availability_with_single_table(self, service, mock_db):
        """Test slot availability checking with single-table design."""
        from datetime import timedelta

        slot_id = 123

        # Use a future date to ensure slot is not in the past
        future_date = date.today() + timedelta(days=7)

        # Mock slot with instructor_id and date directly
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = slot_id
        mock_slot.instructor_id = 1
        mock_slot.date = future_date
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        service.repository.get_slot_with_availability.return_value = mock_slot

        # Mock the Booking model and query
        from app.models.booking import Booking

        mock_booking_query = Mock()
        mock_booking_filter = Mock()
        mock_booking_query.filter.return_value = mock_booking_filter
        mock_booking_filter.first.return_value = None  # No booking found

        # Set up the mock to return our query mock when Booking is queried
        def query_side_effect(model):
            if model == Booking:
                return mock_booking_query
            return Mock()

        mock_db.query.side_effect = query_side_effect

        # Also need to set service.db for the query
        service.db = mock_db

        # Execute
        result = service.check_slot_availability(slot_id=slot_id)

        # Assert
        assert result["available"] is True
        assert result["slot_info"]["instructor_id"] == 1
        assert result["slot_info"]["date"] == future_date.isoformat()


# Run with: pytest backend/tests/services/test_availability_services.py -v
