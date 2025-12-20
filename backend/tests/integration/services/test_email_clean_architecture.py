# backend/tests/services/test_email_clean_architecture.py
"""
Test that email templates use clean architecture with no references
to removed concepts. Ensures emails use booking's self-contained data.

Run with:
    cd backend
    pytest tests/services/test_email_clean_architecture.py -v
"""

from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services.notification_service import NotificationService


class TestEmailCleanArchitecture:
    """Test email templates follow clean architecture principles."""

    @pytest.fixture
    def mock_booking(self):
        """Create a mock booking with all required fields."""
        # Mock users
        student = Mock(spec=User)
        student.id = 1
        student.email = "student@example.com"
        student.first_name = "Test"
        student.last_name = "Student"

        instructor = Mock(spec=User)
        instructor.id = 2
        instructor.email = "instructor@example.com"
        instructor.first_name = "Test"
        instructor.last_name = "Instructor"

        # Mock booking with clean fields
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.student = student
        booking.instructor = instructor
        booking.student_id = student.id
        booking.instructor_id = instructor.id

        # Time-based fields (no slot references!)
        booking.booking_date = date(2025, 7, 15)
        booking.start_time = time(9, 0)
        booking.end_time = time(10, 0)
        booking.duration_minutes = 60

        # Service details
        booking.service_id = generate_ulid()
        booking.service_name = "Piano Lessons"
        booking.hourly_rate = 50.00
        booking.total_price = 50.00
        booking.service_area = "Manhattan"

        # Location details
        booking.location_type = "neutral"
        booking.location_type_display = "Neutral Location"
        booking.meeting_location = "Central Park"

        # Notes
        booking.student_note = "Looking forward to the lesson"
        booking.instructor_note = None

        # Status
        booking.status = BookingStatus.CONFIRMED

        # Ensure NO slot references
        assert not hasattr(booking, "availability_slot_id")
        assert not hasattr(booking, "availability_slot")

        return booking

    @pytest.fixture
    def notification_service(self, db):
        """Create notification service with mocked email sending."""
        service = NotificationService(db)
        # Mock the email service to not actually send emails
        service.email_service.send_email = Mock(return_value={"id": "test-email-id"})
        return service

    def test_student_booking_confirmation_uses_clean_data(self, notification_service, mock_booking):
        """Test student booking confirmation email uses booking's direct fields."""
        # Send the email
        result = notification_service._send_student_booking_confirmation(mock_booking)

        assert result is True

        # Get the email that was "sent"
        call_args = notification_service.email_service.send_email.call_args
        assert call_args is not None

        # Extract email content
        kwargs = call_args.kwargs
        html_content = kwargs["html_content"]
        subject = kwargs["subject"]

        # Verify subject uses booking data
        assert "Piano Lessons" in subject
        assert "Test" in subject  # First name only in friendly context per Clean Break

        # Verify email content uses booking's time fields
        assert "July 15, 2025" in html_content or "2025-07-15" in html_content
        assert "9:00" in html_content
        assert "60 minutes" in html_content

        # Verify NO references to removed concepts
        assert "availability_slot_id" not in html_content.lower()
        assert "slot_id" not in html_content.lower()
        assert "is_available" not in html_content.lower()
        assert "is_recurring" not in html_content.lower()

    def test_instructor_notification_uses_clean_data(self, notification_service, mock_booking):
        """Test instructor notification email uses booking's direct fields."""
        result = notification_service._send_instructor_booking_notification(mock_booking)

        assert result is True

        # Verify email was sent with clean data
        call_args = notification_service.email_service.send_email.call_args
        html_content = call_args.kwargs["html_content"]

        # Should include booking details
        assert "Test Student" in html_content
        assert "Piano Lessons" in html_content
        assert "$50.00" in html_content

        # Should NOT include removed concepts
        assert "availability_slot" not in html_content.lower()

    def test_cancellation_email_uses_clean_data(self, notification_service, mock_booking):
        """Test cancellation emails use booking's direct fields."""
        # Mock cancelled_by user
        cancelled_by = Mock(spec=User)
        cancelled_by.id = mock_booking.student_id

        _result = notification_service.send_cancellation_notification(
            mock_booking, cancelled_by, reason="Schedule conflict"
        )

        # Should send two emails (to both parties)
        assert notification_service.email_service.send_email.call_count >= 2

        # Check all sent emails
        for call in notification_service.email_service.send_email.call_args_list:
            html_content = call.kwargs["html_content"]

            # Should include booking info
            assert "Piano Lessons" in html_content

            # Should NOT include slot references
            assert "slot_id" not in html_content.lower()

    def test_reminder_email_uses_clean_data(self, notification_service, mock_booking):
        """Test reminder emails use booking's direct fields."""
        # Test student reminder
        result = notification_service._send_student_reminder(mock_booking)
        assert result is True

        # Test instructor reminder
        result = notification_service._send_instructor_reminder(mock_booking)
        assert result is True

        # Both emails should have been sent
        assert notification_service.email_service.send_email.call_count == 2

        # Check both emails
        for call in notification_service.email_service.send_email.call_args_list:
            html_content = call.kwargs["html_content"]

            # Should show tomorrow's lesson info
            assert "tomorrow" in html_content.lower()
            assert "9:00" in html_content

            # Should NOT reference slots
            assert "availability_slot" not in html_content.lower()

    def test_email_formatting_helpers_work(self, mock_booking):
        """Test that date/time formatting in emails works correctly."""
        # Test the formatting pattern used in emails
        booking_datetime = datetime.combine(mock_booking.booking_date, mock_booking.start_time)
        formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
        formatted_time = booking_datetime.strftime("%-I:%M %p")

        assert formatted_date == "Tuesday, July 15, 2025"
        assert formatted_time == "9:00 AM"

        # These should never reference slots
        assert "slot" not in formatted_date.lower()
        assert "slot" not in formatted_time.lower()

    def test_all_email_types_avoid_removed_fields(self, notification_service, mock_booking):
        """Comprehensive test that all email types avoid removed fields."""
        # List of all email methods
        email_methods = [
            notification_service._send_student_booking_confirmation,
            notification_service._send_instructor_booking_notification,
            notification_service._send_student_reminder,
            notification_service._send_instructor_reminder,
        ]

        # Test each email type
        for method in email_methods:
            # Reset mock
            notification_service.email_service.send_email.reset_mock()

            # Send email directly
            method(mock_booking)

            # Verify email was sent
            assert notification_service.email_service.send_email.called

            # Get email content
            call_args = notification_service.email_service.send_email.call_args
            html_content = call_args.kwargs["html_content"]

            # List of removed concepts that should NEVER appear
            removed_concepts = [
                "availability_slot_id",
                "slot_id",
                "is_available",
                "is_recurring",
                "day_of_week",
                "InstructorAvailability",
            ]

            for concept in removed_concepts:
                assert concept not in html_content, f"Found '{concept}' in {method.__name__} email"


