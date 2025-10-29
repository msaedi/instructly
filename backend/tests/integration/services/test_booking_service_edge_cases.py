# backend/tests/integration/services/test_booking_service_edge_cases.py
"""
Additional edge case tests for BookingService to achieve >90% coverage.

This test suite covers:
- Error handling paths
- Edge cases in statistics
- Booking reminders functionality
- Various filter combinations

UPDATED FOR WORK STREAM #10: Single-table availability design.
UPDATED FOR WORK STREAM #9: Layer independence - time-based booking.
"""

from datetime import date, datetime, time, timedelta, timezone
import logging
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from app.core.ulid_helper import generate_ulid
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService

try:  # pragma: no cover - fallback when pytest runs from backend/
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Edge-case flows use seeded $50 bookings."""
    yield


class TestBookingServiceErrorHandling:
    """Test error handling in BookingService."""

    @pytest.mark.asyncio
    async def test_create_booking_notification_failure(
        self, db: Session, test_instructor_with_availability: User, test_student: User, mock_notification_service: Mock
    ):
        """Test booking creation succeeds even if notification fails."""
        # Setup notification to fail
        mock_notification_service.send_booking_confirmation.side_effect = Exception("Email service down")

        # Get valid booking data
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        tomorrow = date.today() + timedelta(days=1)
        # Get slot directly (single-table design) - FIXED: date → specific_date
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,  # FIXED: date → specific_date
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)

        # FIXED: Use time-based booking (Work Stream #9)
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            end_time=slot.end_time,
            selected_duration=60,
            instructor_service_id=service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Should succeed despite notification failure
        booking = await booking_service.create_booking(
            test_student, booking_data, selected_duration=booking_data.selected_duration
        )

        assert booking.id is not None
        assert booking.status == BookingStatus.CONFIRMED
        mock_notification_service.send_booking_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_booking_notification_failure(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock, caplog
    ):
        """Test booking cancellation succeeds even if notification fails."""
        # Setup notification to fail
        mock_notification_service.send_cancellation_notification.side_effect = Exception("Email service down")

        booking_service = BookingService(db, mock_notification_service)

        with caplog.at_level(logging.ERROR):
            cancelled_booking = await booking_service.cancel_booking(
                booking_id=test_booking.id, user=test_student, reason="Test cancellation"
            )

        # Booking should still be cancelled
        assert cancelled_booking.status == BookingStatus.CANCELLED
        assert "Failed to send cancellation notification" in caplog.text
        mock_notification_service.send_cancellation_notification.assert_called_once()


class TestBookingServiceQueryVariations:
    """Test various query parameter combinations."""

    def test_get_bookings_with_status_filter(
        self, db: Session, test_student: User, test_instructor_with_availability: User, mock_notification_service: Mock
    ):
        """Test getting bookings filtered by status."""
        # Get instructor's service
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create a cancelled booking
        cancelled_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,  # Required field
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CANCELLED,
            location_type="neutral",
        )
        db.add(cancelled_booking)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Get only cancelled bookings
        cancelled_bookings = booking_service.get_bookings_for_user(test_student, status=BookingStatus.CANCELLED)

        assert all(b.status == BookingStatus.CANCELLED for b in cancelled_bookings)
        assert any(b.id == cancelled_booking.id for b in cancelled_bookings)

    def test_get_bookings_with_limit(
        self, db: Session, test_student: User, test_instructor_with_availability: User, mock_notification_service: Mock
    ):
        """Test getting bookings with limit parameter."""
        # Get instructor's service
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create multiple bookings
        for i in range(5):
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor_with_availability.id,
                instructor_service_id=service.id,  # Required field
                booking_date=date.today() + timedelta(days=i + 1),
                start_time=time(10, 0),
                end_time=time(11, 0),
                service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
                hourly_rate=service.hourly_rate,
                total_price=50.0,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
                location_type="neutral",
            )
            db.add(booking)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Get only 3 bookings
        limited_bookings = booking_service.get_bookings_for_user(test_student, limit=3)

        assert len(limited_bookings) == 3


class TestBookingServiceStatisticsEdgeCases:
    """Test edge cases in booking statistics."""

    def test_booking_stats_no_bookings(self, db: Session, test_instructor: User, mock_notification_service: Mock):
        """Test statistics when instructor has no bookings."""
        booking_service = BookingService(db, mock_notification_service)
        stats = booking_service.get_booking_stats_for_instructor(test_instructor.id)

        assert stats["total_bookings"] == 0
        assert stats["upcoming_bookings"] == 0
        assert stats["completed_bookings"] == 0
        assert stats["cancelled_bookings"] == 0
        assert stats["total_earnings"] == 0
        assert stats["this_month_earnings"] == 0
        assert stats["completion_rate"] == 0
        assert stats["cancellation_rate"] == 0

    def test_booking_stats_with_completed_bookings(
        self, db: Session, test_instructor_with_availability: User, test_student: User, mock_notification_service: Mock
    ):
        """Test statistics with completed bookings for earnings calculation."""
        # Get instructor's service
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create a completed booking
        completed_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,  # Required field
            booking_date=date.today() - timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(12, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=100.0,  # 2 hours
            duration_minutes=120,
            status=BookingStatus.COMPLETED,
            location_type="neutral",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(completed_booking)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)
        stats = booking_service.get_booking_stats_for_instructor(test_instructor_with_availability.id)

        assert stats["completed_bookings"] >= 1
        assert stats["total_earnings"] >= 100.0
        if completed_booking.booking_date.month == date.today().month:
            assert stats["this_month_earnings"] >= 100.0


class TestBookingServiceUpdateEdgeCases:
    """Test edge cases in booking updates."""

    def test_update_booking_not_found(self, db: Session, test_instructor: User, mock_notification_service: Mock):
        """Test updating non-existent booking."""
        booking_service = BookingService(db, mock_notification_service)
        update_data = BookingUpdate(instructor_note="Test note")

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.update_booking(
                booking_id=generate_ulid(), user=test_instructor, update_data=update_data  # Non-existent ID
            )

    def test_update_booking_meeting_location(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test updating meeting location."""
        booking_service = BookingService(db, mock_notification_service)

        new_location = "123 Main St, Room 202"
        update_data = BookingUpdate(meeting_location=new_location)
        updated = booking_service.update_booking(
            booking_id=test_booking.id, user=test_instructor_with_availability, update_data=update_data
        )

        assert updated.meeting_location == new_location


