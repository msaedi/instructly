"""Test privacy protection for instructor last names in booking endpoints."""

from datetime import date, timedelta

from backend.tests._utils.bitmap_avail import seed_day
import pytest

from app.models.booking import Booking


@pytest.fixture(autouse=True)
def _seed_availability_for_privacy_tests(db, test_instructor):
    """
    Ensure the instructor used in this module always has availability bits on the day
    these tests book so BookingService passes availability validation.
    """
    instructor_id = test_instructor.id
    tomorrow = date.today() + timedelta(days=1)
    seed_day(db, instructor_id, tomorrow, [("09:00:00", "17:00:00")])


@pytest.fixture(autouse=True)
def _no_min_advance_requirement(db, test_instructor):
    from app.models.instructor import InstructorProfile

    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    if profile:
        profile.min_advance_booking_hours = 0
        db.add(profile)
        db.commit()


@pytest.fixture(autouse=True)
def _reset_bookings_for_privacy_tests(db, test_instructor):
    """Ensure prior tests don't leave overlapping bookings for this instructor."""
    db.query(Booking).filter(Booking.instructor_id == test_instructor.id).delete()
    # No commit needed - pytest handles transaction rollback


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Privacy scenarios create $50 bookings intentionally."""
    yield


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch):
    yield


@pytest.mark.asyncio
async def test_student_sees_instructor_last_initial_only(
    client,
    db,
    test_student,
    test_instructor,  # Use base instructor fixture which has services
    auth_headers_student,
    auth_headers_instructor,
):
    """Test that students only see instructor last initial, not full last name."""

    # Get the instructor's actual service ID from the database
    from app.models.instructor import InstructorProfile
    from app.models.service_catalog import InstructorService as Service

    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    assert profile is not None, "Test instructor must have a profile"

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
    assert service is not None, "Test instructor must have at least one active service"

    # Create a booking as a student
    tomorrow = date.today() + timedelta(days=1)
    booking_data = {
        "instructor_id": test_instructor.id,
        "instructor_service_id": service.id,  # Use actual service ID
        "booking_date": tomorrow.isoformat(),
        "start_time": "10:00",
        "selected_duration": 60,
        "student_note": "Test booking for privacy",
    }

    # Create booking
    response = client.post("/api/v1/bookings/", json=booking_data, headers=auth_headers_student)
    assert response.status_code == 201
    booking_id = response.json()["id"]

    # Test 1: GET /bookings - List bookings
    response = client.get("/api/v1/bookings/", headers=auth_headers_student)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

    # Find our booking
    booking = next((b for b in data["items"] if b["id"] == booking_id), None)
    assert booking is not None

    # Check instructor info - should have last_initial, not full last_name
    instructor_info = booking["instructor"]
    assert "last_initial" in instructor_info
    assert len(instructor_info["last_initial"]) == 1  # Single character
    assert instructor_info["first_name"] == test_instructor.first_name
    assert instructor_info["last_initial"] == test_instructor.last_name[0]

    print(f"✅ List bookings shows: {instructor_info['first_name']} {instructor_info['last_initial']}")

    # Test 2: GET /bookings/{id} - Single booking
    response = client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers_student)
    assert response.status_code == 200
    data = response.json()

    instructor_info = data["instructor"]
    assert "last_initial" in instructor_info
    assert len(instructor_info["last_initial"]) == 1
    assert instructor_info["first_name"] == test_instructor.first_name
    assert instructor_info["last_initial"] == test_instructor.last_name[0]

    print(f"✅ Single booking shows: {instructor_info['first_name']} {instructor_info['last_initial']}")

    # Test 3: GET /bookings/upcoming
    response = client.get("/api/v1/bookings/upcoming", headers=auth_headers_student)
    assert response.status_code == 200
    data = response.json()

    if data["items"]:
        upcoming = data["items"][0]
        # Should only show last initial for instructor
        assert "instructor_first_name" in upcoming
        assert "instructor_last_name" in upcoming
        # The endpoint now returns last initial in instructor_last_name field
        assert len(upcoming["instructor_last_name"]) == 1
        assert upcoming["instructor_last_name"] == test_instructor.last_name[0]

        print(f"✅ Upcoming bookings shows: {upcoming['instructor_first_name']} {upcoming['instructor_last_name']}")

    # Test 4: GET /bookings/{id}/preview
    response = client.get(f"/api/v1/bookings/{booking_id}/preview", headers=auth_headers_student)
    assert response.status_code == 200
    data = response.json()

    assert "instructor_first_name" in data
    assert "instructor_last_name" in data
    # Should only show last initial
    assert len(data["instructor_last_name"]) == 1
    assert data["instructor_last_name"] == test_instructor.last_name[0]

    print(f"✅ Preview shows: {data['instructor_first_name']} {data['instructor_last_name']}")

    print("\n✅ All privacy tests passed - students only see instructor last initials!")


@pytest.mark.asyncio
async def test_instructor_sees_own_full_name(
    client,
    db,
    test_instructor,  # Use base instructor fixture which has services
    test_student,
    auth_headers_instructor,
    auth_headers_student,
):
    """Test that instructors see their own full last name in bookings."""

    # Get the instructor's actual service ID from the database
    from app.models.instructor import InstructorProfile
    from app.models.service_catalog import InstructorService as Service

    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    assert profile is not None, "Test instructor must have a profile"

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
    assert service is not None, "Test instructor must have at least one active service"

    # Create a booking as a student first
    tomorrow = date.today() + timedelta(days=1)
    booking_data = {
        "instructor_id": test_instructor.id,
        "instructor_service_id": service.id,  # Use actual service ID
        "booking_date": tomorrow.isoformat(),
        "start_time": "14:00",
        "selected_duration": 60,
        "student_note": "Test booking",
    }

    # Student creates booking
    response = client.post("/api/v1/bookings/", json=booking_data, headers=auth_headers_student)
    assert response.status_code == 201
    booking_id = response.json()["id"]

    # Now check as instructor - should see full name
    response = client.get("/api/v1/bookings/upcoming", headers=auth_headers_instructor)
    assert response.status_code == 200
    data = response.json()

    if data["items"]:
        upcoming = data["items"][0]
        # Instructor should see their full last name
        assert upcoming["instructor_first_name"] == test_instructor.first_name
        assert upcoming["instructor_last_name"] == test_instructor.last_name  # Full name

        print(
            f"✅ Instructor sees their full name: {upcoming['instructor_first_name']} {upcoming['instructor_last_name']}"
        )

    # Check preview as instructor
    response = client.get(f"/api/v1/bookings/{booking_id}/preview", headers=auth_headers_instructor)
    assert response.status_code == 200
    data = response.json()

    assert data["instructor_first_name"] == test_instructor.first_name
    assert data["instructor_last_name"] == test_instructor.last_name  # Full name

    print(f"✅ Instructor preview shows full name: {data['instructor_first_name']} {data['instructor_last_name']}")

    print("\n✅ Instructors correctly see their own full names!")
