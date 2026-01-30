# backend/tests/unit/services/test_conflict_checker_coverage_r5.py
"""
Round 5 Coverage Tests for ConflictChecker Service.

Target: Raise coverage from 86.36% to 92%+
Missed lines: 129-132, 186, 284, 363, 372->380, 376->380, 391, 399->408, 402->408, 446, 448, 484-498
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.repositories.conflict_checker_repository import ConflictCheckerRepository
from app.repositories.user_repository import UserRepository
from app.services.conflict_checker import ConflictChecker


class TestConflictCheckerCheckTimeConflicts:
    """Tests for check_time_conflicts method (Lines 129-132)."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        return svc

    def test_check_time_conflicts_returns_true_when_conflicts_exist(self, service):
        """Line 132: Returns True when there are conflicts."""
        # Create mock booking that will cause a conflict
        mock_booking = Mock(spec=Booking)
        mock_booking.id = generate_ulid()
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.student = Mock(first_name="John", last_name="Doe")
        mock_booking.service_name = "Test"
        mock_booking.status = BookingStatus.CONFIRMED

        service.repository.get_bookings_for_conflict_check.return_value = [mock_booking]

        # Check overlapping time - should return True
        result = service.check_time_conflicts(
            instructor_id=generate_ulid(),
            booking_date=date.today(),
            start_time=time(9, 30),
            end_time=time(10, 30),
        )

        assert result is True

    def test_check_time_conflicts_returns_false_when_no_conflicts(self, service):
        """Line 132: Returns False when no conflicts."""
        service.repository.get_bookings_for_conflict_check.return_value = []

        result = service.check_time_conflicts(
            instructor_id=generate_ulid(),
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        assert result is False

    def test_check_time_conflicts_with_exclude_booking_id(self, service):
        """Line 131: Test with exclude_booking_id parameter."""
        service.repository.get_bookings_for_conflict_check.return_value = []

        exclude_id = generate_ulid()
        result = service.check_time_conflicts(
            instructor_id=generate_ulid(),
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            exclude_booking_id=exclude_id,
        )

        assert result is False
        # Verify exclude_id was passed to repository
        call_args = service.repository.get_bookings_for_conflict_check.call_args
        assert call_args[0][2] == exclude_id


class TestConflictCheckerGetBookedTimesForWeek:
    """Tests for get_booked_times_for_week - skipping non-confirmed bookings (Line 186)."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        return svc

    def test_skips_cancelled_bookings(self, service):
        """Line 186: Cancelled bookings should be skipped in weekly view."""
        base_date = date(2024, 1, 15)  # Monday

        # Create bookings with different statuses
        mock_bookings = []

        # Confirmed booking - should be included
        confirmed_booking = Mock(spec=Booking)
        confirmed_booking.id = generate_ulid()
        confirmed_booking.booking_date = base_date
        confirmed_booking.start_time = time(10, 0)
        confirmed_booking.end_time = time(11, 0)
        confirmed_booking.student_id = generate_ulid()
        confirmed_booking.service_name = "Confirmed Service"
        confirmed_booking.status = BookingStatus.CONFIRMED
        mock_bookings.append(confirmed_booking)

        # Cancelled booking - should be skipped (Line 186)
        cancelled_booking = Mock(spec=Booking)
        cancelled_booking.id = generate_ulid()
        cancelled_booking.booking_date = base_date
        cancelled_booking.start_time = time(14, 0)
        cancelled_booking.end_time = time(15, 0)
        cancelled_booking.student_id = generate_ulid()
        cancelled_booking.service_name = "Cancelled Service"
        cancelled_booking.status = BookingStatus.CANCELLED
        mock_bookings.append(cancelled_booking)

        # Pending booking - should be skipped
        pending_booking = Mock(spec=Booking)
        pending_booking.id = generate_ulid()
        pending_booking.booking_date = base_date
        pending_booking.start_time = time(16, 0)
        pending_booking.end_time = time(17, 0)
        pending_booking.student_id = generate_ulid()
        pending_booking.service_name = "Pending Service"
        pending_booking.status = BookingStatus.PENDING
        mock_bookings.append(pending_booking)

        service.repository.get_bookings_for_week.return_value = mock_bookings

        result = service.get_booked_times_for_week(
            instructor_id=generate_ulid(),
            week_start=base_date,
        )

        # Only confirmed booking should be included
        assert len(result) == 1
        date_str = base_date.isoformat()
        assert date_str in result
        assert len(result[date_str]) == 1
        assert result[date_str][0]["service_name"] == "Confirmed Service"

    def test_skips_no_show_bookings(self, service):
        """Line 186: NO_SHOW bookings should be skipped."""
        base_date = date(2024, 1, 15)

        no_show_booking = Mock(spec=Booking)
        no_show_booking.id = generate_ulid()
        no_show_booking.booking_date = base_date
        no_show_booking.start_time = time(10, 0)
        no_show_booking.end_time = time(11, 0)
        no_show_booking.student_id = generate_ulid()
        no_show_booking.service_name = "No Show Service"
        no_show_booking.status = BookingStatus.NO_SHOW

        service.repository.get_bookings_for_week.return_value = [no_show_booking]

        result = service.get_booked_times_for_week(
            instructor_id=generate_ulid(),
            week_start=base_date,
        )

        # NO_SHOW booking should be skipped
        assert len(result) == 0


class TestConflictCheckerMinimumAdvanceBooking:
    """Tests for check_minimum_advance_booking - instructor not found (Line 284)."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        svc.user_repository = Mock(spec=UserRepository)
        return svc

    def test_instructor_not_found_returns_invalid(self, service):
        """Line 284: Returns invalid when instructor not found."""
        # Profile exists but instructor doesn't
        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 24
        service.repository.get_instructor_profile.return_value = mock_profile

        # Instructor NOT found
        service.user_repository.get_by_id.return_value = None

        result = service.check_minimum_advance_booking(
            instructor_id=generate_ulid(),
            booking_date=date.today() + timedelta(days=1),
            booking_time=time(10, 0),
        )

        assert result["valid"] is False
        assert "Instructor not found" in result["reason"]


class TestConflictCheckerValidateBookingConstraints:
    """Tests for validate_booking_constraints - various error paths."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        svc.user_repository = Mock(spec=UserRepository)
        return svc

    def _setup_basic_mocks(self, service, instructor_id):
        """Helper to set up basic mocks for validation tests."""
        mock_user = Mock()
        mock_user.id = instructor_id
        mock_user.timezone = "America/New_York"
        service.user_repository.get_by_id.return_value = mock_user

        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_blackout_date.return_value = None

        return mock_user

    @patch("app.services.conflict_checker.get_user_today_by_id")
    def test_time_validation_failure_adds_error(self, mock_get_today, service):
        """Line 363: Time validation failure adds error to list."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        # Invalid time range - end before start
        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(13, 0),  # End before start!
        )

        assert result["valid"] is False
        assert any("after start time" in error for error in result["errors"])

    @patch("app.services.conflict_checker.get_user_today_by_id")
    @patch("app.core.timezone_utils.get_user_now")
    def test_same_day_past_time_adds_error(self, mock_get_user_now, mock_get_today, service):
        """Lines 372->380, 376->380: Same-day booking with past time adds error."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        # Current time is 14:00
        import pytz
        ny_tz = pytz.timezone("America/New_York")
        current_time = ny_tz.localize(datetime.combine(today, time(14, 0)))
        mock_get_user_now.return_value = current_time

        # Try to book for 13:00 (in the past)
        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today,  # Same day
            start_time=time(13, 0),  # Before current time
            end_time=time(14, 0),
        )

        assert result["valid"] is False
        assert any("past time slots" in error for error in result["errors"])

    @patch("app.services.conflict_checker.get_user_today_by_id")
    @patch("app.core.timezone_utils.get_user_now")
    def test_conflicts_add_error(self, mock_get_user_now, mock_get_today, service):
        """Line 391: Conflicts add error to list."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        import pytz
        ny_tz = pytz.timezone("America/New_York")
        mock_get_user_now.return_value = ny_tz.localize(datetime.combine(today, time(8, 0)))

        # Create a conflicting booking
        mock_booking = Mock(spec=Booking)
        mock_booking.id = generate_ulid()
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.student = Mock(first_name="John", last_name="Doe")
        mock_booking.service_name = "Existing Booking"
        mock_booking.status = BookingStatus.CONFIRMED
        service.repository.get_bookings_for_conflict_check.return_value = [mock_booking]

        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today + timedelta(days=1),
            start_time=time(10, 30),  # Overlaps
            end_time=time(11, 30),
        )

        assert result["valid"] is False
        assert any("conflicts with" in error for error in result["errors"])

    @patch("app.services.conflict_checker.get_user_today_by_id")
    @patch("app.core.timezone_utils.get_user_now")
    def test_service_not_found_adds_error(self, mock_get_user_now, mock_get_today, service):
        """Lines 399->408: Service not found adds error."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        import pytz
        ny_tz = pytz.timezone("America/New_York")
        mock_get_user_now.return_value = ny_tz.localize(datetime.combine(today, time(8, 0)))

        # Service not found
        service.repository.get_active_service.return_value = None

        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_id=generate_ulid(),
        )

        assert result["valid"] is False
        assert any("not found or no longer available" in error for error in result["errors"])

    @patch("app.services.conflict_checker.get_user_today_by_id")
    @patch("app.core.timezone_utils.get_user_now")
    def test_service_duration_mismatch_adds_warning(self, mock_get_user_now, mock_get_today, service):
        """Lines 402->408: Service duration mismatch adds warning."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        import pytz
        ny_tz = pytz.timezone("America/New_York")
        mock_get_user_now.return_value = ny_tz.localize(datetime.combine(today, time(8, 0)))

        # Service with specific duration options
        mock_service = Mock(spec=Service)
        mock_service.duration_options = [60, 90, 120]  # Only these durations allowed
        service.repository.get_active_service.return_value = mock_service

        # Book for 45 minutes (not in duration_options)
        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(14, 45),  # 45 minutes - not in options
            service_id=generate_ulid(),
        )

        # Should be valid but with warning
        assert result["valid"] is True
        assert len(result["warnings"]) > 0
        assert any("[60, 90, 120] minutes" in warning for warning in result["warnings"])


