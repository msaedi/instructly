# backend/tests/integration/repositories/test_availability_repository.py
"""
Integration tests for AvailabilityRepository.

These tests verify:
1. Complex query methods work correctly with real database
2. Time overlap and conflict detection queries
3. Aggregation and statistics queries
4. Blackout date operations
5. Edge cases and error handling
"""

from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.availability import AvailabilitySlot, BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.repositories import RepositoryFactory
from app.repositories.availability_repository import AvailabilityRepository

try:  # pragma: no cover - fallback for direct backend pytest invocation
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs


@pytest.fixture
def test_service(db, test_instructor):
    """Create a test service for the instructor."""
    # Get or create instructor profile
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

    if not profile:
        profile = InstructorProfile(
            user_id=test_instructor.id,
            bio="Test bio",
            years_experience=5,
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan"])

    # Get or create catalog service
    category = db.query(ServiceCategory).first()
    if not category:
        category_ulid = generate_ulid()
        category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
        db.add(category)
        db.flush()

    service_ulid = generate_ulid()
    catalog_service = (
        db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"test-service-{service_ulid.lower()}").first()
    )
    if not catalog_service:
        catalog_service = ServiceCatalog(
            name="Test Service",
            slug=f"test-service-{service_ulid.lower()}",
            category_id=category.id,
            description="Test service description",
        )
        db.add(catalog_service)
        db.flush()

    # Create service
    service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.0,
        description="Test service description",
        is_active=True,
    )
    db.add(service)
    db.commit()
    return service


