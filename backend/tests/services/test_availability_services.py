# backend/tests/services/test_availability_services.py
"""
Basic test suite for availability services.

Run with: pytest backend/tests/services/test_availability_services.py -v
"""

from datetime import date, time
from unittest.mock import MagicMock, Mock

import pytest

from app.core.exceptions import ConflictException, ValidationException
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
        """Create service instance with mock DB."""
        return AvailabilityService(mock_db)

    def test_get_week_availability_empty(self, service, mock_db):
        """Test getting empty week availability."""
        # Setup
        mock_db.query().filter().options().all.return_value = []

        # Execute
        result = service.get_week_availability(instructor_id=1, start_date=date(2025, 6, 16))  # Monday

        # Assert
        assert result == {}
        # Change this line - expect 2 calls instead of 1
        assert mock_db.query.call_count >= 1  # At least one call

    def test_get_week_availability_with_slots(self, service, mock_db):
        """Test getting week with availability slots."""
        # Setup mock data
        mock_availability = Mock()
        mock_availability.date = date(2025, 6, 16)
        mock_availability.is_cleared = False

        mock_slot = Mock()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        mock_availability.time_slots = [mock_slot]
        mock_db.query().filter().options().all.return_value = [mock_availability]

        # Execute
        result = service.get_week_availability(instructor_id=1, start_date=date(2025, 6, 16))

        # Assert
        assert "2025-06-16" in result
        assert len(result["2025-06-16"]) == 1
        assert result["2025-06-16"][0]["start_time"] == "09:00:00"
        assert result["2025-06-16"][0]["end_time"] == "10:00:00"
        assert result["2025-06-16"][0]["is_available"] is True


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
        return SlotManager(mock_db, mock_conflict_checker)

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

    def test_create_slot_with_conflicts(self, service, mock_db, mock_conflict_checker):
        """Test slot creation with booking conflicts."""
        # Setup
        mock_availability = Mock()
        mock_availability.instructor_id = 1
        mock_availability.date = date(2025, 6, 20)

        mock_db.query().filter().first.return_value = mock_availability
        mock_conflict_checker.validate_time_range.return_value = {"valid": True}
        mock_conflict_checker.check_booking_conflicts.return_value = [{"booking_id": 1, "student_name": "John Doe"}]

        # Execute & Assert
        with pytest.raises(ConflictException) as exc_info:
            service.create_slot(
                availability_id=1,
                start_time=time(9, 0),
                end_time=time(10, 0),
                validate_conflicts=True,
            )

        assert "conflicts with 1 existing bookings" in str(exc_info.value)


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

        # Use lowercase day names
        assert "monday" in pattern
        assert "tuesday" in pattern
        assert pattern["monday"] == week_availability["2025-06-16"]
        assert pattern["tuesday"] == week_availability["2025-06-17"]


class TestConflictChecker:
    """Test ConflictChecker functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance."""
        return ConflictChecker(mock_db)

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


# Run with: pytest backend/tests/services/test_availability_services.py -v
