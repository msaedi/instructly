# backend/tests/integration/services/test_booking_service_edge_cases_student_bug.py
"""
Test that verifies student double-booking prevention is working correctly.
This test ensures students cannot book overlapping sessions with different instructors.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.enums import RoleName
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.services.permission_service import PermissionService
from tests._utils.bitmap_avail import seed_day

try:  # pragma: no cover - fallback for direct backend test executions
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Double-booking regression uses sub-floor rates."""
    yield


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    yield


@pytest.mark.asyncio
async def test_student_cannot_double_book_overlapping_sessions(db: Session, catalog_data: dict):
    """
    Test that students cannot book overlapping sessions with different instructors.
    This verifies the double-booking prevention is working correctly.
    """
    # Create a student
    student = User(
        email="double.booking.student@test.com",
        hashed_password=get_password_hash("testpass123"),
        first_name="Double",
        last_name="Booking Student",
        phone="+12125550000",
        zip_code="10001",
        is_active=True,
    )
    db.add(student)
    db.flush()

    # RBAC: Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    db.refresh(student)

    # Create first instructor with Math service
    instructor1 = User(
        email="math.instructor@test.com",
        hashed_password=get_password_hash("testpass123"),
        first_name="Math",
        last_name="Instructor",
        phone="+12125550000",
        zip_code="10001",
        is_active=True,
    )
    db.add(instructor1)
    db.flush()

    # RBAC: Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(instructor1.id, RoleName.INSTRUCTOR)
    db.refresh(instructor1)

    profile1 = InstructorProfile(
        user_id=instructor1.id,
        min_advance_booking_hours=1,
    )
    db.add(profile1)
    db.flush()
    add_service_areas_for_boroughs(db, user=instructor1, boroughs=["Manhattan"])

    # Get Math catalog service
    math_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name.ilike("%math%")).first()
    if not math_catalog:
        # Create one if it doesn't exist
        category = db.query(ServiceCategory).first()
        math_catalog = ServiceCatalog(name="Math Tutoring", slug="math-tutoring", category_id=category.id)
        db.add(math_catalog)
        db.flush()

    math_service = Service(
        instructor_profile_id=profile1.id,
        service_catalog_id=math_catalog.id,
        hourly_rate=50.0,
        is_active=True,
    )
    db.add(math_service)

    # Create second instructor with Piano service
    instructor2 = User(
        email="piano.instructor@test.com",
        hashed_password=get_password_hash("testpass123"),
        first_name="Piano",
        last_name="Instructor",
        phone="+12125550000",
        zip_code="10001",
        is_active=True,
    )
    db.add(instructor2)
    db.flush()

    # RBAC: Assign role
    permission_service = PermissionService(db)
    permission_service.assign_role(instructor2.id, RoleName.INSTRUCTOR)
    db.refresh(instructor2)

    profile2 = InstructorProfile(
        user_id=instructor2.id,
        min_advance_booking_hours=1,
    )
    db.add(profile2)
    db.flush()
    add_service_areas_for_boroughs(db, user=instructor2, boroughs=["Brooklyn"])

    # Get Piano catalog service
    piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name.ilike("%piano%")).first()
    if not piano_catalog:
        # Create one if it doesn't exist
        category = db.query(ServiceCategory).first()
        piano_catalog = ServiceCatalog(name="Piano Lessons", slug="piano-lessons", category_id=category.id)
        db.add(piano_catalog)
        db.flush()

    piano_service = Service(
        instructor_profile_id=profile2.id,
        service_catalog_id=piano_catalog.id,
        hourly_rate=75.0,
        is_active=True,
    )
    db.add(piano_service)

    # Add availability for both instructors on the same day
    tomorrow = date.today() + timedelta(days=1)

    # Math instructor available 9 AM - 5 PM
    seed_day(db, instructor1.id, tomorrow, [("09:00", "17:00")])

    # Piano instructor available 9 AM - 5 PM
    seed_day(db, instructor2.id, tomorrow, [("09:00", "17:00")])

    # Create booking service (notifications will fail but that's OK)
    booking_service = BookingService(db)

    # First booking: Math lesson 3:00-4:00 PM
    booking1_data = BookingCreate(
        instructor_id=instructor1.id,
        booking_date=tomorrow,
        start_time=time(15, 0),  # 3:00 PM
        end_time=time(16, 0),  # 4:00 PM
        selected_duration=60,
        instructor_service_id=math_service.id,
        location_type="neutral",
        meeting_location="Online",
    )

    booking1 = await booking_service.create_booking(
        student, booking1_data, selected_duration=booking1_data.selected_duration
    )
    assert booking1.id is not None
    assert booking1.status == BookingStatus.CONFIRMED

    # Second booking: Piano lesson 3:30-4:30 PM (overlaps with first)
    booking2_data = BookingCreate(
        instructor_id=instructor2.id,
        booking_date=tomorrow,
        start_time=time(15, 30),  # 3:30 PM - overlaps with Math lesson
        end_time=time(16, 30),  # 4:30 PM
        selected_duration=60,
        instructor_service_id=piano_service.id,
        location_type="neutral",
        meeting_location="Online",
    )

    # This should fail with ConflictException
    from app.core.exceptions import ConflictException

    with pytest.raises(ConflictException) as exc_info:
        await booking_service.create_booking(student, booking2_data, selected_duration=booking2_data.selected_duration)

    # Verify the error message
    assert "Student already has a booking that overlaps this time" in str(exc_info.value)

    # Verify only the first booking exists
    student_bookings = booking_service.get_bookings_for_user(student)
    confirmed_tomorrow = [
        b for b in student_bookings if b.booking_date == tomorrow and b.status == BookingStatus.CONFIRMED
    ]
    assert len(confirmed_tomorrow) == 1
    assert confirmed_tomorrow[0].id == booking1.id

    # Verify the time overlap would have occurred
    assert booking1.start_time < time(16, 30)  # booking2 end time
    assert booking1.end_time > time(15, 30)  # booking2 start time

    print("SUCCESS: Student double-booking prevention is working correctly!")
    print(
        f"Booking 1: {booking1.service_name} with {booking1.instructor.first_name} {booking1.instructor.last_name} at {booking1.start_time}-{booking1.end_time}"
    )
    print("Booking 2: BLOCKED - ConflictException raised as expected")