class TestBookingServiceCompleteEdgeCases:
    """Test edge cases for completing bookings."""

    def test_complete_booking_not_found(self, db: Session, test_instructor: User, mock_notification_service: Mock):
        """Test completing non-existent booking."""
        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.complete_booking(booking_id=generate_ulid(), instructor=test_instructor)  # Non-existent ID

    def test_complete_booking_wrong_instructor(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test instructor can only complete their own bookings."""
        # Create another instructor
        another_instructor = User(
            email="another.instructor@example.com",
            first_name="Another",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(another_instructor)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(ValidationException, match="Only instructors can mark bookings as complete"):
            booking_service.complete_booking(
                booking_id=test_booking.id, instructor=another_instructor  # Wrong instructor
            )

    def test_complete_cancelled_booking(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test cannot complete a cancelled booking."""
        # Cancel the booking first
        test_booking.status = BookingStatus.CANCELLED
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(BusinessRuleException, match="Only confirmed bookings can be completed"):
            booking_service.complete_booking(booking_id=test_booking.id, instructor=test_instructor_with_availability)


class TestBookingServiceAvailabilityEdgeCases:
    """Test edge cases for availability checking."""

    @pytest.mark.asyncio
    async def test_check_availability_slot_not_found(self, db: Session, mock_notification_service: Mock):
        """Test checking availability for non-existent time slot."""
        booking_service = BookingService(db, mock_notification_service)

        # FIXED: Use time-based check_availability method
        result = await booking_service.check_availability(
            instructor_id=generate_ulid(),  # Non-existent instructor
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_id=generate_ulid(),
        )

        assert result["available"] is False
        assert "not found" in result["reason"].lower() or "instructor" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_check_availability_service_not_found(
        self, db: Session, test_instructor_with_availability: User, mock_notification_service: Mock
    ):
        """Test checking availability with non-existent service."""
        tomorrow = date.today() + timedelta(days=1)

        # Get a valid slot to know the available times - FIXED: date → specific_date
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,  # FIXED: date → specific_date
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)

        # FIXED: Use time-based check_availability method
        result = await booking_service.check_availability(
            instructor_id=test_instructor_with_availability.id,
            booking_date=tomorrow,
            start_time=slot.start_time if slot else time(9, 0),
            end_time=slot.end_time if slot else time(10, 0),
            service_id=generate_ulid(),  # Non-existent service
        )

        assert result["available"] is False
        assert result["reason"] == "Service not found or no longer available"


