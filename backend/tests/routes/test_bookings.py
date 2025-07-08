# backend/tests/routes/test_bookings.py
"""
Comprehensive test suite for booking routes.
Target: Increase coverage from 49% to 80%+
Focus on time-based booking (NO slot IDs per Work Stream #9)
FIXED: Correct route paths, auth requirements, and dependency overrides
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import status

from app.api.dependencies.services import get_booking_service
from app.core.exceptions import ConflictException, NotFoundException
from app.main import app
from app.models.booking import BookingStatus


class TestBookingRoutes:
    """Test booking API endpoints with time-based pattern."""

    @pytest.fixture
    def booking_data(self):
        """Standard booking data following time-based pattern."""
        tomorrow = date.today() + timedelta(days=1)
        return {
            "instructor_id": 1,
            "service_id": 1,
            "booking_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "10:00",
            "student_note": "Looking forward to the lesson!",
            "meeting_location": "Central Park",
            "location_type": "neutral",
        }

    @pytest.fixture
    def mock_booking_service(self):
        """Create mock booking service."""
        from app.services.booking_service import BookingService

        mock_service = MagicMock(spec=BookingService)

        # Mock common methods
        mock_service.create_booking = AsyncMock()
        mock_service.get_booking_for_user = Mock()
        mock_service.get_bookings_for_user = Mock()
        mock_service.cancel_booking = AsyncMock()
        mock_service.complete_booking = Mock()
        mock_service.check_availability = AsyncMock()
        mock_service.get_booking_stats_for_instructor = Mock()
        mock_service.send_booking_reminders = AsyncMock()
        mock_service.update_booking = Mock()

        return mock_service

    @pytest.fixture
    def client_with_mock_booking_service(self, client, mock_booking_service):
        """Create test client with mocked booking service."""
        app.dependency_overrides[get_booking_service] = lambda: mock_booking_service
        yield client
        app.dependency_overrides.clear()

    def test_create_booking_success(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test successful booking creation with time-based pattern."""
        # Setup mock response
        mock_booking = Mock()
        mock_booking.id = 123
        mock_booking.student_id = 1
        mock_booking.instructor_id = 1
        mock_booking.service_id = 1
        mock_booking.booking_date = date.today() + timedelta(days=1)
        mock_booking.start_time = time(9, 0)
        mock_booking.end_time = time(10, 0)
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.total_price = 50.0
        mock_booking.service_name = "Piano Lesson"
        mock_booking.hourly_rate = 50.0
        mock_booking.duration_minutes = 60
        mock_booking.service_area = "Manhattan"
        mock_booking.meeting_location = "Central Park"
        mock_booking.location_type = "neutral"
        mock_booking.student_note = "Looking forward to the lesson!"
        mock_booking.instructor_note = None
        mock_booking.created_at = datetime.now()
        mock_booking.confirmed_at = datetime.now()
        mock_booking.completed_at = None
        mock_booking.cancelled_at = None
        mock_booking.cancelled_by_id = None
        mock_booking.cancellation_reason = None

        # Setup related objects
        mock_booking.student = Mock(id=1, full_name="Test Student", email="student@test.com")
        mock_booking.instructor = Mock(id=1, full_name="Test Instructor", email="instructor@test.com")
        mock_booking.service = Mock(id=1, skill="Piano", description="Piano lessons")

        mock_booking_service.create_booking.return_value = mock_booking

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["id"] == 123
        assert data["status"] == BookingStatus.CONFIRMED.value

        # Verify service was called with correct parameters
        mock_booking_service.create_booking.assert_called_once()

    def test_create_booking_no_slot_id(self, client_with_mock_booking_service, auth_headers_student, booking_data):
        """Test that booking creation doesn't accept availability_slot_id."""
        # Add forbidden field
        booking_data["availability_slot_id"] = 999

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Should return 422 due to extra field with extra='forbid'
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_booking_past_date(self, client, auth_headers_student, booking_data):
        """Test booking creation for past date fails."""
        # Set past date
        yesterday = date.today() - timedelta(days=1)
        booking_data["booking_date"] = yesterday.isoformat()

        # Execute
        response = client.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify - should fail validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_booking_time_conflict(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test booking creation with time conflict."""
        mock_booking_service.create_booking.side_effect = ConflictException("Time slot conflicts with existing booking")

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify - ConflictException should result in 409
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_create_booking_instructor_not_found(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test booking creation with non-existent instructor."""
        mock_booking_service.create_booking.side_effect = NotFoundException("Instructor not found")

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_booking_invalid_time_range(self, client, auth_headers_student, booking_data):
        """Test booking with end time before start time."""
        booking_data["start_time"] = "10:00"
        booking_data["end_time"] = "09:00"

        # Execute
        response = client.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Should fail validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_bookings_list(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test retrieving bookings list."""
        # Setup mock bookings
        mock_bookings = []
        for i in range(3):
            booking = Mock()
            booking.id = i + 1
            booking.booking_date = date.today() + timedelta(days=i + 1)
            booking.start_time = time(9, 0)
            booking.end_time = time(10, 0)
            booking.status = BookingStatus.CONFIRMED
            booking.service_name = f"Service {i+1}"
            booking.total_price = 50.0
            booking.hourly_rate = 50.0
            booking.duration_minutes = 60
            booking.service_area = "Manhattan"
            booking.meeting_location = "Location"
            booking.location_type = "neutral"
            booking.student_note = None
            booking.instructor_note = None
            booking.student_id = 1
            booking.instructor_id = 2
            booking.service_id = 1
            booking.created_at = datetime.now()
            booking.confirmed_at = datetime.now()
            booking.completed_at = None
            booking.cancelled_at = None
            booking.cancelled_by_id = None
            booking.cancellation_reason = None
            booking.student = Mock(id=1, full_name="Student", email="student@test.com")
            booking.instructor = Mock(id=2, full_name="Instructor", email="instructor@test.com")
            booking.service = Mock(id=1, skill="Service", description="Description")
            mock_bookings.append(booking)

        mock_booking_service.get_bookings_for_user.return_value = mock_bookings

        # Execute
        response = client_with_mock_booking_service.get("/bookings/", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 3
        assert len(data["bookings"]) == 3
        assert data["page"] == 1
        assert data["per_page"] == 20

    def test_get_bookings_with_filters(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test retrieving bookings with status filter."""
        mock_booking_service.get_bookings_for_user.return_value = []

        # Execute with status filter
        response = client_with_mock_booking_service.get("/bookings/?status=completed", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        # Verify service was called with correct filter
        mock_booking_service.get_bookings_for_user.assert_called_once()
        call_args = mock_booking_service.get_bookings_for_user.call_args
        assert call_args[1]["status"] == BookingStatus.COMPLETED

    def test_cancel_booking_success(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test successful booking cancellation."""
        booking_id = 123

        # Setup mock return
        cancelled_booking = Mock()
        cancelled_booking.id = booking_id
        cancelled_booking.status = BookingStatus.CANCELLED
        cancelled_booking.booking_date = date.today() + timedelta(days=1)
        cancelled_booking.start_time = time(9, 0)
        cancelled_booking.end_time = time(10, 0)
        cancelled_booking.service_name = "Piano"
        cancelled_booking.total_price = 50.0
        cancelled_booking.hourly_rate = 50.0
        cancelled_booking.duration_minutes = 60
        cancelled_booking.service_area = "Manhattan"
        cancelled_booking.meeting_location = "Location"
        cancelled_booking.location_type = "neutral"
        cancelled_booking.student_note = None
        cancelled_booking.instructor_note = None
        cancelled_booking.student_id = 1
        cancelled_booking.instructor_id = 2
        cancelled_booking.service_id = 1
        cancelled_booking.created_at = datetime.now()
        cancelled_booking.confirmed_at = datetime.now()
        cancelled_booking.completed_at = None
        cancelled_booking.cancelled_at = datetime.now()
        cancelled_booking.cancelled_by_id = 1
        cancelled_booking.cancellation_reason = "Schedule conflict"
        cancelled_booking.student = Mock(id=1, full_name="Student", email="student@test.com")
        cancelled_booking.instructor = Mock(id=2, full_name="Instructor", email="instructor@test.com")
        cancelled_booking.service = Mock(id=1, skill="Piano", description="Piano lessons")

        mock_booking_service.cancel_booking.return_value = cancelled_booking

        # Execute
        response = client_with_mock_booking_service.post(
            f"/bookings/{booking_id}/cancel", json={"reason": "Schedule conflict"}, headers=auth_headers_student
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == BookingStatus.CANCELLED.value

    def test_cancel_booking_not_found(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test cancelling non-existent booking."""
        booking_id = 999
        mock_booking_service.cancel_booking.side_effect = NotFoundException("Booking not found")

        # Execute
        response = client_with_mock_booking_service.post(
            f"/bookings/{booking_id}/cancel", json={"reason": "Not needed"}, headers=auth_headers_student
        )

        # Verify
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_booking_missing_reason(self, client, auth_headers_student):
        """Test cancelling booking without reason."""
        booking_id = 123

        # Execute - missing reason
        response = client.post(f"/bookings/{booking_id}/cancel", json={}, headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_complete_booking_instructor_only(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test that only instructors can complete bookings."""
        booking_id = 123

        # Setup mock
        completed_booking = Mock()
        completed_booking.id = booking_id
        completed_booking.status = BookingStatus.COMPLETED
        completed_booking.booking_date = date.today()
        completed_booking.start_time = time(9, 0)
        completed_booking.end_time = time(10, 0)
        completed_booking.service_name = "Piano"
        completed_booking.total_price = 50.0
        completed_booking.hourly_rate = 50.0
        completed_booking.duration_minutes = 60
        completed_booking.service_area = "Manhattan"
        completed_booking.meeting_location = "Location"
        completed_booking.location_type = "neutral"
        completed_booking.student_note = None
        completed_booking.instructor_note = "Great progress!"
        completed_booking.student_id = 1
        completed_booking.instructor_id = 2
        completed_booking.service_id = 1
        completed_booking.created_at = datetime.now()
        completed_booking.confirmed_at = datetime.now()
        completed_booking.completed_at = datetime.now()
        completed_booking.cancelled_at = None
        completed_booking.cancelled_by_id = None
        completed_booking.cancellation_reason = None
        completed_booking.student = Mock(id=1, full_name="Student", email="student@test.com")
        completed_booking.instructor = Mock(id=2, full_name="Instructor", email="instructor@test.com")
        completed_booking.service = Mock(id=1, skill="Piano", description="Piano lessons")

        mock_booking_service.complete_booking.return_value = completed_booking

        # Execute
        response = client_with_mock_booking_service.post(
            f"/bookings/{booking_id}/complete", headers=auth_headers_instructor
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == BookingStatus.COMPLETED.value

    def test_check_availability_requires_auth(self, client):
        """Test that availability check requires authentication."""
        # Execute without auth headers
        response = client.post(
            "/bookings/check-availability",
            json={
                "instructor_id": 1,
                "service_id": 1,
                "booking_date": date.today().isoformat(),
                "start_time": "14:00",
                "end_time": "15:00",
            },
        )

        # Verify - should require auth
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_check_availability_success(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test availability check with auth."""
        mock_booking_service.check_availability.return_value = {
            "available": True,
            "reason": None,
            "min_advance_hours": 2,
            "conflicts_with": [],
        }

        # Execute with auth
        response = client_with_mock_booking_service.post(
            "/bookings/check-availability",
            json={
                "instructor_id": 1,
                "service_id": 1,
                "booking_date": (date.today() + timedelta(days=1)).isoformat(),
                "start_time": "14:00",
                "end_time": "15:00",
            },
            headers=auth_headers_student,
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["available"] is True

    def test_get_booking_stats_instructor_only(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test instructor getting their booking statistics."""
        mock_stats = {
            "total_bookings": 50,
            "upcoming_bookings": 2,
            "completed_bookings": 45,
            "cancelled_bookings": 3,
            "total_earnings": 2500.00,
            "this_month_earnings": 500.00,
            "average_rating": None,
        }

        mock_booking_service.get_booking_stats_for_instructor.return_value = mock_stats

        # Execute
        response = client_with_mock_booking_service.get("/bookings/stats", headers=auth_headers_instructor)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_bookings"] == 50
        assert data["total_earnings"] == 2500.00

    def test_get_booking_stats_student_forbidden(self, client_with_mock_booking_service, auth_headers_student):
        """Test that students cannot access booking stats."""
        # Execute
        response = client_with_mock_booking_service.get("/bookings/stats", headers=auth_headers_student)

        # Verify - students should get validation error
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_send_booking_reminders_admin_only(self, client_with_mock_booking_service, auth_headers_student):
        """Test that only admin can send reminders."""
        # Execute as regular user
        response = client_with_mock_booking_service.post("/bookings/send-reminders", headers=auth_headers_student)

        # Should be forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_upcoming_bookings(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test getting upcoming bookings."""
        # Setup mock
        upcoming = []
        for i in range(2):
            booking = Mock()
            booking.id = i + 1
            booking.booking_date = date.today() + timedelta(days=i + 1)
            booking.start_time = time(9 + i, 0)
            booking.end_time = time(10 + i, 0)
            booking.service_name = f"Service {i+1}"
            booking.student_name = "Test Student"
            booking.instructor_name = "Test Instructor"
            booking.meeting_location = "Location"
            upcoming.append(booking)

        mock_booking_service.get_bookings_for_user.return_value = upcoming

        # Execute
        response = client_with_mock_booking_service.get("/bookings/upcoming?limit=5", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2

    def test_get_booking_preview(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test getting booking preview."""
        booking_id = 123

        # Setup mock
        mock_booking = Mock()
        mock_booking.id = booking_id
        mock_booking.student = Mock(full_name="Test Student")
        mock_booking.instructor = Mock(full_name="Test Instructor")
        mock_booking.service_name = "Piano Lesson"
        mock_booking.booking_date = date.today() + timedelta(days=1)
        mock_booking.start_time = time(9, 0)
        mock_booking.end_time = time(10, 0)
        mock_booking.duration_minutes = 60
        mock_booking.location_type = "neutral"
        mock_booking.location_type_display = "Neutral Location"
        mock_booking.meeting_location = "Central Park"
        mock_booking.service_area = "Manhattan"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.student_note = "Looking forward!"
        mock_booking.total_price = 50.0

        mock_booking_service.get_booking_for_user.return_value = mock_booking

        # Execute
        response = client_with_mock_booking_service.get(f"/bookings/{booking_id}/preview", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["booking_id"] == booking_id
        assert data["student_name"] == "Test Student"

    def test_update_booking(self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service):
        """Test updating booking details."""
        booking_id = 123

        # Setup mock
        updated_booking = Mock()
        updated_booking.id = booking_id
        updated_booking.instructor_note = "Updated note"
        updated_booking.meeting_location = "New location"
        # Add all required fields for response
        updated_booking.student_id = 1
        updated_booking.instructor_id = 2
        updated_booking.service_id = 1
        updated_booking.booking_date = date.today() + timedelta(days=1)
        updated_booking.start_time = time(9, 0)
        updated_booking.end_time = time(10, 0)
        updated_booking.service_name = "Piano"
        updated_booking.hourly_rate = 50.0
        updated_booking.total_price = 50.0
        updated_booking.duration_minutes = 60
        updated_booking.status = BookingStatus.CONFIRMED
        updated_booking.service_area = "Manhattan"
        updated_booking.location_type = "neutral"
        updated_booking.student_note = None
        updated_booking.created_at = datetime.now()
        updated_booking.confirmed_at = datetime.now()
        updated_booking.completed_at = None
        updated_booking.cancelled_at = None
        updated_booking.cancelled_by_id = None
        updated_booking.cancellation_reason = None
        updated_booking.student = Mock(id=1, full_name="Student", email="student@test.com")
        updated_booking.instructor = Mock(id=2, full_name="Instructor", email="instructor@test.com")
        updated_booking.service = Mock(id=1, skill="Piano", description="Piano lessons")

        mock_booking_service.update_booking.return_value = updated_booking

        # Execute
        response = client_with_mock_booking_service.patch(
            f"/bookings/{booking_id}",
            json={"instructor_note": "Updated note", "meeting_location": "New location"},
            headers=auth_headers_instructor,
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["instructor_note"] == "Updated note"


class TestBookingIntegration:
    """Integration tests for booking flow."""

    @pytest.mark.asyncio
    async def test_complete_booking_flow(self, client, db, test_student, test_instructor_with_availability):
        """Test complete booking flow from creation to completion."""
        # Get auth headers
        from app.auth import create_access_token

        student_token = create_access_token(data={"sub": test_student.email})
        student_headers = {"Authorization": f"Bearer {student_token}"}

        instructor_token = create_access_token(data={"sub": test_instructor_with_availability.email})
        instructor_headers = {"Authorization": f"Bearer {instructor_token}"}

        # Get service
        from app.models.service import Service

        service = (
            db.query(Service)
            .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
            .first()
        )

        # Create booking
        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": test_instructor_with_availability.id,
            "service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "10:00",
            "end_time": "11:00",
            "meeting_location": "Test Location",
        }

        response = client.post("/bookings/", json=booking_data, headers=student_headers)
        assert response.status_code == status.HTTP_201_CREATED
        booking_id = response.json()["id"]

        # Verify booking appears in student's list
        response = client.get("/bookings/", headers=student_headers)
        assert response.status_code == status.HTTP_200_OK
        bookings = response.json()["bookings"]
        assert any(b["id"] == booking_id for b in bookings)

        # Verify booking appears in instructor's list
        response = client.get("/bookings/", headers=instructor_headers)
        assert response.status_code == status.HTTP_200_OK
        bookings = response.json()["bookings"]
        assert any(b["id"] == booking_id for b in bookings)

        # Complete the booking (as instructor)
        response = client.post(f"/bookings/{booking_id}/complete", headers=instructor_headers)
        assert response.status_code == status.HTTP_200_OK

        # Verify status changed
        from app.models.booking import Booking

        booking = db.query(Booking).get(booking_id)
        assert booking.status == BookingStatus.COMPLETED