class TestAvailabilityRepositoryQueries:
    """Test complex query methods with real database."""

    def test_get_week_availability(self, db, test_instructor):
        """Test getting availability for a week with proper ordering."""
        repo = AvailabilityRepository(db)

        # Create slots across a week
        monday = date.today() - timedelta(days=date.today().weekday())
        slots_data = []

        for day_offset in range(7):  # Monday to Sunday
            current_date = monday + timedelta(days=day_offset)
            for hour in [9, 14, 18]:  # Morning, afternoon, evening
                slot = AvailabilitySlot(
                    instructor_id=test_instructor.id,
                    specific_date=current_date,
                    start_time=time(hour, 0),
                    end_time=time(hour + 1, 0),
                )
                db.add(slot)
                slots_data.append((current_date, time(hour, 0)))

        db.flush()

        # Test query
        results = repo.get_week_availability(
            instructor_id=test_instructor.id, start_date=monday, end_date=monday + timedelta(days=6)
        )

        # Verify results
        assert len(results) == 21  # 7 days * 3 slots

        # Verify ordering (by date, then start time)
        for i in range(1, len(results)):
            prev = results[i - 1]
            curr = results[i]
            assert curr.specific_date > prev.specific_date or (
                curr.specific_date == prev.specific_date and curr.start_time >= prev.start_time
            )

    def test_get_booked_slots_in_range(self, db, test_instructor, test_student, test_service):
        """Test finding bookings within a date range."""
        repo = AvailabilityRepository(db)

        # Create bookings across different dates
        today = date.today()
        bookings = []

        for day_offset in [-1, 0, 1, 7]:  # Yesterday, today, tomorrow, next week
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=test_service.id,
                booking_date=today + timedelta(days=day_offset),
                start_time=time(10, 0),
                end_time=time(11, 0),
                status=BookingStatus.CONFIRMED,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
            bookings.append(booking)

        # Add a cancelled booking (should not be included)
        cancelled = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=test_service.id,
            booking_date=today,
            start_time=time(14, 0),
            end_time=time(15, 0),
            status=BookingStatus.CANCELLED,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(cancelled)
        db.flush()

        # Test query for this week
        results = repo.get_booked_slots_in_range(
            instructor_id=test_instructor.id, start_date=today - timedelta(days=1), end_date=today + timedelta(days=1)
        )

        # Should include yesterday, today, tomorrow but not next week or cancelled
        assert len(results) == 3
        assert all(r.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED] for r in results)

        # Verify date range
        for booking in results:
            assert today - timedelta(days=1) <= booking.booking_date <= today + timedelta(days=1)

    def test_get_booked_time_ranges(self, db, test_instructor, test_student, test_service):
        """Test getting booked time ranges for a specific date."""
        repo = AvailabilityRepository(db)
        target_date = date.today()

        # Create multiple bookings with different times
        booking_times = [
            (time(9, 0), time(10, 0)),
            (time(11, 0), time(12, 30)),
            (time(14, 0), time(15, 0)),
        ]

        for start, end in booking_times:
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=test_service.id,
                booking_date=target_date,
                start_time=start,
                end_time=end,
                status=BookingStatus.CONFIRMED,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        # Add a booking for different date (should not be included)
        other_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=test_service.id,
            booking_date=target_date + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            status=BookingStatus.CONFIRMED,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(other_booking)
        db.flush()

        # Test query
        results = repo.get_booked_time_ranges(instructor_id=test_instructor.id, target_date=target_date)

        # Verify results
        assert len(results) == 3
        assert results == booking_times

    def test_find_time_conflicts(self, db, test_instructor):
        """Test finding slots that conflict with a proposed time range."""
        repo = AvailabilityRepository(db)
        target_date = date.today()

        # Create existing slots
        existing_slots = [
            (time(9, 0), time(10, 0)),  # No conflict
            (time(10, 30), time(11, 30)),  # Partial overlap at start
            (time(11, 0), time(12, 0)),  # Fully contained
            (time(11, 30), time(13, 0)),  # Partial overlap at end
            (time(13, 0), time(14, 0)),  # No conflict
        ]

        for start, end in existing_slots:
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id, specific_date=target_date, start_time=start, end_time=end
            )
            db.add(slot)
        db.flush()

        # Test conflicts with 10:45 - 12:15 time range
        conflicts = repo.find_time_conflicts(
            instructor_id=test_instructor.id, target_date=target_date, start_time=time(10, 45), end_time=time(12, 15)
        )

        # Should find 3 conflicts
        assert len(conflicts) == 3

        # Verify the conflicting slots
        conflict_times = [(c.start_time, c.end_time) for c in conflicts]
        assert (time(10, 30), time(11, 30)) in conflict_times
        assert (time(11, 0), time(12, 0)) in conflict_times
        assert (time(11, 30), time(13, 0)) in conflict_times

    def test_get_availability_summary(self, db, test_instructor):
        """Test aggregation query for availability summary."""
        repo = AvailabilityRepository(db)

        # Create slots with different counts per day
        start_date = date.today()
        slot_counts = [3, 5, 2, 0, 4]  # Different counts per day

        for day_offset, count in enumerate(slot_counts):
            current_date = start_date + timedelta(days=day_offset)
            for i in range(count):
                slot = AvailabilitySlot(
                    instructor_id=test_instructor.id,
                    specific_date=current_date,
                    start_time=time(9 + i, 0),
                    end_time=time(10 + i, 0),
                )
                db.add(slot)
        db.flush()

        # Test summary query
        summary = repo.get_availability_summary(
            instructor_id=test_instructor.id, start_date=start_date, end_date=start_date + timedelta(days=4)
        )

        # Verify results
        assert len(summary) == 4  # Days with 0 slots are not included

        for day_offset, count in enumerate(slot_counts):
            if count > 0:  # Only days with slots appear in results
                date_str = (start_date + timedelta(days=day_offset)).isoformat()
                assert summary.get(date_str) == count

    def test_get_instructor_availability_stats(self, db, test_instructor, test_student, test_service):
        """Test complex statistics query with subqueries."""
        repo = AvailabilityRepository(db)

        # Create future slots
        today = date.today()
        future_dates = [today + timedelta(days=i) for i in range(1, 8)]

        for date_val in future_dates:
            for hour in [9, 11, 14]:
                slot = AvailabilitySlot(
                    instructor_id=test_instructor.id,
                    specific_date=date_val,
                    start_time=time(hour, 0),
                    end_time=time(hour + 1, 0),
                )
                db.add(slot)

        # Create some bookings that overlap with slots
        for i in range(5):  # Book 5 slots
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=test_service.id,
                booking_date=future_dates[i],
                start_time=time(9, 0),
                end_time=time(10, 0),
                status=BookingStatus.CONFIRMED,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        db.flush()

        # Test stats query
        stats = repo.get_instructor_availability_stats(test_instructor.id)

        # Verify results
        assert stats["total_slots"] == 21  # 7 days * 3 slots
        assert stats["booked_slots"] == 5  # 5 bookings overlap with slots
        assert stats["utilization_rate"] == pytest.approx(23.8, rel=0.1)
        assert stats["earliest_availability"] == future_dates[0]
        assert stats["latest_availability"] == future_dates[-1]