class TestConflictCheckerFindNextAvailableTime:
    """Tests for find_next_available_time - default time bounds and after-all-bookings."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        return svc

    def _create_mock_booking(self, start: time, end: time) -> Mock:
        """Helper to create mock booking."""
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.start_time = start
        booking.end_time = end
        booking.status = BookingStatus.CONFIRMED
        return booking

    def test_default_earliest_time(self, service):
        """Line 446: Uses 9 AM as default earliest_time."""
        service.repository.get_bookings_for_date.return_value = []

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            # earliest_time not provided - should default to 9:00
        )

        assert result is not None
        assert result["start_time"] == "09:00:00"

    def test_default_latest_time(self, service):
        """Line 448: Uses 9 PM as default latest_time."""
        # Fill with bookings until 8 PM
        bookings = [
            self._create_mock_booking(time(9, 0), time(20, 0)),
        ]
        service.repository.get_bookings_for_date.return_value = bookings

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            # latest_time not provided - should default to 21:00
        )

        # Should find slot at 20:00-21:00
        assert result is not None
        assert result["start_time"] == "20:00:00"
        assert result["end_time"] == "21:00:00"

    def test_finds_slot_after_all_bookings(self, service):
        """Lines 484-498: Finds availability after all existing bookings."""
        # Create bookings that leave a gap at the end
        bookings = [
            self._create_mock_booking(time(9, 0), time(11, 0)),
            self._create_mock_booking(time(11, 0), time(13, 0)),
            self._create_mock_booking(time(14, 0), time(16, 0)),
        ]
        service.repository.get_bookings_for_date.return_value = bookings

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            earliest_time=time(9, 0),
            latest_time=time(18, 0),
        )

        # Should find slot at 13:00-14:00 (between second and third booking)
        assert result is not None
        assert result["start_time"] == "13:00:00"
        assert result["end_time"] == "14:00:00"

    def test_returns_none_when_no_slot_fits(self, service):
        """Lines 484-498: Returns None when no slot fits."""
        # Fill entire day
        bookings = [
            self._create_mock_booking(time(9, 0), time(21, 0)),
        ]
        service.repository.get_bookings_for_date.return_value = bookings

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            earliest_time=time(9, 0),
            latest_time=time(21, 0),
        )

        assert result is None

    def test_finds_slot_at_end_of_day(self, service):
        """Lines 484-498: Finds slot at end of day after last booking."""
        # Bookings leave slot at end of day
        bookings = [
            self._create_mock_booking(time(9, 0), time(12, 0)),
            self._create_mock_booking(time(14, 0), time(17, 0)),
        ]
        service.repository.get_bookings_for_date.return_value = bookings

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            earliest_time=time(9, 0),
            latest_time=time(18, 0),
        )

        # Should find slot at 12:00-13:00 (first available gap)
        assert result is not None
        assert result["start_time"] == "12:00:00"
        assert result["end_time"] == "13:00:00"

    def test_no_slot_when_duration_exceeds_latest_time(self, service):
        """Lines 490-498: Returns None when slot would exceed latest_time."""
        # Booking ends at 17:30, looking for 60 min slot with 18:00 latest
        bookings = [
            self._create_mock_booking(time(9, 0), time(17, 30)),
        ]
        service.repository.get_bookings_for_date.return_value = bookings

        result = service.find_next_available_time(
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
            earliest_time=time(9, 0),
            latest_time=time(18, 0),  # Only 30 min left, need 60
        )

        assert result is None


class TestGetBookedTimesForDate:
    """Tests for get_booked_times_for_date - Line 150-152."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        return svc

    def test_returns_confirmed_bookings(self, service):
        """Lines 150-152: Returns booked times for confirmed bookings."""
        mock_booking = Mock(spec=Booking)
        mock_booking.id = generate_ulid()
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.student_id = generate_ulid()
        mock_booking.service_name = "Test Service"
        mock_booking.status = BookingStatus.CONFIRMED

        service.repository.get_bookings_for_date.return_value = [mock_booking]

        result = service.get_booked_times_for_date(
            instructor_id=generate_ulid(),
            target_date=date.today(),
        )

        assert len(result) == 1
        assert result[0]["start_time"] == "10:00:00"
        assert result[0]["end_time"] == "11:00:00"
        assert result[0]["status"] == BookingStatus.CONFIRMED

    def test_filters_out_cancelled_bookings(self, service):
        """Lines 150-152: Filters out non-confirmed bookings."""
        confirmed = Mock(spec=Booking)
        confirmed.id = generate_ulid()
        confirmed.start_time = time(10, 0)
        confirmed.end_time = time(11, 0)
        confirmed.student_id = generate_ulid()
        confirmed.service_name = "Test"
        confirmed.status = BookingStatus.CONFIRMED

        cancelled = Mock(spec=Booking)
        cancelled.id = generate_ulid()
        cancelled.start_time = time(12, 0)
        cancelled.end_time = time(13, 0)
        cancelled.student_id = generate_ulid()
        cancelled.service_name = "Cancelled"
        cancelled.status = BookingStatus.CANCELLED

        service.repository.get_bookings_for_date.return_value = [confirmed, cancelled]

        result = service.get_booked_times_for_date(
            instructor_id=generate_ulid(),
            target_date=date.today(),
        )

        # Only confirmed booking should be returned
        assert len(result) == 1
        assert result[0]["status"] == BookingStatus.CONFIRMED


