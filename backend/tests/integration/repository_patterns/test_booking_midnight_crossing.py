"""
Tests for midnight-crossing booking classification.

Verifies that bookings spanning midnight (e.g. 11:30 PM → 12:00 AM)
appear as upcoming/not-yet-ended when queried before midnight.

Regression test for the isoformat() string comparison bug where
time(0,0,0) > time(23,0,0) evaluated as False.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.repositories.booking_repository import BookingRepository

try:  # pragma: no cover
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs

EST = ZoneInfo("America/New_York")


@pytest.fixture
def midnight_fixtures(db: Session, test_instructor, test_student):
    """Create an instructor service and a midnight-crossing booking."""
    # Ensure instructor profile exists
    profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == test_instructor.id
    ).first()
    if not profile:
        profile = InstructorProfile(
            user_id=test_instructor.id,
            bio="Test bio",
            years_experience=5,
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan"])
        from app.services.permission_service import PermissionService
        PermissionService(db).assign_role(profile.id, RoleName.STUDENT)
        db.refresh(profile)

    # Get or create catalog service
    catalog_service = db.query(ServiceCatalog).first()
    if not catalog_service:
        category = ServiceCategory(name="Test Category")
        db.add(category)
        db.flush()
        subcategory = ServiceSubcategory(
            name="General", category_id=category.id, display_order=1,
        )
        db.add(subcategory)
        db.flush()
        catalog_service = ServiceCatalog(
            name="Test Service",
            slug=f"test-service-{generate_ulid().lower()}",
            subcategory_id=subcategory.id,
        )
        db.add(catalog_service)
        db.flush()

    # Get or create instructor service
    service = db.query(Service).filter(
        Service.instructor_profile_id == profile.id,
        Service.service_catalog_id == catalog_service.id,
    ).first()
    if not service:
        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=50.0,
            description="Test",
            is_active=True,
        )
        db.add(service)
        db.flush()

    # Create a midnight-crossing booking: 11:30 PM → 12:00 AM
    booking_date = date(2025, 2, 18)
    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=time(23, 30),
        end_time=time(0, 0),
        # EST = UTC-5. 11:30 PM EST = 04:30 UTC next day
        booking_start_utc=datetime(2025, 2, 19, 4, 30, tzinfo=timezone.utc),
        # Midnight EST = 05:00 UTC next day
        booking_end_utc=datetime(2025, 2, 19, 5, 0, tzinfo=timezone.utc),
        lesson_timezone="America/New_York",
        instructor_tz_at_booking="America/New_York",
        student_tz_at_booking="America/New_York",
        service_name="Test Service",
        hourly_rate=50.0,
        total_price=25.0,
        duration_minutes=30,
        status=BookingStatus.CONFIRMED,
        location_type="online",
        meeting_location="Online",
    )
    db.add(booking)
    db.flush()

    return {
        "instructor": test_instructor,
        "student": test_student,
        "booking": booking,
        "service": service,
    }


@pytest.mark.integration
class TestMidnightCrossingBooking:
    """Bookings that cross midnight (e.g. 23:30→00:00) must appear as upcoming
    when the current time is before the lesson starts."""

    def test_midnight_booking_appears_in_upcoming(
        self, db: Session, midnight_fixtures: dict,
    ) -> None:
        """A 11:30 PM→12:00 AM booking at 11:00 PM should be upcoming."""
        instructor = midnight_fixtures["instructor"]
        repo = BookingRepository(db)

        # Mock current time to 11:00 PM EST = 04:00 UTC on 2025-02-19
        fake_now = datetime(2025, 2, 18, 23, 0, 0, tzinfo=EST)

        with patch(
            "app.repositories.booking_repository.get_user_now_by_id",
            return_value=fake_now,
        ):
            results = repo.get_instructor_bookings(
                instructor_id=instructor.id,
                upcoming_only=True,
            )

        booking_ids = [b.id for b in results]
        assert midnight_fixtures["booking"].id in booking_ids, (
            "Midnight-crossing booking should appear as upcoming at 11:00 PM"
        )

    def test_midnight_booking_not_in_history_before_end(
        self, db: Session, midnight_fixtures: dict,
    ) -> None:
        """A 11:30 PM→12:00 AM booking at 11:00 PM should NOT be in history."""
        instructor = midnight_fixtures["instructor"]
        repo = BookingRepository(db)

        fake_now = datetime(2025, 2, 18, 23, 0, 0, tzinfo=EST)

        with patch(
            "app.repositories.booking_repository.get_user_now_by_id",
            return_value=fake_now,
        ):
            results = repo.get_instructor_bookings(
                instructor_id=instructor.id,
                exclude_future_confirmed=True,
            )

        booking_ids = [b.id for b in results]
        assert midnight_fixtures["booking"].id not in booking_ids, (
            "Midnight-crossing booking should NOT appear in history before it ends"
        )

    def test_midnight_booking_in_history_after_end(
        self, db: Session, midnight_fixtures: dict,
    ) -> None:
        """A 11:30 PM→12:00 AM booking at 12:30 AM next day should be in history."""
        instructor = midnight_fixtures["instructor"]
        repo = BookingRepository(db)

        # 12:30 AM on the 19th = after the booking ended at midnight
        fake_now = datetime(2025, 2, 19, 0, 30, 0, tzinfo=EST)

        with patch(
            "app.repositories.booking_repository.get_user_now_by_id",
            return_value=fake_now,
        ):
            results = repo.get_instructor_bookings(
                instructor_id=instructor.id,
                exclude_future_confirmed=True,
            )

        booking_ids = [b.id for b in results]
        assert midnight_fixtures["booking"].id in booking_ids, (
            "Midnight-crossing booking should appear in history after it has ended"
        )

    def test_student_midnight_booking_upcoming(
        self, db: Session, midnight_fixtures: dict,
    ) -> None:
        """Student view: midnight-crossing booking should be upcoming before midnight."""
        student = midnight_fixtures["student"]
        repo = BookingRepository(db)

        fake_now = datetime(2025, 2, 18, 23, 0, 0, tzinfo=EST)

        with patch(
            "app.repositories.booking_repository.get_user_now_by_id",
            return_value=fake_now,
        ):
            results = repo.get_student_bookings(
                student_id=student.id,
                upcoming_only=True,
            )

        booking_ids = [b.id for b in results]
        assert midnight_fixtures["booking"].id in booking_ids, (
            "Student should see midnight-crossing booking as upcoming"
        )

    def test_count_pending_completion_excludes_active_midnight_booking(
        self, db: Session, midnight_fixtures: dict,
    ) -> None:
        """A midnight-crossing booking still in progress should not count as pending completion."""
        repo = BookingRepository(db)

        # 11:45 PM: the lesson is in progress (started at 11:30, ends at midnight)
        now_utc = datetime(2025, 2, 19, 4, 45, tzinfo=timezone.utc)  # 11:45 PM EST
        count = repo.count_pending_completion(now_utc)

        # The booking hasn't ended yet, so it shouldn't be pending completion
        # (it might have other bookings from fixtures, but our midnight booking shouldn't be counted)
        # We verify by checking again at 5:01 AM UTC (12:01 AM EST) when it should be counted
        count_after = repo.count_pending_completion(
            datetime(2025, 2, 19, 5, 1, tzinfo=timezone.utc),
        )
        assert count_after >= count + 1, (
            "After the midnight-crossing booking ends, pending completion count should increase"
        )
