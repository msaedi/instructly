# backend/tests/test_timezone_handling.py
"""
Comprehensive timezone handling tests for Part 11 bug fixes.

These tests specifically verify that:
1. check_availability uses instructor timezone (not UTC)
2. capture_completed_lessons Celery task uses instructor timezone (not UTC)
3. check_availability and create_booking are consistent

THESE TESTS WILL FAIL LOUDLY if someone reintroduces UTC assumptions.

Bug Context (Part 11):
- Bug A: check_availability used `tzinfo=timezone.utc` for booking datetime
- Bug B: Celery capture_completed_lessons used `tzinfo=timezone.utc` for lesson_end
- Both bugs caused incorrect time comparisons when instructor timezone != UTC
"""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.user import User

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_instructor_est() -> MagicMock:
    """Create a mock instructor in Eastern timezone."""
    user = MagicMock(spec=User)
    user.id = generate_ulid()
    user.timezone = "America/New_York"

    profile = MagicMock(spec=InstructorProfile)
    profile.user = user
    profile.min_advance_booking_hours = 1
    profile.hourly_rate = 100

    return profile


@pytest.fixture
def mock_instructor_pst() -> MagicMock:
    """Create a mock instructor in Pacific timezone."""
    user = MagicMock(spec=User)
    user.id = generate_ulid()
    user.timezone = "America/Los_Angeles"

    profile = MagicMock(spec=InstructorProfile)
    profile.user = user
    profile.min_advance_booking_hours = 1
    profile.hourly_rate = 100

    return profile


@pytest.fixture
def mock_instructor_tokyo() -> MagicMock:
    """Create a mock instructor in Tokyo timezone (UTC+9)."""
    user = MagicMock(spec=User)
    user.id = generate_ulid()
    user.timezone = "Asia/Tokyo"

    profile = MagicMock(spec=InstructorProfile)
    profile.user = user
    profile.min_advance_booking_hours = 1
    profile.hourly_rate = 100

    return profile


@pytest.fixture
def mock_instructor_london() -> MagicMock:
    """Create a mock instructor in London timezone (UTC+0/+1)."""
    user = MagicMock(spec=User)
    user.id = generate_ulid()
    user.timezone = "Europe/London"

    profile = MagicMock(spec=InstructorProfile)
    profile.user = user
    profile.min_advance_booking_hours = 1
    profile.hourly_rate = 100

    return profile


# =============================================================================
# TEST: check_availability TIMEZONE HANDLING
# =============================================================================