class TestBookingServiceReminders:
    """Test booking reminder functionality."""

    @pytest.mark.asyncio
    async def test_send_booking_reminders_success(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test sending reminders for tomorrow's bookings."""
        # Ensure booking is for tomorrow based on student's timezone
        from app.core.timezone_utils import get_user_today_by_id

        student_today = get_user_today_by_id(test_booking.student_id, db)
        test_booking.booking_date = student_today + timedelta(days=1)
        test_booking.status = BookingStatus.CONFIRMED
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Mock the notification service to succeed
        mock_notification_service._send_booking_reminders = AsyncMock(return_value=1)

        count = await booking_service.send_booking_reminders()

        assert count >= 1
        mock_notification_service._send_booking_reminders.assert_called()

    @pytest.mark.asyncio
    async def test_send_booking_reminders_with_failures(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        test_student: User,
        mock_notification_service: Mock,
        caplog,
    ):
        """Test reminder sending continues despite individual failures."""
        # Get instructor's service
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create multiple bookings for tomorrow based on student's timezone
        from app.core.timezone_utils import get_user_today_by_id

        student_today = get_user_today_by_id(test_booking.student_id, db)
        tomorrow = student_today + timedelta(days=1)
        test_booking.booking_date = tomorrow
        test_booking.status = BookingStatus.CONFIRMED

        # Create another booking
        another_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,  # Required field
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="neutral",
        )
        db.add(another_booking)
        db.commit()

        # Make reminder sending fail for all
        mock_notification_service._send_booking_reminders = AsyncMock(side_effect=Exception("Email service error"))

        booking_service = BookingService(db, mock_notification_service)

        with caplog.at_level(logging.ERROR):
            count = await booking_service.send_booking_reminders()

        # Should return 0 since all failed
        assert count == 0
        assert "Error sending reminder for booking" in caplog.text

    @pytest.mark.asyncio
    async def test_send_booking_reminders_no_bookings_tomorrow(self, db: Session, mock_notification_service: Mock):
        """Test reminder sending when no bookings for tomorrow."""
        # Ensure no bookings for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        bookings_tomorrow = (
            db.query(Booking).filter(Booking.booking_date == tomorrow, Booking.status == BookingStatus.CONFIRMED).all()
        )
        for booking in bookings_tomorrow:
            booking.status = BookingStatus.CANCELLED
        db.commit()

        booking_service = BookingService(db, mock_notification_service)
        count = await booking_service.send_booking_reminders()

        assert count == 0


