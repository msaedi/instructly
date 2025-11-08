# backend/tests/repositories/test_booking_repository_future_bookings.py
"""
Tests for BookingRepository.get_instructor_future_bookings() method.

Tests various scenarios including:
- No future bookings
- Multiple future bookings
- Mix of past and future bookings
- Cancelled bookings exclusion
- Date filtering
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.repositories.booking_repository import BookingRepository

try:  # pragma: no cover - fallback for direct backend test invocation
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs

try:  # pragma: no cover - allow running from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


class TestBookingRepositoryFutureBookings:
    """Test the get_instructor_future_bookings method."""

    @pytest.fixture
    def booking_repository(self, db: Session):
        """Create a BookingRepository instance."""
        return BookingRepository(db)

    def get_user_today(self, user_id: int, db: Session) -> date:
        """Get today's date using the same timezone logic as the repository."""
        from app.core.timezone_utils import get_user_today_by_id

        return get_user_today_by_id(user_id, db)

    @pytest.fixture
    def instructor_service(self, db: Session, test_instructor: User):
        """Get or create a service for the test instructor."""
        profile = test_instructor.instructor_profile
        if not profile:
            raise ValueError("Test instructor has no profile")

        service = next((s for s in profile.instructor_services if s.is_active), None)
        if not service:
            raise ValueError("Test instructor has no active services")

        return service

    def create_booking(
        self,
        db: Session,
        instructor_id: int,
        student_id: int,
        service_id: int,
        booking_date: date,
        status: BookingStatus = BookingStatus.CONFIRMED,
        start_hour: int = 14,
        duration_minutes: int = 60,
        offset_index: int | None = None,
    ) -> Booking:
        """Helper to create a booking."""
        start_time = time(start_hour % 24, 0)
        end_time = (datetime.combine(booking_date, start_time) + timedelta(minutes=duration_minutes)).time()
        booking = create_booking_pg_safe(
            db,
            student_id=student_id,
            instructor_id=instructor_id,
            instructor_service_id=service_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=duration_minutes,
            status=status,
            meeting_location="Online",
            location_type="neutral",
            offset_index=offset_index,
        )
        if status == BookingStatus.CANCELLED:
            booking.cancelled_at = datetime.now(timezone.utc)
            db.flush()
        return booking

    def test_no_future_bookings(self, booking_repository: BookingRepository, test_instructor: User):
        """Test when instructor has no future bookings."""
        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert future_bookings == []

    def test_single_future_booking(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test with a single future booking."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)
        booking = self.create_booking(
            db, test_instructor.id, test_student.id, instructor_service.id, tomorrow, offset_index=0
        )
        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert len(future_bookings) == 1
        assert future_bookings[0].id == booking.id
        assert future_bookings[0].booking_date == tomorrow

    def test_multiple_future_bookings(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test with multiple future bookings."""
        today = self.get_user_today(test_instructor.id, db)
        # Create bookings for next 3 days
        bookings = []
        for i in range(1, 4):
            future_date = today + timedelta(days=i)
            booking = self.create_booking(
                db,
                test_instructor.id,
                test_student.id,
                instructor_service.id,
                future_date,
                offset_index=i,
            )
            bookings.append(booking)
        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert len(future_bookings) == 3
        # Should be ordered by date
        assert future_bookings[0].booking_date < future_bookings[1].booking_date
        assert future_bookings[1].booking_date < future_bookings[2].booking_date

    def test_mix_of_past_and_future_bookings(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that only future bookings are returned when past bookings exist."""
        # Use the same date calculation as the repository to avoid timezone issues
        today = self.get_user_today(test_instructor.id, db)

        # Create past bookings
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        past_booking1 = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            yesterday,
            offset_index=0,
        )
        past_booking2 = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            last_week,
            offset_index=1,
        )

        # Create future bookings
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)

        future_booking1 = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            tomorrow,
            offset_index=2,
        )
        future_booking2 = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            next_week,
            offset_index=3,
        )

        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        # Filter to only the bookings we created (ignore any today bookings from other tests)
        # We expect at least our 2 future bookings
        our_booking_ids = {future_booking1.id, future_booking2.id}
        our_future_bookings = [b for b in future_bookings if b.id in our_booking_ids]

        assert len(our_future_bookings) == 2

        # Verify past bookings are not included
        past_booking_ids = {past_booking1.id, past_booking2.id}
        returned_booking_ids = {b.id for b in future_bookings}
        assert not past_booking_ids.intersection(returned_booking_ids)

    def test_cancelled_bookings_excluded_by_default(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that cancelled bookings are excluded by default."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)

        # Create confirmed and cancelled bookings
        confirmed_booking = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            tomorrow,
            BookingStatus.CONFIRMED,
            offset_index=0,
        )

        _cancelled_booking = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            tomorrow,
            BookingStatus.CANCELLED,
            offset_index=1,
        )

        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert len(future_bookings) == 1
        assert future_bookings[0].id == confirmed_booking.id
        assert future_bookings[0].status == BookingStatus.CONFIRMED

    def test_cancelled_bookings_included_when_requested(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that cancelled bookings can be included when requested."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)

        # Create confirmed and cancelled bookings
        _confirmed_booking = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            tomorrow,
            BookingStatus.CONFIRMED,
            offset_index=0,
        )

        _cancelled_booking = self.create_booking(
            db,
            test_instructor.id,
            test_student.id,
            instructor_service.id,
            tomorrow,
            BookingStatus.CANCELLED,
            offset_index=1,
        )

        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(
            instructor_id=test_instructor.id, exclude_cancelled=False
        )

        assert len(future_bookings) == 2
        booking_statuses = {b.status for b in future_bookings}
        assert BookingStatus.CONFIRMED in booking_statuses
        assert BookingStatus.CANCELLED in booking_statuses

    def test_custom_from_date(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test using a custom from_date parameter."""
        today = self.get_user_today(test_instructor.id, db)
        # Create bookings at different points in the future
        tomorrow = today + timedelta(days=1)
        in_3_days = today + timedelta(days=3)
        in_5_days = today + timedelta(days=5)

        booking1 = self.create_booking(
            db, test_instructor.id, test_student.id, instructor_service.id, tomorrow, offset_index=0
        )
        booking2 = self.create_booking(
            db, test_instructor.id, test_student.id, instructor_service.id, in_3_days, offset_index=1
        )
        booking3 = self.create_booking(
            db, test_instructor.id, test_student.id, instructor_service.id, in_5_days, offset_index=2
        )

        db.commit()

        # Get bookings from 3 days in the future
        future_bookings = booking_repository.get_instructor_future_bookings(
            instructor_id=test_instructor.id, from_date=in_3_days
        )

        assert len(future_bookings) == 2
        booking_ids = [b.id for b in future_bookings]
        assert booking1.id not in booking_ids  # Before from_date
        assert booking2.id in booking_ids
        assert booking3.id in booking_ids

    def test_booking_on_today_is_future(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that bookings on today's date are considered future bookings."""
        today = self.get_user_today(test_instructor.id, db)

        booking = self.create_booking(
            db, test_instructor.id, test_student.id, instructor_service.id, today, offset_index=0
        )

        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert len(future_bookings) == 1
        assert future_bookings[0].id == booking.id
        assert future_bookings[0].booking_date == today

    def test_different_booking_statuses(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test handling of different booking statuses."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)

        # Create bookings with different statuses
        statuses = [
            BookingStatus.CONFIRMED,
            BookingStatus.PENDING,
            BookingStatus.COMPLETED,
            BookingStatus.NO_SHOW,
            BookingStatus.CANCELLED,
        ]

        bookings = []
        for index, status in enumerate(statuses):
            booking = self.create_booking(
                db,
                test_instructor.id,
                test_student.id,
                instructor_service.id,
                tomorrow,
                status,
                start_hour=14 + index * 2,
                offset_index=index,
            )
            bookings.append(booking)

        db.commit()

        # Default: exclude cancelled
        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        # Should get all except cancelled
        assert len(future_bookings) == 4
        returned_statuses = {b.status for b in future_bookings}
        assert BookingStatus.CANCELLED not in returned_statuses

    def test_no_bookings_for_instructor(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that method only returns bookings for specified instructor."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)

        # Create a second instructor
        from app.auth import get_password_hash
        from app.models.instructor import InstructorProfile

        second_instructor = User(
            email="second.instructor@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            first_name="Second",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(second_instructor)
        db.flush()

        # Create profile for second instructor
        profile = InstructorProfile(
            user_id=second_instructor.id,
            bio="Second instructor bio",
            years_experience=3,
            min_advance_booking_hours=2,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=second_instructor, boroughs=["Manhattan"])
        db.commit()

        # Create booking for first instructor
        self.create_booking(db, test_instructor.id, test_student.id, instructor_service.id, tomorrow)

        db.commit()

        # Query for second instructor
        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=second_instructor.id)

        assert len(future_bookings) == 0

    def test_ordering_by_date_and_time(
        self,
        db: Session,
        booking_repository: BookingRepository,
        test_instructor: User,
        test_student: User,
        instructor_service: Service,
    ):
        """Test that bookings are ordered by date and start time."""
        today = self.get_user_today(test_instructor.id, db)
        tomorrow = today + timedelta(days=1)

        # Create bookings at different times on same day
        booking_afternoon = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            instructor_service_id=instructor_service.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Online",
            location_type="neutral",
        )

        booking_morning = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            instructor_service_id=instructor_service.id,
            booking_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Online",
            location_type="neutral",
        )

        # Add in reverse order
        db.add(booking_afternoon)
        db.add(booking_morning)
        db.commit()

        future_bookings = booking_repository.get_instructor_future_bookings(instructor_id=test_instructor.id)

        assert len(future_bookings) == 2
        # Should be ordered by time
        assert future_bookings[0].start_time == time(9, 0)
        assert future_bookings[1].start_time == time(14, 0)
