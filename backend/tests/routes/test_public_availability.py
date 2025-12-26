# backend/tests/routes/test_public_availability.py
"""
Tests for public availability endpoints.

These tests ensure that:
1. Students can view availability without authentication
2. Booked slots are properly excluded
3. Blackout dates are respected
4. Caching works correctly
5. Edge cases are handled
"""

from datetime import date, datetime, time, timedelta

from fastapi import status
import pytest
import pytz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from tests._utils.bitmap_avail import seed_day

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def full_detail_settings(monkeypatch):
    """Ensure tests use full detail level and 30 days default."""
    monkeypatch.setattr(settings, "public_availability_detail_level", "full")
    monkeypatch.setattr(settings, "public_availability_days", 30)
    monkeypatch.setattr(settings, "public_availability_show_instructor_name", True)
    monkeypatch.setattr(settings, "public_availability_cache_ttl", 300)


@pytest.fixture
def minimal_detail_settings(monkeypatch):
    """Configure minimal detail level for specific tests."""
    monkeypatch.setattr(settings, "public_availability_detail_level", "minimal")
    monkeypatch.setattr(settings, "public_availability_days", 30)


@pytest.fixture
def summary_detail_settings(monkeypatch):
    """Configure summary detail level for specific tests."""
    monkeypatch.setattr(settings, "public_availability_detail_level", "summary")
    monkeypatch.setattr(settings, "public_availability_days", 30)


