# backend/tests/unit/services/test_notification_service.py
"""
Unit tests for the refactored NotificationService.

Tests all functionality including:
- BaseService integration
- Performance metrics collection
- Retry logic
- Exception handling
- Email sending with templates
- Database queries for reminders
"""

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from jinja2.exceptions import TemplateNotFound
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services.notification_service import NotificationService, retry


class TestRetryDecorator:
    """Test the retry decorator functionality."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_attempt(self):
        """Test retry decorator succeeds on first attempt."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test retry decorator succeeds after initial failures."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_attempts(self):
        """Test retry decorator exhausts all attempts."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Permanent failure")

        with pytest.raises(Exception, match="Permanent failure"):
            await test_func()

        assert call_count == 3


class TestNotificationService:
    """Test NotificationService functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_email_service(self):
        """Create a mock email service."""
        mock = Mock()
        mock.send_email = Mock(return_value={"id": "test-email-id"})
        return mock

    @pytest.fixture
    def mock_template_service(self):
        """Create a mock template service."""
        mock = Mock()
        mock.render_template = Mock(return_value="<html>Test Email</html>")
        return mock

    @pytest.fixture
    def notification_service(self, mock_db, mock_email_service, mock_template_service):
        """Create NotificationService with mocked dependencies."""
        # NEW APPROACH: Pass mocks directly to constructor
        service = NotificationService(db=mock_db, template_service=mock_template_service)  # Inject the mock!
        # Still need to replace email_service since it's created internally
        service.email_service = mock_email_service
        return service

    # Alternative approach if you need to patch email_service import:
    @pytest.fixture
    def notification_service_with_patched_email(self, mock_db, mock_email_service, mock_template_service):
        """Create NotificationService with patched email service."""
        with patch("app.services.notification_service.email_service", mock_email_service):
            service = NotificationService(db=mock_db, template_service=mock_template_service)
            return service

    @pytest.fixture
    def sample_booking(self):
        """Create a sample booking for testing."""
        student = User(id=1, email="student@test.com", full_name="Test Student", role="student")

        instructor = User(id=2, email="instructor@test.com", full_name="Test Instructor", role="instructor")

        booking = Booking(
            id=123,
            student=student,
            instructor=instructor,
            student_id=1,
            instructor_id=2,
            service_name="Piano Lessons",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            duration_minutes=60,
            total_price=75.00,
            status=BookingStatus.CONFIRMED,
        )

        return booking

    # Test BaseService Integration

    def test_inherits_from_base_service(self, notification_service):
        """Test that NotificationService inherits from BaseService."""
        from app.services.base import BaseService

        assert isinstance(notification_service, BaseService)

    def test_has_logger(self, notification_service):
        """Test that service has logger from BaseService."""
        assert hasattr(notification_service, "logger")
        assert notification_service.logger is not None

    def test_has_metrics_capability(self, notification_service):
        """Test that service can collect metrics."""
        assert hasattr(notification_service, "get_metrics")
        assert callable(notification_service.get_metrics)

    # Test Initialization

    def test_init_with_db(self, mock_db):
        """Test initialization with database session."""
        service = NotificationService(db=mock_db)
        assert service.db == mock_db
        assert not service._owns_db

    def test_init_without_db(self):
        """Test initialization without database session."""
        with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session

            service = NotificationService()
            assert service.db == mock_session
            assert service._owns_db

    # Test send_booking_confirmation

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_success(self, notification_service, sample_booking):
        """Test successful booking confirmation email sending."""
        result = await notification_service.send_booking_confirmation(sample_booking)

        assert result is True

        # Verify both emails were sent
        assert notification_service.email_service.send_email.call_count == 2

        # Verify templates were rendered
        assert notification_service.template_service.render_template.call_count == 2

        # Check template names
        template_calls = notification_service.template_service.render_template.call_args_list
        assert template_calls[0][0][0] == "email/booking/confirmation_student.html"
        assert template_calls[1][0][0] == "email/booking/confirmation_instructor.html"

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_student_email_fails(self, notification_service, sample_booking):
        """Test booking confirmation when student email fails."""
        # Make student email fail
        notification_service.email_service.send_email.side_effect = [
            Exception("Email failed"),  # Student email fails
            {"id": "test-email-id"},  # Instructor email succeeds
        ]

        result = await notification_service.send_booking_confirmation(sample_booking)

        # Should return False but not raise exception
        assert result is False

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_template_error(self, notification_service, sample_booking):
        """Test booking confirmation with template error."""
        notification_service.template_service.render_template.side_effect = TemplateNotFound("template.html")

        with pytest.raises(ServiceException, match="Email template error"):
            await notification_service.send_booking_confirmation(sample_booking)

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_metrics(self, notification_service, sample_booking):
        """Test that booking confirmation collects metrics."""
        # Clear any existing metrics
        notification_service.reset_metrics()

        await notification_service.send_booking_confirmation(sample_booking)

        metrics = notification_service.get_metrics()
        assert "send_booking_confirmation" in metrics
        assert metrics["send_booking_confirmation"]["count"] == 1
        assert metrics["send_booking_confirmation"]["success_count"] == 1

    # Test send_cancellation_notification

    @pytest.mark.asyncio
    async def test_send_cancellation_student_cancelled(self, notification_service, sample_booking):
        """Test cancellation notification when student cancels."""
        cancelled_by = sample_booking.student
        reason = "Schedule conflict"

        result = await notification_service.send_cancellation_notification(sample_booking, cancelled_by, reason)

        assert result is True

        # Should send 2 emails (instructor notification + student confirmation)
        assert notification_service.email_service.send_email.call_count == 2

    @pytest.mark.asyncio
    async def test_send_cancellation_instructor_cancelled(self, notification_service, sample_booking):
        """Test cancellation notification when instructor cancels."""
        cancelled_by = sample_booking.instructor
        reason = "Emergency"

        result = await notification_service.send_cancellation_notification(sample_booking, cancelled_by, reason)

        assert result is True

        # Should send 2 emails (student notification + instructor confirmation)
        assert notification_service.email_service.send_email.call_count == 2

    # Test send_reminder_emails

    @pytest.mark.asyncio
    async def test_send_reminder_emails_success(self, notification_service, sample_booking):
        """Test successful reminder email sending."""
        # Mock the database query
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [sample_booking]
        notification_service.db.query.return_value = mock_query

        count = await notification_service.send_reminder_emails()

        assert count == 1

        # Should send 2 emails per booking (student + instructor)
        assert notification_service.email_service.send_email.call_count == 2

    @pytest.mark.asyncio
    async def test_send_reminder_emails_no_bookings(self, notification_service):
        """Test reminder emails with no bookings."""
        # Mock empty query result
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        notification_service.db.query.return_value = mock_query

        count = await notification_service.send_reminder_emails()

        assert count == 0
        assert notification_service.email_service.send_email.call_count == 0

    @pytest.mark.asyncio
    async def test_send_reminder_emails_no_db_session(self):
        """Test reminder emails without database session."""
        service = NotificationService(db=None)
        service._owns_db = False  # Simulate no DB
        service.db = None

        with pytest.raises(ServiceException, match="Database session required"):
            await service.send_reminder_emails()

    @pytest.mark.asyncio
    async def test_send_reminder_emails_partial_failure(self, notification_service, sample_booking):
        """Test reminder emails with partial failures."""
        # Create a second booking
        booking2 = Booking(
            id=124,
            student=sample_booking.student,
            instructor=sample_booking.instructor,
            student_id=1,
            instructor_id=2,
            service_name="Piano Lessons",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 0),
            end_time=time(16, 0),
            duration_minutes=60,
            total_price=75.00,
            status=BookingStatus.CONFIRMED,
        )

        # Mock query to return 2 bookings
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [sample_booking, booking2]
        notification_service.db.query.return_value = mock_query

        # Make first booking's emails fail even after retries, second succeed
        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First 6 calls fail (3 retries x 2 emails for first booking)
            if call_count <= 6:
                raise Exception("Failed")
            return {"id": f"email-{call_count}"}  # Calls 7-8 succeed

        notification_service.email_service.send_email = mock_send

        with patch("asyncio.sleep", new_callable=AsyncMock):
            count = await notification_service.send_reminder_emails()

        # Only 1 booking successfully sent reminders
        assert count == 1
        assert call_count == 8  # 6 failed + 2 succeeded

    # Test retry logic

    @pytest.mark.asyncio
    async def test_email_retry_on_failure(self, notification_service, sample_booking):
        """Test that email sending retries on failure."""
        # Track call count manually
        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {"id": "test-email-id"}

        notification_service.email_service.send_email = mock_send

        # Call the actual method which has retry decorator
        # Need to patch the retry delay for testing
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await notification_service._send_student_reminder(sample_booking)

        assert result is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_email_retry_exhaustion(self, notification_service, sample_booking):
        """Test that email sending raises exception after retry exhaustion."""
        # Track call count
        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Permanent failure")

        notification_service.email_service.send_email = mock_send

        # Should raise exception after retries are exhausted
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="Permanent failure"):
                await notification_service._send_student_reminder(sample_booking)

        assert call_count == 3

    # Test template rendering

    @pytest.mark.asyncio
    async def test_template_context_includes_common_data(self, notification_service, sample_booking):
        """Test that template context includes all required data."""
        await notification_service.send_booking_confirmation(sample_booking)

        # Get the context passed to template
        render_calls = notification_service.template_service.render_template.call_args_list
        student_context = render_calls[0][0][1]  # Second argument of first call

        assert "booking" in student_context
        assert "formatted_date" in student_context
        assert "formatted_time" in student_context
        assert "subject" in student_context

    @pytest.mark.asyncio
    async def test_instructor_email_custom_colors(self, notification_service, sample_booking):
        """Test that instructor emails have custom colors."""
        await notification_service.send_booking_confirmation(sample_booking)

        # Get instructor email context
        render_calls = notification_service.template_service.render_template.call_args_list
        instructor_context = render_calls[1][0][1]  # Second call is instructor

        assert instructor_context.get("header_bg_color") == "#10B981"
        assert instructor_context.get("header_text_color") == "#D1FAE5"

    # Test error handling

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_with_none_booking(self, notification_service):
        """Test that sending confirmation with None booking returns False."""
        result = await notification_service.send_booking_confirmation(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_cancellation_with_none_booking(self, notification_service):
        """Test that sending cancellation with None booking returns False."""
        user = Mock(spec=User)
        result = await notification_service.send_cancellation_notification(None, user)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_cancellation_with_none_user(self, notification_service, sample_booking):
        """Test that sending cancellation with None user returns False."""
        result = await notification_service.send_cancellation_notification(sample_booking, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_template_error_propagation(self, notification_service, sample_booking):
        """Test that template not found errors raise ServiceException."""
        # Template not found should raise ServiceException
        notification_service.template_service.render_template.side_effect = TemplateNotFound("template.html")

        with pytest.raises(ServiceException, match="Email template error"):
            await notification_service.send_booking_confirmation(sample_booking)

    @pytest.mark.asyncio
    async def test_email_sending_failure_handled_gracefully(self, notification_service, sample_booking):
        """Test that email sending failures are handled gracefully."""
        # Make email sending fail with runtime error
        notification_service.email_service.send_email.side_effect = RuntimeError("Email service down")

        # Should return False, not raise exception
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await notification_service.send_booking_confirmation(sample_booking)

        assert result is False  # Graceful degradation

    # Test edge cases

    @pytest.mark.asyncio
    async def test_cancellation_without_reason(self, notification_service, sample_booking):
        """Test cancellation notification without reason."""
        result = await notification_service.send_cancellation_notification(sample_booking, sample_booking.student, None)

        assert result is True

        # Verify reason is handled as None
        render_calls = notification_service.template_service.render_template.call_args_list
        context = render_calls[0][0][1]
        assert context["reason"] is None

    @pytest.mark.asyncio
    async def test_date_time_formatting(self, notification_service, sample_booking):
        """Test that dates and times are formatted correctly in context."""
        await notification_service.send_booking_confirmation(sample_booking)

        render_calls = notification_service.template_service.render_template.call_args_list
        context = render_calls[0][0][1]

        # Verify date formatting
        assert "formatted_date" in context
        assert context["formatted_date"]  # Should have a value

        # Verify time formatting
        assert "formatted_time" in context
        assert ":" in context["formatted_time"]  # Should have time separator

    def test_singleton_instance_created(self):
        """Test that module creates singleton instance."""
        # Just verify the pattern is followed
        import app.services.notification_service as ns_module

        assert hasattr(ns_module, "notification_service")
        # Don't check type since it would trigger initialization


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
