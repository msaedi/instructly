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
from unittest.mock import Mock, patch

from jinja2.exceptions import TemplateNotFound
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceException
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services.notification_service import NotificationService, retry


class TestRetryDecorator:
    """Test the retry decorator functionality."""

    def test_retry_succeeds_first_attempt(self):
        """Test retry decorator succeeds on first attempt."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.1)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_succeeds_after_failures(self):
        """Test retry decorator succeeds after initial failures."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.01)  # Reduced from 0.1 for faster tests
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausts_attempts(self):
        """Test retry decorator exhausts all attempts."""
        call_count = 0

        @retry(max_attempts=3, backoff_seconds=0.01)  # Reduced from 0.1 for faster tests
        def test_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Permanent failure")

        with pytest.raises(Exception, match="Permanent failure"):
            test_func()

        assert call_count == 3


class TestNotificationService:
    """Test NotificationService functionality."""

    @pytest.fixture
    def mock_db(self):
        return Mock(spec=Session)

    @pytest.fixture
    def mock_email_service(self):
        mock = Mock()
        mock.send_email = Mock(return_value={"id": "test-email-id"})
        return mock

    @pytest.fixture
    def mock_template_service(self):
        mock = Mock()
        mock.render_template = Mock(return_value="<html>Test Email</html>")
        return mock

    @pytest.fixture
    def notification_service(self, mock_db, mock_email_service, mock_template_service):
        service = NotificationService(db=mock_db, template_service=mock_template_service)
        service.email_service = mock_email_service
        return service

    @pytest.fixture
    def sample_booking(self):
        student = User(
            id=generate_ulid(),
            email="student@test.com",
            first_name="Test",
            last_name="Student",
            phone="+12125550000",
            zip_code="10001",
        )
        instructor = User(
            id=generate_ulid(),
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
        )
        return Booking(
            id=123,
            student=student,
            instructor=instructor,
            student_id=generate_ulid(),
            instructor_id=generate_ulid(),
            service_name="Piano Lessons",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            duration_minutes=60,
            total_price=75.00,
            status=BookingStatus.CONFIRMED,
        )

    def test_inherits_from_base_service(self, notification_service):
        from app.services.base import BaseService

        assert isinstance(notification_service, BaseService)

    def test_has_logger_and_metrics(self, notification_service):
        assert hasattr(notification_service, "logger") and notification_service.logger
        assert hasattr(notification_service, "get_metrics") and callable(notification_service.get_metrics)

    def test_init_with_db(self, mock_db):
        service = NotificationService(db=mock_db)
        assert service.db == mock_db
        assert not service._owns_db

    def test_init_without_db(self):
        with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            service = NotificationService()
            assert service.db == mock_session
            assert service._owns_db

    def test_send_booking_confirmation_success(self, notification_service, sample_booking):
        result = notification_service.send_booking_confirmation(sample_booking)
        assert result is True
        assert notification_service.email_service.send_email.call_count == 2
        template_calls = notification_service.template_service.render_template.call_args_list
        assert template_calls[0][0][0] == "email/booking/confirmation_student.html"
        assert template_calls[1][0][0] == "email/booking/confirmation_instructor.html"

    @patch("app.services.notification_service.time.sleep")
    def test_send_booking_confirmation_student_email_fails(
        self, mock_sleep, notification_service, sample_booking
    ):
        notification_service.email_service.send_email.side_effect = [
            Exception("Email failed"),
            {"id": "test-email-id"},
        ]
        result = notification_service.send_booking_confirmation(sample_booking)
        assert result is False

    @patch("app.services.notification_service.time.sleep")
    def test_send_booking_confirmation_template_error(
        self, mock_sleep, notification_service, sample_booking
    ):
        notification_service.template_service.render_template.side_effect = TemplateNotFound("template.html")
        with pytest.raises(ServiceException, match="Email template error"):
            notification_service.send_booking_confirmation(sample_booking)

    def test_send_booking_confirmation_metrics(self, notification_service, sample_booking):
        notification_service.reset_metrics()
        notification_service.send_booking_confirmation(sample_booking)
        metrics = notification_service.get_metrics()
        assert metrics["send_booking_confirmation"]["count"] == 1
        assert metrics["send_booking_confirmation"]["success_count"] == 1

    def test_send_cancellation_student_cancelled(self, notification_service, sample_booking):
        result = notification_service.send_cancellation_notification(sample_booking, sample_booking.student, "Reason")
        assert result is True
        assert notification_service.email_service.send_email.call_count == 2

    def test_send_cancellation_instructor_cancelled(self, notification_service, sample_booking):
        result = notification_service.send_cancellation_notification(sample_booking, sample_booking.instructor, "Reason")
        assert result is True
        assert notification_service.email_service.send_email.call_count == 2

    def test_send_cancellation_missing_booking(self, notification_service):
        user = Mock(spec=User)
        assert notification_service.send_cancellation_notification(None, user) is False

    def test_send_cancellation_missing_user(self, notification_service, sample_booking):
        assert notification_service.send_cancellation_notification(sample_booking, None) is False

    def test_send_reminder_emails_uses_session_local_when_missing_db(self, monkeypatch):
        mock_db = Mock(spec=Session)
        with patch("app.database.SessionLocal", return_value=mock_db) as mock_session_local:
            service = NotificationService(db=None)

        assert mock_session_local.called
        monkeypatch.setattr(service, "_get_tomorrows_bookings", Mock(return_value=[]))

        result = service.send_reminder_emails()

        assert result == 0

    def test_send_reminder_emails_partial_failure(self, notification_service, sample_booking):
        booking2 = Booking(
            id=124,
            student=sample_booking.student,
            instructor=sample_booking.instructor,
            student_id=generate_ulid(),
            instructor_id=generate_ulid(),
            service_name="Piano Lessons",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 0),
            end_time=time(16, 0),
            duration_minutes=60,
            total_price=75.00,
            status=BookingStatus.CONFIRMED,
        )
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [sample_booking, booking2]
        notification_service.db.query.return_value = mock_query

        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 6:
                raise Exception("Failed")
            return {"id": f"email-{call_count}"}

        notification_service.email_service.send_email = mock_send
        with patch("time.sleep"):
            count = notification_service.send_reminder_emails()
        assert count == 1
        assert call_count == 8

    def test_email_retry_on_failure(self, notification_service, sample_booking):
        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {"id": "test-email-id"}

        notification_service.email_service.send_email = mock_send
        with patch("time.sleep"):
            result = notification_service._send_student_reminder(sample_booking)
        assert result is True
        assert call_count == 3

    def test_email_retry_exhaustion(self, notification_service, sample_booking):
        call_count = 0

        def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Permanent failure")

        notification_service.email_service.send_email = mock_send
        with patch("time.sleep"):
            with pytest.raises(Exception, match="Permanent failure"):
                notification_service._send_student_reminder(sample_booking)
        assert call_count == 3

    def test_template_context_includes_common_data(self, notification_service, sample_booking):
        notification_service.send_booking_confirmation(sample_booking)
        render_calls = notification_service.template_service.render_template.call_args_list
        student_context = render_calls[0][0][1]
        assert "booking" in student_context
        assert "formatted_date" in student_context
        assert "formatted_time" in student_context
        assert "subject" in student_context

    def test_instructor_email_custom_colors(self, notification_service, sample_booking):
        notification_service.send_booking_confirmation(sample_booking)
        render_calls = notification_service.template_service.render_template.call_args_list
        instructor_context = render_calls[1][0][1]
        assert instructor_context.get("header_bg_color") == "#10B981"
        assert instructor_context.get("header_text_color") == "#D1FAE5"

    def test_send_booking_confirmation_with_none_booking(self, notification_service):
        assert notification_service.send_booking_confirmation(None) is False

    def test_send_cancellation_with_none_booking(self, notification_service):
        user = Mock(spec=User)
        assert notification_service.send_cancellation_notification(None, user) is False

    def test_send_cancellation_with_none_user(self, notification_service, sample_booking):
        assert notification_service.send_cancellation_notification(sample_booking, None) is False

    @patch("app.services.notification_service.time.sleep")
    def test_template_error_propagation(self, mock_sleep, notification_service, sample_booking):
        notification_service.template_service.render_template.side_effect = TemplateNotFound("template.html")
        with pytest.raises(ServiceException, match="Email template error"):
            notification_service.send_booking_confirmation(sample_booking)

    @patch("app.services.notification_service.time.sleep")
    def test_email_sending_failure_handled_gracefully(
        self, mock_sleep, notification_service, sample_booking
    ):
        notification_service.email_service.send_email.side_effect = RuntimeError("Email service down")
        result = notification_service.send_booking_confirmation(sample_booking)
        assert result is False

    def test_cancellation_without_reason(self, notification_service, sample_booking):
        result = notification_service.send_cancellation_notification(sample_booking, sample_booking.student, None)
        assert result is True
        context = notification_service.template_service.render_template.call_args_list[0][0][1]
        assert context["reason"] is None

    def test_date_time_formatting(self, notification_service, sample_booking):
        notification_service.send_booking_confirmation(sample_booking)
        render_calls = notification_service.template_service.render_template.call_args_list
        context = render_calls[0][0][1]
        assert "formatted_date" in context
        assert "formatted_time" in context

    def test_no_singleton_exists(self):
        import app.services.notification_service as ns_module

        assert not hasattr(ns_module, "notification_service")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
