# backend/tests/unit/services/test_week_operation_logic.py
"""
Unit tests for WeekOperationService business logic.

Tests initialization, week calculations, and pattern extraction.
"""

from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.week_operation_repository import WeekOperationRepository
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService


class TestWeekOperationInitialization:
    """Test service initialization and dependency injection."""

    def test_initialization_with_dependencies(self, unit_db):
        """Test initialization with provided dependencies."""
        mock_availability = Mock(spec=AvailabilityService)
        mock_conflict = Mock(spec=ConflictChecker)
        mock_cache = Mock(spec=CacheService)
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)

        service = WeekOperationService(
            unit_db, mock_availability, mock_conflict, mock_cache, mock_repository, mock_availability_repository
        )

        assert service.db is unit_db
        assert service.availability_service == mock_availability
        assert service.conflict_checker == mock_conflict
        assert service.cache_service == mock_cache
        assert service.repository == mock_repository
        assert service.availability_repository == mock_availability_repository

    def test_initialization_lazy_dependencies(self, unit_db):
        """Test lazy loading of dependencies."""
        # Just test that service initializes with defaults
        service = WeekOperationService(unit_db)

        # These should be initialized (not None)
        assert service.db is unit_db
        assert service.availability_service is not None
        assert service.conflict_checker is not None
        assert service.cache_service is None  # This one is None by default
        assert service.repository is not None  # Repository should be created
        assert service.availability_repository is not None  # Should be created


class TestWeekCalculations:
    """Test week calculation business logic."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mock dependencies."""
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)
        service = WeekOperationService(
            unit_db, repository=mock_repository, availability_repository=mock_availability_repository
        )
        service.event_outbox_repository = Mock()
        return service

    def test_calculate_week_dates_from_monday(self, service):
        """Test calculating week dates starting from Monday."""
        monday = date(2025, 6, 23)  # Monday
        week_dates = service.calculate_week_dates(monday)

        assert len(week_dates) == 7
        assert week_dates[0] == monday
        assert week_dates[1] == date(2025, 6, 24)  # Tuesday
        assert week_dates[2] == date(2025, 6, 25)  # Wednesday
        assert week_dates[3] == date(2025, 6, 26)  # Thursday
        assert week_dates[4] == date(2025, 6, 27)  # Friday
        assert week_dates[5] == date(2025, 6, 28)  # Saturday
        assert week_dates[6] == date(2025, 6, 29)  # Sunday

    def test_calculate_week_dates_from_other_day(self, service):
        """Test calculating week dates from non-Monday."""
        thursday = date(2025, 6, 26)  # Thursday
        week_dates = service.calculate_week_dates(thursday)

        # Should still return 7 dates starting from the given date
        assert len(week_dates) == 7
        assert week_dates[0] == thursday
        assert week_dates[6] == thursday + timedelta(days=6)


class TestWeekPatternExtraction:
    """Test week pattern extraction logic."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mock dependencies."""
        mock_availability = Mock(spec=AvailabilityService)
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)
        service = WeekOperationService(
            unit_db,
            mock_availability,
            repository=mock_repository,
            availability_repository=mock_availability_repository,
        )
        service.event_outbox_repository = Mock()
        return service

    def test_extract_week_pattern_full_week(self, service):
        """Test extracting pattern from full week data.

        In single-table design, days without slots don't exist in the pattern.
        This is correct behavior - no need to track empty days.
        """
        week_start = date(2025, 6, 23)  # Monday
        week_availability = {
            "2025-06-23": [{"start_time": "09:00", "end_time": "10:00"}],  # Monday
            "2025-06-24": [{"start_time": "14:00", "end_time": "16:00"}],  # Tuesday
            "2025-06-25": [{"start_time": "10:00", "end_time": "12:00"}],  # Wednesday
            "2025-06-26": [],  # Thursday - no slots
            "2025-06-27": [{"start_time": "09:00", "end_time": "17:00"}],  # Friday
            "2025-06-28": [],  # Saturday
            "2025-06-29": [],  # Sunday
        }

        pattern = service._extract_week_pattern(week_availability, week_start)

        # Only days WITH SLOTS appear in the pattern
        assert "Monday" in pattern
        assert "Tuesday" in pattern
        assert "Wednesday" in pattern
        assert "Friday" in pattern

        # Days without slots DO NOT appear in pattern (this is correct!)
        assert "Thursday" not in pattern
        assert "Saturday" not in pattern
        assert "Sunday" not in pattern

        assert len(pattern["Monday"]) == 1
        assert pattern["Monday"][0]["start_time"] == "09:00"
        assert len(pattern["Friday"]) == 1
        assert pattern["Friday"][0]["end_time"] == "17:00"

    def test_extract_week_pattern_partial_week(self, service):
        """Test extracting pattern from partial week data."""
        week_start = date(2025, 6, 23)
        week_availability = {
            "2025-06-23": [{"start_time": "09:00", "end_time": "10:00"}],
            "2025-06-25": [{"start_time": "14:00", "end_time": "15:00"}],
            # Missing other days
        }

        pattern = service._extract_week_pattern(week_availability, week_start)

        assert len(pattern) == 2
        assert "Monday" in pattern
        assert "Wednesday" in pattern
        assert "Tuesday" not in pattern

    def test_get_week_pattern_integration(self, service):
        """Test get_week_pattern with availability service integration."""
        instructor_id = 123
        week_start = date(2025, 6, 23)

        # Mock availability service response
        mock_week_data = {
            "2025-06-23": [{"start_time": "09:00", "end_time": "12:00"}],
            "2025-06-24": [{"start_time": "14:00", "end_time": "17:00"}],
        }
        service.availability_service.get_week_availability.return_value = mock_week_data

        pattern = service.get_week_pattern(instructor_id, week_start)

        # Verify service was called
        service.availability_service.get_week_availability.assert_called_once_with(instructor_id, week_start)

        # Verify pattern extraction
        assert "Monday" in pattern
        assert "Tuesday" in pattern
        assert pattern["Monday"][0]["start_time"] == "09:00"
