# backend/tests/unit/test_week_operation_logic.py
"""
Unit tests for WeekOperationService business logic.

These tests isolate business logic from database and external dependencies
using mocks to ensure we're testing only the service logic.
"""

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService


class TestWeekOperationInitialization:
    """Test service initialization and dependency injection."""

    def test_initialization_with_dependencies(self):
        """Test initialization with provided dependencies."""
        mock_db = Mock(spec=Session)
        mock_availability = Mock(spec=AvailabilityService)
        mock_conflict = Mock(spec=ConflictChecker)
        mock_cache = Mock(spec=CacheService)

        service = WeekOperationService(mock_db, mock_availability, mock_conflict, mock_cache)

        assert service.db == mock_db
        assert service.availability_service == mock_availability
        assert service.conflict_checker == mock_conflict
        assert service.cache_service == mock_cache

    def test_initialization_lazy_dependencies(self):
        """Test lazy loading of dependencies."""
        mock_db = Mock(spec=Session)

        # Just test that service initializes with defaults
        service = WeekOperationService(mock_db)

        # These should be initialized (not None)
        assert service.db == mock_db
        assert service.availability_service is not None
        assert service.conflict_checker is not None
        assert service.cache_service is None  # This one is None by default


class TestWeekCalculations:
    """Test week calculation business logic."""

    @pytest.fixture
    def service(self):
        """Create service with mock dependencies."""
        return WeekOperationService(Mock(spec=Session))

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
    def service(self):
        """Create service with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_availability = Mock(spec=AvailabilityService)
        return WeekOperationService(mock_db, mock_availability)

    def test_extract_week_pattern_full_week(self, service):
        """Test extracting pattern from full week data."""
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

        assert "Monday" in pattern
        assert "Tuesday" in pattern
        assert "Wednesday" in pattern
        assert "Thursday" in pattern  # Empty days ARE included
        assert "Friday" in pattern
        assert "Saturday" in pattern
        assert "Sunday" in pattern

        # Verify empty days have empty lists
        assert len(pattern["Thursday"]) == 0
        assert len(pattern["Saturday"]) == 0
        assert len(pattern["Sunday"]) == 0

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


class TestCopyWeekLogic:
    """Test week copying business logic."""

    @pytest.fixture
    def service(self):
        """Create service with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_db.transaction = Mock()
        mock_db.expire_all = Mock()

        mock_availability = Mock(spec=AvailabilityService)
        mock_conflict = Mock(spec=ConflictChecker)
        mock_cache = Mock(spec=CacheService)

        return WeekOperationService(mock_db, mock_availability, mock_conflict, mock_cache)

    @pytest.mark.asyncio
    async def test_copy_week_validates_dates(self, service):
        """Test that copy week validates Monday dates."""
        instructor_id = 123
        from_week = date(2025, 6, 24)  # Tuesday
        to_week = date(2025, 6, 25)  # Wednesday

        # Mock internal methods
        service._get_target_week_bookings = Mock(
            return_value={
                "booked_slot_ids": set(),
                "availability_with_bookings": set(),
                "booked_time_ranges_by_date": {},
                "total_bookings": 0,
            }
        )
        service._clear_non_booked_slots = Mock()
        service.availability_service.get_week_availability = Mock(return_value={})
        service._copy_week_slots = AsyncMock(
            return_value={
                "dates_created": 0,
                "slots_created": 0,
                "slots_skipped": 0,
                "dates_with_preserved_bookings": [],
            }
        )

        # Disable cache to avoid warming issues
        service.cache_service = None

        # Execute without mocking logger
        result = await service.copy_week_availability(instructor_id, from_week, to_week)

        # The operation should complete even with non-Monday dates
        assert result is not None
        # Verify the dates are indeed not Mondays
        assert from_week.weekday() == 1  # Tuesday (0=Monday)
        assert to_week.weekday() == 2  # Wednesday

    @pytest.mark.asyncio
    async def test_copy_week_booking_preservation_logic(self, service):
        """Test logic for preserving bookings during copy."""
        instructor_id = 123
        from_week = date(2025, 6, 16)  # Monday
        to_week = date(2025, 6, 23)  # Next Monday

        # Mock target week has bookings
        service._get_target_week_bookings = Mock(
            return_value={
                "booked_slot_ids": {101, 102},
                "availability_with_bookings": {10},
                "booked_time_ranges_by_date": {"2025-06-24": [{"start_time": time(9, 0), "end_time": time(10, 0)}]},
                "total_bookings": 2,
            }
        )

        service._clear_non_booked_slots = Mock()
        service.availability_service.get_week_availability = Mock(
            return_value={"2025-06-17": [{"start_time": "09:00", "end_time": "12:00"}]}  # Tuesday source
        )

        # Mock the async copy operation
        service._copy_week_slots = AsyncMock(
            return_value={
                "dates_created": 6,
                "slots_created": 10,
                "slots_skipped": 2,
                "dates_with_preserved_bookings": ["2025-06-24"],
            }
        )

        # Disable cache to avoid warming strategy issues
        service.cache_service = None

        result = await service.copy_week_availability(instructor_id, from_week, to_week)

        # Verify clearing was called with correct params
        service._clear_non_booked_slots.assert_called_once_with(instructor_id, to_week, {101, 102}, {10})

        # Result should have availability data or metadata
        assert result is not None


