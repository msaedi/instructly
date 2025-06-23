# backend/tests/test_booked_slots_endpoint.py
"""
Test the enhanced booked slots endpoint - fixed version with commit
"""
from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


def get_monday_of_current_week():
    today = date.today()
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    return monday


def test_booked_slots_endpoint(
    client: TestClient,
    db: Session,
    test_instructor_with_availability: User,
    test_student: User,
    auth_headers_instructor: dict,
):
    """Test the booked slots endpoint with proper test infrastructure."""

    # IMPORTANT: Commit the test data so the API endpoint can see it
    # db.commit()

    # First, create a booking for this week to ensure we have data
    monday = get_monday_of_current_week()

    # Get instructor's profile and service
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    # Get or create availability for Monday
    availability = (
        db.query(InstructorAvailability)
        .filter(
            InstructorAvailability.instructor_id == test_instructor_with_availability.id,
            InstructorAvailability.date == monday,
        )
        .first()
    )

    if not availability:
        availability = InstructorAvailability(
            instructor_id=test_instructor_with_availability.id, date=monday, is_cleared=False
        )
        db.add(availability)
        db.flush()

        # Add a slot
        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(9, 0), end_time=time(10, 0))
        db.add(slot)
        db.flush()
    else:
        slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability.id).first()

    # Create booking with CORRECT location_type values
    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        service_id=service.id,
        availability_slot_id=slot.id,
        booking_date=monday,
        start_time=slot.start_time,
        end_time=slot.end_time,
        service_name=service.skill,
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        location_type="student_home",  # FIXED: was "student"
        service_area="Manhattan",
        meeting_location="123 Test St",
    )
    db.add(booking)
    db.commit()  # Commit the booking too

    # Now test the endpoint
    response = client.get(
        "/instructors/availability-windows/week/booked-slots",
        params={"start_date": monday.isoformat()},
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "booked_slots" in data
    assert len(data["booked_slots"]) >= 1

    # Check the slot data
    slot_data = data["booked_slots"][0]

    # Verify required fields
    required_fields = [
        "booking_id",
        "date",
        "start_time",
        "end_time",
        "student_first_name",
        "student_last_initial",
        "service_name",
        "service_area_short",
        "duration_minutes",
        "location_type",
    ]

    for field in required_fields:
        assert field in slot_data, f"Missing field: {field}"

    # Verify data correctness
    assert slot_data["date"] == monday.isoformat()
    assert slot_data["student_first_name"] == "Test"
    assert slot_data["student_last_initial"] == "S."
    assert slot_data["service_name"] == service.skill
    assert slot_data["duration_minutes"] == 60
    assert slot_data["location_type"] == "student_home"


def test_booked_slots_endpoint_empty_week(
    client: TestClient, db: Session, test_instructor: User, auth_headers_instructor: dict
):
    """Test the endpoint with no bookings."""

    # IMPORTANT: Commit the test data
    # db.commit()

    # Get a week far in the future that won't have bookings
    future_monday = date.today() + timedelta(days=365)

    response = client.get(
        "/instructors/availability-windows/week/booked-slots",
        params={"start_date": future_monday.isoformat()},
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()

    assert "booked_slots" in data
    assert len(data["booked_slots"]) == 0
