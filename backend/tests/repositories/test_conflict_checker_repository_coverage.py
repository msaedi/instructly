from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import RepositoryException
from app.models.availability import BlackoutDate
from app.models.booking import BookingStatus
from app.models.service_catalog import InstructorService
from app.repositories.conflict_checker_repository import ConflictCheckerRepository

try:  # pragma: no cover - allow repo root or backend/ test execution
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


class TestConflictCheckerRepositoryCoverage:
    def test_conflict_queries(self, db, test_student, test_instructor_with_availability):
        repo = ConflictCheckerRepository(db)
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)

        profile = (
            db.query(InstructorService)
            .filter(InstructorService.instructor_profile_id.isnot(None))
            .first()
        )
        service_id = profile.id if profile else None
        if service_id is None:
            pytest.skip("No instructor service available for conflict tests")

        booking1 = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=BookingStatus.CONFIRMED,
            service_name="Test",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            meeting_location="Test",
            service_area="Manhattan",
        )
        create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=tomorrow,
            start_time=time(11, 0),
            end_time=time(12, 0),
            status=BookingStatus.CONFIRMED,
            service_name="Test",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            meeting_location="Test",
            service_area="Manhattan",
        )
        db.commit()

        conflicts = repo.get_bookings_for_conflict_check(
            test_instructor_with_availability.id, tomorrow
        )
        assert len(conflicts) >= 2

        filtered = repo.get_bookings_for_conflict_check(
            test_instructor_with_availability.id, tomorrow, exclude_booking_id=booking1.id
        )
        assert all(b.id != booking1.id for b in filtered)

        day_bookings = repo.get_bookings_for_date(test_instructor_with_availability.id, tomorrow)
        assert day_bookings
        assert day_bookings[0].start_time <= day_bookings[-1].start_time

        week_bookings = repo.get_bookings_for_week(
            test_instructor_with_availability.id, [tomorrow]
        )
        assert week_bookings

    def test_blackout_profile_and_service(self, db, test_instructor_with_availability, test_booking):
        repo = ConflictCheckerRepository(db)
        target_date = test_booking.booking_date

        blackout = BlackoutDate(
            instructor_id=test_instructor_with_availability.id,
            date=target_date,
            reason="vacation",
        )
        db.add(blackout)
        db.commit()

        assert repo.get_blackout_date(test_instructor_with_availability.id, target_date) is not None
        assert repo.get_instructor_profile(test_instructor_with_availability.id) is not None

        service = (
            db.query(InstructorService)
            .filter(InstructorService.id == test_booking.instructor_service_id)
            .first()
        )
        assert service is not None
        active = repo.get_active_service(service.id)
        assert active is not None

    def test_error_paths_raise_repository_exception(self):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("boom")
        repo = ConflictCheckerRepository(mock_db)

        with pytest.raises(RepositoryException):
            repo.get_bookings_for_conflict_check("inst", datetime.now(timezone.utc).date())

        with pytest.raises(RepositoryException):
            repo.get_bookings_for_date("inst", datetime.now(timezone.utc).date())

        with pytest.raises(RepositoryException):
            repo.get_bookings_for_week("inst", [datetime.now(timezone.utc).date()])

        with pytest.raises(RepositoryException):
            repo.get_blackout_date("inst", datetime.now(timezone.utc).date())

        with pytest.raises(RepositoryException):
            repo.get_instructor_profile("inst")

        with pytest.raises(RepositoryException):
            repo.get_active_service("svc")
