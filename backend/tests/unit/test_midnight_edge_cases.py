from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day

from app.core.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.services.availability_service import AvailabilityService
from app.services.timezone_service import TimezoneService
from app.utils.time_utils import minutes_to_time_str, time_to_minutes

try:  # pragma: no cover - allow tests to run from repo root or backend/
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


def _configure_profile(db: Session, instructor_id: str) -> InstructorProfile:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).one()
    profile.min_advance_booking_hours = 0
    profile.buffer_time_minutes = 0
    db.flush()
    return profile


def _get_active_service(db: Session, profile_id: int) -> InstructorService:
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile_id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if service is None:
        raise RuntimeError("Active instructor service not found for midnight edge-case test")
    return service


def _booking_tz_fields_with_midnight(
    booking_date: date, start_time: time, end_time: time, lesson_timezone: str
) -> dict[str, object]:
    fields = booking_timezone_fields(
        booking_date, start_time, end_time, instructor_timezone=lesson_timezone
    )
    if end_time == time(0, 0) and start_time != time(0, 0):
        fields["booking_end_utc"] = TimezoneService.local_to_utc(
            booking_date + timedelta(days=1), end_time, lesson_timezone
        )
    return fields


def _create_booking(
    db: Session,
    *,
    instructor_id: str,
    student_id: str,
    service: InstructorService,
    booking_date: date,
    start_time: time,
    end_time: time,
    lesson_timezone: str,
) -> None:
    duration_minutes = time_to_minutes(end_time, is_end_time=True) - time_to_minutes(
        start_time, is_end_time=False
    )
    booking = Booking(
        instructor_id=instructor_id,
        student_id=student_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **_booking_tz_fields_with_midnight(booking_date, start_time, end_time, lesson_timezone),
        status=BookingStatus.CONFIRMED,
        instructor_service_id=service.id,
        service_name=service.catalog_entry.name if service.catalog_entry else "Service",
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate,
        duration_minutes=duration_minutes,
    )
    db.add(booking)
    db.commit()


class TestTimeToMinutes:
    """Test the canonical time_to_minutes utility."""

    def test_midnight_as_start_of_day(self):
        """time(0,0) as start time = 0 minutes."""
        assert time_to_minutes(time(0, 0), is_end_time=False) == 0

    def test_midnight_as_end_of_day(self):
        """time(0,0) as end time = 1440 minutes."""
        assert time_to_minutes(time(0, 0), is_end_time=True) == 1440

    def test_normal_times(self):
        assert time_to_minutes(time(9, 0), is_end_time=False) == 540
        assert time_to_minutes(time(14, 30), is_end_time=True) == 870
        assert time_to_minutes(time(23, 59), is_end_time=True) == 1439

    def test_noon(self):
        assert time_to_minutes(time(12, 0), is_end_time=False) == 720
        assert time_to_minutes(time(12, 0), is_end_time=True) == 720


class TestMinutesToTimeStr:
    def test_midnight_end_of_day(self):
        assert minutes_to_time_str(1440) == "24:00"

    def test_midnight_start_of_day(self):
        assert minutes_to_time_str(0) == "00:00"

    def test_normal_times(self):
        assert minutes_to_time_str(540) == "09:00"
        assert minutes_to_time_str(870) == "14:30"


class TestAvailabilityMidnightEdgeCases:
    """Integration tests for availability with midnight windows."""

    def test_availability_ending_at_midnight_not_dropped(self, db: Session, test_instructor):
        """
        REGRESSION TEST: Availability 14:00-24:00 must not be dropped.
        """
        _configure_profile(db, test_instructor.id)
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("14:00", "24:00")])

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result[target_date.isoformat()]

        assert slots == [(time(14, 0), time(0, 0))]

    def test_availability_starting_at_midnight(self, db: Session, test_instructor):
        """Availability 00:00-08:00 should work."""
        _configure_profile(db, test_instructor.id)
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("00:00", "08:00")])

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result[target_date.isoformat()]

        assert slots == [(time(0, 0), time(8, 0))]

    def test_full_day_availability(self, db: Session, test_instructor):
        """Availability 00:00-24:00 (full day) should work."""
        _configure_profile(db, test_instructor.id)
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("00:00", "24:00")])

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result[target_date.isoformat()]

        assert len(slots) == 1
        start_time, end_time = slots[0]
        assert time_to_minutes(start_time, is_end_time=False) == 0
        assert time_to_minutes(end_time, is_end_time=True) == 1440

    def test_booking_at_2300_to_midnight(
        self, db: Session, test_instructor, test_student
    ):
        """Booking 23:00-24:00 should subtract from availability."""
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("20:00", "24:00")])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(23, 0),
            end_time=time(0, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result[target_date.isoformat()]

        assert slots == [(time(20, 0), time(23, 0))]

    def test_subtract_booking_from_midnight_window(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability 14:00-24:00 with booking 16:00-17:00
        should return [(14:00, 16:00), (17:00, 24:00)].
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("14:00", "24:00")])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(16, 0),
            end_time=time(17, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result[target_date.isoformat()]

        assert slots == [(time(14, 0), time(16, 0)), (time(17, 0), time(0, 0))]


@pytest.fixture
def full_detail_settings(monkeypatch):
    """Ensure public availability returns full detail for midnight checks."""
    monkeypatch.setattr(settings, "public_availability_detail_level", "full")
    monkeypatch.setattr(settings, "public_availability_days", 30)
    monkeypatch.setattr(settings, "public_availability_show_instructor_name", True)
    monkeypatch.setattr(settings, "public_availability_cache_ttl", 300)


class TestPublicAvailabilityMidnight:
    """Test public availability API with midnight edge cases."""

    def test_today_availability_ending_midnight_visible(
        self, client, db: Session, test_instructor, full_detail_settings
    ):
        """Same-day availability ending at midnight should be visible."""
        _configure_profile(db, test_instructor.id)
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("14:00", "24:00")])

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": target_date.isoformat(), "end_date": target_date.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == 200
        data = response.json()
        day = data["availability_by_date"][target_date.isoformat()]
        slot_times = {(slot["start_time"], slot["end_time"]) for slot in day["available_slots"]}
        assert ("14:00", "00:00") in slot_times

    def test_slots_near_midnight(self, client, db: Session, test_instructor, full_detail_settings):
        """Slots near midnight should remain bookable."""
        _configure_profile(db, test_instructor.id)
        target_date = date.today()

        seed_day(db, test_instructor.id, target_date, [("21:00", "24:00")])

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={"start_date": target_date.isoformat(), "end_date": target_date.isoformat()},
        )

        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == 200
        data = response.json()
        day = data["availability_by_date"][target_date.isoformat()]
        assert any(
            slot["end_time"] == "00:00" and slot["start_time"] <= "23:30"
            for slot in day["available_slots"]
        )
