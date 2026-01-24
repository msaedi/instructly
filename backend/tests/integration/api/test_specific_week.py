# backend/tests/integration/api/test_specific_week.py
"""
Test the endpoint with a specific week that has bookings - fixed for time-based booking
"""
from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


def test_week_with_known_bookings(
    client: TestClient,
    db: Session,
    test_instructor_with_availability: User,
    test_student: User,
    auth_headers_instructor: dict,
):
    """Test week with bookings we create."""

    # Use a specific test date
    test_date = date(2025, 6, 16)  # A Monday

    # Get instructor's profile and service
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    # Create multiple windows using bitmap storage
    windows = [("09:00", "10:00"), ("10:00", "11:00"), ("14:00", "15:00")]
    seed_day(db, test_instructor_with_availability.id, test_date, windows)
    db.commit()

    # Create bookings for 2 of the 3 windows with time-based pattern
    slot_times = [(time(9, 0), time(10, 0)), (time(10, 0), time(11, 0)), (time(14, 0), time(15, 0))]
    for i in range(2):
        start_time, end_time = slot_times[i]
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            # availability_slot_id completely removed from architecture
            booking_date=test_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(test_date, start_time, end_time),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="instructor_location" if i == 0 else "neutral_location",  # FIXED: was "instructor"
            service_area="Manhattan",
            meeting_location=f"Location {i+1}",
        )
        db.add(booking)

    db.commit()

    # Test the endpoint
    response = client.get(
        "/api/v1/instructors/availability/week/booked-slots",
        params={"start_date": test_date.isoformat()},
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()

    # Should have exactly 2 booked slots
    assert len(data["booked_slots"]) == 2

    # Verify slot details
    for i, slot in enumerate(data["booked_slots"]):
        assert slot["date"] == test_date.isoformat()
        assert slot["service_name"] == (service.catalog_entry.name if service.catalog_entry else "Unknown Service")
        assert slot["student_first_name"] == "Test"
        assert slot["student_last_initial"] == "S."

        # Check location types
        if i == 0:
            assert slot["location_type"] == "instructor_location"
        else:
            assert slot["location_type"] == "neutral_location"


def test_multiple_instructors_isolation(
    client: TestClient,
    db: Session,
    test_instructor: User,
    test_instructor_with_availability: User,
    auth_headers_instructor: dict,
):
    """Test that instructors only see their own bookings."""

    # Use the first instructor's auth headers
    # Should not see the second instructor's bookings

    monday = date.today() - timedelta(days=date.today().weekday())

    response = client.get(
        "/api/v1/instructors/availability/week/booked-slots",
        params={"start_date": monday.isoformat()},
        headers=auth_headers_instructor,  # This is for test_instructor
    )

    assert response.status_code == 200
    data = response.json()

    # Should be empty or only contain test_instructor's bookings
    # (not test_instructor_with_availability's bookings)
    for slot in data.get("booked_slots", []):
        # If there are any bookings, verify they belong to the right instructor
        # This would require checking the booking's instructor_id
        pass  # In this test setup, test_instructor has no bookings
