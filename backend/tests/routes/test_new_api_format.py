# backend/tests/routes/test_new_api_format.py
"""
Test examples demonstrating the new API format.
FIXED VERSION - Properly uses existing fixtures and correct setup.

Key fixes applied:
1. Use existing fixtures from conftest.py (no test_service)
2. Proper auth headers for instructors
3. Correct data ownership for updates
4. Proper prerequisite data creation
5. Relative dates instead of hardcoded dates

To run these tests:
    cd backend
    pytest tests/routes/test_new_api_format.py -v
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """New API format tests assert legacy 201 flows without floors."""
    yield


class TestBookingRoutesNewFormat:
    """Test booking endpoints with new time-based format."""

    def test_create_booking_new_format(
        self, client, db: Session, test_student, test_instructor_with_availability, auth_headers_student
    ):
        """Verify booking creation with time-based format."""
        # Get the instructor's service
        instructor = test_instructor_with_availability

        # Get service from database
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Use tomorrow's date to ensure availability exists
        tomorrow = date.today() + timedelta(days=1)

        response = client.post(
            "/bookings/",  # With trailing slash
            json={
                "instructor_id": instructor.id,
                "instructor_service_id": service.id,
                "booking_date": tomorrow.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
                "selected_duration": 60,
                "student_note": "Looking forward to the lesson!",
                "meeting_location": "123 Main St",
                "location_type": "neutral",
            },
            headers=auth_headers_student,
        )

        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.json()}"
        data = response.json()

        # Verify response has new format
        assert "instructor_id" in data
        assert "booking_date" in data
        assert "start_time" in data
        assert "end_time" in data

        # Verify NO slot_id in response
        assert "availability_slot_id" not in data

    def test_old_format_rejected(self, client, auth_headers_student):
        """Verify old slot-based format is rejected."""
        response = client.post(
            "/bookings/",  # With trailing slash
            json={"availability_slot_id": 123, "instructor_service_id": 1, "student_note": "This should fail"},
            headers=auth_headers_student,
        )

        assert response.status_code == 422
        error = response.json()
        # Should complain about missing required fields
        assert "Field required" in str(error)

    def test_check_availability_new_format(
        self, client, db: Session, test_student, test_instructor_with_availability, auth_headers_student
    ):
        """Verify availability check with time-based format."""
        instructor = test_instructor_with_availability

        # Get service
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        tomorrow = date.today() + timedelta(days=1)

        response = client.post(
            "/bookings/check-availability",
            json={
                "instructor_id": instructor.id,
                "instructor_service_id": service.id,
                "booking_date": tomorrow.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
            },
            headers=auth_headers_student,
        )

        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert isinstance(data["available"], bool)

    def test_check_availability_old_format_rejected(self, client, auth_headers_student):
        """Verify old availability check format is rejected."""
        response = client.post(
            "/bookings/check-availability",
            json={"availability_slot_id": 123, "instructor_service_id": 1},
            headers=auth_headers_student,
        )

        assert response.status_code == 422
        error = response.json()
        assert "Field required" in str(error)


class TestAvailabilityRoutesCleanResponses:
    """Test availability endpoints return clean responses."""

    def test_get_all_availability_no_legacy_fields(
        self, client, test_instructor_with_availability, auth_headers_instructor
    ):
        """Verify availability responses have no legacy fields."""
        response = client.get("/instructors/availability/", headers=auth_headers_instructor)

        assert response.status_code == 200
        slots = response.json()

        # Should have slots from test_instructor_with_availability
        assert len(slots) > 0

        slot = slots[0]

        # Verify clean response
        assert "id" in slot
        assert "instructor_id" in slot
        assert "specific_date" in slot
        assert "start_time" in slot
        assert "end_time" in slot

        # Verify NO legacy fields
        assert "is_available" not in slot
        assert "is_recurring" not in slot
        assert "day_of_week" not in slot

    def test_update_availability_clean_response(
        self, client, test_instructor_with_availability, auth_headers_instructor
    ):
        """Verify update returns clean response."""
        # First get existing slots
        response = client.get("/instructors/availability/", headers=auth_headers_instructor)

        assert response.status_code == 200
        slots = response.json()

        if not slots:
            pytest.skip("No slots available to update")

        slot = slots[0]
        slot_id = slot["id"]

        # Update the slot
        update_response = client.patch(
            f"/instructors/availability/{slot_id}",
            json={"start_time": "09:30", "end_time": "10:30"},
            headers=auth_headers_instructor,
        )

        assert update_response.status_code == 200, f"Update failed: {update_response.json()}"
        updated_slot = update_response.json()

        # Verify clean response
        assert "id" in updated_slot
        assert updated_slot["start_time"] == "09:30:00"
        assert updated_slot["end_time"] == "10:30:00"

        # Verify NO legacy fields
        assert "is_available" not in updated_slot
        assert "is_recurring" not in updated_slot
        assert "day_of_week" not in updated_slot

    def test_update_with_legacy_field_rejected(
        self, client, test_instructor_with_availability, auth_headers_instructor
    ):
        """Verify update with legacy field is rejected."""
        # Get existing slot
        response = client.get("/instructors/availability/", headers=auth_headers_instructor)

        assert response.status_code == 200
        slots = response.json()

        if not slots:
            pytest.skip("No slots available to update")

        slot_id = slots[0]["id"]

        # Try to update with legacy field
        response = client.patch(
            f"/instructors/availability/{slot_id}",
            json={
                "start_time": "09:00",
                "end_time": "10:00",
                "is_available": False,  # This field doesn't exist anymore
            },
            headers=auth_headers_instructor,
        )

        # Should get 422 because is_available is not a valid field
        assert response.status_code == 422
        error = response.json()
        assert "Extra inputs are not permitted" in str(error)


class TestBookingResponseFormat:
    """Test booking responses are clean."""

    def test_booking_response_no_slot_id(
        self, client, db: Session, test_student, test_instructor_with_availability, auth_headers_student
    ):
        """Verify booking responses don't include slot_id."""
        instructor = test_instructor_with_availability

        # Get service
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Book for day after tomorrow to avoid conflicts
        book_date = date.today() + timedelta(days=2)

        # Create a booking
        create_response = client.post(
            "/bookings/",
            json={
                "instructor_id": instructor.id,
                "instructor_service_id": service.id,
                "booking_date": book_date.isoformat(),
                "start_time": "14:00",
                "selected_duration": 60,
                "end_time": "15:00",
                "student_note": "Test booking",
                "location_type": "neutral",
            },
            headers=auth_headers_student,
        )

        assert create_response.status_code == 201, f"Booking creation failed: {create_response.json()}"
        booking = create_response.json()

        # Get booking details
        booking_id = booking["id"]
        get_response = client.get(f"/bookings/{booking_id}", headers=auth_headers_student)

        assert get_response.status_code == 200
        booking_details = get_response.json()

        # Verify no slot_id
        assert "availability_slot_id" not in booking_details

        # Verify self-contained booking data
        assert "instructor_id" in booking_details
        assert "booking_date" in booking_details
        assert "start_time" in booking_details
        assert "end_time" in booking_details


