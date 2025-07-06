# backend/tests/integration/test_booking_service_edge_cases.py
"""
Additional edge case tests for BookingService to achieve >90% coverage.

This test suite covers:
- Error handling paths
- Edge cases in statistics
- Booking reminders functionality
- Various filter combinations

UPDATED FOR WORK STREAM #10: Single-table availability design.
"""

import logging
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService


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
        # Get slot directly (single-table design)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date == tomorrow,
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            availability_slot_id=slot.id, service_id=service.id, location_type="neutral", meeting_location="Online"
        )

        # Should succeed despite notification failure
        booking = await booking_service.create_booking(test_student, booking_data)

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
            service_id=service.id,  # Required field
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.skill,
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
                service_id=service.id,  # Required field
                booking_date=date.today() + timedelta(days=i + 1),
                start_time=time(10, 0),
                end_time=time(11, 0),
                service_name=service.skill,
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
            service_id=service.id,  # Required field
            booking_date=date.today() - timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(12, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=100.0,  # 2 hours
            duration_minutes=120,
            status=BookingStatus.COMPLETED,
            location_type="neutral",
            completed_at=datetime.utcnow(),
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
                booking_id=99999, user=test_instructor, update_data=update_data  # Non-existent ID
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
            booking_service.complete_booking(booking_id=99999, instructor=test_instructor)  # Non-existent ID

    def test_complete_booking_wrong_instructor(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test instructor can only complete their own bookings."""
        # Create another instructor
        another_instructor = User(
            email="another.instructor@example.com",
            full_name="Another Instructor",
            hashed_password="hashed",
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        db.add(another_instructor)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(ValidationException, match="You can only complete your own bookings"):
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
        """Test checking availability for non-existent slot."""
        booking_service = BookingService(db, mock_notification_service)
        result = await booking_service.check_availability(slot_id=99999, service_id=1)  # Non-existent

        assert result["available"] is False
        assert result["reason"] == "Slot not found"

    @pytest.mark.asyncio
    async def test_check_availability_service_not_found(
        self, db: Session, test_instructor_with_availability: User, mock_notification_service: Mock
    ):
        """Test checking availability with non-existent service."""
        # Get a valid slot directly (single-table design)
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date == tomorrow,
            )
            .first()
        )

        booking_service = BookingService(db, mock_notification_service)
        result = await booking_service.check_availability(slot_id=slot.id, service_id=99999)  # Non-existent

        assert result["available"] is False
        assert result["reason"] == "Service not found or no longer available"


class TestBookingServiceReminders:
    """Test booking reminder functionality."""

    @pytest.mark.asyncio
    async def test_send_booking_reminders_success(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test sending reminders for tomorrow's bookings."""
        # Ensure booking is for tomorrow
        test_booking.booking_date = date.today() + timedelta(days=1)
        test_booking.status = BookingStatus.CONFIRMED
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        # Mock the notification service to succeed
        mock_notification_service.send_reminder_emails = AsyncMock(return_value=None)

        count = await booking_service.send_booking_reminders()

        assert count >= 1
        mock_notification_service.send_reminder_emails.assert_called()

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

        # Create multiple bookings for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        test_booking.booking_date = tomorrow
        test_booking.status = BookingStatus.CONFIRMED

        # Create another booking
        another_booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            service_id=service.id,  # Required field
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="neutral",
        )
        db.add(another_booking)
        db.commit()

        # Make reminder sending fail for all
        mock_notification_service.send_reminder_emails = AsyncMock(side_effect=Exception("Email service error"))

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


# Fixtures


@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    mock = Mock(spec=NotificationService)
    mock.send_booking_confirmation = AsyncMock()
    mock.send_cancellation_notification = AsyncMock()
    mock.send_reminder_emails = AsyncMock()
    return mock
