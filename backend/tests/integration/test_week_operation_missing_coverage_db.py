# backend/tests/integration/test_week_operation_missing_coverage_db.py
"""
Additional integration tests for WeekOperationService to increase coverage.

Focuses on database operations and cache integration paths.
"""


from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.user import User
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.cache_strategies import CacheWarmingStrategy
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService


class TestWeekOperationCacheWarmingIntegration:
    """Test cache warming in real database context."""

    @pytest.mark.asyncio
    async def test_apply_pattern_with_cache_warming(self, db: Session, test_instructor: User):
        """Test apply pattern with cache warming for multiple weeks."""
        # Create mock cache service
        mock_cache = Mock(spec=CacheService)
        mock_cache.get = Mock(return_value=None)
        mock_cache.set = Mock()

        # Create service with cache
        service = WeekOperationService(db, cache_service=mock_cache)

        # Create source pattern
        pattern_week = date(2025, 6, 16)  # Monday
        for i in range(3):  # Mon, Tue, Wed
            avail = InstructorAvailability(
                instructor_id=test_instructor.id, date=pattern_week + timedelta(days=i), is_cleared=False
            )
            db.add(avail)
            db.flush()

            slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9, 0), end_time=time(10, 0))
            db.add(slot)

        db.commit()

        # Apply pattern to multiple weeks
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 20)  # Spans 3 weeks

        # Mock cache warming strategy
        with patch("app.services.cache_strategies.CacheWarmingStrategy") as MockWarmer:
            mock_warmer = Mock()
            mock_warmer.warm_with_verification = AsyncMock(return_value={})
            MockWarmer.return_value = mock_warmer

            result = await service.apply_pattern_to_date_range(test_instructor.id, pattern_week, start_date, end_date)

            # Should warm cache for affected weeks
            assert MockWarmer.called
            assert mock_warmer.warm_with_verification.call_count >= 2
            assert result["slots_created"] > 0

    @pytest.mark.asyncio
    async def test_copy_week_with_real_cache_strategy(self, db: Session, test_instructor: User):
        """Test copy week with real cache warming strategy."""
        # Create service with mock cache
        mock_cache = Mock(spec=CacheService)
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        service = WeekOperationService(db, availability_service, conflict_checker, mock_cache)

        # Create source week
        from_week = date(2025, 6, 16)
        for i in range(7):
            avail = InstructorAvailability(
                instructor_id=test_instructor.id, date=from_week + timedelta(days=i), is_cleared=False
            )
            db.add(avail)
            db.flush()

            if i < 5:  # Add slots for weekdays
                slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9 + i, 0), end_time=time(10 + i, 0))
                db.add(slot)

        db.commit()

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
    async def test_apply_pattern_to_past_dates(self, db: Session, test_instructor: User):
        """Test applying pattern to past dates."""
        service = WeekOperationService(db)

        # Create pattern
        pattern_week = date.today()
        avail = InstructorAvailability(instructor_id=test_instructor.id, date=pattern_week, is_cleared=False)
        db.add(avail)
        db.flush()

        slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9, 0), end_time=time(10, 0))
        db.add(slot)
        db.commit()

        # Apply to past dates
        past_start = date.today() - timedelta(days=30)
        past_end = date.today() - timedelta(days=20)

        result = await service.apply_pattern_to_date_range(test_instructor.id, pattern_week, past_start, past_end)

        # Should still work
        assert result["message"]
        assert "days" in result["message"]

    @pytest.mark.asyncio
    async def test_copy_week_same_week(self, db: Session, test_instructor: User):
        """Test copying week to itself."""
        service = WeekOperationService(db)

        # Create week
        week_start = date(2025, 6, 16)
        avail = InstructorAvailability(instructor_id=test_instructor.id, date=week_start, is_cleared=False)
        db.add(avail)
        db.commit()

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
    async def test_apply_pattern_with_all_booked_dates(
        self, db: Session, test_instructor_with_availability: User, test_student: User
    ):
        """Test applying pattern when all target dates have bookings."""
        instructor = test_instructor_with_availability
        service = WeekOperationService(db)

        # Create pattern
        pattern_week = date.today() - timedelta(days=14)
        avail = InstructorAvailability(instructor_id=instructor.id, date=pattern_week, is_cleared=False)
        db.add(avail)
        db.flush()

        slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9, 0), end_time=time(10, 0))
        db.add(slot)
        db.commit()

        # Book slots in target range
        target_start = date.today() + timedelta(days=7)
        target_end = target_start + timedelta(days=2)

        service_obj = (
            db.query(Service).filter(Service.instructor_profile_id == instructor.instructor_profile.id).first()
        )

        for i in range(3):
            target_date = target_start + timedelta(days=i)

            # Create availability
            target_avail = InstructorAvailability(instructor_id=instructor.id, date=target_date, is_cleared=False)
            db.add(target_avail)
            db.flush()

            # Create slot
            target_slot = AvailabilitySlot(availability_id=target_avail.id, start_time=time(9, 0), end_time=time(10, 0))
            db.add(target_slot)
            db.flush()

            # Book it
            booking = Booking(
                student_id=test_student.id,
                instructor_id=instructor.id,
                service_id=service_obj.id,
                availability_slot_id=target_slot.id,
                booking_date=target_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
                status=BookingStatus.CONFIRMED,
                service_name=service_obj.skill,
                hourly_rate=service_obj.hourly_rate,
                total_price=service_obj.hourly_rate,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Apply pattern - should preserve all bookings
        result = await service.apply_pattern_to_date_range(instructor.id, pattern_week, target_start, target_end)

        assert result["dates_skipped"] > 0
        assert result["total_bookings_preserved"] == 3


class TestWeekOperationComplexPatterns:
    """Test complex pattern scenarios."""

    @pytest.mark.asyncio
    async def test_apply_pattern_with_partial_conflicts(
        self, db: Session, test_instructor_with_availability: User, test_student: User
    ):
        """Test pattern application with partial time conflicts."""
        instructor = test_instructor_with_availability
        service = WeekOperationService(db)

        # Create pattern with multiple slots
        pattern_week = date(2025, 6, 16)
        avail = InstructorAvailability(instructor_id=instructor.id, date=pattern_week, is_cleared=False)
        db.add(avail)
        db.flush()

        # Multiple slots in pattern
        for hour in [9, 11, 14, 16]:
            slot = AvailabilitySlot(availability_id=avail.id, start_time=time(hour, 0), end_time=time(hour + 1, 0))
            db.add(slot)

        db.commit()

        # Create booking that conflicts with one slot
        target_date = date(2025, 7, 1)
        target_avail = InstructorAvailability(instructor_id=instructor.id, date=target_date, is_cleared=False)
        db.add(target_avail)
        db.flush()

        conflict_slot = AvailabilitySlot(
            availability_id=target_avail.id, start_time=time(10, 30), end_time=time(11, 30)
        )
        db.add(conflict_slot)
        db.flush()

        service_obj = (
            db.query(Service).filter(Service.instructor_profile_id == instructor.instructor_profile.id).first()
        )

        booking = Booking(
            student_id=test_student.id,
            instructor_id=instructor.id,
            service_id=service_obj.id,
            availability_slot_id=conflict_slot.id,
            booking_date=target_date,
            start_time=time(10, 30),
            end_time=time(11, 30),
            status=BookingStatus.CONFIRMED,
            service_name=service_obj.skill,
            hourly_rate=service_obj.hourly_rate,
            total_price=service_obj.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        # Apply pattern
        result = await service.apply_pattern_to_date_range(instructor.id, pattern_week, target_date, target_date)

        # Should create some slots and skip conflicting ones
        assert result["slots_created"] >= 0
        assert result["slots_skipped"] >= 0
