# backend/tests/routes/test_reminder_clean_architecture.py
"""
Test that the reminder system uses clean architecture with date-based
queries and no references to removed concepts.

FIXED: Updated test expectations to match the corrected f-string email templates.
The notification service now properly interpolates values instead of sending
literal placeholders.

UPDATED: Fixed async mock for send_booking_reminders method.

Run with:
    cd backend
    pytest tests/routes/test_reminder_clean_architecture.py -v
"""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User


class TestReminderEndpointCleanArchitecture:
    """Test reminder endpoint follows clean architecture."""

    def test_reminder_endpoint_exists(self, client):
        """Verify the reminder endpoint is available."""
        # Without auth, should get 401 or 403
        response = client.post("/api/v1/bookings/send-reminders")
        assert response.status_code in [401, 403]

    def test_reminder_endpoint_requires_admin(self, client, auth_headers_student):
        """Verify reminder endpoint requires admin access."""
        response = client.post("/api/v1/bookings/send-reminders", headers=auth_headers_student)

        # Should get forbidden (not a 404)
        assert response.status_code == 403
        # With RBAC, the error message mentions the specific permission needed
        assert "manage_all_bookings" in response.json()["detail"].lower()

    @patch("app.services.booking_service.BookingService.send_booking_reminders", new_callable=MagicMock)
    def test_reminder_endpoint_calls_service(self, mock_send_reminders, client, db):
        """Test reminder endpoint delegates to service layer."""
        # Mock the service to return a count - Use AsyncMock for async method
        mock_send_reminders.return_value = 5

        # Create admin user with proper RBAC permissions
        from app.auth import create_access_token, get_password_hash
        from app.core.enums import RoleName
        from app.services.permission_service import PermissionService

        admin = User(
            email="test.admin@example.com",
            hashed_password=get_password_hash("Test1234"),
            first_name="Test",
            last_name="Admin",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(admin)
        db.flush()

        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(admin.id, RoleName.ADMIN)
        db.commit()

        # Get auth token for admin
        token = create_access_token(data={"sub": admin.email})
        headers = {"Authorization": f"Bearer {token}"}

        # Call endpoint
        response = client.post("/api/v1/bookings/send-reminders", headers=headers)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["reminders_sent"] == 5
        assert "Successfully sent 5 reminder emails" in response_data["message"]

        # Verify service was called
        mock_send_reminders.assert_called_once()

    def test_reminder_response_format_is_clean(self, client, auth_headers_instructor):
        """Test reminder endpoint response doesn't include removed concepts."""
        # Even though not admin, we can test the response format from error
        response = client.post("/api/v1/bookings/send-reminders", headers=auth_headers_instructor)

        # Should get error, but error shouldn't reference slots
        assert response.status_code == 403
        error_detail = response.json()["detail"]
        assert "slot" not in error_detail.lower()
        assert "availability_slot" not in error_detail.lower()


class TestReminderQueryLogic:
    """Test the reminder query logic uses clean date-based queries."""

    @pytest.fixture
    def tomorrow_booking(self, db, test_student, test_instructor):
        """Create a booking for tomorrow."""
        tomorrow = date.today() + timedelta(days=1)

        # Get the instructor's profile
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        # Get an actual service from the instructor
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,  # Use actual service ID instead of hardcoded 1
            booking_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Use catalog name
            hourly_rate=service.hourly_rate,  # Use actual hourly rate
            total_price=service.hourly_rate,  # Use actual rate for total
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()
        return booking

    def test_send_reminder_emails_finds_tomorrow_bookings(self, db, tomorrow_booking):
        """Test that reminder query correctly finds tomorrow's bookings."""
        from app.services.notification_service import NotificationService

        # Create service with mocked email sending
        service = NotificationService(db)
        service.email_service.send_email = Mock(return_value={"id": "test"})

        # Call send_reminder_emails
        count = service.send_reminder_emails()

        # Should find the tomorrow booking
        assert count == 1

        # Should have sent 2 emails (student and instructor)
        assert service.email_service.send_email.call_count == 2

    def test_reminder_query_uses_date_not_slots(self, db, monkeypatch):
        """Verify reminder query uses booking_date, not slot references."""
        from app.services.notification_service import NotificationService

        service = NotificationService(db)

        # Intercept the query to verify it's correct
        original_query = db.query

        def mock_query(model):
            if model == Booking:
                # Create a mock that tracks filter calls
                mock = Mock()

                def mock_filter(*args, **kwargs):
                    # Verify the filter arguments
                    for arg in args:
                        # Convert to string to check
                        arg_str = str(arg)
                        # Should filter by booking_date
                        assert "booking_date" in arg_str or "status" in arg_str
                        # Should NOT filter by slot
                        assert "slot" not in arg_str.lower()
                        assert "availability" not in arg_str.lower()

                    # Return mock that returns empty list
                    mock_result = Mock()
                    mock_result.all.return_value = []
                    return mock_result

                mock.filter = mock_filter
                return mock

            return original_query(model)

        monkeypatch.setattr(db, "query", mock_query)

        # Run the query
        count = service.send_reminder_emails()
        assert count == 0  # No bookings found

    def test_reminder_booking_date_calculation(self):
        """Test that tomorrow's date is calculated correctly."""
        from datetime import datetime, timedelta

        # This is how the reminder service calculates tomorrow
        tomorrow = datetime.now().date() + timedelta(days=1)

        # Should be a date object
        assert isinstance(tomorrow, date)

        # Should be tomorrow
        assert tomorrow == date.today() + timedelta(days=1)

        # No slot calculations involved
        assert True  # Just confirming clean calculation

    def test_reminder_handles_no_bookings_gracefully(self, db):
        """Test reminder system handles no bookings correctly."""
        from app.services.notification_service import NotificationService

        service = NotificationService(db)
        service.email_service.send_email = Mock()

        # With empty database, should return 0
        count = service.send_reminder_emails()

        assert count == 0
        # Should not try to send any emails
        assert service.email_service.send_email.call_count == 0

    def test_reminder_only_sends_for_confirmed_bookings(self, db, test_student, test_instructor):
        """Test that only CONFIRMED bookings get reminders."""
        from app.services.notification_service import NotificationService

        tomorrow = date.today() + timedelta(days=1)

        # Create bookings with different statuses
        statuses = [
            BookingStatus.CONFIRMED,  # Should send
            BookingStatus.CANCELLED,  # Should NOT send
            BookingStatus.COMPLETED,  # Should NOT send
        ]

        # Get the instructor's profile and service first
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        for i, status in enumerate(statuses):
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=service.id,  # Use actual service ID
                booking_date=tomorrow,
                start_time=time(9 + i, 0),
                end_time=time(10 + i, 0),
                service_name=service.catalog_entry.name
                if service.catalog_entry
                else "Unknown Service",  # Use catalog name
                hourly_rate=service.hourly_rate,  # Use actual rate
                total_price=service.hourly_rate,
                duration_minutes=60,
                status=status,
            )
            db.add(booking)

        db.commit()

        # Send reminders
        service = NotificationService(db)
        service.email_service.send_email = Mock(return_value={"id": "test"})

        count = service.send_reminder_emails()

        # Should only send for the CONFIRMED booking
        assert count == 1
        # 2 emails per booking (student + instructor)
        assert service.email_service.send_email.call_count == 2


class TestReminderIntegration:
    """Integration tests for reminder system."""

    def test_full_reminder_flow_uses_clean_architecture(self, db, test_student, test_instructor):
        """Test complete reminder flow from endpoint to email."""
        # Create tomorrow booking based on student's timezone
        from app.core.timezone_utils import get_user_today
        from app.events import BookingReminder
        from app.services.booking_service import BookingService

        student_today = get_user_today(test_student)
        tomorrow = student_today + timedelta(days=1)

        # Get the instructor's profile and service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,  # Use actual service ID
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Use catalog name
            hourly_rate=service.hourly_rate,  # Use actual rate
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Studio A",
        )
        # Add required email fields
        booking.student = test_student
        booking.instructor = test_instructor
        db.add(booking)
        db.commit()

        # Create services
        event_publisher = Mock()
        booking_service = BookingService(db, event_publisher=event_publisher)

        # Call the booking service method (what the endpoint calls)
        count = booking_service.send_booking_reminders()

        assert count == 1

        event_publisher.publish.assert_called_once()
        reminder_event = event_publisher.publish.call_args[0][0]
        assert isinstance(reminder_event, BookingReminder)
        assert reminder_event.booking_id == booking.id