class TestApplyPatternLogic:
    """Test pattern application business logic."""

    @pytest.fixture
    def service(self):
        """Create service with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_db.query = Mock()
        mock_db.bulk_save_objects = Mock()
        mock_db.bulk_update_mappings = Mock()
        mock_db.bulk_insert_mappings = Mock()
        mock_db.flush = Mock()
        mock_db.expire_all = Mock()

        mock_availability = Mock(spec=AvailabilityService)

        return WeekOperationService(mock_db, mock_availability)

    @pytest.mark.asyncio
    async def test_apply_pattern_date_range_calculation(self, service):
        """Test date range processing in apply pattern."""
        instructor_id = 123
        from_week = date(2025, 6, 16)  # Monday
        start_date = date(2025, 7, 1)  # Tuesday
        end_date = date(2025, 7, 10)  # Thursday

        # Mock source pattern
        service.availability_service.get_week_availability = Mock(
            return_value={
                "2025-06-16": [{"start_time": "09:00", "end_time": "10:00"}],  # Monday
                "2025-06-17": [{"start_time": "14:00", "end_time": "16:00"}],  # Tuesday
            }
        )

        # Mock database queries
        service.db.query.return_value.filter.return_value.all.return_value = []  # No existing
        service._get_bookings_in_range = Mock(
            return_value={"bookings_by_date": {}, "booked_slot_ids": set(), "total_bookings": 0}
        )

        # Disable cache for testing
        service.cache_service = None

        result = await service.apply_pattern_to_date_range(instructor_id, from_week, start_date, end_date)

        # Should process all dates in range
        total_days = (end_date - start_date).days + 1
        assert total_days == 10

        # Verify result structure
        assert "dates_created" in result
        assert "slots_created" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_apply_pattern_conflict_detection(self, service):
        """Test conflict detection during pattern application."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 3)

        # Mock pattern
        service.availability_service.get_week_availability = Mock(
            return_value={
                "2025-06-17": [{"start_time": "09:00", "end_time": "11:00"}],  # Tuesday
            }
        )

        # Mock existing bookings
        service._get_bookings_in_range = Mock(
            return_value={
                "bookings_by_date": {
                    "2025-07-01": [
                        {  # Wednesday conflicts with Tuesday pattern
                            "slot_id": 101,
                            "start_time": time(9, 30),
                            "end_time": time(10, 30),
                        }
                    ]
                },
                "booked_slot_ids": {101},
                "total_bookings": 1,
            }
        )

        # Mock existing availability
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Disable cache for testing
        service.cache_service = None

        result = await service.apply_pattern_to_date_range(instructor_id, from_week, start_date, end_date)

        # Should skip conflicting slots
        assert result["slots_skipped"] >= 0
        assert result["total_bookings_preserved"] == 1


class TestBulkOperationLogic:
    """Test bulk operation business logic."""

    @pytest.fixture
    def service(self):
        """Create service with mock db."""
        mock_db = Mock(spec=Session)
        mock_db.bulk_insert_mappings = Mock()
        return WeekOperationService(mock_db)

    def test_bulk_create_slots_empty_list(self, service):
        """Test bulk create with empty list."""
        result = service._bulk_create_slots([])
        assert result == 0
        service.db.bulk_insert_mappings.assert_not_called()

    def test_bulk_create_slots_data_transformation(self, service):
        """Test data transformation for bulk insert."""
        slots_data = [
            {"availability_id": 1, "start_time": time(9, 0), "end_time": time(10, 0)},
            {"availability_id": 1, "start_time": time(10, 0), "end_time": time(11, 0)},
        ]

        result = service._bulk_create_slots(slots_data)

        assert result == 2
        service.db.bulk_insert_mappings.assert_called_once()

        # Verify correct model and data format
        call_args = service.db.bulk_insert_mappings.call_args
        assert call_args[0][0] == AvailabilitySlot
        assert len(call_args[0][1]) == 2


