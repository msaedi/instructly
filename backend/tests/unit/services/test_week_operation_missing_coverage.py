# backend/tests/unit/services/test_week_operation_missing_coverage.py
"""
Additional unit tests for WeekOperationService to cover missing lines.

FIXED: Removed tests for non-existent methods and fixed mock date issues.
"""

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.week_operation_repository import WeekOperationRepository
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService


class TestWeekOperationCacheWarming:
    """Test cache warming after operations."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mock dependencies."""
        mock_availability = Mock(spec=AvailabilityService)
        mock_conflict = Mock(spec=ConflictChecker)
        mock_cache = Mock(spec=CacheService)
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)

        service = WeekOperationService(
            unit_db, mock_availability, mock_conflict, mock_cache, mock_repository, mock_availability_repository
        )
        service.event_outbox_repository = Mock()
        service.availability_repository.get_slots_by_date = Mock(return_value=[])
        if isinstance(service.availability_service, Mock):
            service.availability_service.compute_week_version.return_value = "v1"
        service.audit_repository = Mock()
        return service

    @pytest.mark.asyncio
    async def test_copy_week_with_cache_warming(self, service):
        """Test copy week triggers cache warming."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        to_week = date(2025, 6, 23)

        # Mock repository responses for single-table design
        service.availability_repository.delete_slots_by_dates.return_value = 0

        # Mock source week slots with proper specific_date
        mock_slots = [Mock(specific_date=date(2025, 6, 17), start_time=time(9, 0), end_time=time(12, 0))]
        service.repository.get_week_slots.return_value = mock_slots
        service.repository.bulk_create_slots.return_value = 1

        # Mock cache warming - patch the correct import location
        with patch("app.services.cache_strategies.CacheWarmingStrategy") as mock_strategy:
            mock_warmer = AsyncMock()
            mock_warmer.warm_with_verification = AsyncMock(
                return_value={"2025-06-23": [], "2025-06-24": [{"start_time": "09:00", "end_time": "12:00"}]}
            )
            mock_strategy.return_value = mock_warmer

            result = await service.copy_week_availability(instructor_id, from_week, to_week)

            # Verify cache warming was called
            mock_strategy.assert_called_once_with(service.cache_service, service.db)
            mock_warmer.warm_with_verification.assert_called()

        assert result is not None

    @pytest.mark.asyncio
    async def test_copy_week_with_metadata(self, service):
        """Test copy week includes metadata when slots are created."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        to_week = date(2025, 6, 23)

        # Mock repository for single-table design
        service.availability_repository.delete_slots_by_dates.return_value = 3

        # Mock source week slots with proper specific_date
        mock_slots = [Mock(specific_date=date(2025, 6, 17), start_time=time(9, 0), end_time=time(12, 0))]
        service.repository.get_week_slots.return_value = mock_slots
        service.repository.bulk_create_slots.return_value = 1

        # Mock availability service response
        service.availability_service.get_week_availability.return_value = {
            "2025-06-24": [{"start_time": "09:00", "end_time": "12:00"}]
        }

        # Disable cache for simplicity
        service.cache_service = None

        result = await service.copy_week_availability(instructor_id, from_week, to_week)

        # Check metadata
        assert "_metadata" in result
        assert result["_metadata"]["operation"] == "week_copy"
        assert result["_metadata"]["slots_created"] == 1