class TestGetBookedTimesForWeekCoverage:
    """Tests for get_booked_times_for_week - Lines 189->192."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        return svc

    def test_groups_bookings_by_date(self, service):
        """Lines 189->192: Groups bookings by date string."""
        week_start = date(2024, 1, 15)  # Monday

        # Create bookings on different days
        booking1 = Mock(spec=Booking)
        booking1.id = generate_ulid()
        booking1.booking_date = date(2024, 1, 15)  # Monday
        booking1.start_time = time(10, 0)
        booking1.end_time = time(11, 0)
        booking1.student_id = generate_ulid()
        booking1.service_name = "Service 1"
        booking1.status = BookingStatus.CONFIRMED

        booking2 = Mock(spec=Booking)
        booking2.id = generate_ulid()
        booking2.booking_date = date(2024, 1, 17)  # Wednesday
        booking2.start_time = time(14, 0)
        booking2.end_time = time(15, 0)
        booking2.student_id = generate_ulid()
        booking2.service_name = "Service 2"
        booking2.status = BookingStatus.COMPLETED

        service.repository.get_bookings_for_week.return_value = [booking1, booking2]

        result = service.get_booked_times_for_week(
            instructor_id=generate_ulid(),
            week_start=week_start,
        )

        # Should have 2 dates with bookings
        assert "2024-01-15" in result
        assert "2024-01-17" in result
        assert len(result["2024-01-15"]) == 1
        assert len(result["2024-01-17"]) == 1

    def test_multiple_bookings_same_date(self, service):
        """Lines 189->192: Multiple bookings grouped under same date."""
        week_start = date(2024, 1, 15)  # Monday

        # Two bookings on same day
        booking1 = Mock(spec=Booking)
        booking1.id = generate_ulid()
        booking1.booking_date = date(2024, 1, 15)
        booking1.start_time = time(10, 0)
        booking1.end_time = time(11, 0)
        booking1.student_id = generate_ulid()
        booking1.service_name = "Morning"
        booking1.status = BookingStatus.CONFIRMED

        booking2 = Mock(spec=Booking)
        booking2.id = generate_ulid()
        booking2.booking_date = date(2024, 1, 15)  # Same day
        booking2.start_time = time(14, 0)
        booking2.end_time = time(15, 0)
        booking2.student_id = generate_ulid()
        booking2.service_name = "Afternoon"
        booking2.status = BookingStatus.CONFIRMED

        service.repository.get_bookings_for_week.return_value = [booking1, booking2]

        result = service.get_booked_times_for_week(
            instructor_id=generate_ulid(),
            week_start=week_start,
        )

        assert "2024-01-15" in result
        assert len(result["2024-01-15"]) == 2


class TestValidateTimeRangeCoverage:
    """Tests for validate_time_range - Lines 244, 252."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        svc = ConflictChecker(mock_db)
        return svc

    def test_duration_below_minimum(self, service):
        """Line 244: Duration below minimum returns invalid."""
        result = service.validate_time_range(
            start_time=time(10, 0),
            end_time=time(10, 15),  # Only 15 minutes
            min_duration_minutes=30,  # Minimum 30 required
            max_duration_minutes=180,
        )

        assert result["valid"] is False
        assert "at least 30 minutes" in result["reason"]
        assert result["duration_minutes"] == 15

    def test_duration_above_maximum(self, service):
        """Line 252: Duration above maximum returns invalid."""
        result = service.validate_time_range(
            start_time=time(10, 0),
            end_time=time(14, 0),  # 4 hours = 240 minutes
            min_duration_minutes=30,
            max_duration_minutes=180,  # Maximum 180 (3 hours)
        )

        assert result["valid"] is False
        assert "cannot exceed 180 minutes" in result["reason"]
        assert result["duration_minutes"] == 240