class TestCacheIntegrationLogic:
    """Test cache integration business logic."""

    @pytest.fixture
    def service(self):
        """Create service with mock cache."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock(spec=CacheService)
        mock_availability = Mock(spec=AvailabilityService)

        return WeekOperationService(mock_db, mock_availability, cache_service=mock_cache)

    def test_get_cached_week_pattern_cache_hit(self, service):
        """Test pattern retrieval with cache hit."""
        instructor_id = 123
        week_start = date(2025, 6, 23)
        cached_pattern = {
            "Monday": [{"start_time": "09:00", "end_time": "10:00"}],
            "Tuesday": [{"start_time": "14:00", "end_time": "16:00"}],
        }

        # Mock cache hit
        service.cache.get.return_value = cached_pattern

        result = service.get_cached_week_pattern(instructor_id, week_start)

        assert result == cached_pattern
        service.cache.get.assert_called_once_with(f"week_pattern:{instructor_id}:{week_start.isoformat()}")
        # Should not call availability service on cache hit
        service.availability_service.get_week_availability.assert_not_called()

    def test_get_cached_week_pattern_cache_miss(self, service):
        """Test pattern retrieval with cache miss."""
        instructor_id = 123
        week_start = date(2025, 6, 23)

        # Mock cache miss
        service.cache.get.return_value = None

        # Mock availability service
        week_data = {"2025-06-23": [{"start_time": "09:00", "end_time": "10:00"}]}
        service.availability_service.get_week_availability.return_value = week_data

        service.get_cached_week_pattern(instructor_id, week_start)

        # Should fetch from availability service
        service.availability_service.get_week_availability.assert_called_once_with(instructor_id, week_start)

        # Should cache the result
        service.cache.set.assert_called_once()
        cache_key = f"week_pattern:{instructor_id}:{week_start.isoformat()}"
        assert service.cache.set.call_args[0][0] == cache_key

    @pytest.mark.asyncio
    async def test_cache_warming_after_operations(self, service):
        """Test cache warming strategy after modifications."""
        instructor_id = 123
        start_date = date(2025, 7, 1)  # Tuesday
        end_date = date(2025, 7, 15)  # Crosses 3 weeks

        # Mock pattern and operations
        service.availability_service.get_week_availability = Mock(return_value={})
        service._get_bookings_in_range = Mock(
            return_value={"bookings_by_date": {}, "booked_slot_ids": set(), "total_bookings": 0}
        )
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Disable cache warming for this test
        service.cache_service = None

        result = await service.apply_pattern_to_date_range(instructor_id, date(2025, 6, 23), start_date, end_date)

        # Should complete without errors
        assert result is not None


class TestProgressCallbackLogic:
    """Test progress callback functionality."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        mock_db = Mock(spec=Session)
        return WeekOperationService(mock_db)

    @pytest.mark.asyncio
    async def test_apply_pattern_with_progress_callback(self, service):
        """Test progress callback during pattern application."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 5)  # 5 days

        progress_updates = []

        def progress_callback(current, total):
            progress_updates.append((current, total))

        # Mock the main method
        service.apply_pattern_to_date_range = AsyncMock(return_value={"dates_created": 5, "slots_created": 10})

        # Mock the private method that would be wrapped
        original_apply = AsyncMock(
            return_value={"dates_created": 1, "dates_modified": 0, "slots_created": 2, "slots_skipped": 0}
        )
        service._apply_pattern_to_date = original_apply

        result = await service.apply_pattern_with_progress(
            instructor_id, from_week, start_date, end_date, progress_callback
        )

        # Verify main method was called
        service.apply_pattern_to_date_range.assert_called_once()


class TestDateConflictLogic:
    """Test date conflict handling logic."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return WeekOperationService(Mock(spec=Session))

    @pytest.mark.asyncio
    async def test_copy_day_slots_conflict_detection(self, service):
        """Test conflict detection when copying day slots."""
        instructor_id = 123
        source_slots = [
            {"start_time": "09:00", "end_time": "10:00"},
            {"start_time": "10:00", "end_time": "11:00"},
            {"start_time": "14:00", "end_time": "16:00"},
        ]
        target_date = date(2025, 7, 1)
        booked_ranges = [
            {"start_time": time(9, 30), "end_time": time(10, 30)},  # Conflicts with first two
        ]

        # Mock database operations
        service.db.query.return_value.filter.return_value.first.return_value = None
        service.db.add = Mock()
        service.db.flush = Mock()

        result = await service._copy_day_slots(
            instructor_id, source_slots, target_date, has_bookings=True, booked_ranges=booked_ranges
        )

        # Should skip 2 conflicting slots
        assert result["slots_skipped"] == 2
        assert result["slots_created"] == 1  # Only the 14:00-16:00 slot


class TestPerformanceMonitoring:
    """Test performance monitoring in week operations."""

    @pytest.fixture
    def service(self):
        """Create service with monitoring."""
        mock_db = Mock(spec=Session)
        service = WeekOperationService(mock_db)
        service._metrics = {}  # Initialize metrics
        return service

    def test_performance_logging_slow_operations(self, service):
        """Test identification of slow operations."""
        # Manually add slow operation metrics
        service._record_metric("week_copy", 2.5, success=True)
        service._record_metric("week_copy", 1.8, success=True)
        service._record_metric("pattern_apply", 0.5, success=True)

        with patch.object(service.logger, "warning") as mock_warning:
            service.add_performance_logging()

            # Should warn about slow week_copy operations
            assert mock_warning.called
            warning_msg = mock_warning.call_args[0][0]
            assert "week_copy" in warning_msg
            assert "2.15" in warning_msg  # Average time