class TestAvailabilityRepositorySlotManagement:
    """Test slot creation, deletion, and validation."""

    def test_create_slot_success(self, db, test_instructor):
        """Test successful slot creation."""
        repo = AvailabilityRepository(db)

        slot = repo.create_slot(
            instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )

        assert slot.id is not None
        assert slot.instructor_id == test_instructor.id
        assert slot.specific_date == date.today()
        assert slot.start_time == time(10, 0)
        assert slot.end_time == time(11, 0)

    def test_create_slot_duplicate_error(self, db, test_instructor):
        """Test creating duplicate slot raises exception."""
        repo = AvailabilityRepository(db)

        # Create first slot
        repo.create_slot(
            instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )
        db.flush()

        # Try to create duplicate
        with pytest.raises(RepositoryException) as exc_info:
            repo.create_slot(
                instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
            )

        assert "Slot already exists" in str(exc_info.value)

    def test_slot_exists(self, db, test_instructor):
        """Test checking if slot exists."""
        repo = AvailabilityRepository(db)

        # Create a slot
        repo.create_slot(
            instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )
        db.flush()

        # Test exists
        assert (
            repo.slot_exists(
                instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
            )
            is True
        )

        # Test not exists
        assert (
            repo.slot_exists(
                instructor_id=test_instructor.id, target_date=date.today(), start_time=time(14, 0), end_time=time(15, 0)
            )
            is False
        )

    def test_delete_slots_except(self, db, test_instructor):
        """Test deleting slots except specified IDs."""
        repo = AvailabilityRepository(db)
        target_date = date.today()

        # Create multiple slots
        slots = []
        for hour in [9, 10, 11, 14, 15]:
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=target_date,
                start_time=time(hour, 0),
                end_time=time(hour + 1, 0),
            )
            db.add(slot)
            slots.append(slot)
        db.flush()

        # Keep first two slots
        keep_ids = [slots[0].id, slots[1].id]

        # Delete others
        deleted_count = repo.delete_slots_except(
            instructor_id=test_instructor.id, target_date=target_date, except_ids=keep_ids
        )

        assert deleted_count == 3

        # Verify remaining slots
        remaining = repo.get_slots_by_date(test_instructor.id, target_date)
        assert len(remaining) == 2
        assert all(s.id in keep_ids for s in remaining)

    def test_delete_slots_by_dates(self, db, test_instructor):
        """Test deleting slots for multiple dates."""
        repo = AvailabilityRepository(db)

        # Create slots across multiple dates
        dates_to_delete = [date.today() + timedelta(days=i) for i in range(3)]
        date_to_keep = date.today() + timedelta(days=5)

        total_slots = 0
        for date_val in dates_to_delete + [date_to_keep]:
            for hour in [9, 10]:
                slot = AvailabilitySlot(
                    instructor_id=test_instructor.id,
                    specific_date=date_val,
                    start_time=time(hour, 0),
                    end_time=time(hour + 1, 0),
                )
                db.add(slot)
                total_slots += 1
        db.flush()

        # Delete slots for specific dates
        deleted = repo.delete_slots_by_dates(instructor_id=test_instructor.id, dates=dates_to_delete)

        assert deleted == 6  # 3 dates * 2 slots

        # Verify kept slots
        remaining = repo.get_slots_by_date(test_instructor.id, date_to_keep)
        assert len(remaining) == 2


