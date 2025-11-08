# backend/tests/integration/services/test_week_operation_service_db.py
"""
Integration tests for WeekOperationService database operations.

These tests verify actual database behavior including transactions,
cascades, and complex multi-table operations.

UPDATED FOR WORK STREAM #10: Single-table availability design.
- No more InstructorAvailability table
- Direct slot operations only
- No cascade operations needed
"""

from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

# AvailabilitySlot removed - bitmap-only storage now
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService
from app.utils.bitset import bits_from_windows


class TestWeekOperationServiceTransactions:
    """Test transaction handling in week operations."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service with real dependencies."""
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        return WeekOperationService(db, availability_service, conflict_checker)


class TestWeekOperationBulkOperations:
    """Test bulk database operations with single-table design."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service instance."""
        return WeekOperationService(db)

    @pytest.mark.asyncio
    async def test_apply_pattern_bulk_operations(
        self,
        db: Session,
        service: WeekOperationService,
        unique_instructor: tuple[str, str],
        clear_week_bits,
    ):
        """Test bulk operations in apply_pattern_to_date_range."""
        # Create source pattern with single-table design
        instructor_id, _ = unique_instructor
        today = date.today()
        days_until_next_monday = (7 - today.weekday()) % 7
        if days_until_next_monday == 0:
            days_until_next_monday = 7
        pattern_week = today + timedelta(days=days_until_next_monday)
        clear_week_bits(instructor_id, pattern_week, weeks=6)
        repo = AvailabilityDayRepository(db)
        day_windows: dict = {}
        for i in range(3):  # Mon, Tue, Wed
            day_date = pattern_week + timedelta(days=i)
            day_windows[day_date] = [
                (f"{hour:02d}:00:00", f"{hour + 1:02d}:00:00") for hour in [9, 11, 14]
            ]

        repo.upsert_week(
            instructor_id,
            [(day, bits_from_windows(windows)) for day, windows in day_windows.items()],
        )
        db.commit()

        source_bits = service.availability_service.get_week_bits(
            instructor_id, pattern_week, use_cache=False
        )
        assert any(bits and any(bits) for bits in source_bits.values())

        # Disable cache for testing
        service.cache_service = None

        # Apply to large date range
        start_date = pattern_week + timedelta(days=7)
        end_date = start_date + timedelta(days=30)

        result = await service.apply_pattern_to_date_range(
            instructor_id, pattern_week, start_date, end_date
        )

        # Verify bulk operations completed
        dates_processed = result.get("dates_processed", result.get("days_written"))
        assert dates_processed == (end_date - start_date).days + 1, result
        assert result["days_written"] > 0, result
        assert result.get("windows_created", 0) >= result["days_written"], result


class TestWeekOperationWithBookings:
    """Test week operations with existing bookings (layer independence)."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service with dependencies."""
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        return WeekOperationService(db, availability_service, conflict_checker)


class TestWeekOperationDateCalculations:
    """Test date calculation logic."""

    def test_calculate_week_dates(self):
        """Test week date calculation."""
        service = WeekOperationService(Mock())

        monday = date(2025, 6, 23)
        week_dates = service.calculate_week_dates(monday)

        assert len(week_dates) == 7
        assert week_dates[0] == monday
        assert week_dates[6] == monday + timedelta(days=6)  # Sunday

        # All dates should be consecutive
        for i in range(1, 7):
            assert week_dates[i] == week_dates[i - 1] + timedelta(days=1)

    def test_week_pattern_extraction(self, db: Session):
        """Test extracting weekly patterns.

        UPDATED: With single-table design, days without slots don't appear in pattern.
        This is correct behavior - empty days are not tracked.
        """
        service = WeekOperationService(db)

        # Create mock week data
        week_availability = {
            "2025-06-23": [{"start_time": "09:00", "end_time": "10:00"}],  # Monday
            "2025-06-24": [{"start_time": "14:00", "end_time": "15:00"}],  # Tuesday
            "2025-06-25": [],  # Wednesday - no slots
            "2025-06-26": [{"start_time": "10:00", "end_time": "12:00"}],  # Thursday
        }

        week_start = date(2025, 6, 23)
        pattern = service._extract_week_pattern(week_availability, week_start)

        assert "Monday" in pattern
        assert "Tuesday" in pattern
        assert "Wednesday" not in pattern  # Empty days NOT included - this is correct!
        assert "Thursday" in pattern
        assert len(pattern["Monday"]) == 1
        assert pattern["Monday"][0]["start_time"] == "09:00"


class TestWeekOperationCacheIntegration:
    """Test cache integration in week operations."""

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache service."""
        cache = Mock(spec=CacheService)
        cache.get = Mock(return_value=None)
        cache.set = Mock(return_value=True)
        cache.invalidate_pattern = Mock()
        return cache


class TestWeekOperationErrorHandling:
    """Test error handling in week operations."""

    @pytest.mark.asyncio
    async def test_copy_week_invalid_dates(self, db: Session, test_instructor: User):
        """Test copy with non-Monday dates."""
        service = WeekOperationService(db)

        # Disable cache
        service.cache_service = None

        # Use non-Monday dates
        from_week = date(2025, 6, 24)  # Tuesday
        to_week = date(2025, 6, 25)  # Wednesday

        # Should log warnings but still process
        result = await service.copy_week_availability(test_instructor.id, from_week, to_week)

        # Operation should complete
        assert result is not None