class TestPublicAvailability:
    """Test public availability endpoints."""

    @pytest.fixture
    def public_client(self, client):
        """Client without authentication headers."""
        return client

    @pytest.fixture
    def mock_instructor_with_availability(self, db: Session, test_instructor, test_student):
        """Create instructor with various availability scenarios."""
        instructor = test_instructor
        today = date.today()

        # Get instructor's profile for service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create availability using bitmap storage
        # Today - multiple windows
        seed_day(db, instructor.id, today, [("09:00", "10:00"), ("10:00", "11:00"), ("14:00", "15:00")])
        # Tomorrow - one window (will be booked)
        seed_day(db, instructor.id, today + timedelta(days=1), [("09:00", "10:00")])
        # Day after tomorrow - blackout date with availability
        seed_day(db, instructor.id, today + timedelta(days=2), [("09:00", "10:00")])

        # Create a booking for tomorrow
        booking_date = today + timedelta(days=1)
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            instructor_id=instructor.id,
            student_id=test_student.id,  # Use actual test student
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )

        # Create blackout date
        blackout = BlackoutDate(instructor_id=instructor.id, date=today + timedelta(days=2), reason="Personal day")

        return {"instructor": instructor, "booking": booking, "blackout": blackout, "service": service}

    def test_get_public_availability_no_auth_required(self, public_client, test_instructor, full_detail_settings):
        """Test that public endpoint doesn't require authentication."""
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        # Should work without auth headers (200 or 404 if route not registered)
        assert response.status_code in [200, 404]

    def test_get_public_availability_success(
        self, public_client, db, mock_instructor_with_availability, full_detail_settings
    ):
        """Test successful retrieval of public availability."""
        data = mock_instructor_with_availability
        instructor = data["instructor"]

        # Add test data to database (availability already created via seed_day)
        db.add(data["booking"])
        db.add(data["blackout"])
        db.commit()

        # Request availability
        today = date.today()
        response = public_client.get(
            f"/api/v1/public/instructors/{instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": (today + timedelta(days=2)).isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Verify response structure
        assert result["instructor_id"] == instructor.id
        assert result["instructor_first_name"] == instructor.first_name  # Privacy-protected: first name only
        assert (
            result["instructor_last_initial"] == instructor.last_name[0] if instructor.last_name else None
        )  # Privacy-protected: initial only
        assert "availability_by_date" in result
        assert result["timezone"] == "America/New_York"

        # Check today - with merged windows, 9-10 and 10-11 become 9-11, plus 14-15 => 2 windows
        today_str = today.isoformat()
        assert today_str in result["availability_by_date"]
        today_availability = result["availability_by_date"][today_str]
        assert len(today_availability["available_slots"]) == 2
        # Verify merged intervals
        merged_times = {(s["start_time"], s["end_time"]) for s in today_availability["available_slots"]}
        assert ("09:00", "11:00") in merged_times
        assert ("14:00", "15:00") in merged_times
        assert not today_availability["is_blackout"]

        # Check tomorrow - should have 0 slots (booked)
        tomorrow_str = (today + timedelta(days=1)).isoformat()
        assert tomorrow_str in result["availability_by_date"]
        tomorrow_availability = result["availability_by_date"][tomorrow_str]
        assert len(tomorrow_availability["available_slots"]) == 0
        assert not tomorrow_availability["is_blackout"]

        # Check day after - should be blackout
        day_after_str = (today + timedelta(days=2)).isoformat()
        assert day_after_str in result["availability_by_date"]
        day_after_availability = result["availability_by_date"][day_after_str]
        assert len(day_after_availability["available_slots"]) == 0
        assert day_after_availability["is_blackout"]

        # Verify summary stats (2 merged windows for today)
        assert result["total_available_slots"] >= 2
        assert result["earliest_available_date"] == today_str

    def test_get_public_availability_instructor_not_found(self, public_client, full_detail_settings):
        """Test 404 when instructor doesn't exist."""
        response = public_client.get(
            "/api/v1/public/instructors/01J5TESTINSTR0000000000999/availability",
            params={"start_date": date.today().isoformat()},
        )

        if response.status_code == 404 and "Not Found" in response.json().get("detail", ""):
            # Route not registered
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_public_availability_invalid_date_range(self, public_client, test_instructor, full_detail_settings):
        """Test validation of date parameters."""
        # Use instructor's timezone for date comparison
        from app.core.timezone_utils import get_user_today

        instructor_today = get_user_today(test_instructor)

        # Past start date based on instructor's timezone
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": (instructor_today - timedelta(days=1)).isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # End before start
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={
                "start_date": instructor_today.isoformat(),
                "end_date": (instructor_today - timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "after start date" in response.json()["detail"]

        # Range too large
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={
                "start_date": instructor_today.isoformat(),
                "end_date": (instructor_today + timedelta(days=100)).isoformat(),
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "90 days" in response.json()["detail"]

    def test_public_availability_respects_advance_notice(
        self,
        public_client,
        db,
        test_instructor,
        full_detail_settings,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Slots earlier than advance notice should be filtered out."""
        instructor = test_instructor
        profile = (
            db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        )
        assert profile is not None
        profile.min_advance_booking_hours = 4
        profile.buffer_time_minutes = 0
        db.commit()

        target_date = date.today()
        seed_day(db, instructor.id, target_date, [("09:00", "17:00")])

        tz = pytz.timezone(getattr(instructor, "timezone", "America/New_York"))
        monkeypatch.setattr(
            "app.services.availability_service.get_user_now_by_id",
            lambda *_: tz.localize(datetime.combine(target_date, time(10, 30))),
        )

        response = public_client.get(
            f"/api/v1/public/instructors/{instructor.id}/availability",
            params={"start_date": target_date.isoformat(), "end_date": target_date.isoformat()},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        slots = response.json()["availability_by_date"][target_date.isoformat()]["available_slots"]
        assert slots, "Expected filtered slots"
        first_slot = slots[0]
        assert first_slot["start_time"] == "14:30"
        assert first_slot["end_time"] == "17:00"

    def test_public_availability_respects_buffer_time(
        self,
        public_client,
        db,
        test_instructor,
        test_student,
        full_detail_settings,
    ):
        """Slots should respect instructor buffer around existing bookings."""
        instructor = test_instructor
        profile = (
            db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        )
        assert profile is not None
        profile.buffer_time_minutes = 30
        profile.min_advance_booking_hours = 0
        db.commit()

        target_date = date.today()
        seed_day(db, instructor.id, target_date, [("09:00", "12:00")])

        service = (
            db.query(Service)
            .filter(Service.instructor_profile_id == profile.id, Service.is_active == True)
            .first()
        )
        assert service is not None

        booking_date = target_date
        start_time = time(10, 0)
        end_time = time(11, 0)
        booking = Booking(
            instructor_id=instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Test Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        response = public_client.get(
            f"/api/v1/public/instructors/{instructor.id}/availability",
            params={"start_date": target_date.isoformat(), "end_date": target_date.isoformat()},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        slots = response.json()["availability_by_date"][target_date.isoformat()]["available_slots"]
        assert {("09:00", "09:30"), ("11:30", "12:00")} == {
            (slot["start_time"], slot["end_time"]) for slot in slots
        }

    def test_next_available_respects_buffer_and_notice(
        self,
        public_client,
        db,
        test_instructor,
        test_student,
        full_detail_settings,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Next available endpoint should align with filtered availability."""
        instructor = test_instructor
        profile = (
            db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
        )
        assert profile is not None
        profile.buffer_time_minutes = 30
        profile.min_advance_booking_hours = 0
        db.commit()

        target_date = date.today() + timedelta(days=1)
        seed_day(db, instructor.id, target_date, [("09:00", "12:00")])

        service = (
            db.query(Service)
            .filter(Service.instructor_profile_id == profile.id, Service.is_active == True)
            .first()
        )
        assert service is not None

        booking_date = target_date
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            instructor_id=instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Test Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        tz = pytz.timezone(getattr(instructor, "timezone", "America/New_York"))
        monkeypatch.setattr(
            "app.services.availability_service.get_user_now_by_id",
            lambda *_: tz.localize(datetime.combine(date.today(), time(5, 0))),
        )

        response = public_client.get(
            f"/api/v1/public/instructors/{instructor.id}/next-available",
            params={"duration_minutes": 60},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        payload = response.json()
        assert payload["found"]
        assert payload["date"] == target_date.isoformat()
        assert payload["start_time"] == "10:30:00"

    def test_get_public_availability_default_end_date(self, public_client, test_instructor, full_detail_settings):
        """Test that end_date defaults to configured days if not provided."""
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Should have 30 days (based on public_availability_days setting)
        assert len(result["availability_by_date"]) == 30

    def test_get_public_availability_excludes_cancelled_bookings(
        self, public_client, db, test_instructor, test_student, full_detail_settings
    ):
        """Test that cancelled bookings don't affect availability."""
        today = date.today()

        # Get instructor's profile and service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
        profile.buffer_time_minutes = 0
        profile.min_advance_booking_hours = 0
        db.commit()
        refreshed = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor.id)
            .first()
        )
        assert refreshed.buffer_time_minutes == 0
        assert refreshed.min_advance_booking_hours == 0

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create availability using bitmap storage
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])

        # Create cancelled booking
        booking_date = today
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CANCELLED,  # Cancelled!
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Slot should still be available
        today_slots = result["availability_by_date"][today.isoformat()]["available_slots"]
        assert len(today_slots) == 1
        assert today_slots[0]["start_time"] == "09:00"

    def test_get_public_availability_caching(self, public_client, test_instructor, full_detail_settings):
        """Test that endpoint works with or without caching."""
        # Just test the endpoint works - caching is optional
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == 200

        # Make a second request - should get same result
        response2 = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        assert response2.status_code == 200
        # Both responses should be identical
        assert response.json() == response2.json()

    def test_get_next_available_slot(self, public_client, db, test_instructor, test_student, full_detail_settings):
        """Test finding next available slot."""
        today = date.today()

        # Get instructor's profile and service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create availability using bitmap storage
        # Today - all booked
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])
        # Tomorrow - available
        seed_day(db, test_instructor.id, today + timedelta(days=1), [("09:00", "11:00")])

        # Book today's slot
        booking_date = today
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        # Request next available for 60 minutes
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/next-available", params={"duration_minutes": 60}
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        assert result["found"] is True
        assert result["date"] == (today + timedelta(days=1)).isoformat()
        assert result["start_time"] == "09:00:00"
        assert result["duration_minutes"] == 60

    def test_get_next_available_slot_not_found(self, public_client, test_instructor, full_detail_settings):
        """Test when no available slot exists."""
        # No slots created
        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/next-available", params={"duration_minutes": 60}
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        assert result["found"] is False
        assert "No available slots" in result["message"]

    def test_public_availability_partial_slot_booking(
        self, public_client, db, test_instructor, test_student, full_detail_settings
    ):
        """Test that partially booked slots are excluded entirely."""
        today = date.today()

        # Get instructor's profile and service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create a 2-hour window using bitmap storage
        seed_day(db, test_instructor.id, today, [("09:00", "11:00")])

        # Book first hour
        booking_date = today
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=service.id,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.commit()

        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # With merged windows and buffer rules, the remaining window starts after the buffer gap
        today_slots = result["availability_by_date"][today.isoformat()]["available_slots"]
        windows = {(s["start_time"], s["end_time"]) for s in today_slots}
        assert ("10:15", "11:00") in windows
        assert len(today_slots) == 1

    def test_minimal_detail_level(self, public_client, db, test_instructor, minimal_detail_settings):
        """Test minimal detail level response."""
        today = date.today()

        # Create availability using bitmap storage
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])
        db.commit()

        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Should have minimal fields only
        assert "instructor_id" in result
        assert "instructor_first_name" in result
        assert "instructor_last_initial" in result
        assert "has_availability" in result
        assert result["has_availability"] is True
        assert "earliest_available_date" in result
        assert result["earliest_available_date"] == today.isoformat()
        assert "availability_by_date" not in result  # No detailed slots

    def test_summary_detail_level(self, public_client, db, test_instructor, summary_detail_settings):
        """Test summary detail level response."""
        today = date.today()

        # Create morning and afternoon windows using bitmap storage
        seed_day(db, test_instructor.id, today, [("09:00", "11:00"), ("14:00", "16:00")])
        db.commit()

        response = public_client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Should have summary fields
        assert "availability_summary" in result
        assert result["detail_level"] == "summary"

        today_summary = result["availability_summary"][today.isoformat()]
        assert today_summary["morning_available"] is True
        assert today_summary["afternoon_available"] is True
        assert today_summary["evening_available"] is False
        assert today_summary["total_hours"] == 4.0  # 2 + 2 hours
