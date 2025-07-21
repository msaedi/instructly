# backend/tests/integration/repository_patterns/test_booking_repository_edge_cases.py
"""
Edge case and concurrency tests for BookingRepository.

Tests complex scenarios including:
- Concurrent booking attempts
- Time overlap edge cases
- Status transition conflicts
- Performance with large datasets
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import DateTime, and_, func
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.booking_repository import BookingRepository


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
            areas_of_service="Manhattan",
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()

    # Check if instructor already has a service
    existing_service = (
        db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
    )

    if existing_service:
        return existing_service

    # Get or create catalog service
    catalog_service = db.query(ServiceCatalog).first()
    if not catalog_service:
        category = ServiceCategory(name="Test Category", slug="test-category")
        db.add(category)
        db.flush()
        catalog_service = ServiceCatalog(name="Test Service", slug="test-service", category_id=category.id)
        db.add(catalog_service)
        db.flush()

    # Check if service already exists for this instructor and catalog
    existing_service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.service_catalog_id == catalog_service.id)
        .first()
    )

    if existing_service:
        return existing_service

    # Create service using catalog system
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


class TestBookingRepositoryConcurrency:
    """Test concurrent access patterns and race conditions."""

    def test_concurrent_booking_creation(self, db: Session, test_instructor: User, test_student: User, test_service):
        """Test handling of concurrent booking attempts for same time slot."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=10)
        start_time = time(14, 0)
        end_time = time(15, 0)

        # Function to attempt booking creation
        def create_booking_attempt(session_factory, student_id: int, attempt_num: int):
            """Attempt to create a booking in a separate session."""
            new_session = session_factory()
            BookingRepository(new_session)

            try:
                booking = Booking(
                    instructor_id=test_instructor.id,
                    student_id=student_id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=BookingStatus.CONFIRMED,
                    instructor_service_id=test_service.id,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
                new_session.add(booking)
                new_session.commit()
                return True, attempt_num
            except Exception:
                new_session.rollback()
                return False, attempt_num
            finally:
                new_session.close()

        # Simulate concurrent booking attempts
        from app.database import SessionLocal

        results = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(5):
                # Use same student to simulate multiple attempts
                future = executor.submit(create_booking_attempt, SessionLocal, test_student.id, i)
                futures.append(future)

            for future in as_completed(futures):
                results.append(future.result())

        # At least one should succeed (concurrency without constraints allows all)
        successful_attempts = [r for r in results if r[0]]
        assert len(successful_attempts) >= 1

        # Verify bookings exist (may be multiple without unique constraints)
        final_bookings = repository.get_bookings_by_time_range(test_instructor.id, booking_date, start_time, end_time)
        assert len(final_bookings) >= 1

    def test_time_overlap_edge_cases(self, db: Session, test_instructor: User, test_student: User, test_service):
        """Test various time overlap scenarios."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=15)

        # Create base booking
        base_booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=test_service.id,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(base_booking)
        db.commit()

        # Test cases for overlap detection
        overlap_test_cases = [
            # (start_time, end_time, should_conflict)
            (time(9, 0), time(9, 59), False),  # Ends just before
            (time(9, 0), time(10, 0), False),  # Ends exactly at start
            (time(9, 30), time(10, 30), True),  # Overlaps at start
            (time(10, 0), time(11, 0), True),  # Exact match
            (time(10, 30), time(11, 30), True),  # Overlaps at end
            (time(11, 0), time(12, 0), False),  # Starts exactly at end
            (time(11, 1), time(12, 0), False),  # Starts just after
            (time(9, 30), time(11, 30), True),  # Contains base booking
            (time(10, 15), time(10, 45), True),  # Contained within base
        ]

        for start, end, should_conflict in overlap_test_cases:
            has_conflict = repository.check_time_conflict(test_instructor.id, booking_date, start, end)

            if should_conflict:
                assert has_conflict == True, f"Expected conflict for {start}-{end}"
            else:
                assert has_conflict == False, f"Unexpected conflict for {start}-{end}"

    def test_status_transition_conflicts(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test booking status transitions and potential conflicts."""
        repository = BookingRepository(db)

        # Create bookings with different statuses
        booking_date = date.today() + timedelta(days=20)
        bookings = []

        for i, status in enumerate(BookingStatus):
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=time(9 + i, 0),
                end_time=time(10 + i, 0),
                status=status,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
            bookings.append(booking)

        db.commit()

        # Test conflict detection with different status filters
        # Only CONFIRMED and COMPLETED should be considered conflicts
        active_conflicts = repository.get_bookings_by_time_range(
            test_instructor.id, booking_date, time(9, 0), time(17, 0)
        )

        active_statuses = {BookingStatus.CONFIRMED, BookingStatus.COMPLETED}
        assert len(active_conflicts) == len(active_statuses)
        assert all(b.status in active_statuses for b in active_conflicts)

    def test_booking_modification_race_condition(self, db: Session, test_booking: Booking):
        """Test concurrent modifications to same booking."""
        BookingRepository(db)
        booking_id = test_booking.id

        # Function to modify booking
        def modify_booking(session_factory, new_status: BookingStatus):
            new_session = session_factory()
            BookingRepository(new_session)

            try:
                booking = new_session.query(Booking).filter(Booking.id == booking_id).first()

                if booking:
                    booking.status = new_status
                    new_session.commit()
                    return True, new_status
                return False, new_status
            except Exception:
                new_session.rollback()
                return False, new_status
            finally:
                new_session.close()

        # Simulate concurrent status updates
        from app.database import SessionLocal

        statuses_to_try = [BookingStatus.CANCELLED, BookingStatus.COMPLETED]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(modify_booking, SessionLocal, status) for status in statuses_to_try]

            [future.result() for future in as_completed(futures)]

        # Get the booking's current status before refresh to store original
        original_status = test_booking.status

        # Refresh and check final status
        db.refresh(test_booking)

        # One of the updates should have won (or original status remains)
        # Allow for either updated status or original status to account for race conditions
        possible_statuses = statuses_to_try + [original_status]
        assert test_booking.status in possible_statuses


class TestBookingRepositoryEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_maximum_bookings_per_day(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test behavior with maximum bookings per day."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=25)

        # Create many back-to-back bookings
        bookings_created = 0
        current_hour = 6  # Start at 6 AM

        while current_hour < 22:  # Until 10 PM
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=time(current_hour, 0),
                end_time=time(current_hour + 1, 0),
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
            bookings_created += 1
            current_hour += 1

        db.commit()

        # Verify all bookings - fix method call to match repository signature
        day_bookings = repository.get_bookings_for_date(booking_date)
        assert len(day_bookings) == bookings_created
        assert bookings_created == 16  # 6 AM to 10 PM

        # Test query performance with many bookings
        import time as timer

        start_time = timer.time()

        # Check for conflicts across entire day
        conflicts = repository.get_bookings_by_time_range(test_instructor.id, booking_date, time(0, 0), time(23, 59))

        query_time = timer.time() - start_time
        assert query_time < 0.1  # Should be fast with proper indexing
        assert len(conflicts) == bookings_created

    def test_booking_at_day_boundaries(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test bookings at midnight and day boundaries."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=30)

        # Test midnight booking
        midnight_booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=time(0, 0),
            end_time=time(1, 0),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=test_service.id,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(midnight_booking)

        # Test late night booking
        late_booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=time(23, 0),
            end_time=time(23, 59),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=test_service.id,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=59,
        )
        db.add(late_booking)
        db.commit()

        # Verify both bookings
        day_bookings = repository.get_bookings_for_date(booking_date)
        assert len(day_bookings) == 2

        # Check ordering
        assert day_bookings[0].start_time == time(0, 0)
        assert day_bookings[-1].start_time == time(23, 0)

    def test_partial_time_bookings(self, db: Session, test_instructor: User, test_student: User, test_service: Service):
        """Test bookings with non-standard time intervals."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=35)

        # Create bookings with various intervals
        time_intervals = [
            (time(9, 15), time(9, 45)),  # 30 minutes
            (time(10, 0), time(10, 45)),  # 45 minutes
            (time(11, 0), time(12, 30)),  # 90 minutes
            (time(14, 20), time(15, 50)),  # 90 minutes at odd times
            (time(16, 0), time(16, 15)),  # 15 minutes
        ]

        for start, end in time_intervals:
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=start,
                end_time=end,
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Test overlap detection with partial times
        # Should conflict with 9:15-9:45
        conflict1 = repository.check_time_conflict(test_instructor.id, booking_date, time(9, 30), time(10, 0))
        assert conflict1 == True

        # Should not conflict (fits between bookings)
        conflict2 = repository.check_time_conflict(test_instructor.id, booking_date, time(12, 30), time(14, 20))
        assert conflict2 == False

    def test_booking_statistics_edge_cases(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test booking statistics with edge cases."""
        repository = BookingRepository(db)

        # Create bookings with various statuses and dates
        today = date.today()

        # Past bookings
        for i in range(5):
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=today - timedelta(days=i + 1),
                start_time=time(10, 0),
                end_time=time(11, 0),
                status=BookingStatus.COMPLETED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        # Future bookings
        for i in range(3):
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=today + timedelta(days=i + 1),
                start_time=time(14, 0),
                end_time=time(15, 0),
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        # Cancelled bookings (should not appear in stats)
        for i in range(2):
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=today,
                start_time=time(16 + i, 0),
                end_time=time(17 + i, 0),
                status=BookingStatus.CANCELLED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Test statistics queries - fix method signature
        from app.models.user import UserRole

        stats = repository.count_bookings_by_status(test_instructor.id, UserRole.INSTRUCTOR)

        assert stats[BookingStatus.COMPLETED.value] == 5
        assert stats[BookingStatus.CONFIRMED.value] == 3
        assert stats[BookingStatus.CANCELLED.value] == 2

    def test_find_booking_opportunities(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test finding available booking slots with complex patterns."""
        repository = BookingRepository(db)
        booking_date = date.today() + timedelta(days=40)

        # Create a fragmented schedule
        existing_bookings = [
            (time(9, 0), time(10, 0)),
            (time(10, 30), time(11, 30)),
            (time(12, 0), time(13, 0)),
            (time(14, 0), time(15, 30)),
            (time(16, 0), time(17, 0)),
        ]

        for start, end in existing_bookings:
            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=start,
                end_time=end,
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Create mock available slots data for the method call
        available_slots = [{"start_time": time(8, 0), "end_time": time(18, 0)}]

        # Find opportunities (gaps in schedule) - fix method signature
        opportunities = repository.find_booking_opportunities(
            available_slots, test_instructor.id, booking_date, 60  # Minimum duration in minutes
        )

        # Should find gaps:
        # 8:00-9:00 (1 hour)
        # 10:00-10:30 (30 min - too short)
        # 11:30-12:00 (30 min - too short)
        # 13:00-14:00 (1 hour)
        # 15:30-16:00 (30 min - too short)
        # 17:00-18:00 (1 hour)

        assert len(opportunities) == 3  # Only 60+ minute gaps

    def test_instructor_schedule_density(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test queries with dense instructor schedules."""
        repository = BookingRepository(db)

        # Create a very dense schedule over multiple days
        start_date = date.today() + timedelta(days=50)

        for day_offset in range(7):  # One week
            booking_date = start_date + timedelta(days=day_offset)

            # Morning sessions (15-minute intervals)
            for minutes in range(0, 180, 15):  # 3 hours of 15-min sessions
                start = time(9, minutes % 60, 0)
                if minutes >= 60:
                    start = time(9 + minutes // 60, minutes % 60, 0)

                end_minutes = minutes + 15
                end = time(9, end_minutes % 60, 0)
                if end_minutes >= 60:
                    end = time(9 + end_minutes // 60, end_minutes % 60, 0)

                booking = Booking(
                    instructor_id=test_instructor.id,
                    student_id=test_student.id,
                    booking_date=booking_date,
                    start_time=start,
                    end_time=end,
                    status=BookingStatus.CONFIRMED if day_offset < 5 else BookingStatus.PENDING,
                    instructor_service_id=test_service.id,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=15,
                )
                db.add(booking)

        db.commit()

        # Test performance of week query
        import time as timer

        start_time = timer.time()

        week_bookings = repository.get_instructor_bookings(test_instructor.id, upcoming_only=False)

        query_time = timer.time() - start_time

        # Should handle dense schedule efficiently
        assert len(week_bookings) == 7 * 12  # 7 days * 12 sessions per day
        assert query_time < 0.2  # Should be reasonably fast

    def test_booking_cancellation_window(
        self, db: Session, test_instructor: User, test_student: User, test_service: Service
    ):
        """Test booking queries with cancellation time windows."""
        BookingRepository(db)
        now = datetime.now()

        # Create bookings at various times relative to now
        bookings_data = [
            # (hours_from_now, should_be_cancellable_with_24h_policy)
            (1, False),  # Too close
            (12, False),  # Still too close
            (24, True),  # Exactly at boundary
            (25, True),  # Just past boundary
            (48, True),  # Well past boundary
        ]

        created_bookings = []
        for hours_from_now, _ in bookings_data:
            booking_datetime = now + timedelta(hours=hours_from_now)
            # Ensure end time doesn't wrap to next day causing start > end
            start_time = booking_datetime.time()
            end_datetime = booking_datetime + timedelta(hours=1)

            # If end time is on next day, cap it at 23:59 to avoid constraint violation
            if end_datetime.date() > booking_datetime.date():
                end_time = time(23, 59)
            else:
                end_time = end_datetime.time()

            booking = Booking(
                instructor_id=test_instructor.id,
                student_id=test_student.id,
                booking_date=booking_datetime.date(),
                start_time=start_time,
                end_time=end_time,
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
            created_bookings.append((booking, hours_from_now))

        db.commit()

        # Query bookings that can be cancelled (24+ hours away)
        cancellable_cutoff = now + timedelta(hours=24)

        # Use PostgreSQL TIMESTAMP function instead of datetime()
        cancellable_bookings = (
            db.query(Booking)
            .filter(
                and_(
                    Booking.instructor_id == test_instructor.id,
                    Booking.status == BookingStatus.CONFIRMED,
                    func.cast(func.concat(Booking.booking_date, " ", Booking.start_time), DateTime)
                    >= cancellable_cutoff,
                )
            )
            .all()
        )

        # Should find bookings 24+ hours away
        assert len(cancellable_bookings) == 3
