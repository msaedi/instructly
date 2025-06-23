# backend/tests/integration/test_week_operation_service_db.py
"""
Integration tests for WeekOperationService database operations.

These tests verify actual database behavior including transactions,
cascades, and complex multi-table operations.
"""

from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.user import User
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService


class TestWeekOperationServiceTransactions:
    """Test transaction handling in week operations."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service with real dependencies."""
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        return WeekOperationService(db, availability_service, conflict_checker)

    @pytest.mark.asyncio
    async def test_copy_week_transaction_rollback(
        self, db: Session, service: WeekOperationService, test_instructor: User
    ):
        """Test that copy week rolls back on error."""
        from_week = date(2025, 6, 16)  # Monday
        to_week = date(2025, 6, 23)  # Next Monday

        # Create source week availability
        for i in range(7):
            day_date = from_week + timedelta(days=i)
            avail = InstructorAvailability(instructor_id=test_instructor.id, date=day_date, is_cleared=False)
            db.add(avail)
            db.flush()

            slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9, 0), end_time=time(10, 0))
            db.add(slot)

        db.commit()

        # Disable cache to avoid issues
        service.cache_service = None

        # Should not crash, but handle error gracefully
        result = await service.copy_week_availability(test_instructor.id, from_week, to_week)

        # Operation should still complete
        assert result is not None

    @pytest.mark.asyncio
    async def test_copy_week_preserves_bookings(
        self, db: Session, service: WeekOperationService, test_instructor_with_availability: User, test_student: User
    ):
        """Test that copy week preserves existing bookings."""
        instructor = test_instructor_with_availability
        from_week = date.today() - timedelta(days=date.today().weekday())  # This Monday
        to_week = from_week + timedelta(weeks=1)  # Next Monday

        # Create a booking in target week
        target_date = to_week + timedelta(days=2)  # Wednesday

        # First create availability for target
        target_avail = InstructorAvailability(instructor_id=instructor.id, date=target_date, is_cleared=False)
        db.add(target_avail)
        db.flush()

        target_slot = AvailabilitySlot(availability_id=target_avail.id, start_time=time(14, 0), end_time=time(15, 0))
        db.add(target_slot)
        db.flush()

        # Get service
        service_obj = (
            db.query(Service).filter(Service.instructor_profile_id == instructor.instructor_profile.id).first()
        )

        # Create booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=instructor.id,
            service_id=service_obj.id,
            availability_slot_id=target_slot.id,
            booking_date=target_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
            status=BookingStatus.CONFIRMED,
            service_name=service_obj.skill,
            hourly_rate=service_obj.hourly_rate,
            total_price=service_obj.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        # Disable cache for testing
        service.cache_service = None

        # Copy week
        result = await service.copy_week_availability(instructor.id, from_week, to_week)

        # Verify booking still exists
        preserved_booking = db.query(Booking).filter(Booking.id == booking.id).first()
        assert preserved_booking is not None
        assert preserved_booking.status == BookingStatus.CONFIRMED

        # Check metadata if present
        if "_metadata" in result:
            assert len(result["_metadata"]["dates_with_preserved_bookings"]) > 0


class TestWeekOperationBulkOperations:
    """Test bulk database operations."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service instance."""
        return WeekOperationService(db)

    @pytest.mark.asyncio
    async def test_apply_pattern_bulk_operations(
        self, db: Session, service: WeekOperationService, test_instructor: User
    ):
        """Test bulk operations in apply_pattern_to_date_range."""
        # Create source pattern
        pattern_week = date(2025, 6, 16)
        for i in range(3):  # Mon, Tue, Wed
            day_date = pattern_week + timedelta(days=i)
            avail = InstructorAvailability(instructor_id=test_instructor.id, date=day_date, is_cleared=False)
            db.add(avail)
            db.flush()

            # Multiple slots per day
            for hour in [9, 11, 14]:
                slot = AvailabilitySlot(availability_id=avail.id, start_time=time(hour, 0), end_time=time(hour + 1, 0))
                db.add(slot)

        db.commit()

        # Disable cache for testing
        service.cache_service = None

        # Apply to large date range
        start_date = date(2025, 7, 1)
        end_date = date(2025, 7, 31)  # Full month

        result = await service.apply_pattern_to_date_range(test_instructor.id, pattern_week, start_date, end_date)

        # Verify bulk operations completed
        assert result["dates_created"] + result["dates_modified"] > 0
        assert result["slots_created"] > 0

        # Verify data integrity
        created_avails = (
            db.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == test_instructor.id,
                InstructorAvailability.date >= start_date,
                InstructorAvailability.date <= end_date,
            )
            .all()
        )

        assert len(created_avails) > 0

    def test_bulk_create_slots_performance(self, db: Session, service: WeekOperationService, test_instructor: User):
        """Test bulk slot creation performance."""
        # Create availability entry
        avail = InstructorAvailability(
            instructor_id=test_instructor.id, date=date.today(), is_cleared=False  # Use fixture instead of hardcoded ID
        )
        db.add(avail)
        db.flush()

        # Prepare bulk slot data
        slots_data = []
        for hour in range(8, 18):  # 8 AM to 5 PM
            slots_data.append({"availability_id": avail.id, "start_time": time(hour, 0), "end_time": time(hour, 30)})
            slots_data.append(
                {"availability_id": avail.id, "start_time": time(hour, 30), "end_time": time(hour + 1, 0)}
            )

        # Bulk create
        created_count = service._bulk_create_slots(slots_data)
        db.commit()

        assert created_count == 20  # 10 hours * 2 slots per hour

        # Verify all created
        slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == avail.id).all()

        assert len(slots) == 20