class TestCheckAvailabilityTimezone:
    """
    Ensure check_availability uses instructor timezone correctly.

    Bug being prevented:
        booking_datetime = datetime.combine(booking_date, start_time, tzinfo=timezone.utc)
        # WRONG! This treats 9am EST as 9am UTC, not 2pm UTC

    Fix applied:
        instructor_zone = ZoneInfo(tz_name)
        booking_local = datetime.combine(booking_date, start_time, tzinfo=instructor_zone)
        # CORRECT! 9am EST is treated as 9am EST, then converted to 2pm UTC
    """

    def test_booking_1hr_advance_in_est_passes(self, db, mock_instructor_est):
        """
        EST instructor, booking 1hr from now should PASS.

        Scenario:
        - Current time: 10:00 AM EST
        - Booking for: 11:00 AM EST (1hr advance meets 1hr minimum)
        - Expected: available=True
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 10:00 AM EST (3:00 PM UTC)
        est_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)

        # Booking for 11:00 AM EST
        booking_date = date(2024, 6, 15)
        start_time = time(11, 0)
        end_time = time(12, 0)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            # Mock repository methods
            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_est

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_est.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        # MUST pass - if it fails, the UTC bug is back
        assert result["available"] is True, (
            "Bug regression! Booking 1hr in advance (in instructor timezone) should pass. "
            "check_availability may be using UTC instead of instructor timezone."
        )

    def test_booking_1hr_advance_in_pst_passes(self, db, mock_instructor_pst):
        """
        PST instructor, booking 1hr from now should PASS.

        Same test as EST but for Pacific timezone to ensure timezone logic isn't hardcoded.
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 10:00 AM PST (6:00 PM UTC)
        pst_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        utc_now = pst_now.astimezone(timezone.utc)

        # Booking for 11:00 AM PST
        booking_date = date(2024, 6, 15)
        start_time = time(11, 0)
        end_time = time(12, 0)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_pst

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_pst.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        assert result["available"] is True

    def test_booking_30min_advance_rejected(self, db, mock_instructor_est):
        """
        Booking only 30min in advance should be REJECTED.

        This confirms the minimum advance check is working, regardless of timezone.
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 10:00 AM EST
        est_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)

        # Booking for 10:30 AM EST (only 30min advance, less than 1hr minimum)
        booking_date = date(2024, 6, 15)
        start_time = time(10, 30)
        end_time = time(11, 30)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_est

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_est.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        assert result["available"] is False
        assert "hours in advance" in result["reason"]

    def test_late_night_booking_not_shifted(self, db, mock_instructor_est):
        """
        11pm EST booking shouldn't be interpreted as 11pm UTC.

        THIS IS THE EXACT BUG SCENARIO from Part 11.

        Bug behavior:
        - Instructor books for 11pm EST
        - Buggy code treats 11pm as 11pm UTC = 6pm EST
        - Results in incorrect time comparison

        Correct behavior:
        - 11pm EST = 3am UTC next day
        - Comparison should be against 3am UTC, not 11pm UTC
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 9:00 PM EST (1:00 AM UTC next day)
        est_now = datetime(2024, 6, 15, 21, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)

        # Booking for 11:00 PM EST (2hr advance, meets 1hr minimum)
        booking_date = date(2024, 6, 15)
        start_time = time(23, 0)  # 11pm
        end_time = time(23, 59)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_est

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_est.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        # MUST pass - if it fails, 11pm EST was incorrectly treated as 11pm UTC
        assert result["available"] is True, (
            "Bug regression! 11pm EST booking (2hr advance) should pass. "
            "The time may be incorrectly interpreted as UTC instead of EST."
        )

    def test_early_morning_booking_same_day(self, db, mock_instructor_est):
        """
        2am EST booking should be same day, not shifted.

        Edge case: early morning hours where UTC date might differ.
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 12:30 AM EST (4:30 AM UTC same day)
        est_now = datetime(2024, 6, 15, 0, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)

        # Booking for 2:00 AM EST (1.5hr advance, meets 1hr minimum)
        booking_date = date(2024, 6, 15)
        start_time = time(2, 0)
        end_time = time(3, 0)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_est

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_est.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        assert result["available"] is True

    def test_cross_midnight_utc_boundary(self, db, mock_instructor_est):
        """
        Booking at 8pm EST (1am UTC next day) should work correctly.

        This tests when the UTC date differs from the local date.
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Mock current time to 7:00 PM EST (12:00 AM UTC next day = midnight)
        est_now = datetime(2024, 6, 15, 19, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)  # This is June 16 00:00 UTC

        # Booking for 8:00 PM EST same day (1hr advance)
        # 8pm EST = 1am UTC June 16
        booking_date = date(2024, 6, 15)  # Local date is still June 15
        start_time = time(20, 0)  # 8pm
        end_time = time(21, 0)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = mock_instructor_est

                    result = booking_service.check_availability(
                        instructor_id=mock_instructor_est.user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        # Should pass - UTC date difference shouldn't matter
        assert result["available"] is True, (
            "Bug regression! Booking across UTC midnight boundary should work. "
            "UTC date change should not affect local time comparison."
        )


# =============================================================================
# TEST: PARAMETERIZED EDGE CASES
# =============================================================================


class TestTimezoneEdgeCases:
    """Parameterized tests for various timezone and time combinations."""

    @pytest.mark.parametrize(
        "instructor_tz,local_hour,advance_hours,expected_pass",
        [
            ("America/New_York", 9, 2, True),  # 9am EST, 2hr advance
            ("America/New_York", 23, 2, True),  # 11pm EST, late night
            ("America/New_York", 2, 2, True),  # 2am EST, early morning
            ("America/Los_Angeles", 21, 2, True),  # 9pm PST
            ("Europe/London", 14, 2, True),  # 2pm GMT
            ("Asia/Tokyo", 10, 2, True),  # 10am JST
            ("Australia/Sydney", 6, 2, True),  # 6am AEST
            ("America/New_York", 9, 0.5, False),  # 9am EST, only 30min advance
            ("Asia/Tokyo", 10, 0.25, False),  # 10am JST, only 15min advance
        ],
    )
    def test_advance_booking_various_timezones(
        self, db, instructor_tz: str, local_hour: int, advance_hours: float, expected_pass: bool
    ):
        """Advance booking check works across various timezones and hours."""
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Create mock instructor
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.timezone = instructor_tz

        profile = MagicMock(spec=InstructorProfile)
        profile.user = user
        profile.min_advance_booking_hours = 1

        # Calculate times
        tz = ZoneInfo(instructor_tz)
        local_now = datetime(2024, 6, 15, local_hour, 0, 0, tzinfo=tz)
        utc_now = local_now.astimezone(timezone.utc)

        # Booking time = now + advance_hours
        booking_local = local_now + timedelta(hours=advance_hours)
        booking_date = booking_local.date()
        start_time = booking_local.time()
        end_time = (booking_local + timedelta(hours=1)).time()

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = profile

                    result = booking_service.check_availability(
                        instructor_id=user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        assert result["available"] is expected_pass, (
            f"Timezone {instructor_tz}, {local_hour}:00, {advance_hours}hr advance: "
            f"expected {'available' if expected_pass else 'unavailable'}"
        )


# =============================================================================
# TEST: CELERY capture_completed_lessons TIMEZONE HANDLING
# =============================================================================


class TestCeleryTaskTimezone:
    """
    Ensure Celery capture_completed_lessons uses instructor timezone for 24hr calculation.

    Bug being prevented:
        lesson_end = datetime.combine(booking_date, booking.end_time, tzinfo=timezone.utc)
        # WRONG! This treats 9pm EST as 9pm UTC

    Fix applied:
        instructor_zone = ZoneInfo(tz_name)
        lesson_end_local = datetime.combine(booking_date, booking.end_time, tzinfo=instructor_zone)
        lesson_end = lesson_end_local.astimezone(timezone.utc)
        # CORRECT! 9pm EST is correctly converted to 1am UTC next day
    """

    def test_lesson_not_captured_before_24hrs_est(self, db):
        """
        EST lesson at 9pm should not auto-complete until 24+ hours later.

        Scenario:
        - Lesson ended: 9pm EST Dec 24 (2am UTC Dec 25)
        - Current time: 2pm EST Dec 25 (7pm UTC Dec 25) - only 17 hours later
        - Expected: Should NOT auto-complete (less than 24 hours)
        """
        from app.tasks.payment_tasks import capture_completed_lessons

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_test"
        booking.instructor_id = "instructor_test"
        booking.payment_intent_id = "pi_test"

        # Instructor in EST
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        # Lesson ended at 9pm EST on Dec 24
        # 9pm EST = 2am UTC Dec 25
        booking.booking_date = date(2024, 12, 24)
        booking.end_time = time(21, 0)  # 9pm

        # Current time: 2pm EST Dec 25 (only 17 hours after 9pm EST)
        # 2pm EST = 7pm UTC Dec 25
        mock_now = datetime(2024, 12, 25, 19, 0, 0, tzinfo=timezone.utc)

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine  # Preserve real combine function

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

                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch("app.tasks.payment_tasks.StudentCreditService"):
                            result = capture_completed_lessons()

        # Should NOT auto-complete because only 17 hours have passed
        assert result["auto_completed"] == 0, (
            "Bug regression! Lesson should NOT auto-complete after only 17 hours. "
            "The lesson end time may be incorrectly interpreted as UTC instead of EST."
        )

    def test_lesson_captured_after_24hrs_est(self, db):
        """
        EST lesson should auto-complete after 24+ hours in EST.

        Scenario:
        - Lesson ended: 9pm EST Dec 24 (2am UTC Dec 25)
        - Current time: 10pm EST Dec 25 (3am UTC Dec 26) - 25 hours later
        - Expected: Should auto-complete
        """
        from app.tasks.payment_tasks import capture_completed_lessons

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_test"
        booking.instructor_id = "instructor_test"
        booking.payment_intent_id = "pi_test_capture"

        # Instructor in EST
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        # Lesson ended at 9pm EST on Dec 24
        booking.booking_date = date(2024, 12, 24)
        booking.end_time = time(21, 0)  # 9pm

        # Current time: 10pm EST Dec 25 (25 hours after 9pm EST Dec 24)
        # 10pm EST = 3am UTC Dec 26
        mock_now = datetime(2024, 12, 26, 3, 0, 0, tzinfo=timezone.utc)

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine  # Preserve real combine function

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

                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch("app.tasks.payment_tasks.StudentCreditService"):
                            with patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": True}):
                                result = capture_completed_lessons()

        # Should auto-complete because 25 hours have passed
        assert result["auto_completed"] == 1, (
            "Lesson should auto-complete after 25 hours. "
            "Verify timezone conversion is working correctly."
        )

    def test_late_night_lesson_not_captured_early(self, db):
        """
        11pm EST lesson shouldn't be captured 5 hours early.

        THIS IS THE EXACT BUG SCENARIO from Part 11.

        Bug behavior:
        - Lesson ended: 11pm EST = 4am UTC next day
        - Buggy code thought lesson ended at 11pm UTC = 6pm EST
        - Bug result: Would trigger capture 5 hours early

        Correct behavior:
        - 11pm EST correctly converted to 4am UTC
        - Capture only happens 24+ hours after 4am UTC (which is 24+ hours after 11pm EST)
        """
        from app.tasks.payment_tasks import capture_completed_lessons

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_late"
        booking.instructor_id = "instructor_late"
        booking.payment_intent_id = "pi_test_late"

        # Instructor in EST
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        # Lesson ended at 11pm EST on Dec 24
        # 11pm EST = 4am UTC Dec 25
        booking.booking_date = date(2024, 12, 24)
        booking.end_time = time(23, 0)  # 11pm

        # Current time: 6pm EST Dec 25 (11pm UTC Dec 25)
        # This is only 19 hours after 11pm EST (but would be 24+ hours after 11pm UTC)
        mock_now = datetime(2024, 12, 25, 23, 0, 0, tzinfo=timezone.utc)  # 11pm UTC = 6pm EST

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine  # Preserve real combine function

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

                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch("app.tasks.payment_tasks.StudentCreditService"):
                            result = capture_completed_lessons()

        # MUST NOT auto-complete - only 19 hours have passed in EST
        # If it does capture, the bug is back (treating 11pm as UTC not EST)
        assert result["auto_completed"] == 0, (
            "Bug regression! 11pm EST lesson should NOT capture after only 19 hours. "
            "If this fails, the lesson end time is being treated as UTC instead of EST."
        )


# =============================================================================
# TEST: EXPLICIT REGRESSION TESTS FOR PART 11 BUGS
# =============================================================================


class TestTimezoneRegressions:
    """
    Explicit regression tests for bugs we've fixed in Part 11.

    These tests document the exact bug scenarios and WILL FAIL
    if someone reintroduces the UTC assumptions.
    """

    def test_regression_check_availability_utc_bug(self, db):
        """
        Regression test for Part 11 Bug A.

        Bug: check_availability used `tzinfo=timezone.utc` for booking datetime
        Location: booking_service.py:1846 (before fix)
        Effect: 9am EST was interpreted as 9am UTC (4am EST equivalent)

        This test will FAIL if someone reintroduces the UTC bug.
        """
        from app.services.booking_service import BookingService

        booking_service = BookingService(db)

        # Setup: Instructor in EST with 1hr minimum advance
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.timezone = "America/New_York"

        profile = MagicMock(spec=InstructorProfile)
        profile.user = user
        profile.min_advance_booking_hours = 1

        # Current time: 8am EST (1pm UTC)
        est_now = datetime(2024, 6, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_now = est_now.astimezone(timezone.utc)

        # Try to book for 9am EST (1hr from now in EST)
        booking_date = date(2024, 6, 15)
        start_time = time(9, 0)
        end_time = time(10, 0)

        with patch("app.services.booking_service.datetime") as mock_dt:
            mock_dt.now.return_value = utc_now
            mock_dt.combine = datetime.combine

            with patch.object(booking_service, "repository") as mock_repo:
                mock_repo.check_time_conflict.return_value = False

                with patch.object(booking_service, "conflict_checker_repository") as mock_ccr:
                    mock_ccr.get_active_service.return_value = MagicMock()
                    mock_ccr.get_instructor_profile.return_value = profile

                    result = booking_service.check_availability(
                        instructor_id=user.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        service_id="test_service",
                    )

        # MUST pass - if it fails, the bug is back
        assert result["available"] is True, (
            "REGRESSION DETECTED in check_availability!\n"
            "Bug: Booking datetime is being interpreted as UTC instead of instructor timezone.\n"
            "Fix location: booking_service.py check_availability method\n"
            "Required fix: Use instructor's timezone from profile.user.timezone"
        )

    def test_regression_celery_early_capture_bug(self, db):
        """
        Regression test for Part 11 Bug B.

        Bug: Celery task interpreted lesson end time as UTC
        Location: payment_tasks.py:645-646, 652-653 (before fix)
        Effect: 9pm EST lesson captured at 4pm EST (5 hours early)

        This test will FAIL if someone reintroduces the UTC bug.
        """
        from app.tasks.payment_tasks import capture_completed_lessons

        # Setup: Booking with lesson ending at 9pm EST
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_regression"
        booking.instructor_id = "instructor_regression"
        booking.payment_intent_id = "pi_regression"

        # Instructor in EST
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        # Lesson ended at 9pm EST Dec 24 (2am UTC Dec 25)
        booking.booking_date = date(2024, 12, 24)
        booking.end_time = time(21, 0)  # 9pm

        # Current time: 8pm EST Dec 25 = 1am UTC Dec 26
        # This is only 23 hours after 9pm EST (but would be 27 hours after 9pm UTC)
        mock_now = datetime(2024, 12, 26, 1, 0, 0, tzinfo=timezone.utc)  # 8pm EST Dec 25

        with patch("app.tasks.payment_tasks.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine  # Preserve real combine function

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

                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch("app.tasks.payment_tasks.StudentCreditService"):
                            result = capture_completed_lessons()

        # MUST NOT capture - if it does, the bug is back
        assert result["auto_completed"] == 0, (
            "REGRESSION DETECTED in capture_completed_lessons!\n"
            "Bug: Lesson end time is being interpreted as UTC instead of instructor timezone.\n"
            "Fix location: payment_tasks.py capture_completed_lessons function\n"
            "Required fix: Use booking.instructor.timezone to interpret lesson end time"
        )

    def test_regression_no_utc_in_check_availability(self):
        """
        Source code scan to ensure UTC is not used directly in check_availability.

        This test scans the actual source code to prevent the bug pattern
        from being reintroduced.
        """
        import inspect

        from app.services.booking_service import BookingService

        # Get the source code of check_availability
        source = inspect.getsource(BookingService.check_availability)

        # The bug pattern: datetime.combine(..., tzinfo=timezone.utc)
        # Should NOT appear in the min_advance_booking section
        lines = source.split("\n")

        bug_pattern_found = False
        for i, line in enumerate(lines):
            # Look for the specific bug pattern
            if "datetime.combine" in line and "timezone.utc" in line:
                # Check if this is in the min advance booking section
                # by looking at surrounding context
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 5)
                context = "\n".join(lines[context_start:context_end])

                if "min_advance" in context.lower() or "booking" in context.lower():
                    bug_pattern_found = True
                    break

        assert not bug_pattern_found, (
            "REGRESSION DETECTED! Found 'timezone.utc' in check_availability booking datetime.\n"
            "The booking datetime should use instructor's timezone, not UTC.\n"
            "Pattern to avoid: datetime.combine(date, time, tzinfo=timezone.utc)\n"
            "Correct pattern: datetime.combine(date, time, tzinfo=instructor_zone)"
        )

    def test_regression_no_utc_in_celery_capture_task(self):
        """
        Source code scan to ensure UTC is not used directly in capture_completed_lessons.

        This test scans the actual source code to prevent the bug pattern
        from being reintroduced.
        """
        import inspect

        from app.tasks.payment_tasks import capture_completed_lessons

        # Get the source code
        source = inspect.getsource(capture_completed_lessons)

        # The bug pattern: datetime.combine(..., tzinfo=timezone.utc) for lesson_end
        lines = source.split("\n")

        bug_pattern_found = False
        bug_line = ""
        for i, line in enumerate(lines):
            # Look for the specific bug pattern in lesson_end calculation
            if "datetime.combine" in line and "timezone.utc" in line:
                # Check if this is in the lesson_end section
                if "lesson" in line.lower() or "end" in line.lower():
                    bug_pattern_found = True
                    bug_line = line.strip()
                    break

                # Also check surrounding lines for context
                context_start = max(0, i - 3)
                context_end = min(len(lines), i + 3)
                context = "\n".join(lines[context_start:context_end])

                if "lesson_end" in context:
                    bug_pattern_found = True
                    bug_line = line.strip()
                    break

        assert not bug_pattern_found, (
            f"REGRESSION DETECTED! Found 'timezone.utc' in capture_completed_lessons.\n"
            f"Line: {bug_line}\n"
            "The lesson_end datetime should use instructor's timezone, not UTC.\n"
            "Pattern to avoid: datetime.combine(date, time, tzinfo=timezone.utc)\n"
            "Correct pattern: Get instructor timezone from booking.instructor.timezone"
        )