class TestAvailabilityRepositoryBlackoutDates:
    """Test blackout date operations."""

    def test_create_blackout_date(self, db, test_instructor):
        """Test creating blackout dates."""
        repo = AvailabilityRepository(db)

        blackout = repo.create_blackout_date(
            instructor_id=test_instructor.id, blackout_date=date.today() + timedelta(days=7), reason="Vacation"
        )

        assert blackout.id is not None
        assert blackout.instructor_id == test_instructor.id
        assert blackout.date == date.today() + timedelta(days=7)
        assert blackout.reason == "Vacation"

    def test_create_duplicate_blackout_error(self, db, test_instructor):
        """Test creating duplicate blackout date raises error."""
        repo = AvailabilityRepository(db)
        blackout_date = date.today() + timedelta(days=7)

        # Create first blackout
        repo.create_blackout_date(instructor_id=test_instructor.id, blackout_date=blackout_date)
        db.flush()

        # Try duplicate
        with pytest.raises(RepositoryException) as exc_info:
            repo.create_blackout_date(instructor_id=test_instructor.id, blackout_date=blackout_date)

        assert "Blackout date already exists" in str(exc_info.value)

    def test_get_future_blackout_dates(self, db, test_instructor):
        """Test getting future blackout dates."""
        repo = AvailabilityRepository(db)

        # Use timezone-aware dates based on instructor's timezone
        from app.core.timezone_utils import get_user_today

        instructor_today = get_user_today(test_instructor)

        # Create past, today, and future blackouts
        past_date = instructor_today - timedelta(days=1)
        future_dates = [instructor_today + timedelta(days=i) for i in range(1, 4)]

        # Past blackout (should not be included)
        past_blackout = BlackoutDate(instructor_id=test_instructor.id, date=past_date, reason="Past")
        db.add(past_blackout)

        # Future blackouts
        for i, future_date in enumerate(future_dates):
            blackout = BlackoutDate(instructor_id=test_instructor.id, date=future_date, reason=f"Future {i}")
            db.add(blackout)
        db.flush()

        # Test query
        results = repo.get_future_blackout_dates(test_instructor.id)

        # Should only include future dates (today and beyond), ordered
        # Note: get_future_blackout_dates includes today as "future"
        assert len(results) >= 3  # At least the 3 future dates we created
        assert all(b.date >= instructor_today for b in results)

        # Verify ordering
        for i in range(1, len(results)):
            assert results[i].date >= results[i - 1].date

    def test_delete_blackout_date(self, db, test_instructor):
        """Test deleting blackout dates."""
        repo = AvailabilityRepository(db)

        # Create blackout
        blackout = repo.create_blackout_date(
            instructor_id=test_instructor.id, blackout_date=date.today() + timedelta(days=7)
        )
        db.flush()

        # Delete it
        deleted = repo.delete_blackout_date(blackout_id=blackout.id, instructor_id=test_instructor.id)

        assert deleted is True

        # Verify deleted
        blackouts = repo.get_future_blackout_dates(test_instructor.id)
        assert len(blackouts) == 0

        # Try deleting non-existent
        deleted = repo.delete_blackout_date(blackout_id=generate_ulid(), instructor_id=test_instructor.id)
        assert deleted is False


class TestAvailabilityRepositoryEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_date_ranges(self, db, test_instructor):
        """Test queries with empty date ranges."""
        repo = AvailabilityRepository(db)

        # Future date range with no data
        future_start = date.today() + timedelta(days=365)
        future_end = future_start + timedelta(days=7)

        results = repo.get_week_availability(
            instructor_id=test_instructor.id, start_date=future_start, end_date=future_end
        )

        assert results == []

    def test_invalid_instructor_id(self, db):
        """Test queries with non-existent instructor."""
        repo = AvailabilityRepository(db)

        # Should return empty results, not error
        results = repo.get_slots_by_date(instructor_id=generate_ulid(), target_date=date.today())

        assert results == []

    def test_database_error_handling(self, db, test_instructor):
        """Test repository handles database errors properly."""
        repo = AvailabilityRepository(db)

        # Mock a database error
        with patch.object(repo.db, "query") as mock_query:
            mock_query.side_effect = SQLAlchemyError("Database connection lost")

            with pytest.raises(RepositoryException) as exc_info:
                repo.get_week_availability(
                    instructor_id=test_instructor.id, start_date=date.today(), end_date=date.today() + timedelta(days=7)
                )

            assert "Failed to get week availability" in str(exc_info.value)

    def test_count_methods_with_no_data(self, db, test_instructor):
        """Test count methods return 0 with no data."""
        repo = AvailabilityRepository(db)

        # Count with no slots
        count = repo.count_available_slots(
            instructor_id=test_instructor.id, start_date=date.today(), end_date=date.today() + timedelta(days=7)
        )

        assert count == 0

        # Count bookings with no data
        booking_count = repo.count_bookings_for_date(instructor_id=test_instructor.id, target_date=date.today())

        assert booking_count == 0


class TestAvailabilityRepositoryFactoryIntegration:
    """Test repository creation via factory."""

    def test_factory_creation(self, db):
        """Test repository can be created via factory."""
        repo = RepositoryFactory.create_availability_repository(db)

        assert repo is not None
        assert isinstance(repo, AvailabilityRepository)
        assert hasattr(repo, "get_week_availability")
        assert hasattr(repo, "create_slot")
        assert hasattr(repo, "get_instructor_availability_stats")
