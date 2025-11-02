"""
Test suite for booking independence from availability saving.

Locks the behavior that bookings do not prevent availability saves,
and that availability display may subtract bookings but saving is unaffected.
"""

from datetime import date, time, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.main
from app.models import Booking, BookingStatus, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module

try:
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability enabled."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)

    yield app.main

    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)


@pytest.fixture
def bitmap_client(bitmap_app) -> TestClient:
    """Return a TestClient backed by the bitmap-enabled app instance."""
    client = TestClient(bitmap_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


class TestSaveWeekSucceedsEvenWithOverlappingBookings:
    """Test that saving availability succeeds even when bookings overlap."""

    def test_save_week_succeeds_even_with_overlapping_bookings(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        test_student: User,
        auth_headers_instructor: dict,
    ) -> None:
        """Create a booking on Tue 10:00-11:00, then save availability including that window."""
        week_start = date(2025, 11, 3)  # Monday
        tuesday = week_start + timedelta(days=1)

        # Get instructor's profile and service
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
        service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

        # Create a booking on Tue 10:00-11:00
        booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=tuesday,
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=0,
        )
        db.commit()

        # Save a week that includes Tue 10:00-11:00 availability
        payload = {
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "schedule": [
                {
                    "date": tuesday.isoformat(),
                    "start_time": "10:00:00",
                    "end_time": "11:00:00",
                },
                {
                    "date": (week_start + timedelta(days=3)).isoformat(),  # Thursday
                    "start_time": "14:00:00",
                    "end_time": "15:00:00",
                },
            ],
        }

        resp = bitmap_client.post(
            "/instructors/availability/week",
            json=payload,
            headers=auth_headers_instructor,
        )

        # Expect 200 - save succeeds despite overlapping booking
        assert resp.status_code == 200

        # GET /week shows availability windows
        get_resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        body = get_resp.json()

        # Tuesday should show the availability window
        assert body[tuesday.isoformat()] == [{"start_time": "10:00:00", "end_time": "11:00:00"}]

        # Thursday should also show its window
        thursday = week_start + timedelta(days=3)
        assert body[thursday.isoformat()] == [{"start_time": "14:00:00", "end_time": "15:00:00"}]

        # Verify the booking still exists
        booking_check = db.query(Booking).filter(Booking.id == booking.id).first()
        assert booking_check is not None
        assert booking_check.status == BookingStatus.CONFIRMED

        # Verify availability bits were saved in database
        repo = AvailabilityDayRepository(db)
        stored = repo.get_week(test_instructor.id, week_start)
        assert stored.get(tuesday) is not None
        assert stored.get(thursday) is not None
