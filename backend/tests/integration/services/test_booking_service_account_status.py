# backend/tests/integration/services/test_booking_service_account_status.py
"""
Integration tests for BookingService with account status constraints.

Tests that suspended/deactivated instructors cannot receive new bookings
and that past bookings remain visible regardless of instructor status.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService


class TestBookingServiceAccountStatus:
    """Test booking service respects account status."""

    @pytest.fixture
    def suspended_instructor(self, db: Session, test_instructor_with_availability: User):
        """Create a suspended instructor."""
        test_instructor_with_availability.account_status = "suspended"
        db.commit()
        return test_instructor_with_availability

    @pytest.fixture
    def deactivated_instructor(self, db: Session, test_instructor_with_availability: User):
        """Create a deactivated instructor."""
        test_instructor_with_availability.account_status = "deactivated"
        db.commit()
        return test_instructor_with_availability

    @pytest.fixture
    def past_booking(self, db: Session, test_instructor: User, test_student: User):
        """Create a past booking for the instructor."""
        profile = test_instructor.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        # Create a past booking
        yesterday = date.today() - timedelta(days=1)
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=yesterday,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.COMPLETED,
            meeting_location="Online",
            location_type="neutral",
        )
        db.add(booking)
        db.commit()
        return booking

    @pytest.mark.asyncio
    async def test_create_booking_with_suspended_instructor(
        self, db: Session, suspended_instructor: User, test_student: User, mock_notification_service
    ):
        """Test that bookings cannot be created with suspended instructors."""
        profile = suspended_instructor.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        # Get an available slot
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == suspended_instructor.id, AvailabilitySlot.specific_date == tomorrow
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=suspended_instructor.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            selected_duration=60,
            end_time=time(slot.start_time.hour + 1, slot.start_time.minute),
            location_type="neutral",
            meeting_location="Online",
            student_note="Test booking",
        )

        with pytest.raises(BusinessRuleException) as exc_info:
            await booking_service.create_booking(test_student, booking_data, 60)

        assert "temporarily suspended" in str(exc_info.value)
        assert "cannot receive new bookings" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_booking_with_deactivated_instructor(
        self, db: Session, deactivated_instructor: User, test_student: User, mock_notification_service
    ):
        """Test that bookings cannot be created with deactivated instructors."""
        profile = deactivated_instructor.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        # Get an available slot
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == deactivated_instructor.id, AvailabilitySlot.specific_date == tomorrow
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=deactivated_instructor.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            selected_duration=60,
            end_time=time(slot.start_time.hour + 1, slot.start_time.minute),
            location_type="neutral",
            meeting_location="Online",
            student_note="Test booking",
        )

        with pytest.raises(BusinessRuleException) as exc_info:
            await booking_service.create_booking(test_student, booking_data, 60)

        assert "deactivated" in str(exc_info.value)
        assert "cannot receive bookings" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_booking_with_active_instructor_succeeds(
        self, db: Session, test_instructor_with_availability: User, test_student: User, mock_notification_service
    ):
        """Test that bookings can be created with active instructors."""
        # Ensure instructor is active
        test_instructor_with_availability.account_status = "active"
        db.commit()

        profile = test_instructor_with_availability.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        # Get an available slot
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            selected_duration=60,
            end_time=time(slot.start_time.hour + 1, slot.start_time.minute),
            location_type="neutral",
            meeting_location="Online",
            student_note="Test booking",
        )

        # Should succeed without exception
        booking = await booking_service.create_booking(test_student, booking_data, 60)

        assert booking.id is not None
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.instructor_id == test_instructor_with_availability.id

    def test_past_bookings_visible_for_suspended_instructor(
        self, db: Session, test_instructor: User, test_student: User, past_booking: Booking, mock_notification_service
    ):
        """Test that past bookings remain visible when instructor is suspended."""
        # Suspend the instructor
        test_instructor.account_status = "suspended"
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Get student's bookings - should include past booking
        student_bookings = booking_service.get_bookings_for_user(test_student)
        assert len(student_bookings) >= 1
        assert any(b.id == past_booking.id for b in student_bookings)

        # Get instructor's bookings - should include past booking
        instructor_bookings = booking_service.get_bookings_for_user(test_instructor)
        assert len(instructor_bookings) >= 1
        assert any(b.id == past_booking.id for b in instructor_bookings)

    def test_past_bookings_visible_for_deactivated_instructor(
        self, db: Session, test_instructor: User, test_student: User, past_booking: Booking, mock_notification_service
    ):
        """Test that past bookings remain visible when instructor is deactivated."""
        # Deactivate the instructor
        test_instructor.account_status = "deactivated"
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Get student's bookings - should include past booking
        student_bookings = booking_service.get_bookings_for_user(test_student)
        assert len(student_bookings) >= 1
        assert any(b.id == past_booking.id for b in student_bookings)

        # Get instructor's bookings - should include past booking
        instructor_bookings = booking_service.get_bookings_for_user(test_instructor)
        assert len(instructor_bookings) >= 1
        assert any(b.id == past_booking.id for b in instructor_bookings)

    def test_booking_details_accessible_for_inactive_instructor(
        self, db: Session, test_instructor: User, past_booking: Booking, mock_notification_service
    ):
        """Test that booking details remain accessible for inactive instructors."""
        # Deactivate the instructor
        test_instructor.account_status = "deactivated"
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Should be able to get booking details
        booking = booking_service.repository.get_booking_with_details(past_booking.id)
        assert booking is not None
        assert booking.id == past_booking.id
        assert booking.instructor_id == test_instructor.id

    @pytest.mark.asyncio
    async def test_cancel_future_booking_when_instructor_suspended(
        self, db: Session, test_instructor: User, test_student: User, mock_notification_service
    ):
        """Test that future bookings can be cancelled when instructor becomes suspended."""
        # Create a future booking first
        profile = test_instructor.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        tomorrow = date.today() + timedelta(days=1)
        future_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Online",
            location_type="neutral",
        )
        db.add(future_booking)
        db.commit()

        # Now suspend the instructor
        test_instructor.account_status = "suspended"
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Student should still be able to cancel the booking
        cancelled_booking = await booking_service.cancel_booking(
            future_booking.id, test_student, "Instructor suspended"
        )

        assert cancelled_booking.status == BookingStatus.CANCELLED
        assert cancelled_booking.cancellation_reason == "Instructor suspended"

    def test_instructor_search_excludes_suspended(self, db: Session, catalog_data: dict, suspended_instructor: User):
        """Test that instructor search excludes suspended instructors."""
        from app.auth import get_password_hash
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service
        from app.models.user import User, UserRole
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        # Create an active instructor with services
        active_instructor = User(
            email="active.instructor@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Active Instructor",
            is_active=True,
            role=UserRole.INSTRUCTOR,
            account_status="active",
        )
        db.add(active_instructor)
        db.flush()

        # Create profile
        profile = InstructorProfile(
            user_id=active_instructor.id,
            bio="Active instructor bio",
            areas_of_service="Manhattan",
            years_experience=5,
            min_advance_booking_hours=2,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()

        # Add a service
        piano_service = next((s for s in catalog_data["services"] if s.slug == "piano-lessons"), None)
        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=piano_service.id,
            hourly_rate=100,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.commit()

        repo = InstructorProfileRepository(db)

        # Get all instructors - should exclude suspended
        all_instructors = repo.get_all_with_details()

        # Should include active instructor (who has services)
        assert any(p.user_id == active_instructor.id for p in all_instructors)

        # Should exclude suspended instructor
        assert not any(p.user_id == suspended_instructor.id for p in all_instructors)

    def test_instructor_search_excludes_deactivated(
        self, db: Session, catalog_data: dict, deactivated_instructor: User
    ):
        """Test that instructor search excludes deactivated instructors."""
        from app.auth import get_password_hash
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service
        from app.models.user import User, UserRole
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        # Create an active instructor with services
        active_instructor = User(
            email="active2.instructor@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Active Instructor 2",
            is_active=True,
            role=UserRole.INSTRUCTOR,
            account_status="active",
        )
        db.add(active_instructor)
        db.flush()

        # Create profile
        profile = InstructorProfile(
            user_id=active_instructor.id,
            bio="Another active instructor bio",
            areas_of_service="Brooklyn",
            years_experience=3,
            min_advance_booking_hours=1,
            buffer_time_minutes=10,
        )
        db.add(profile)
        db.flush()

        # Add a service
        guitar_service = next((s for s in catalog_data["services"] if s.slug == "guitar-lessons"), None)
        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=guitar_service.id,
            hourly_rate=90,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.commit()

        repo = InstructorProfileRepository(db)

        # Get all instructors - should exclude deactivated
        all_instructors = repo.get_all_with_details()

        # Should include active instructor (who has services)
        assert any(p.user_id == active_instructor.id for p in all_instructors)

        # Should exclude deactivated instructor
        assert not any(p.user_id == deactivated_instructor.id for p in all_instructors)