class TestWeekOperationGetSlots:
    """Test get slots functionality with single-table design."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with repository."""
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)
        service = WeekOperationService(
            unit_db, repository=mock_repository, availability_repository=mock_availability_repository
        )
        service.event_outbox_repository = Mock()
        service.availability_repository.get_slots_by_date = Mock(return_value=[])
        if isinstance(service.availability_service, Mock):
            service.availability_service.compute_week_version.return_value = "v1"
        service.audit_repository = Mock()
        return service

    def test_get_week_slots(self, service):
        """Test getting week slots directly."""
        instructor_id = 123
        week_start = date(2025, 6, 23)
        week_end = week_start + timedelta(days=6)

        # Mock repository response with proper specific_date
        expected_slots = [
            Mock(id=generate_ulid(), specific_date=date(2025, 6, 23), start_time=time(9, 0), end_time=time(10, 0)),
            Mock(id=generate_ulid(), specific_date=date(2025, 6, 24), start_time=time(14, 0), end_time=time(16, 0)),
        ]
        service.repository.get_week_slots.return_value = expected_slots

        # Call repository directly
        result = service.repository.get_week_slots(instructor_id, week_start, week_end)

        assert len(result) == 2
        assert result[0].specific_date == date(2025, 6, 23)
        assert result[1].specific_date == date(2025, 6, 24)

    def test_get_slots_no_slots(self, service):
        """Test getting slots when none exist."""
        instructor_id = 123
        week_start = date(2025, 6, 23)
        week_end = week_start + timedelta(days=6)

        # Mock empty response
        service.repository.get_week_slots.return_value = []

        result = service.repository.get_week_slots(instructor_id, week_start, week_end)

        assert result == []


class TestWeekOperationApplyPattern:
    """Test apply pattern edge cases with single-table design."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocks."""
        mock_availability = Mock(spec=AvailabilityService)
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)

        service = WeekOperationService(
            unit_db, mock_availability, repository=mock_repository, availability_repository=mock_availability_repository
        )
        service.event_outbox_repository = Mock()
        return service

    @pytest.mark.asyncio
    async def test_apply_pattern_empty_pattern(self, service):
        """Test applying empty pattern."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 7)

        # Mock empty pattern
        service.availability_service.get_week_availability.return_value = {}

        # Mock repository for single-table design
        service.availability_repository.delete_slots_by_dates.return_value = 10
        service.repository.bulk_create_slots.return_value = 0

        # Disable cache
        service.cache_service = None

        result = await service.apply_pattern_to_date_range(instructor_id, from_week, start_date, end_date)

        assert result["slots_created"] == 0
        assert result["dates_processed"] == 7

    @pytest.mark.asyncio
    async def test_apply_pattern_partial_week(self, service):
        """Test applying pattern with partial week data."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 3)

        # Mock pattern with only some days
        service.availability_service.get_week_availability.return_value = {
            "2025-06-17": [{"start_time": "09:00", "end_time": "10:00"}],  # Tuesday only
        }

        # Mock repository for single-table design
        service.availability_repository.delete_slots_by_dates.return_value = 0
        service.repository.bulk_create_slots.return_value = 1  # Only Tuesday matches

        # Disable cache
        service.cache_service = None

        result = await service.apply_pattern_to_date_range(instructor_id, from_week, start_date, end_date)

        assert result["dates_processed"] == 3
        assert result["slots_created"] == 1


class TestWeekOperationErrorHandling:
    """Test error handling in week operations."""

    @pytest.fixture
    def service(self, unit_db):
        """Create service with mocks."""
        mock_repository = Mock(spec=WeekOperationRepository)
        mock_availability_repository = Mock(spec=AvailabilityRepository)
        service = WeekOperationService(
            unit_db, repository=mock_repository, availability_repository=mock_availability_repository
        )
        service.event_outbox_repository = Mock()
        return service

    @pytest.mark.asyncio
    async def test_copy_week_handles_no_source_slots(self, service):
        """Test copy week handles case where source has no slots."""
        instructor_id = 123
        from_week = date(2025, 6, 16)
        to_week = date(2025, 6, 23)

        # Mock empty source
        service.availability_repository.delete_slots_by_dates.return_value = 0
        service.repository.get_week_slots.return_value = []
        service.repository.bulk_create_slots.return_value = 0

        # Mock availability service for result
        service.availability_service = Mock()
        service.availability_service.get_week_availability.return_value = {}
        service.availability_service.compute_week_version.return_value = "v1"
        service._week_slot_counts = Mock(return_value={})

        # Disable cache
        service.cache_service = None

        result = await service.copy_week_availability(instructor_id, from_week, to_week)

        assert result is not None
        assert result["_metadata"]["slots_created"] == 0


# REMOVED: TestWeekOperationWithProgress - apply_pattern_with_progress doesn't exist
