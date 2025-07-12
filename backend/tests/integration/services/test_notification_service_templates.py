# backend/tests/integration/services/test_notification_service_templates.py
"""
Tests for the template-based notification service.

This test suite ensures that the refactored notification service
correctly renders templates and maintains the same functionality
as the original embedded HTML version.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest

from app.models.booking import Booking, BookingStatus
from app.models.user import User


@pytest.fixture
def test_booking():
    """Create a test booking with all required fields."""
    student = User(id=1, email="student@example.com", full_name="Test Student", role="student")

    instructor = User(id=2, email="instructor@example.com", full_name="Test Instructor", role="instructor")

    booking = Booking(
        id=100,
        student_id=1,
        instructor_id=2,
        service_id=10,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(14, 0),
        end_time=time(15, 0),
        service_name="Piano Lessons",
        hourly_rate=75.00,
        total_price=75.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        location_type="instructor_location",
        meeting_location="123 Music Studio, NYC",
        student_note="First time learning piano!",
        service_area="Manhattan",
    )

    # Set relationships
    booking.student = student
    booking.instructor = instructor

    return booking


class TestTemplateRendering:
    """Test that templates render correctly."""

    def test_base_template_exists(self, template_service):
        """Test that base template exists."""
        assert template_service.template_exists("email/base.html")

    def test_booking_confirmation_templates_exist(self, template_service):
        """Test that all booking confirmation templates exist."""
        templates = [
            "email/booking/confirmation_student.html",
            "email/booking/confirmation_instructor.html",
            "email/booking/cancellation_student.html",
            "email/booking/cancellation_instructor.html",
            "email/booking/cancellation_confirmation_student.html",
            "email/booking/cancellation_confirmation_instructor.html",
            "email/booking/reminder_student.html",
            "email/booking/reminder_instructor.html",
        ]

        for template in templates:
            assert template_service.template_exists(template), f"Template {template} not found"

    def test_template_renders_without_errors(self, test_booking, template_service):
        """Test that templates render without errors."""
        context = {
            "booking": test_booking,
            "formatted_date": "Monday, January 15, 2025",
            "formatted_time": "2:00 PM",
            "subject": "Test Subject",
        }

        # Test student confirmation template
        html = template_service.render_template("email/booking/confirmation_student.html", context)

        # Check key content is present
        assert test_booking.student.full_name in html
        assert test_booking.instructor.full_name in html
        assert test_booking.service_name in html
        assert "2:00 PM" in html
        assert "$75.00" in html


class TestBookingConfirmation:
    """Test booking confirmation email functionality."""

    @pytest.fixture(autouse=True)
    def reset_mock(self, notification_service_with_mocked_email):
        """Reset the email service mock before each test."""
        notification_service_with_mocked_email.email_service.send_email.reset_mock()
        yield

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_success(self, notification_service_with_mocked_email, test_booking):
        """Test successful booking confirmation sends both emails."""
        result = await notification_service_with_mocked_email.send_booking_confirmation(test_booking)

        assert result is True
        # Check the email service that's inside the notification service
        assert notification_service_with_mocked_email.email_service.send_email.call_count == 2

        # Check student email
        student_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[0]
        assert student_call.kwargs["to_email"] == test_booking.student.email
        assert "Booking Confirmed" in student_call.kwargs["subject"]

        # Check instructor email
        instructor_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[1]
        assert instructor_call.kwargs["to_email"] == test_booking.instructor.email
        assert "New Booking" in instructor_call.kwargs["subject"]

    @pytest.mark.asyncio
    async def test_booking_confirmation_content(self, notification_service_with_mocked_email, test_booking):
        """Test that confirmation emails contain correct content."""
        await notification_service_with_mocked_email.send_booking_confirmation(test_booking)

        # Check student email content
        student_html = notification_service_with_mocked_email.email_service.send_email.call_args_list[0].kwargs[
            "html_content"
        ]
        assert test_booking.student.full_name in student_html
        assert test_booking.service_name in student_html
        assert test_booking.meeting_location in student_html
        assert "75.00" in student_html  # Price

        # Check no f-string bugs
        assert "{" not in student_html or "{{" in student_html  # Only Jinja syntax
        assert "}" not in student_html or "}}" in student_html


class TestCancellationNotification:
    """Test cancellation notification functionality."""

    @pytest.fixture(autouse=True)
    def reset_mock(self, notification_service_with_mocked_email):
        """Reset the email service mock before each test."""
        notification_service_with_mocked_email.email_service.send_email.reset_mock()
        yield

    @pytest.mark.asyncio
    async def test_student_cancellation(self, notification_service_with_mocked_email, test_booking):
        """Test when student cancels booking."""
        result = await notification_service_with_mocked_email.send_cancellation_notification(
            booking=test_booking, cancelled_by=test_booking.student, reason="Schedule conflict"
        )

        assert result is True
        assert notification_service_with_mocked_email.email_service.send_email.call_count == 2

        # Instructor should get cancellation notification
        instructor_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[0]
        assert instructor_call.kwargs["to_email"] == test_booking.instructor.email
        instructor_html = instructor_call.kwargs["html_content"]
        assert "Schedule conflict" in instructor_html

        # Student should get confirmation
        student_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[1]
        assert student_call.kwargs["to_email"] == test_booking.student.email

    @pytest.mark.asyncio
    async def test_instructor_cancellation(self, notification_service_with_mocked_email, test_booking):
        """Test when instructor cancels booking."""
        result = await notification_service_with_mocked_email.send_cancellation_notification(
            booking=test_booking, cancelled_by=test_booking.instructor, reason="Emergency"
        )

        assert result is True
        assert notification_service_with_mocked_email.email_service.send_email.call_count == 2

        # Student should get cancellation notification
        student_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[0]
        assert student_call.kwargs["to_email"] == test_booking.student.email
        student_html = student_call.kwargs["html_content"]
        assert "Emergency" in student_html

        # Instructor should get confirmation
        instructor_call = notification_service_with_mocked_email.email_service.send_email.call_args_list[1]
        assert instructor_call.kwargs["to_email"] == test_booking.instructor.email


class TestReminderEmails:
    """Test reminder email functionality."""

    @pytest.fixture(autouse=True)
    def reset_mock(self, notification_service_with_mocked_email):
        """Reset the email service mock before each test."""
        notification_service_with_mocked_email.email_service.send_email.reset_mock()
        yield

    @pytest.mark.asyncio
    async def test_send_reminders(self, notification_service_with_mocked_email, test_booking):
        """Test reminder emails are sent correctly."""
        # Test individual reminder methods
        result = await notification_service_with_mocked_email._send_student_reminder(test_booking)
        assert result is True

        result = await notification_service_with_mocked_email._send_instructor_reminder(test_booking)
        assert result is True

        assert notification_service_with_mocked_email.email_service.send_email.call_count == 2

        # Check content
        for call in notification_service_with_mocked_email.email_service.send_email.call_args_list:
            html = call.kwargs["html_content"]
            assert "tomorrow" in html.lower()
            assert test_booking.service_name in html


class TestTemplateVariables:
    """Test that all required template variables are provided."""

    def test_common_context(self, template_service):
        """Test common context variables."""
        context = template_service.get_common_context()

        assert "brand_name" in context
        assert "current_year" in context
        assert "frontend_url" in context
        assert context["current_year"] == datetime.now().year

    def test_no_missing_variables(self, test_booking, template_service):
        """Test templates don't have missing variables."""
        context = {
            "booking": test_booking,
            "formatted_date": "Monday, January 15, 2025",
            "formatted_time": "2:00 PM",
            "subject": "Test Subject",
            "reason": "Test reason",
            "cancelled_by": "student",
        }

        # This should not raise any undefined variable errors
        for template in [
            "email/booking/confirmation_student.html",
            "email/booking/cancellation_student.html",
            "email/booking/reminder_student.html",
        ]:
            html = template_service.render_template(template, context)
            # Check no Jinja2 undefined markers
            assert "undefined" not in html.lower()


class TestErrorHandling:
    """Test error handling in notification service."""

    @pytest.fixture(autouse=True)
    def reset_mock(self, notification_service_with_mocked_email):
        """Reset the email service mock before each test."""
        notification_service_with_mocked_email.email_service.send_email.reset_mock()
        yield

    @pytest.mark.asyncio
    async def test_handles_email_service_failure(self, notification_service_with_mocked_email, test_booking):
        """Test graceful handling when email service fails."""
        notification_service_with_mocked_email.email_service.send_email.side_effect = Exception("Email service down")

        result = await notification_service_with_mocked_email.send_booking_confirmation(test_booking)
        assert result is False  # Should return False on failure

    @pytest.mark.asyncio
    async def test_handles_template_error(self, notification_service_with_mocked_email, test_booking, template_service):
        """Test handling of template rendering errors."""
        # We need to patch the template service that's inside the notification service
        with patch.object(
            notification_service_with_mocked_email.template_service,
            "render_template",
            side_effect=Exception("Template error"),
        ):
            result = await notification_service_with_mocked_email.send_booking_confirmation(test_booking)
            assert result is False