class TestStudentDoubleBookingPrevention:
    """Test that student double-booking prevention is working correctly."""

    @pytest.mark.asyncio
    async def test_student_cannot_double_book_overlapping_sessions(
        self,
        db: Session,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor: User,
        mock_notification_service: Mock,
    ):
        """
        Test that students cannot book overlapping sessions with different instructors.
        This verifies the double-booking prevention is working correctly.
        """
        # Get first instructor's service (Math)
        profile1 = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service1 = (
            db.query(Service).filter(Service.instructor_profile_id == profile1.id, Service.is_active == True).first()
        )

        # Create a truly different second instructor
        from app.auth import get_password_hash
        from app.models.user import User

        second_instructor = User(
            email="second.instructor@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Second",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(second_instructor)
        db.flush()

        profile2 = db.query(InstructorProfile).filter(InstructorProfile.user_id == second_instructor.id).first()

        # If no profile exists, create one
        if not profile2:
            profile2 = InstructorProfile(
                user_id=second_instructor.id,
                min_advance_booking_hours=1,
            )
            db.add(profile2)
            db.flush()
            add_service_areas_for_boroughs(db, user=second_instructor, boroughs=["Manhattan"])

        # Get or create Piano service for second instructor
        # Get Piano catalog service
        piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name.ilike("%piano%")).first()
        if not piano_catalog:
            # Create one if it doesn't exist
            category = db.query(ServiceCategory).first()
            piano_catalog = ServiceCatalog(name="Piano Lessons", slug="piano-lessons", category_id=category.id)
            db.add(piano_catalog)
            db.flush()

        # Check if service already exists for this instructor
        piano_service = (
            db.query(Service)
            .filter(
                Service.instructor_profile_id == profile2.id,
                Service.service_catalog_id == piano_catalog.id,
                Service.is_active == True,
            )
            .first()
        )

        if not piano_service:
            piano_service = Service(
                instructor_profile_id=profile2.id,
                service_catalog_id=piano_catalog.id,
                hourly_rate=100.0,
                duration_options=[60],  # Add duration_options
                is_active=True,
            )
            db.add(piano_service)

        # Add availability for both instructors using service-level week save
        availability_service = AvailabilityService(db)
        tomorrow = date.today() + timedelta(days=7)  # ensure future week to avoid fixture data collisions
        monday = tomorrow - timedelta(days=tomorrow.weekday())
        # Seed future schedules so both instructors have non-overlapping windows
        schedule_second = [
            {
                "date": tomorrow.isoformat(),
                "start_time": "09:00",
                "end_time": "12:00",
            },
            {
                "date": tomorrow.isoformat(),
                "start_time": "13:00",
                "end_time": "17:00",
            },
        ]
        week_payload_second = WeekSpecificScheduleCreate(
            week_start=monday,
            clear_existing=True,
            schedule=schedule_second,
        )
        await availability_service.save_week_availability(second_instructor.id, week_payload_second)

        schedule_first = [
            {
                "date": tomorrow.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
            }
        ]
        week_payload_first = WeekSpecificScheduleCreate(
            week_start=monday,
            clear_existing=True,
            schedule=schedule_first,
        )
        await availability_service.save_week_availability(
            test_instructor_with_availability.id, week_payload_first
        )

        booking_service = BookingService(db, mock_notification_service)

        # First booking: Math lesson 10:00-11:00 AM
        # Get available slot for first instructor
        _math_slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,
            )
            .first()
        )

        booking1_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            booking_date=tomorrow,
            start_time=time(10, 0),  # Fixed time 10:00-11:00
            end_time=time(11, 0),
            selected_duration=60,
            instructor_service_id=service1.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            test_student, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.id is not None
        assert booking1.status == BookingStatus.CONFIRMED

        # Second booking: Piano lesson that overlaps with first booking
        booking2_data = BookingCreate(
            instructor_id=second_instructor.id,
            booking_date=tomorrow,
            start_time=time(10, 30),  # Overlaps with first booking (10:00-11:00)
            end_time=time(11, 30),
            selected_duration=60,
            instructor_service_id=piano_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # This should fail with ConflictException
        from app.core.exceptions import ConflictException

        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                test_student, booking2_data, selected_duration=booking2_data.selected_duration
            )

        # Verify the error message
        assert "already have a booking" in str(exc_info.value) or "conflicts with an existing booking" in str(
            exc_info.value
        )

        # Verify only the first booking exists
        student_bookings = booking_service.get_bookings_for_user(test_student)
        confirmed_tomorrow = [
            b for b in student_bookings if b.booking_date == tomorrow and b.status == BookingStatus.CONFIRMED
        ]
        assert len(confirmed_tomorrow) == 1
        assert confirmed_tomorrow[0].id == booking1.id

    @pytest.mark.asyncio
    async def test_student_can_book_non_overlapping_sessions(
        self,
        db: Session,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor: User,
        mock_notification_service: Mock,
    ):
        """
        Test that students CAN book non-overlapping sessions with different instructors.
        This ensures the conflict checker doesn't block valid bookings.
        """
        # Get first instructor's service (Math)
        profile1 = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service1 = (
            db.query(Service).filter(Service.instructor_profile_id == profile1.id, Service.is_active == True).first()
        )

        # Create second instructor with Piano service
        second_instructor = test_instructor
        profile2 = db.query(InstructorProfile).filter(InstructorProfile.user_id == second_instructor.id).first()

        # If no profile exists, create one
        if not profile2:
            profile2 = InstructorProfile(
                user_id=second_instructor.id,
                min_advance_booking_hours=1,
            )
            db.add(profile2)
            db.flush()
            add_service_areas_for_boroughs(db, user=second_instructor, boroughs=["Manhattan"])

        # Get or create Piano service for second instructor
        # Get Piano catalog service
        piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name.ilike("%piano%")).first()
        if not piano_catalog:
            # Create one if it doesn't exist
            category = db.query(ServiceCategory).first()
            piano_catalog = ServiceCatalog(name="Piano Lessons", slug="piano-lessons", category_id=category.id)
            db.add(piano_catalog)
            db.flush()

        # Check if service already exists for this instructor
        piano_service = (
            db.query(Service)
            .filter(
                Service.instructor_profile_id == profile2.id,
                Service.service_catalog_id == piano_catalog.id,
                Service.is_active == True,
            )
            .first()
        )

        if not piano_service:
            piano_service = Service(
                instructor_profile_id=profile2.id,
                service_catalog_id=piano_catalog.id,
                hourly_rate=100.0,
                duration_options=[60],  # Add duration_options
                is_active=True,
            )
            db.add(piano_service)

        # Add availability for both instructors using the service layer to avoid overlaps
        availability_service = AvailabilityService(db)
        tomorrow = date.today() + timedelta(days=1)
        monday = tomorrow - timedelta(days=tomorrow.weekday())

        schedule_second = [
            {
                "date": tomorrow.isoformat(),
                "start_time": "09:00",
                "end_time": "12:00",
            },
            {
                "date": tomorrow.isoformat(),
                "start_time": "13:00",
                "end_time": "17:00",
            },
        ]
        week_payload_second = WeekSpecificScheduleCreate(
            week_start=monday,
            clear_existing=True,
            schedule=schedule_second,
        )
        await availability_service.save_week_availability(second_instructor.id, week_payload_second)

        db.expire_all()

        booking_service = BookingService(db, mock_notification_service)

        # First booking: Math lesson 10:00-11:00 AM
        booking1_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            booking_date=tomorrow,
            start_time=time(10, 0),
            end_time=time(11, 0),
            selected_duration=60,
            instructor_service_id=service1.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            test_student, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.id is not None
        assert booking1.status == BookingStatus.CONFIRMED

        # Second booking: Piano lesson 2:00-3:00 PM (no overlap)
        booking2_data = BookingCreate(
            instructor_id=second_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 0),  # 2:00 PM - no overlap with 10-11 AM
            end_time=time(15, 0),  # 3:00 PM
            selected_duration=60,
            instructor_service_id=piano_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # This should succeed - no overlap
        booking2 = await booking_service.create_booking(
            test_student, booking2_data, selected_duration=booking2_data.selected_duration
        )

        # Both bookings should exist
        assert booking2.id is not None
        assert booking2.status == BookingStatus.CONFIRMED

        # Verify both bookings were created
        student_bookings = booking_service.get_bookings_for_user(test_student)
        confirmed_tomorrow = [
            b for b in student_bookings if b.booking_date == tomorrow and b.status == BookingStatus.CONFIRMED
        ]
        assert len(confirmed_tomorrow) == 2

        # Verify no time overlap
        assert booking1.end_time <= booking2.start_time

        print("SUCCESS: Student can book non-overlapping sessions correctly!")


# Fixtures


@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    mock = Mock(spec=NotificationService)
    mock.send_booking_confirmation = AsyncMock()
    mock.send_cancellation_notification = AsyncMock()
    mock.send_reminder_emails = AsyncMock()
    return mock
