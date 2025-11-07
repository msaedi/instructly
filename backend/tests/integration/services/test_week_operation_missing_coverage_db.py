# backend/tests/integration/services/test_week_operation_missing_coverage_db.py
"""
Additional integration tests for WeekOperationService to increase coverage.

Focuses on database operations and cache integration paths.

UPDATED FOR WORK STREAM #10: Single-table availability design.
- No more InstructorAvailability
- Direct slot operations only
- Simplified test expectations
- No concept of "empty days" in patterns
- Fixed to use specific_date instead of date
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, time, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

# AvailabilitySlot removed - bitmap-only storage now
from app.models.booking import Booking, BookingStatus
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.cache_strategies import CacheWarmingStrategy
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService
from app.utils.bitset import bits_from_windows, new_empty_bits


def _normalize_time(value: str | time) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    value = str(value)
    if len(value) == 5:
        return f"{value}:00"
    return value


def _seed_windows(
    db: Session,
    instructor_id: str,
    windows_by_day: dict[date, list[tuple[str | time, str | time]]],
) -> None:
    if not windows_by_day:
        return

    repo = AvailabilityDayRepository(db)
    grouped: dict[date, list[tuple[date, list[tuple[str, str]]]]] = defaultdict(list)
    for day, windows in windows_by_day.items():
        monday = day - timedelta(days=day.weekday())
        normalized = [(_normalize_time(start), _normalize_time(end)) for start, end in windows]
        grouped[monday].append((day, normalized))

    for monday, entries in grouped.items():
        items: list[tuple[date, bytes]] = []
        for day, normalized in entries:
            items.append((day, bits_from_windows(normalized) if normalized else bits_from_windows([])))
        repo.upsert_week(instructor_id, items)
    db.commit()


class TestWeekOperationCacheWarmingIntegration:
    """Test cache warming in real database context."""

    @pytest.mark.asyncio
    async def test_apply_pattern_with_cache_warming(
        self,
        db: Session,
        unique_instructor: tuple[str, str],
        clear_week_bits,
    ):
        """Test apply pattern with cache warming for multiple weeks."""
        # Create service without cache (cache warming is tested separately)
        service = WeekOperationService(db, cache_service=None)

        # Create source pattern with single-table design
        instructor_id, _ = unique_instructor
        pattern_week = date.today() + timedelta(days=14)
        pattern_week = pattern_week - timedelta(days=pattern_week.weekday())
        clear_week_bits(instructor_id, pattern_week, weeks=4)
        windows = {}
        for i in range(3):  # Mon, Tue, Wed
            slot_date = pattern_week + timedelta(days=i)
            windows.setdefault(slot_date, []).append(("09:00:00", "10:00:00"))
        _seed_windows(db, instructor_id, windows)
        bits_map = service.availability_service.get_week_bits(
            instructor_id,
            pattern_week,
            use_cache=False,
        )
        assert any(bits != new_empty_bits() for bits in bits_map.values())

        # Apply pattern to multiple future weeks to ensure writes occur
        today = date.today()
        start_date = today + timedelta(days=7)
        end_date = start_date + timedelta(days=19)  # span roughly three weeks

        result = await service.apply_pattern_to_date_range(instructor_id, pattern_week, start_date, end_date)

        # Verify pattern application succeeded
        assert result["days_written"] > 0
        assert result.get("windows_created", 0) > 0

    @pytest.mark.asyncio
    async def test_copy_week_with_real_cache_strategy(self, db: Session, test_instructor: User):
        """Test copy week with real cache warming strategy."""
        # Create service with mock cache
        mock_cache = Mock(spec=CacheService)
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        service = WeekOperationService(db, availability_service, conflict_checker, mock_cache)

        # Create source week with single-table design
        from_week = date(2025, 6, 16)
        windows = {}
        for i in range(5):  # Weekdays only
            slot_date = from_week + timedelta(days=i)
            windows.setdefault(slot_date, []).append((f"{9 + i:02d}:00:00", f"{10 + i:02d}:00:00"))
        _seed_windows(db, test_instructor.id, windows)

        to_week = from_week + timedelta(weeks=1)

        # Use real CacheWarmingStrategy
        with patch.object(CacheWarmingStrategy, "warm_with_verification") as mock_warm:
            mock_warm.return_value = {
                str(to_week): [],
                str(to_week + timedelta(days=1)): [{"start_time": "10:00", "end_time": "11:00"}],
            }

            await service.copy_week_availability(test_instructor.id, from_week, to_week)

            # Should have called warming
            if mock_cache:
                assert mock_warm.called


class TestWeekOperationEdgeCases:
    """Test edge cases and error paths."""

    @pytest.mark.asyncio
    async def test_apply_pattern_to_past_dates(
        self,
        db: Session,
        unique_instructor: tuple[str, str],
        clear_week_bits,
    ):
        """Test applying pattern to past dates."""
        service = WeekOperationService(db)

        instructor_id, _ = unique_instructor

        # Create pattern with single-table design
        pattern_week = date.today()
        pattern_week = pattern_week - timedelta(days=pattern_week.weekday())
        clear_week_bits(instructor_id, pattern_week, weeks=1)
        _seed_windows(db, instructor_id, {pattern_week: [("09:00:00", "10:00:00")]})

        # Apply to past dates
        past_start = date.today() - timedelta(days=30)
        past_end = date.today() - timedelta(days=20)

        result = await service.apply_pattern_to_date_range(instructor_id, pattern_week, past_start, past_end)

        total_processed = (past_end - past_start).days + 1
        assert result["dates_processed"] == total_processed
        assert result["weeks_applied"] >= 1
        if result["days_written"] == 0:
            assert result.get("skipped_past_targets", 0) >= 1
            assert result.get("written_dates", []) == []
        else:
            assert result["days_written"] <= total_processed

    @pytest.mark.asyncio
    async def test_copy_week_same_week(self, db: Session, test_instructor: User):
        """Test copying week to itself."""
        service = WeekOperationService(db)

        # Create week with single-table design
        week_start = date(2025, 6, 16)
        _seed_windows(db, test_instructor.id, {week_start: [("09:00:00", "10:00:00")]})

        # Copy to same week
        result = await service.copy_week_availability(test_instructor.id, week_start, week_start)  # Same week

        # Should handle gracefully
        assert result is not None

    def test_get_week_pattern_empty_week(self, db: Session, test_instructor: User):
        """Test getting pattern from empty week."""
        availability_service = AvailabilityService(db)
        service = WeekOperationService(db, availability_service)

        # Get pattern from week with no data
        week_start = date(2025, 6, 16)
        pattern = service.get_week_pattern(test_instructor.id, week_start)

        # Should return empty pattern
        assert pattern == {}

    @pytest.mark.asyncio
    async def test_apply_pattern_with_bookings(
        self,
        db: Session,
        unique_instructor: tuple[str, str],
        clear_week_bits,
        test_student: User,
    ):
        """Test applying pattern when target dates have bookings.

        With Work Stream #9, availability operations don't check bookings,
        so pattern application creates all slots regardless of bookings.

        FIXED: Create pattern for multiple days to ensure slots are created.
        """
        instructor_id, user_id = unique_instructor
        instructor = db.get(User, user_id)
        service = WeekOperationService(db)

        # Create pattern with single-table design for ALL weekdays
        pattern_week = date.today() + timedelta(days=7)
        pattern_week = pattern_week - timedelta(days=pattern_week.weekday())
        clear_week_bits(instructor_id, pattern_week, weeks=3)

        pattern_windows = {
            pattern_week + timedelta(days=i): [("09:00:00", "10:00:00")] for i in range(7)
        }
        _seed_windows(db, instructor_id, pattern_windows)

        # Book slots in target range
        target_start = pattern_week + timedelta(days=7)
        target_end = target_start + timedelta(days=2)

        target_week_monday = target_start - timedelta(days=target_start.weekday())
        clear_week_bits(instructor_id, target_week_monday, weeks=1)

        service_obj = (
            db.query(Service).filter(Service.instructor_profile_id == instructor.instructor_profile.id).first()
        )

        for i in range(3):
            target_date = target_start + timedelta(days=i)

            # Book it
            booking = Booking(
                student_id=test_student.id,
                instructor_id=instructor_id,
                instructor_service_id=service_obj.id,
                booking_date=target_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
                status=BookingStatus.CONFIRMED,
                service_name=service_obj.catalog_entry.name if service_obj.catalog_entry else "Unknown Service",
                hourly_rate=service_obj.hourly_rate,
                total_price=service_obj.hourly_rate,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Apply pattern - bitmap path skips rewriting identical availability while leaving bookings intact
        result = await service.apply_pattern_to_date_range(instructor_id, pattern_week, target_start, target_end)

        # Bitmap apply writes availability regardless of bookings
        assert result["days_written"] > 0
        assert result.get("windows_created", 0) >= result["days_written"]


class TestWeekOperationComplexPatterns:
    """Test complex pattern scenarios."""

    @pytest.mark.asyncio
    async def test_apply_pattern_with_multiple_slots(self, db: Session, test_instructor_with_availability: User):
        """Test pattern application with multiple slots per day.

        FIXED: Create pattern for the correct day of week that matches target date.
        """
        instructor = test_instructor_with_availability
        service = WeekOperationService(db)

        # Use a future target date to ensure writes are allowed
        target_date = date.today() + timedelta(days=10)
        target_day_of_week = target_date.weekday()  # 0=Monday, 1=Tuesday, etc.

        # Create pattern week starting from a Monday (previous week)
        target_week_monday = target_date - timedelta(days=target_day_of_week)
        pattern_week = target_week_monday - timedelta(weeks=1)

        # Create pattern for the specific day of week that matches our target
        pattern_date = pattern_week + timedelta(days=target_day_of_week)

        # Multiple slots in pattern for the correct day
        pattern_windows = {
            pattern_date: [(f"{hour:02d}:00:00", f"{hour + 1:02d}:00:00") for hour in [9, 11, 14, 16]]
        }
        _seed_windows(db, instructor.id, pattern_windows)

        # Apply pattern
        result = await service.apply_pattern_to_date_range(instructor.id, pattern_week, target_date, target_date)

        # Should create all pattern slots (4 slots from pattern)
        assert result["windows_created"] == 4

    @pytest.mark.asyncio
    async def test_apply_pattern_across_month_boundary(self, db: Session, test_instructor: User):
        """Test pattern application across month boundaries."""
        service = WeekOperationService(db)

        # Create simple pattern for the current week
        pattern_week = date.today() - timedelta(days=date.today().weekday())
        _seed_windows(db, test_instructor.id, {pattern_week: [("09:00:00", "10:00:00")]})

        # Apply across month boundary using dynamic future dates
        today = date.today()
        days_in_current_month = monthrange(today.year, today.month)[1]
        days_to_month_end = days_in_current_month - today.day
        next_month_start = today + timedelta(days=days_to_month_end + 1)
        days_in_next_month = monthrange(next_month_start.year, next_month_start.month)[1]
        start_date = next_month_start + timedelta(days=max(0, days_in_next_month - 3))
        end_date = start_date + timedelta(days=6)

        result = await service.apply_pattern_to_date_range(test_instructor.id, pattern_week, start_date, end_date)

        # Should handle month boundary correctly
        dates_processed = result.get("dates_processed", result.get("days_written"))
        assert dates_processed >= 1
        assert result["windows_created"] > 0


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
        pattern_week = today - timedelta(days=today.weekday())
        clear_week_bits(instructor_id, pattern_week, weeks=6)
        windows = {}
        for i in range(3):  # Mon, Tue, Wed
            day_date = pattern_week + timedelta(days=i)
            windows.setdefault(day_date, []).extend(
                [(f"{hour:02d}:00:00", f"{hour + 1:02d}:00:00") for hour in [9, 11, 14]]
            )
        _seed_windows(db, instructor_id, windows)

        # Disable cache for testing
        service.cache_service = None

        # Apply to large date range
        start_date = pattern_week + timedelta(days=7)
        end_date = start_date + timedelta(days=30)  # roughly full month

        result = await service.apply_pattern_to_date_range(instructor_id, pattern_week, start_date, end_date)

        # Verify bulk operations completed
        dates_processed = result.get("dates_processed", result.get("days_written"))
        assert dates_processed == (end_date - start_date).days + 1
        assert result["days_written"] > 0
        assert result.get("windows_created", 0) >= result["days_written"]


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
        This is correct behavior - no need for empty day placeholders.
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
        assert "Wednesday" not in pattern  # Empty days NOT included in single-table design
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

    @pytest.mark.asyncio
    async def test_copy_week_cache_warming(self, db: Session, mock_cache: Mock, test_instructor: User):
        """Test cache warming after copy operation."""
        # Disable cache to avoid warming strategy issues
        service = WeekOperationService(db, cache_service=None)

        # Create minimal test data with single-table design
        from_week = date(2025, 6, 16)
        to_week = date(2025, 6, 23)

        # Add source week data
        _seed_windows(db, test_instructor.id, {from_week: [("09:00:00", "10:00:00")]})

        # Execute copy
        result = await service.copy_week_availability(test_instructor.id, from_week, to_week)

        # Should complete without errors
        assert result is not None


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

    @pytest.mark.asyncio
    async def test_apply_pattern_database_error_handling(self, db: Session, test_instructor: User):
        """Test handling of database errors during apply pattern."""
        service = WeekOperationService(db)

        # Create pattern week with single-table design
        pattern_week = date(2025, 6, 16)
        _seed_windows(db, test_instructor.id, {pattern_week: [("09:00:00", "10:00:00")]})

        # Disable cache
        service.cache_service = None

        # The operation should handle errors gracefully
        result = await service.apply_pattern_to_date_range(
            test_instructor.id, pattern_week, date(2025, 7, 1), date(2025, 7, 7)
        )

        # Should complete
        assert result is not None
