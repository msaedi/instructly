"""
UTC timezone handling tests.

These tests verify that:
1. Booking availability checks use UTC consistently.
2. Auto-completion cutoff uses UTC lesson end times.
3. Instructor timezone does not alter backend calculations.
"""

from datetime import date, datetime, time, timezone
from unittest.mock import MagicMock, patch

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.user import User


def _make_instructor_profile(tz_name: str, min_advance_hours: int = 1) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = generate_ulid()
    user.timezone = tz_name

    profile = MagicMock(spec=InstructorProfile)
    profile.user = user
    profile.min_advance_booking_hours = min_advance_hours
    profile.hourly_rate = 100

    return profile


def _run_check_availability(
    db,
    instructor_profile: MagicMock,
    now_utc: datetime,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> dict:
    from app.services.booking_service import BookingService

    booking_service = BookingService(db)

    with patch("app.services.booking_service.datetime") as mock_dt:
        mock_dt.now.return_value = now_utc
        mock_dt.combine = datetime.combine

        with patch.object(booking_service, "repository") as mock_repo:
            mock_repo.check_time_conflict.return_value = False

            with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                mock_ccr.get_active_service.return_value = MagicMock()
                mock_ccr.get_instructor_profile.return_value = instructor_profile

                return booking_service.check_availability(
                    instructor_id=instructor_profile.user.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    service_id="test_service",
                )


def _make_booking(booking_date: date, end_time: time, tz_name: str) -> MagicMock:
    booking = MagicMock(spec=Booking)
    booking.id = generate_ulid()
    booking.status = BookingStatus.CONFIRMED
    booking.payment_status = "authorized"
    booking.student_id = "student_test"
    booking.instructor_id = "instructor_test"
    booking.payment_intent_id = "pi_test"
    booking.booking_date = booking_date
    booking.end_time = end_time
    booking.instructor = MagicMock()
    booking.instructor.timezone = tz_name
    return booking


class TestCheckAvailabilityUTC:
    def test_booking_1hr_advance_passes_in_utc(self, db):
        instructor_profile = _make_instructor_profile("Asia/Tokyo")
        now_utc = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        result = _run_check_availability(
            db=db,
            instructor_profile=instructor_profile,
            now_utc=now_utc,
            booking_date=date(2024, 6, 15),
            start_time=time(11, 0),
            end_time=time(12, 0),
        )

        assert result["available"] is True

    def test_booking_30min_advance_rejected_even_with_offset_timezone(self, db):
        instructor_profile = _make_instructor_profile("America/Los_Angeles")
        now_utc = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        result = _run_check_availability(
            db=db,
            instructor_profile=instructor_profile,
            now_utc=now_utc,
            booking_date=date(2024, 6, 15),
            start_time=time(10, 30),
            end_time=time(11, 30),
        )

        assert result["available"] is False
        assert "hours in advance" in result["reason"]

    def test_booking_cross_midnight_utc_boundary(self, db):
        instructor_profile = _make_instructor_profile("America/New_York")
        now_utc = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)

        result = _run_check_availability(
            db=db,
            instructor_profile=instructor_profile,
            now_utc=now_utc,
            booking_date=date(2024, 6, 16),
            start_time=time(0, 30),
            end_time=time(1, 30),
        )

        assert result["available"] is True


class TestCaptureCompletedLessonsUTC:
    def test_lesson_not_auto_completed_before_24_hours(self, db):
        from app.tasks.payment_tasks import capture_completed_lessons

        booking = _make_booking(date(2024, 12, 24), time(21, 0), "America/New_York")
        now_utc = datetime(2024, 12, 25, 20, 0, 0, tzinfo=timezone.utc)

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = now_utc
            mock_dt.combine = datetime.combine

            with patch("app.database.SessionLocal") as mock_session_local:
                mock_db = MagicMock()
                mock_session_local.return_value = mock_db

                with patch("app.tasks.payment_tasks.RepositoryFactory") as mock_factory:
                    mock_booking_repo = MagicMock()
                    mock_booking_repo.get_bookings_for_payment_capture.return_value = []
                    mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
                    mock_booking_repo.get_bookings_with_expired_auth.return_value = []
                    mock_factory.get_booking_repository.return_value = mock_booking_repo

                    mock_payment_repo = MagicMock()
                    mock_factory.get_payment_repository.return_value = mock_payment_repo

                    with patch("app.tasks.payment_tasks._auto_complete_booking") as mock_auto:
                        result = capture_completed_lessons()

        assert result["auto_completed"] == 0
        mock_auto.assert_not_called()

    def test_lesson_auto_completed_uses_utc_time(self, db):
        from app.tasks.payment_tasks import capture_completed_lessons

        booking = _make_booking(date(2024, 12, 24), time(21, 0), "America/New_York")
        now_utc = datetime(2024, 12, 25, 21, 30, 0, tzinfo=timezone.utc)

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = now_utc
            mock_dt.combine = datetime.combine

            with patch("app.database.SessionLocal") as mock_session_local:
                mock_db = MagicMock()
                mock_session_local.return_value = mock_db

                with patch("app.tasks.payment_tasks.RepositoryFactory") as mock_factory:
                    mock_booking_repo = MagicMock()
                    mock_booking_repo.get_bookings_for_payment_capture.return_value = []
                    mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
                    mock_booking_repo.get_bookings_with_expired_auth.return_value = []
                    mock_factory.get_booking_repository.return_value = mock_booking_repo

                    mock_payment_repo = MagicMock()
                    mock_factory.get_payment_repository.return_value = mock_payment_repo

                    with patch(
                        "app.tasks.payment_tasks._auto_complete_booking",
                        return_value={
                            "auto_completed": True,
                            "captured": False,
                            "capture_attempted": False,
                        },
                    ) as mock_auto:
                        result = capture_completed_lessons()

        assert result["auto_completed"] == 1
        mock_auto.assert_called_once_with(booking.id, now_utc)