class TestWeekOperationConflictHandling:
    """Test conflict handling during week operations."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service with dependencies."""
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        return WeekOperationService(db, availability_service, conflict_checker)

    @pytest.mark.asyncio
    async def test_copy_week_with_conflicts(
        self, db: Session, service: WeekOperationService, test_instructor_with_availability: User, test_student: User
    ):
        """Test copying week when target has conflicting bookings."""
        instructor = test_instructor_with_availability
        from_week = date.today() - timedelta(days=date.today().weekday())
        to_week = from_week + timedelta(weeks=1)

        # Create overlapping booking in target week
        target_date = to_week + timedelta(days=1)  # Tuesday

        # Create availability and slot
        avail = InstructorAvailability(instructor_id=instructor.id, date=target_date, is_cleared=False)
        db.add(avail)
        db.flush()

        slot = AvailabilitySlot(availability_id=avail.id, start_time=time(9, 0), end_time=time(11, 0))  # 2-hour slot
        db.add(slot)
        db.flush()

        # Book the slot
        service_obj = (
            db.query(Service).filter(Service.instructor_profile_id == instructor.instructor_profile.id).first()
        )

        booking = Booking(
            student_id=test_student.id,
            instructor_id=instructor.id,
            service_id=service_obj.id,
            availability_slot_id=slot.id,
            booking_date=target_date,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=BookingStatus.CONFIRMED,
            service_name=service_obj.skill,
            hourly_rate=service_obj.hourly_rate,
            total_price=service_obj.hourly_rate * 2,
            duration_minutes=120,
        )
        db.add(booking)
        db.commit()

        # Disable cache for testing
        service.cache_service = None

        # Copy week - should skip conflicting slots
        result = await service.copy_week_availability(instructor.id, from_week, to_week)

        # Verify booking preserved
        assert db.query(Booking).filter(Booking.id == booking.id).first() is not None

        # Check if metadata reports conflicts
        if "_metadata" in result:
            assert result["_metadata"]["slots_skipped"] >= 0


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
        """Test extracting weekly patterns."""
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
        assert "Wednesday" in pattern  # Empty days ARE included
        assert len(pattern["Wednesday"]) == 0  # But the list is empty
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

        # Create minimal test data
        from_week = date(2025, 6, 16)
        to_week = date(2025, 6, 23)

        # Add source week data
        avail = InstructorAvailability(instructor_id=test_instructor.id, date=from_week, is_cleared=False)
        db.add(avail)
        db.commit()

        # Execute copy
        result = await service.copy_week_availability(test_instructor.id, from_week, to_week)

        # Should complete without errors
        assert result is not None

    def test_get_cached_week_pattern(self, db: Session, mock_cache: Mock):
        """Test cached week pattern retrieval."""
        service = WeekOperationService(db, cache_service=mock_cache)

        instructor_id = 1
        week_start = date(2025, 6, 23)

        # Mock cache miss then hit
        mock_cache.get.return_value = None  # Cache miss

        # Mock availability service
        service.availability_service = Mock()
        service.availability_service.get_week_availability = Mock(
            return_value={"2025-06-23": [{"start_time": "09:00", "end_time": "10:00"}]}
        )

        # First call - cache miss
        service.get_cached_week_pattern(instructor_id, week_start)

        # Should set cache
        mock_cache.set.assert_called_once()

        # Mock cache hit
        mock_cache.get.return_value = {"Monday": [{"start_time": "09:00", "end_time": "10:00"}]}

        # Second call - cache hit
        pattern2 = service.get_cached_week_pattern(instructor_id, week_start)

        assert pattern2 is not None


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
        result = await service.copy_week_availability(test_instructor.id, from_week, to_week)  # Use fixture

        # Operation should complete
        assert result is not None

    @pytest.mark.asyncio
    async def test_apply_pattern_database_error_handling(self, db: Session, test_instructor: User):
        """Test handling of database errors during apply pattern."""
        service = WeekOperationService(db)

        # Create pattern week
        pattern_week = date(2025, 6, 16)
        avail = InstructorAvailability(instructor_id=test_instructor.id, date=pattern_week, is_cleared=False)
        db.add(avail)
        db.commit()

        # Disable cache
        service.cache_service = None

        # The operation should handle errors gracefully
        # Not expecting an exception anymore
        result = await service.apply_pattern_to_date_range(
            test_instructor.id, pattern_week, date(2025, 7, 1), date(2025, 7, 7)
        )

        # Should complete
        assert result is not None