class TestCheckMinimumAdvanceBookingCoverage:
    """Tests for check_minimum_advance_booking - Line 279."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repositories."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        svc.user_repository = Mock(spec=UserRepository)
        return svc

    def test_profile_not_found_returns_invalid(self, service):
        """Line 279: Profile not found returns invalid."""
        service.repository.get_instructor_profile.return_value = None

        result = service.check_minimum_advance_booking(
            instructor_id=generate_ulid(),
            booking_date=date.today() + timedelta(days=1),
            booking_time=time(10, 0),
        )

        assert result["valid"] is False
        assert "profile not found" in result["reason"]


class TestValidateBookingConstraintsCoverage:
    """Additional tests for validate_booking_constraints - Lines 368, 386."""

    @pytest.fixture
    def service(self):
        """Create ConflictChecker with mock repository."""
        mock_db = Mock(spec=Session)
        mock_repository = Mock(spec=ConflictCheckerRepository)
        svc = ConflictChecker(mock_db)
        svc.repository = mock_repository
        svc.user_repository = Mock(spec=UserRepository)
        return svc

    def _setup_basic_mocks(self, service, instructor_id):
        """Helper to set up basic mocks for validation tests."""
        mock_user = Mock()
        mock_user.id = instructor_id
        mock_user.timezone = "America/New_York"
        service.user_repository.get_by_id.return_value = mock_user

        mock_profile = Mock(spec=InstructorProfile)
        mock_profile.min_advance_booking_hours = 2
        service.repository.get_instructor_profile.return_value = mock_profile
        service.repository.get_bookings_for_conflict_check.return_value = []
        service.repository.get_blackout_date.return_value = None

    @patch("app.services.conflict_checker.get_user_today_by_id")
    def test_past_date_adds_error(self, mock_get_today, service):
        """Line 368: Past date adds error to list."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        # Try to book for yesterday
        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=date(2024, 1, 14),  # Yesterday
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        assert result["valid"] is False
        assert any("past dates" in error for error in result["errors"])

    @patch("app.services.conflict_checker.get_user_today_by_id")
    @patch("app.core.timezone_utils.get_user_now")
    def test_blackout_date_adds_error(self, mock_get_user_now, mock_get_today, service):
        """Line 386: Blackout date adds error to list."""
        instructor_id = generate_ulid()
        today = date(2024, 1, 15)
        mock_get_today.return_value = today

        self._setup_basic_mocks(service, instructor_id)

        import pytz
        ny_tz = pytz.timezone("America/New_York")
        mock_get_user_now.return_value = ny_tz.localize(datetime.combine(today, time(8, 0)))

        # Set up blackout date
        service.repository.get_blackout_date.return_value = Mock()  # Blackout exists

        result = service.validate_booking_constraints(
            instructor_id=instructor_id,
            booking_date=today + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        assert result["valid"] is False
        assert any("not available on this date" in error for error in result["errors"])