# Integration test showing full flow
def test_full_booking_flow_clean_architecture(
    client, db: Session, test_student, test_instructor_with_availability, auth_headers_student, auth_headers_instructor
):
    """Test complete booking flow with clean architecture."""
    instructor = test_instructor_with_availability

    # Get service
    from app.models.instructor import InstructorProfile
    from app.models.service_catalog import InstructorService as Service

    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    # Use a date far in the future to avoid conflicts
    future_date = date.today() + timedelta(days=10)

    # Step 1: Instructor adds availability
    availability_response = client.post(
        "/instructors/availability/specific-date",
        json={"specific_date": future_date.isoformat(), "start_time": "10:00", "end_time": "12:00"},
        headers=auth_headers_instructor,
    )

    assert availability_response.status_code == 200, f"Failed to create availability: {availability_response.json()}"
    slot = availability_response.json()

    # Verify clean slot response
    assert "is_available" not in slot
    assert "is_recurring" not in slot
    assert "day_of_week" not in slot

    # Step 2: Student checks availability
    check_response = client.post(
        "/bookings/check-availability",
        json={
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": future_date.isoformat(),
            "start_time": "10:00",
            "end_time": "11:00",
        },
        headers=auth_headers_student,
    )

    assert check_response.status_code == 200
    availability_result = check_response.json()
    assert availability_result["available"] is True

    # Step 3: Student creates booking
    booking_response = client.post(
        "/bookings/",
        json={
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": future_date.isoformat(),
            "start_time": "10:00",
            "selected_duration": 60,
            "end_time": "11:00",
            "student_note": "Excited for my first lesson!",
            "location_type": "neutral",
        },
        headers=auth_headers_student,
    )

    assert booking_response.status_code == 201, f"Failed to create booking: {booking_response.json()}"
    booking = booking_response.json()

    # Verify booking is self-contained
    assert "availability_slot_id" not in booking
    assert booking["booking_date"] == future_date.isoformat()
    assert booking["start_time"] == "10:00:00"
    assert booking["end_time"] == "11:00:00"

    print("✅ Full booking flow works with clean architecture!")


def test_debug_database_connections(client, db, auth_headers_student):
    """Debug test to see which databases are being used"""
    from app.core.config import settings
    from app.database import SessionLocal, engine

    print("\n=== DATABASE DEBUG ===")
    print(f"settings.is_testing: {settings.is_testing}")
    print(f"settings.database_url: {settings.database_url}")
    print(f"settings.get_database_url(): {settings.get_database_url()}")
    print(f"Engine URL: {engine.url}")

    # Check what database the session is using
    session = SessionLocal()
    result = session.execute(text("SELECT current_database()"))
    current_db = result.scalar()
    print(f"Session database: {current_db}")
    session.close()

    # Make a simple API call
    response = client.get("/health")
    print(f"Health check response: {response.status_code}")

    # Try to get current user
    response = client.get("/me", headers=auth_headers_student)
    print(f"Get current user: {response.status_code}")
    if response.status_code != 200:
        print(f"Response: {response.json()}")
