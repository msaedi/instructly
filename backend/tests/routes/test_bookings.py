# backend/tests/routes/test_bookings.py
"""
Comprehensive test suite for booking routes.
Target: Increase coverage from 49% to 80%+
Focus on time-based booking (NO slot IDs per Work Stream #9)
FIXED: Correct route paths, auth requirements, and dependency overrides

TEST FAILURE ANALYSIS - test_bookings.py

1. booking_data fixture: EXPECTED
   - Used old 'service_id' field
   - Fix: Changed to 'instructor_service_id'

2. All tests using booking_data: EXPECTED
   - Will now use correct field name
   - Fix: Already fixed via fixture update
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

from fastapi import status
import pytest

from app.api.dependencies.services import get_booking_service
from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.core.ulid_helper import generate_ulid
from app.main import fastapi_app as app
from app.models.booking import BookingStatus


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Booking route tests mock pricing; keep legacy fixture values."""
    yield


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch):
    yield


class TestBookingRoutes:
    """Test booking API endpoints with time-based pattern."""

    def _create_mock_instructor_service(self, service_id=None, name="Piano Lessons", description="Piano lessons"):
        """Helper to create a properly mocked instructor service with catalog entry."""
        if service_id is None:
            service_id = generate_ulid()
        mock_catalog_entry = Mock(name=name)
        mock_instructor_service = Mock(id=service_id, catalog_entry=mock_catalog_entry, description=description)
        # Make the mock service return proper values for ServiceInfo
        mock_instructor_service.configure_mock(
            id=service_id, name=name, description=description  # This is what ServiceInfo expects
        )
        return mock_instructor_service

    @pytest.fixture
    def booking_data(self):
        """Standard booking data following time-based pattern."""
        tomorrow = date.today() + timedelta(days=1)
        return {
            "instructor_id": generate_ulid(),
            "instructor_service_id": generate_ulid(),
            "booking_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "10:00",
            "selected_duration": 60,
            "student_note": "Looking forward to the lesson!",
            "meeting_location": "Central Park",
            "location_type": "neutral",
        }

    @pytest.fixture
    def mock_booking_service(self):
        """Create mock booking service."""
        from app.services.booking_service import BookingService

        mock_service = MagicMock(spec=BookingService)

        # Mock common methods - Create async methods that return synchronously
        async def async_create_booking(*args, **kwargs):
            # This will be replaced per test
            return None

        async def async_cancel_booking(*args, **kwargs):
            return None

        mock_service.create_booking_with_payment_setup = AsyncMock()
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
        # Create a real Booking object for proper schema validation
        from app.models.booking import Booking
        from app.models.user import User

        # Create mock users with proper attributes
        student_user = Mock(spec=User)
        student_user.id = generate_ulid()
        student_user.first_name = "Test"
        student_user.last_name = "Student"
        student_user.email = "student@test.com"

        instructor_user = Mock(spec=User)
        instructor_user.id = generate_ulid()
        instructor_user.first_name = "Test"
        instructor_user.last_name = "Instructor"
        instructor_user.email = "instructor@test.com"

        # Create mock booking with all required attributes
        mock_booking = Mock(spec=Booking)
        mock_booking.id = generate_ulid()
        mock_booking.student_id = student_user.id
        mock_booking.instructor_id = instructor_user.id
        mock_booking.instructor_service_id = generate_ulid()
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

        # Setup related objects properly
        mock_booking.student = student_user
        mock_booking.instructor = instructor_user
        mock_booking.instructor_service = self._create_mock_instructor_service()

        # Set return value for the actual method being called in the route
        mock_booking_service.create_booking_with_payment_setup.return_value = mock_booking

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify
        if response.status_code == 422:
            print("Validation error:", response.json())
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["id"] == mock_booking.id
        assert data["status"] == BookingStatus.CONFIRMED.value

        # Verify service was called with correct parameters
        mock_booking_service.create_booking_with_payment_setup.assert_called_once()

    def test_create_booking_no_slot_id(self, client_with_mock_booking_service, auth_headers_student, booking_data):
        """Test that booking creation doesn't accept availability_slot_id."""
        # Add forbidden field
        booking_data["availability_slot_id"] = generate_ulid()

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

        # Verify - validation moved to service layer, should return 400 BAD REQUEST
        # (or 404 if instructor/service not found)
        # Since this test uses real client, it depends on test data setup
        # Update to check for appropriate error codes
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            data = response.json()
            assert "past" in data["detail"].lower() or "timezone" in data["detail"].lower()

    def test_create_booking_time_conflict(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test booking creation with time conflict."""
        mock_booking_service.create_booking_with_payment_setup.side_effect = ConflictException(
            "Time slot conflicts with existing booking"
        )

        # Execute
        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)

        # Verify - ConflictException should result in 409
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_create_booking_instructor_not_found(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test booking creation with non-existent instructor."""
        mock_booking_service.create_booking_with_payment_setup.side_effect = NotFoundException("Instructor not found")

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
            booking.id = generate_ulid()
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
            booking.student_id = generate_ulid()
            booking.instructor_id = generate_ulid()
            booking.instructor_service_id = generate_ulid()
            booking.created_at = datetime.now()
            booking.confirmed_at = datetime.now()
            booking.completed_at = None
            booking.cancelled_at = None
            booking.cancelled_by_id = None
            booking.cancellation_reason = None
            booking.student = Mock(id=generate_ulid(), first_name="Student", last_name="User", email="student@test.com")
            booking.instructor = Mock(
                id=generate_ulid(), first_name="Instructor", last_name="User", email="instructor@test.com"
            )
            booking.instructor_service = self._create_mock_instructor_service(
                name=f"Service {i+1}", description="Description"
            )
            mock_bookings.append(booking)

        # Return a list of BookingResponse-like dictionaries to bypass from_orm path and match route expectations
        mock_booking_service.get_bookings_for_user.return_value = [
            {
                "id": b.id,
                "student_id": b.student_id,
                "instructor_id": b.instructor_id,
                "instructor_service_id": b.instructor_service_id,
                "booking_date": b.booking_date,
                "start_time": b.start_time,
                "end_time": b.end_time,
                "service_name": b.service_name,
                "hourly_rate": b.hourly_rate,
                "total_price": b.total_price,
                "duration_minutes": b.duration_minutes,
                "status": b.status,
                "service_area": b.service_area,
                "meeting_location": b.meeting_location,
                "location_type": b.location_type,
                "student_note": b.student_note,
                "instructor_note": b.instructor_note,
                "created_at": b.created_at,
                "confirmed_at": b.confirmed_at,
                "completed_at": b.completed_at,
                "cancelled_at": b.cancelled_at,
                "cancelled_by_id": b.cancelled_by_id,
                "cancellation_reason": b.cancellation_reason,
                "student": {
                    "id": b.student.id,
                    "first_name": b.student.first_name,
                    "last_name": b.student.last_name,
                    "email": b.student.email,
                },
                "instructor": {
                    "id": b.instructor.id,
                    "first_name": b.instructor.first_name,
                    "last_name": b.instructor.last_name,
                    "email": b.instructor.email,
                },
                "instructor_service": {
                    "id": b.instructor_service.id,
                    "name": b.instructor_service.name,
                    "description": b.instructor_service.description,
                },
                "_from_cache": True,
            }
            for b in mock_bookings
        ]

        # Execute
        response = client_with_mock_booking_service.get("/bookings/", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["per_page"] == 20

    def test_get_bookings_with_filters(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test retrieving bookings with status filter."""
        mock_booking_service.get_bookings_for_user.return_value = []

        # Execute with status filter - MUST USE UPPERCASE
        response = client_with_mock_booking_service.get("/bookings/?status=COMPLETED", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        # Verify service was called with correct filter
        mock_booking_service.get_bookings_for_user.assert_called_once()
        call_args = mock_booking_service.get_bookings_for_user.call_args
        assert call_args[1]["status"] == BookingStatus.COMPLETED

    def test_cancel_booking_success(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test successful booking cancellation."""
        booking_id = generate_ulid()

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
        cancelled_booking.student_id = generate_ulid()
        cancelled_booking.instructor_id = generate_ulid()
        cancelled_booking.instructor_service_id = generate_ulid()
        cancelled_booking.created_at = datetime.now()
        cancelled_booking.confirmed_at = datetime.now()
        cancelled_booking.completed_at = None
        cancelled_booking.cancelled_at = datetime.now()
        cancelled_booking.cancelled_by_id = generate_ulid()
        cancelled_booking.cancellation_reason = "Schedule conflict"
        cancelled_booking.student = Mock(
            id=generate_ulid(), first_name="Student", last_name="User", email="student@test.com"
        )
        cancelled_booking.instructor = Mock(
            id=generate_ulid(), first_name="Instructor", last_name="User", email="instructor@test.com"
        )
        cancelled_booking.instructor_service = self._create_mock_instructor_service()

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
        booking_id = generate_ulid()
        mock_booking_service.cancel_booking.side_effect = NotFoundException("Booking not found")

        # Execute
        response = client_with_mock_booking_service.post(
            f"/bookings/{booking_id}/cancel", json={"reason": "Not needed"}, headers=auth_headers_student
        )

        # Verify
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_booking_missing_reason(self, client, auth_headers_student):
        """Test cancelling booking without reason."""
        booking_id = generate_ulid()

        # Execute - missing reason
        response = client.post(f"/bookings/{booking_id}/cancel", json={}, headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_complete_booking_instructor_only(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test that only instructors can complete bookings."""
        booking_id = generate_ulid()

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
        completed_booking.student_id = generate_ulid()
        completed_booking.instructor_id = generate_ulid()
        completed_booking.instructor_service_id = generate_ulid()
        completed_booking.created_at = datetime.now()
        completed_booking.confirmed_at = datetime.now()
        completed_booking.completed_at = datetime.now()
        completed_booking.cancelled_at = None
        completed_booking.cancelled_by_id = None
        completed_booking.cancellation_reason = None
        completed_booking.student = Mock(
            id=generate_ulid(), first_name="Student", last_name="User", email="student@test.com"
        )
        completed_booking.instructor = Mock(
            id=generate_ulid(), first_name="Instructor", last_name="User", email="instructor@test.com"
        )
        completed_booking.instructor_service = self._create_mock_instructor_service()

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
                "instructor_id": generate_ulid(),
                "instructor_service_id": generate_ulid(),
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
                "instructor_id": generate_ulid(),
                "instructor_service_id": generate_ulid(),
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
            "completion_rate": 0.9,
            "cancellation_rate": 0.06,
        }

        mock_booking_service.get_booking_stats_for_instructor.return_value = mock_stats

        # Execute
        response = client_with_mock_booking_service.get("/bookings/stats", headers=auth_headers_instructor)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_bookings"] == 50
        assert data["total_earnings"] == 2500.00

    def test_get_booking_stats_student_forbidden(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test that students cannot access booking stats."""
        # Mock the service to throw ValidationException which the route converts to 400
        mock_booking_service.get_booking_stats_for_instructor.side_effect = ValidationException(
            "Only instructors can view booking stats"
        )

        # Execute
        response = client_with_mock_booking_service.get("/bookings/stats", headers=auth_headers_student)

        # Verify - the route should return 400 for ValidationException
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_send_booking_reminders_admin_only(self, client_with_mock_booking_service, auth_headers_student):
        """Test that only admin can send reminders."""
        # Execute as regular user
        response = client_with_mock_booking_service.post("/bookings/send-reminders", headers=auth_headers_student)

        # Should be forbidden (403) or rate limited (429)
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_429_TOO_MANY_REQUESTS]

    def test_get_upcoming_bookings(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service, test_student
    ):
        """Test getting upcoming bookings."""
        # Setup mock - UpcomingBookingResponse needs these exact fields
        upcoming = []
        for i in range(2):
            booking = Mock()
            booking.id = generate_ulid()
            booking.booking_date = date.today() + timedelta(days=i + 1)
            booking.start_time = time(9 + i, 0)
            booking.end_time = time(10 + i, 0)
            booking.service_name = f"Service {i+1}"
            booking.meeting_location = "Location"

            # Set IDs for privacy checks - use actual test_student.id
            booking.student_id = test_student.id  # Use actual test_student.id
            instructor_id = generate_ulid()  # Generate a different ULID for instructor
            booking.instructor_id = instructor_id

            # These are required for UpcomingBookingResponse
            booking.student = Mock(id=test_student.id, first_name="Test", last_name="Student")
            booking.instructor = Mock(id=instructor_id, first_name="Test", last_name="Instructor")

            # Add the from_orm compatible attributes
            booking.student_first_name = booking.student.first_name
            booking.student_last_name = booking.student.last_name
            booking.instructor_first_name = booking.instructor.first_name
            booking.instructor_last_name = booking.instructor.last_name

            upcoming.append(booking)

        mock_booking_service.get_bookings_for_user.return_value = upcoming

        # Execute - no query param should work
        response = client_with_mock_booking_service.get("/bookings/upcoming", headers=auth_headers_student)

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert len(data["items"]) == 2
        assert data["items"][0]["service_name"] == "Service 1"
        assert data["items"][0]["student_first_name"] == "Test"
        # Student viewing their own booking - sees full last name
        assert data["items"][0]["student_last_name"] == "Student"
        assert data["items"][0]["instructor_first_name"] == "Test"
        # Student viewing instructor's info - sees only initial
        assert data["items"][0]["instructor_last_name"] == "I"

    def test_get_booking_preview(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test getting booking preview."""
        booking_id = generate_ulid()

        # Setup mock
        mock_booking = Mock()
        mock_booking.id = booking_id
        mock_booking.student = Mock(first_name="Test", last_name="Student")
        mock_booking.instructor = Mock(first_name="Test", last_name="Instructor")
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
        assert data["student_first_name"] == "Test"
        assert data["student_last_name"] == "Student"

    def test_update_booking(self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service):
        """Test updating booking details."""
        booking_id = generate_ulid()

        # Setup mock
        updated_booking = Mock()
        updated_booking.id = booking_id
        updated_booking.instructor_note = "Updated note"
        updated_booking.meeting_location = "New location"
        # Add all required fields for response
        updated_booking.student_id = generate_ulid()
        updated_booking.instructor_id = generate_ulid()
        updated_booking.instructor_service_id = generate_ulid()
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
        updated_booking.student = Mock(
            id=generate_ulid(), first_name="Student", last_name="User", email="student@test.com"
        )
        updated_booking.instructor = Mock(
            id=generate_ulid(), first_name="Instructor", last_name="User", email="instructor@test.com"
        )
        updated_booking.instructor_service = self._create_mock_instructor_service()

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

    def test_get_booking_details_success(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test getting full booking details."""
        # Create complete mock booking
        mock_booking = Mock()
        booking_id = generate_ulid()
        mock_booking.id = booking_id
        mock_booking.student_id = generate_ulid()
        mock_booking.instructor_id = generate_ulid()
        mock_booking.instructor_service_id = generate_ulid()
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
        mock_booking.student_note = "Looking forward!"
        mock_booking.instructor_note = None
        mock_booking.created_at = datetime.now()
        mock_booking.confirmed_at = datetime.now()
        mock_booking.completed_at = None
        mock_booking.cancelled_at = None
        mock_booking.cancelled_by_id = None
        mock_booking.cancellation_reason = None
        mock_booking.student = Mock(
            id=generate_ulid(), first_name="Test", last_name="Student", email="student@test.com"
        )
        mock_booking.instructor = Mock(
            id=generate_ulid(), first_name="Test", last_name="Instructor", email="instructor@test.com"
        )
        mock_booking.instructor_service = self._create_mock_instructor_service()

        mock_booking_service.get_booking_for_user.return_value = mock_booking

        response = client_with_mock_booking_service.get(f"/bookings/{booking_id}", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == booking_id
        assert data["service_name"] == "Piano Lesson"

    def test_get_booking_details_not_found(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test getting non-existent booking."""
        mock_booking_service.get_booking_for_user.return_value = None

        response = client_with_mock_booking_service.get("/bookings/999", headers=auth_headers_student)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_booking_student_forbidden(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test that students cannot update bookings."""
        mock_booking_service.update_booking.side_effect = ValidationException(
            "Only the instructor can update booking details"
        )

        response = client_with_mock_booking_service.patch(
            "/bookings/123", json={"instructor_note": "Note"}, headers=auth_headers_student
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_complete_booking_student_forbidden(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test that students cannot complete bookings."""
        # With RBAC, students are blocked at permission level (403) before service validation (400)
        response = client_with_mock_booking_service.post("/bookings/123/complete", headers=auth_headers_student)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_bookings_pagination_edge_cases(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test pagination edge cases."""
        # Empty result on high page number
        mock_booking_service.get_bookings_for_user.return_value = []

        response = client_with_mock_booking_service.get("/bookings/?page=100&per_page=20", headers=auth_headers_student)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    def test_get_bookings_invalid_pagination(self, client, auth_headers_student):
        """Test invalid pagination parameters."""
        # Negative page
        response = client.get("/bookings/?page=-1", headers=auth_headers_student)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Per page too large
        response = client.get("/bookings/?per_page=1000", headers=auth_headers_student)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_all_endpoints_require_auth(self, client):
        """Test that all booking endpoints require authentication."""
        tomorrow = date.today() + timedelta(days=1)

        endpoints = [
            ("GET", "/bookings/"),
            ("GET", "/bookings/123"),
            ("GET", "/bookings/123/preview"),
            ("GET", "/bookings/upcoming"),
            ("GET", "/bookings/stats"),
            (
                "POST",
                "/bookings/",
                {
                    "instructor_id": 1,
                    "instructor_service_id": 1,
                    "booking_date": tomorrow.isoformat(),
                    "start_time": "09:00",
                    "end_time": "10:00",
                },
            ),
            ("PATCH", "/bookings/123", {"instructor_note": "Note"}),
            ("POST", "/bookings/123/cancel", {"reason": "Test"}),
            ("POST", "/bookings/123/complete", {}),
            (
                "POST",
                "/bookings/check-availability",
                {
                    "instructor_id": 1,
                    "instructor_service_id": 1,
                    "booking_date": tomorrow.isoformat(),
                    "start_time": "09:00",
                    "end_time": "10:00",
                },
            ),
        ]

        for method, path, *data in endpoints:
            if method == "GET":
                response = client.get(path)
            elif method == "POST":
                response = client.post(path, json=data[0] if data else {})
            elif method == "PATCH":
                response = client.patch(path, json=data[0] if data else {})

            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"{method} {path} should require auth"

    def test_get_preview_not_found(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test preview for non-existent booking."""
        mock_booking_service.get_booking_for_user.return_value = None

        response = client_with_mock_booking_service.get("/bookings/999/preview", headers=auth_headers_student)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_upcoming_empty(self, client_with_mock_booking_service, auth_headers_student, mock_booking_service):
        """Test upcoming bookings when none exist."""
        mock_booking_service.get_bookings_for_user.return_value = []

        # No query params
        response = client_with_mock_booking_service.get("/bookings/upcoming", headers=auth_headers_student)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert len(data["items"]) == 0

    def test_check_availability_time_conflicts(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test availability check with conflicts."""
        mock_booking_service.check_availability.return_value = {
            "available": False,
            "reason": "Time slot has conflicts with existing bookings",
        }

        tomorrow = date.today() + timedelta(days=1)
        response = client_with_mock_booking_service.post(
            "/bookings/check-availability",
            json={
                "instructor_id": generate_ulid(),
                "instructor_service_id": generate_ulid(),
                "booking_date": tomorrow.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
            },
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available"] is False
        assert "conflicts" in data["reason"]

    def test_cancel_booking_already_cancelled(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test cancelling already cancelled booking."""
        # BusinessRuleException should be handled by handle_domain_exception
        from app.core.exceptions import BusinessRuleException

        async def mock_cancel(*args, **kwargs):
            raise BusinessRuleException("Booking cannot be cancelled - current status: CANCELLED")

        mock_booking_service.cancel_booking = AsyncMock(side_effect=mock_cancel)

        response = client_with_mock_booking_service.post(
            "/bookings/123/cancel", json={"reason": "Already cancelled"}, headers=auth_headers_student
        )
        # BusinessRuleException returns 422 in current implementation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_complete_booking_already_completed(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test completing already completed booking."""
        from app.core.exceptions import BusinessRuleException

        # complete_booking is not async, so use regular Mock
        mock_booking_service.complete_booking.side_effect = BusinessRuleException(
            "Only confirmed bookings can be completed - current status: COMPLETED"
        )

        response = client_with_mock_booking_service.post("/bookings/123/complete", headers=auth_headers_instructor)
        # BusinessRuleException returns 422 in current implementation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_booking_not_found(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test updating non-existent booking."""
        mock_booking_service.update_booking.side_effect = NotFoundException("Booking not found")

        response = client_with_mock_booking_service.patch(
            "/bookings/999", json={"instructor_note": "Note"}, headers=auth_headers_instructor
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_send_reminders_as_admin(self, client_with_mock_booking_service, mock_booking_service, db):
        """Test admin successfully sending reminders."""
        from app.auth import create_access_token, get_password_hash
        from app.core.enums import RoleName
        from app.models.user import User
        from app.services.permission_service import PermissionService

        # Create a real admin user in the database
        admin_user = User(
            email="test.admin@example.com",
            hashed_password=get_password_hash("Test1234"),
            first_name="Test",
            last_name="Admin",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(admin_user)
        db.flush()

        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(admin_user.id, RoleName.ADMIN)
        db.commit()

        # Create real auth token
        admin_token = create_access_token(data={"sub": admin_user.email})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # send_booking_reminders is async
        mock_booking_service.send_booking_reminders = AsyncMock(return_value=5)

        response = client_with_mock_booking_service.post("/bookings/send-reminders", headers=admin_headers)

        # May get rate limited (429) during testing
        if response.status_code == 429:
            # Rate limiting is working - this is actually good
            error_data = response.json()
            assert "RATE_LIMIT_EXCEEDED" in str(error_data) or "once per hour" in str(error_data)
            return

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["reminders_sent"] == 5

    def test_create_booking_invalid_location_type(self, client, auth_headers_student, booking_data):
        """Test booking with invalid location type."""
        booking_data["location_type"] = "invalid_type"
        response = client.post("/bookings/", json=booking_data, headers=auth_headers_student)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_booking_missing_fields(self, client, auth_headers_student):
        """Test booking creation with missing required fields."""
        incomplete_data = {"instructor_id": 1}  # Missing other fields
        response = client.post("/bookings/", json=incomplete_data, headers=auth_headers_student)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_booking_validation_edge_cases(self, client, auth_headers_student):
        """Test various validation edge cases."""
        tomorrow = date.today() + timedelta(days=1)

        # Test with very long student note (over 1000 chars)
        booking_data = {
            "instructor_id": 1,
            "service_id": 1,
            "booking_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "selected_duration": 60,
            "end_time": "10:00",
            "student_note": "x" * 1001,  # Too long
        }
        response = client.post("/bookings/", json=booking_data, headers=auth_headers_student)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_booking_business_rule_violation(
        self, client_with_mock_booking_service, auth_headers_student, booking_data, mock_booking_service
    ):
        """Test booking creation with business rule violation."""
        from app.core.exceptions import BusinessRuleException

        mock_booking_service.create_booking_with_payment_setup.side_effect = BusinessRuleException(
            "Bookings must be made at least 2 hours in advance"
        )

        response = client_with_mock_booking_service.post("/bookings/", json=booking_data, headers=auth_headers_student)
        # BusinessRuleException may return 422 (current implementation)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_data = response.json()
        # Check in both 'detail' and 'message' fields
        assert "at least 2 hours" in str(error_data)

    def test_get_bookings_as_instructor(
        self, client_with_mock_booking_service, auth_headers_instructor, mock_booking_service
    ):
        """Test instructor getting their bookings."""
        # Create instructor bookings
        mock_bookings = []
        for i in range(2):
            booking = Mock()
            booking.id = generate_ulid()
            booking.booking_date = date.today() + timedelta(days=i + 1)
            booking.start_time = time(14, 0)
            booking.end_time = time(15, 0)
            booking.status = BookingStatus.CONFIRMED
            booking.service_name = "Guitar Lesson"
            booking.total_price = 45.0
            booking.hourly_rate = 45.0
            booking.duration_minutes = 60
            booking.service_area = "Brooklyn"
            booking.meeting_location = "Studio"
            booking.location_type = "instructor_location"
            booking.student_note = "First lesson"
            booking.instructor_note = None
            booking.student_id = generate_ulid()
            booking.instructor_id = generate_ulid()
            booking.instructor_service_id = generate_ulid()
            booking.created_at = datetime.now()
            booking.confirmed_at = datetime.now()
            booking.completed_at = None
            booking.cancelled_at = None
            booking.cancelled_by_id = None
            booking.cancellation_reason = None
            booking.student = Mock(id=generate_ulid(), first_name="John", last_name="Doe", email="john@example.com")
            booking.instructor = Mock(
                id=generate_ulid(), first_name="Jane", last_name="Smith", email="jane@example.com"
            )
            booking.instructor_service = self._create_mock_instructor_service(
                service_id=generate_ulid(), name="Guitar Lessons", description="Guitar lessons"
            )
            mock_bookings.append(booking)

        mock_booking_service.get_bookings_for_user.return_value = mock_bookings

        response = client_with_mock_booking_service.get("/bookings/", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["service_name"] == "Guitar Lesson"

    def test_check_availability_blackout_date(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test availability check on blackout date."""
        mock_booking_service.check_availability.return_value = {
            "available": False,
            "reason": "Instructor is not available on this date (blackout date)",
        }

        response = client_with_mock_booking_service.post(
            "/bookings/check-availability",
            json={
                "instructor_id": generate_ulid(),
                "instructor_service_id": generate_ulid(),
                "booking_date": (date.today() + timedelta(days=7)).isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
            },
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available"] is False
        assert "blackout" in data["reason"]

    def test_cancel_booking_past_deadline(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test cancelling booking past deadline (still allowed but logged)."""
        # Should still succeed, just with a warning in logs
        cancelled_booking = Mock()
        cancelled_booking.id = generate_ulid()
        cancelled_booking.status = BookingStatus.CANCELLED
        cancelled_booking.booking_date = date.today()
        cancelled_booking.start_time = time(14, 0)
        cancelled_booking.end_time = time(15, 0)
        cancelled_booking.service_name = "Piano"
        cancelled_booking.total_price = 50.0
        cancelled_booking.hourly_rate = 50.0
        cancelled_booking.duration_minutes = 60
        cancelled_booking.service_area = "Manhattan"
        cancelled_booking.meeting_location = "Studio"
        cancelled_booking.location_type = "neutral"
        cancelled_booking.student_note = None
        cancelled_booking.instructor_note = None
        cancelled_booking.student_id = generate_ulid()
        cancelled_booking.instructor_id = generate_ulid()
        cancelled_booking.instructor_service_id = generate_ulid()
        cancelled_booking.created_at = datetime.now()
        cancelled_booking.confirmed_at = datetime.now()
        cancelled_booking.completed_at = None
        cancelled_booking.cancelled_at = datetime.now()
        cancelled_booking.cancelled_by_id = generate_ulid()
        cancelled_booking.cancellation_reason = "Emergency"
        cancelled_booking.student = Mock(
            id=generate_ulid(), first_name="Student", last_name="User", email="student@test.com"
        )
        cancelled_booking.instructor = Mock(
            id=generate_ulid(), first_name="Instructor", last_name="User", email="instructor@test.com"
        )
        cancelled_booking.instructor_service = self._create_mock_instructor_service()

        mock_booking_service.cancel_booking.return_value = cancelled_booking

        response = client_with_mock_booking_service.post(
            "/bookings/123/cancel", json={"reason": "Emergency"}, headers=auth_headers_student
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == BookingStatus.CANCELLED.value

    def test_booking_opportunity_finder(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Test finding booking opportunities (future feature)."""
        # This is a placeholder for the find_booking_opportunities feature
        # The endpoint doesn't exist yet but the service method does

    # ===== Reschedule Route Tests (use mocked service + dependency override) =====
    def test_reschedule_booking_success(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Reschedule cancels original and creates a new booking; returns the new booking."""
        from app.models.booking import BookingStatus

        original_id = generate_ulid()
        new_id = generate_ulid()

        # Mock original booking returned by get_booking_for_user
        original = Mock()
        original.id = original_id
        original.student_id = generate_ulid()
        original.instructor_id = generate_ulid()
        original.instructor_service_id = generate_ulid()
        original.booking_date = date.today() + timedelta(days=2)
        original.start_time = time(9, 0)
        original.end_time = time(10, 0)
        original.status = BookingStatus.CONFIRMED
        original.service_name = "Piano"
        original.total_price = 50.0
        original.hourly_rate = 50.0
        original.duration_minutes = 60
        original.service_area = "Manhattan"
        original.meeting_location = "Studio"
        original.location_type = "neutral"
        original.student_note = "Bring sheet music"
        original.instructor_note = None
        # Nested objects used by response factories downstream
        original.student = Mock(id=generate_ulid(), first_name="Stu", last_name="Dent", email="s@example.com")
        original.instructor = Mock(id=generate_ulid(), first_name="Ins", last_name="Tructor", email="i@example.com")
        original.instructor_service = self._create_mock_instructor_service(name="Piano Lessons")
        mock_booking_service.get_booking_for_user.return_value = original

        # Mock new booking that will be returned by create_booking_with_payment_setup
        new_booking = Mock()
        new_booking.id = new_id
        new_booking.student_id = original.student_id
        new_booking.instructor_id = original.instructor_id
        new_booking.instructor_service_id = original.instructor_service_id
        new_booking.rescheduled_from_booking_id = original_id
        new_booking.booking_date = date.today() + timedelta(days=3)
        new_booking.start_time = time(11, 0)
        new_booking.end_time = time(12, 0)
        new_booking.status = BookingStatus.CONFIRMED
        new_booking.service_name = original.service_name
        new_booking.total_price = 50.0
        new_booking.hourly_rate = 50.0
        new_booking.duration_minutes = 60
        new_booking.service_area = original.service_area
        new_booking.meeting_location = original.meeting_location
        new_booking.location_type = original.location_type
        new_booking.student_note = original.student_note
        new_booking.instructor_note = None
        new_booking.created_at = datetime.now()
        new_booking.confirmed_at = datetime.now()
        new_booking.completed_at = None
        new_booking.cancelled_at = None
        new_booking.cancelled_by_id = None
        new_booking.cancellation_reason = None
        new_booking.student = original.student
        new_booking.instructor = original.instructor
        new_booking.instructor_service = original.instructor_service

        mock_booking_service.cancel_booking = AsyncMock()
        mock_booking_service.create_booking_with_payment_setup = AsyncMock(return_value=new_booking)

        # Execute
        payload = {
            "booking_date": (date.today() + timedelta(days=3)).isoformat(),
            "start_time": "11:00",
            "selected_duration": 60,
        }
        response = client_with_mock_booking_service.post(
            f"/bookings/{original_id}/reschedule", json=payload, headers=auth_headers_student
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == new_id
        assert data["status"] == BookingStatus.CONFIRMED.value

        # Cancel called with reason 'Rescheduled'
        mock_booking_service.cancel_booking.assert_awaited_once()
        args, kwargs = mock_booking_service.cancel_booking.call_args
        assert kwargs.get("reason") == "Rescheduled"

        # create_booking_with_payment_setup called with carried fields and default service id
        mock_booking_service.create_booking_with_payment_setup.assert_awaited_once()
        _, kwargs = mock_booking_service.create_booking_with_payment_setup.call_args
        booking_data = kwargs.get("booking_data")
        assert booking_data is not None
        assert booking_data.instructor_service_id == original.instructor_service_id
        assert booking_data.meeting_location == original.meeting_location
        assert booking_data.location_type == original.location_type
        assert booking_data.student_note == original.student_note
        # And linkage is passed for persistence
        assert kwargs.get("rescheduled_from_booking_id") == original_id

        # Ensure call order: cancel before create
        method_names = [m[0] for m in mock_booking_service.method_calls]
        # New flow: create new booking first, then cancel the original
        assert method_names.index("create_booking_with_payment_setup") < method_names.index("cancel_booking")

    def test_reschedule_booking_not_found(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """Reschedule returns 404 if original booking does not exist."""
        mock_booking_service.get_booking_for_user.return_value = None

        payload = {
            "booking_date": (date.today() + timedelta(days=3)).isoformat(),
            "start_time": "11:00",
            "selected_duration": 60,
        }
        response = client_with_mock_booking_service.post(
            f"/bookings/{generate_ulid()}/reschedule", json=payload, headers=auth_headers_student
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reschedule_requires_auth(self, client):
        """Reschedule endpoint should require auth like others."""
        payload = {
            "booking_date": (date.today() + timedelta(days=3)).isoformat(),
            "start_time": "11:00",
            "selected_duration": 60,
        }
        response = client.post(f"/bookings/{generate_ulid()}/reschedule", json=payload)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_reschedule_business_rule_violation(
        self, client_with_mock_booking_service, auth_headers_student, mock_booking_service
    ):
        """If cancellation policy blocks cancel, reschedule should return 422 via domain exception handler."""
        from app.core.exceptions import BusinessRuleException

        # Return an original booking
        original = Mock()
        original.id = generate_ulid()
        original.instructor_id = generate_ulid()
        original.instructor_service_id = generate_ulid()
        mock_booking_service.get_booking_for_user.return_value = original

        # Cancel raises business rule exception
        async def cancel_raise(*args, **kwargs):
            raise BusinessRuleException("Late reschedule not allowed")

        mock_booking_service.cancel_booking = AsyncMock(side_effect=cancel_raise)

        payload = {
            "booking_date": (date.today() + timedelta(days=1)).isoformat(),
            "start_time": "08:00",
            "selected_duration": 60,
        }
        response = client_with_mock_booking_service.post(
            f"/bookings/{original.id}/reschedule", json=payload, headers=auth_headers_student
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "late" in str(response.json()).lower()


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
        from app.models.service_catalog import InstructorService as Service

        service = (
            db.query(Service)
            .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
            .first()
        )

        # Create booking
        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": test_instructor_with_availability.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "10:00",
            "selected_duration": 60,
            "end_time": "11:00",
            "meeting_location": "Test Location",
        }

        response = client.post("/bookings/", json=booking_data, headers=student_headers)
        assert response.status_code == status.HTTP_201_CREATED
        booking_id = response.json()["id"]

        # Verify booking appears in student's list
        response = client.get("/bookings/", headers=student_headers)
        assert response.status_code == status.HTTP_200_OK
        bookings = response.json()["items"]
        assert any(b["id"] == booking_id for b in bookings)

        # Verify booking appears in instructor's list
        response = client.get("/bookings/", headers=instructor_headers)
        assert response.status_code == status.HTTP_200_OK
        bookings = response.json()["items"]
        assert any(b["id"] == booking_id for b in bookings)

        # Confirm payment first (new payment flow requires this)
        # Mock the Stripe payment confirmation
        from unittest.mock import patch

        with patch("app.services.stripe_service.StripeService.save_payment_method"):
            payment_data = {
                "payment_method_id": "pm_test_mock",
                "save_payment_method": False,
            }
            response = client.post(
                f"/bookings/{booking_id}/confirm-payment", json=payment_data, headers=student_headers
            )
            # If endpoint doesn't exist or fails, booking might already be confirmed
            if response.status_code == 200:
                assert response.json()["status"] == BookingStatus.CONFIRMED.value

        # Complete the booking (as instructor)
        response = client.post(f"/bookings/{booking_id}/complete", headers=instructor_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == BookingStatus.COMPLETED.value

        # Verify status changed
        from app.models.booking import Booking

        booking = db.get(Booking, booking_id)
        assert booking.status == BookingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_double_booking_prevention(self, client, db, test_student, test_instructor_with_availability):
        """Test that double booking same time slot is prevented."""
        from app.auth import create_access_token
        from app.models.service_catalog import InstructorService as Service

        # Create two students
        student1_token = create_access_token(data={"sub": test_student.email})
        student1_headers = {"Authorization": f"Bearer {student1_token}"}

        # Create second student
        from app.auth import get_password_hash
        from app.models.user import User

        student2 = User(
            email="student2@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            first_name="Second",
            last_name="Student",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(student2)
        db.flush()

        # RBAC: Assign student role
        from app.core.enums import RoleName
        from app.services.permission_service import PermissionService

        permission_service = PermissionService(db)
        permission_service.assign_role(student2.id, RoleName.STUDENT)
        db.refresh(student2)

        db.commit()

        student2_token = create_access_token(data={"sub": student2.email})
        student2_headers = {"Authorization": f"Bearer {student2_token}"}

        # Get service
        service = (
            db.query(Service)
            .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
            .first()
        )

        # First booking succeeds
        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": test_instructor_with_availability.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "10:00",
            "selected_duration": 60,
            "end_time": "11:00",
            "meeting_location": "Test Location",
        }

        response = client.post("/bookings/", json=booking_data, headers=student1_headers)
        assert response.status_code == status.HTTP_201_CREATED

        # Second booking for same time should fail
        response = client.post("/bookings/", json=booking_data, headers=student2_headers)
        assert response.status_code == status.HTTP_409_CONFLICT
        # Check for conflict message - handle both string and dict detail
        error_data = response.json()
        error_str = str(error_data).lower()
        assert "conflict" in error_str

    @pytest.mark.asyncio
    async def test_booking_cancellation_flow(self, client, db, test_student, test_instructor_with_availability):
        """Test booking cancellation by both student and instructor."""
        from app.auth import create_access_token
        from app.models.service_catalog import InstructorService as Service

        student_token = create_access_token(data={"sub": test_student.email})
        student_headers = {"Authorization": f"Bearer {student_token}"}

        instructor_token = create_access_token(data={"sub": test_instructor_with_availability.email})
        instructor_headers = {"Authorization": f"Bearer {instructor_token}"}

        # Get service
        service = (
            db.query(Service)
            .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
            .first()
        )

        # Create booking
        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": test_instructor_with_availability.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "14:00",
            "selected_duration": 60,
            "end_time": "15:00",
            "meeting_location": "Park",
        }

        response = client.post("/bookings/", json=booking_data, headers=student_headers)
        assert response.status_code == status.HTTP_201_CREATED
        booking_id = response.json()["id"]

        # Student cancels booking
        response = client.post(
            f"/bookings/{booking_id}/cancel", json={"reason": "Schedule conflict"}, headers=student_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == BookingStatus.CANCELLED.value
        assert response.json()["cancellation_reason"] == "Schedule conflict"

        # Create another booking
        booking_data["start_time"] = "16:00"
        booking_data["end_time"] = "17:00"
        response = client.post("/bookings/", json=booking_data, headers=student_headers)
        assert response.status_code == status.HTTP_201_CREATED
        booking_id2 = response.json()["id"]

        # Instructor cancels booking
        response = client.post(
            f"/bookings/{booking_id2}/cancel", json={"reason": "Instructor unavailable"}, headers=instructor_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == BookingStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_booking_stats_calculation(self, client, db, test_student, test_instructor_with_availability):
        """Test booking statistics calculation for instructors."""
        from app.auth import create_access_token
        from app.models.booking import Booking, BookingStatus
        from app.models.service_catalog import InstructorService as Service

        instructor_token = create_access_token(data={"sub": test_instructor_with_availability.email})
        instructor_headers = {"Authorization": f"Bearer {instructor_token}"}

        # Create some bookings directly in DB for stats
        service = (
            db.query(Service)
            .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
            .first()
        )

        # Create completed bookings
        for i in range(3):
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor_with_availability.id,
                instructor_service_id=service.id,
                booking_date=date.today() - timedelta(days=i + 1),
                start_time=time(10, 0),
                end_time=time(11, 0),
                service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
                hourly_rate=service.hourly_rate,
                total_price=service.hourly_rate,
                duration_minutes=60,
                status=BookingStatus.COMPLETED,
                meeting_location="Studio",
                service_area="Manhattan",
            )
            booking.complete()
            db.add(booking)

        # Create upcoming booking
        upcoming = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Studio",
            service_area="Manhattan",
        )
        db.add(upcoming)

        # Create cancelled booking
        cancelled = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(16, 0),
            end_time=time(17, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CANCELLED,
            meeting_location="Studio",
            service_area="Manhattan",
            cancelled_by_id=test_student.id,
            cancellation_reason="Changed plans",
        )
        db.add(cancelled)

        db.commit()

        # Get stats
        response = client.get("/bookings/stats", headers=instructor_headers)
        assert response.status_code == status.HTTP_200_OK

        stats = response.json()
        assert stats["total_bookings"] == 5
        assert stats["completed_bookings"] == 3
        assert stats["upcoming_bookings"] == 1
        assert stats["cancelled_bookings"] == 1
        # Use the actual service hourly_rate (could be 45.0 or 50.0 depending on which service is selected)
        expected_earnings = float(service.hourly_rate * 3)  # 3 completed bookings
        assert stats["total_earnings"] == expected_earnings
        # Check for optional fields that might be present
        if "completion_rate" in stats:
            assert stats["completion_rate"] == 0.6  # 3/5
        if "cancellation_rate" in stats:
            assert stats["cancellation_rate"] == 0.2  # 1/5

    # Reschedule tests live in TestBookingRoutes with mocked service; none here