class TestEmailDataStructures:
    """Test that email data structures are clean."""

    def test_booking_object_has_required_fields(self, test_booking, db):
        """Verify test booking has all fields emails need."""
        required_fields = [
            "id",
            "student",
            "instructor",
            "booking_date",
            "start_time",
            "end_time",
            "duration_minutes",
            "service_name",
            "total_price",
            "location_type_display",
            "status",
        ]

        for field in required_fields:
            assert hasattr(test_booking, field), f"Booking missing required field: {field}"

        # Verify NO slot reference
        assert not hasattr(test_booking, "availability_slot_id")

    def test_booking_location_display_works(self, test_booking):
        """Test that location_type_display property works correctly."""
        # This is used in emails
        assert test_booking.location_type_display == "Neutral Location"

        # Should not reference slots
        assert "slot" not in test_booking.location_type_display.lower()

    def test_send_reminder_emails_queries_correctly(self, db):
        """Test that send_reminder_emails uses clean date-based query."""
        service = NotificationService(db)

        # Mock the query to return empty list
        with patch.object(db, "query") as mock_query:
            mock_filter = Mock()
            mock_filter.all.return_value = []
            mock_query.return_value.filter.return_value = mock_filter

            # Call the method
            count = service.send_reminder_emails()

            # Verify it queried correctly
            mock_query.assert_called_with(Booking)

            # The filter should check booking_date and status
            # but NOT availability_slot_id
            mock_query.return_value.filter.call_args

            # This is a bit tricky to test, but we can at least verify
            # the method completed without errors
            assert count == 0  # No bookings found
