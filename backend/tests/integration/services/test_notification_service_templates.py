# backend/tests/integration/services/test_notification_service_templates.py
"""
Tests for the template-based notification service.

This test suite ensures that the refactored notification service
correctly renders templates and maintains the same functionality
as the original embedded HTML version.
"""

from datetime import date, datetime, time, timedelta
import re
from unittest.mock import patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.user import User

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def test_booking():
    """Create a test booking with all required fields."""
    student = User(
        id=generate_ulid(),
        email="student@example.com",
        first_name="Test",
        last_name="Student",
        phone="+12125550000",
        zip_code="10001",
    )

    instructor = User(
        id=generate_ulid(),
        email="instructor@example.com",
        first_name="Test",
        last_name="Instructor",
        phone="+12125550000",
        zip_code="10001",
    )

    booking_date = date.today() + timedelta(days=1)
    start_time = time(14, 0)
    end_time = time(15, 0)
    booking = Booking(
        id=100,
        student_id=student.id,  # Use the actual student ID
        instructor_id=instructor.id,  # Use the actual instructor ID
        instructor_service_id=10,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(booking_date, start_time, end_time),
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
        assert test_booking.student.first_name in html
        assert test_booking.instructor.first_name in html
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

    def test_send_booking_confirmation_success(self, notification_service_with_mocked_email, test_booking):
        """Test successful booking confirmation sends both emails."""
        result = notification_service_with_mocked_email.send_booking_confirmation(test_booking)

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

    def test_booking_confirmation_content(self, notification_service_with_mocked_email, test_booking):
        """Test that confirmation emails contain correct content."""
        notification_service_with_mocked_email.send_booking_confirmation(test_booking)

        # Check student email content
        student_html = notification_service_with_mocked_email.email_service.send_email.call_args_list[0].kwargs[
            "html_content"
        ]
        assert test_booking.student.first_name in student_html
        assert test_booking.service_name in student_html
        assert test_booking.meeting_location in student_html
        assert "75.00" in student_html  # Price

        # Ensure no unrendered Jinja tokens slipped through
        assert re.search(r'{{\s*.+?\s*}}', student_html) is None, "Found unrendered variable token"
        assert re.search(r'{%\s*.+?\s*%}', student_html) is None, "Found unrendered block token"
        assert re.search(r'{#\s*.+?\s*#}', student_html) is None, "Found unrendered comment token"


class TestCancellationNotification:
    """Test cancellation notification functionality."""

    @pytest.fixture(autouse=True)
    def reset_mock(self, notification_service_with_mocked_email):
        """Reset the email service mock before each test."""
        notification_service_with_mocked_email.email_service.send_email.reset_mock()
        yield

    def test_student_cancellation(self, notification_service_with_mocked_email, test_booking):
        """Test when student cancels booking."""
        result = notification_service_with_mocked_email.send_cancellation_notification(
            booking=test_booking, cancelled_by=test_booking.student, reason="Schedule conflict"
        )

        assert result is True
        assert notification_service_with_mocked_email.email_service.send_email.call_count == 2

        # Check both emails were sent to correct recipients
        email_calls = notification_service_with_mocked_email.email_service.send_email.call_args_list
        recipients = [call.kwargs["to_email"] for call in email_calls]
        assert test_booking.student.email in recipients
        assert test_booking.instructor.email in recipients

        # Find the instructor's email (should contain the reason)
        for call in email_calls:
            if call.kwargs["to_email"] == test_booking.instructor.email:
                instructor_html = call.kwargs["html_content"]
                assert "Schedule conflict" in instructor_html
                break
        else:
            assert False, "Instructor email not found"

    def test_instructor_cancellation(self, notification_service_with_mocked_email, test_booking):
        """Test when instructor cancels booking."""
        result = notification_service_with_mocked_email.send_cancellation_notification(
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

    def test_send_reminders(self, notification_service_with_mocked_email, test_booking):
        """Test reminder emails are sent correctly."""
        # Test individual reminder methods
        result = notification_service_with_mocked_email._send_student_reminder(test_booking)
        assert result is True

        result = notification_service_with_mocked_email._send_instructor_reminder(test_booking)
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

    @patch("app.services.notification_service.time.sleep")
    def test_handles_email_service_failure(
        self, mock_sleep, notification_service_with_mocked_email, test_booking
    ):
        """Test graceful handling when email service fails."""
        notification_service_with_mocked_email.email_service.send_email.side_effect = Exception(
            "Email service down"
        )

        result = notification_service_with_mocked_email.send_booking_confirmation(test_booking)
        assert result is False  # Should return False on failure

    @patch("app.services.notification_service.time.sleep")
    def test_handles_template_error(
        self, mock_sleep, notification_service_with_mocked_email, test_booking, template_service
    ):
        """Test handling of template rendering errors."""
        # We need to patch the template service that's inside the notification service
        with patch.object(
            notification_service_with_mocked_email.template_service,
            "render_template",
            side_effect=Exception("Template error"),
        ):
            result = notification_service_with_mocked_email.send_booking_confirmation(test_booking)
            assert result is False
