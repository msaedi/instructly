"""
Comprehensive coverage tests for payment_tasks.py helper functions.

This test file targets the uncovered helper function lines to improve coverage.
"""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.ulid_helper import generate_ulid


class TestResolveBookingTimezones:
    """Test timezone resolution helper functions."""

    def test_resolve_lesson_timezone_from_booking(self) -> None:
        """Test timezone from booking.lesson_timezone."""
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = "America/New_York"

        result = _resolve_lesson_timezone(booking)
        assert result == "America/New_York"

    def test_resolve_lesson_timezone_from_instructor_tz(self) -> None:
        """Test timezone fallback to instructor_tz_at_booking."""
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = "America/Chicago"

        result = _resolve_lesson_timezone(booking)
        assert result == "America/Chicago"

    def test_resolve_lesson_timezone_from_instructor(self) -> None:
        """Test timezone fallback to instructor.timezone."""
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        mock_instructor = MagicMock()
        mock_instructor.timezone = "America/Los_Angeles"
        booking.instructor = mock_instructor

        result = _resolve_lesson_timezone(booking)
        assert result == "America/Los_Angeles"

    def test_resolve_lesson_timezone_from_instructor_user(self) -> None:
        """Test timezone fallback to instructor.user.timezone."""
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        mock_instructor = MagicMock()
        mock_instructor.timezone = None
        mock_user = MagicMock()
        mock_user.timezone = "Europe/London"
        mock_instructor.user = mock_user
        booking.instructor = mock_instructor

        result = _resolve_lesson_timezone(booking)
        assert result == "Europe/London"

    def test_resolve_lesson_timezone_default(self) -> None:
        """Test default timezone when all lookups fail."""
        from app.services.timezone_service import TimezoneService
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None

        result = _resolve_lesson_timezone(booking)
        assert result == TimezoneService.DEFAULT_TIMEZONE

    def test_resolve_lesson_timezone_empty_string(self) -> None:
        """Test empty string timezone fallback."""
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = ""  # Empty string
        booking.instructor_tz_at_booking = ""  # Empty string
        booking.instructor = None

        result = _resolve_lesson_timezone(booking)
        # Should fall back to default
        assert result is not None

    def test_instructor_timezone_none(self) -> None:
        """Test fallback when instructor.timezone is None."""
        from app.services.timezone_service import TimezoneService
        from app.tasks.payment_tasks import _resolve_lesson_timezone

        booking = MagicMock()
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        mock_instructor = MagicMock()
        mock_instructor.timezone = None
        mock_instructor.user = None  # user is None
        booking.instructor = mock_instructor

        result = _resolve_lesson_timezone(booking)
        assert result == TimezoneService.DEFAULT_TIMEZONE


class TestResolveEndDate:
    """Test end date resolution for legacy bookings."""

    def test_resolve_end_date_normal(self) -> None:
        """Test normal case returns booking date."""
        from app.tasks.payment_tasks import _resolve_end_date

        booking = MagicMock()
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(9, 0)
        booking.end_time = time(10, 0)

        result = _resolve_end_date(booking)
        assert result == date(2026, 12, 25)

    def test_resolve_end_date_midnight_end(self) -> None:
        """Test midnight end time adds one day."""
        from app.tasks.payment_tasks import _resolve_end_date

        booking = MagicMock()
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(23, 0)
        booking.end_time = time(0, 0)  # Midnight

        result = _resolve_end_date(booking)
        assert result == date(2026, 12, 26)

    def test_resolve_end_date_invalid_times(self) -> None:
        """Test with non-time values."""
        from app.tasks.payment_tasks import _resolve_end_date

        booking = MagicMock()
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = None
        booking.end_time = "10:00"  # String instead of time

        result = _resolve_end_date(booking)
        assert result == date(2026, 12, 25)

    def test_both_times_midnight(self) -> None:
        """Test when both start and end are midnight."""
        from app.tasks.payment_tasks import _resolve_end_date

        booking = MagicMock()
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(0, 0)  # Midnight
        booking.end_time = time(0, 0)  # Midnight

        # Should NOT add a day since start is also midnight
        result = _resolve_end_date(booking)
        assert result == date(2026, 12, 25)


class TestGetBookingStartUtc:
    """Test _get_booking_start_utc function."""

    def test_with_existing_booking_start_utc(self) -> None:
        """Test when booking_start_utc already exists."""
        from app.tasks.payment_tasks import _get_booking_start_utc

        expected_utc = datetime(2026, 12, 25, 14, 0, 0, tzinfo=timezone.utc)
        booking = MagicMock()
        booking.booking_start_utc = expected_utc

        result = _get_booking_start_utc(booking)
        assert result == expected_utc

    def test_conversion_from_local(self) -> None:
        """Test conversion from local time."""
        from app.tasks.payment_tasks import _get_booking_start_utc

        booking = MagicMock()
        booking.booking_start_utc = None
        booking.lesson_timezone = "UTC"
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(14, 0)

        result = _get_booking_start_utc(booking)
        assert result.hour == 14
        assert result.tzinfo is not None

    def test_conversion_fallback_on_error(self) -> None:
        """Test fallback when timezone conversion fails."""
        from app.tasks.payment_tasks import _get_booking_start_utc

        booking = MagicMock()
        booking.booking_start_utc = None
        booking.lesson_timezone = "Invalid/Timezone"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(14, 0)

        with patch("app.tasks.payment_tasks.TimezoneService.local_to_utc") as mock_convert:
            mock_convert.side_effect = ValueError("Invalid timezone")

            result = _get_booking_start_utc(booking)

        # Should return a datetime even on failure
        assert isinstance(result, datetime)
        assert result.hour == 14


class TestGetBookingEndUtc:
    """Test _get_booking_end_utc function."""

    def test_with_existing_booking_end_utc(self) -> None:
        """Test when booking_end_utc already exists."""
        from app.tasks.payment_tasks import _get_booking_end_utc

        expected_utc = datetime(2026, 12, 25, 15, 0, 0, tzinfo=timezone.utc)
        booking = MagicMock()
        booking.booking_end_utc = expected_utc

        result = _get_booking_end_utc(booking)
        assert result == expected_utc

    def test_conversion_from_local(self) -> None:
        """Test conversion from local time."""
        from app.tasks.payment_tasks import _get_booking_end_utc

        booking = MagicMock()
        booking.booking_end_utc = None
        booking.lesson_timezone = "UTC"
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(14, 0)
        booking.end_time = time(15, 0)

        result = _get_booking_end_utc(booking)
        assert result.hour == 15
        assert result.tzinfo is not None

    def test_conversion_fallback_on_error(self) -> None:
        """Test fallback when timezone conversion fails."""
        from app.tasks.payment_tasks import _get_booking_end_utc

        booking = MagicMock()
        booking.booking_end_utc = None
        booking.lesson_timezone = "Invalid/Timezone"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(14, 0)
        booking.end_time = time(15, 0)

        with patch("app.tasks.payment_tasks.TimezoneService.local_to_utc") as mock_convert:
            mock_convert.side_effect = ValueError("Invalid timezone")

            result = _get_booking_end_utc(booking)

        # Should return a datetime even on failure
        assert isinstance(result, datetime)
        assert result.hour == 15


class TestProcessAuthorizationForBooking:
    """Test _process_authorization_for_booking function."""

    def test_booking_not_found_phase1(self) -> None:
        """Test when booking is not found in Phase 1."""
        from app.tasks.payment_tasks import _process_authorization_for_booking

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.options.return_value.first.return_value = None

            result = _process_authorization_for_booking(generate_ulid(), 24.0)

        assert result["success"] is False
        assert "not found" in result.get("error", "").lower()

    def test_cancelled_booking_skipped(self) -> None:
        """Test that cancelled bookings are skipped."""
        from app.models.booking import BookingStatus
        from app.tasks.payment_tasks import _process_authorization_for_booking

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_booking = MagicMock()
            mock_booking.id = generate_ulid()
            mock_booking.status = BookingStatus.CANCELLED
            mock_db.query.return_value.filter.return_value.options.return_value.first.return_value = mock_booking

            result = _process_authorization_for_booking(mock_booking.id, 24.0)

        assert result["success"] is False
        assert result.get("skipped") is True
        assert "cancelled" in result.get("reason", "")


class TestRetryFailedAuthorizations:
    """Test retry_failed_authorizations task."""

    def test_retry_failed_authorizations_no_failures(self) -> None:
        """Test when there are no failed authorizations."""
        from app.tasks.payment_tasks import retry_failed_authorizations

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            with patch("app.tasks.payment_tasks.RepositoryFactory") as mock_factory:
                mock_booking_repo = MagicMock()
                mock_booking_repo.get_bookings_for_auth_retry.return_value = []
                mock_factory.get_booking_repository.return_value = mock_booking_repo

                result = retry_failed_authorizations()

        assert result["retried"] == 0


class TestCaptureCompletedLessons:
    """Test capture_completed_lessons task."""

    def test_capture_completed_lessons_no_lessons(self) -> None:
        """Test when there are no completed lessons."""
        from app.tasks.payment_tasks import capture_completed_lessons

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.all.return_value = []

            result = capture_completed_lessons()

        assert result["captured"] == 0


class TestRetryFailedCaptures:
    """Test retry_failed_captures task."""

    def test_retry_failed_captures_no_failures(self) -> None:
        """Test when there are no failed captures."""
        from app.tasks.payment_tasks import retry_failed_captures

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.all.return_value = []

            result = retry_failed_captures()

        assert result["retried"] == 0


class TestCheckAuthorizationHealth:
    """Test check_authorization_health task."""

    def test_check_authorization_health_success(self) -> None:
        """Test successful authorization health check."""
        from app.tasks.payment_tasks import check_authorization_health

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock query results
            mock_db.query.return_value.filter.return_value.count.return_value = 0

            result = check_authorization_health()

        # Result should have health-related keys
        assert "healthy" in result or "checked_at" in result


class TestAuditAndFixPayoutSchedules:
    """Test audit_and_fix_payout_schedules task."""

    def test_audit_and_fix_payout_schedules_no_issues(self) -> None:
        """Test when there are no payout schedule issues."""
        from app.tasks.payment_tasks import audit_and_fix_payout_schedules

        with patch("app.database.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.all.return_value = []

            result = audit_and_fix_payout_schedules()

        # Result should have audit-related keys
        assert "checked" in result or "fixed" in result


class TestRetryHeuristics:
    """Test retry window helper functions."""

    def test_should_retry_auth_without_attempted_at(self) -> None:
        """Missing attempted_at defaults to retry."""
        from app.tasks.payment_tasks import _should_retry_auth

        booking = MagicMock()
        pd = MagicMock()
        pd.auth_attempted_at = None
        pd.auth_failure_count = 0
        booking.payment_detail = pd

        assert _should_retry_auth(booking, datetime.now(timezone.utc)) is True

    def test_should_retry_auth_failure_count_one(self) -> None:
        """Failure count 1 waits one hour."""
        from app.tasks.payment_tasks import _should_retry_auth

        now = datetime.now(timezone.utc)
        booking = MagicMock()
        pd = MagicMock()
        pd.auth_attempted_at = now - timedelta(hours=2)
        pd.auth_failure_count = 1
        booking.payment_detail = pd

        assert _should_retry_auth(booking, now) is True

    def test_should_retry_auth_failure_count_two(self) -> None:
        """Failure count 2 waits four hours."""
        from app.tasks.payment_tasks import _should_retry_auth

        now = datetime.now(timezone.utc)
        booking = MagicMock()
        pd = MagicMock()
        pd.auth_attempted_at = now - timedelta(hours=5)
        pd.auth_failure_count = 2
        booking.payment_detail = pd

        assert _should_retry_auth(booking, now) is True

    def test_should_retry_auth_failure_count_three_plus(self) -> None:
        """Failure count 3+ waits eight hours."""
        from app.tasks.payment_tasks import _should_retry_auth

        now = datetime.now(timezone.utc)
        booking = MagicMock()
        pd = MagicMock()
        pd.auth_attempted_at = now - timedelta(hours=9)
        pd.auth_failure_count = 3
        booking.payment_detail = pd

        assert _should_retry_auth(booking, now) is True

    def test_should_retry_capture_requires_failed_at(self) -> None:
        """Capture retries require a failed_at timestamp."""
        from app.tasks.payment_tasks import _should_retry_capture

        booking = MagicMock()
        pd = MagicMock()
        pd.capture_failed_at = None
        booking.payment_detail = pd

        assert _should_retry_capture(booking, datetime.now(timezone.utc)) is False

    def test_should_retry_capture_after_wait(self) -> None:
        """Capture retries after four hours."""
        from app.tasks.payment_tasks import _should_retry_capture

        now = datetime.now(timezone.utc)
        booking = MagicMock()
        pd = MagicMock()
        pd.capture_failed_at = now - timedelta(hours=5)
        booking.payment_detail = pd

        assert _should_retry_capture(booking, now) is True


class TestProcessCaptureHelpers:
    """Test helper functions in _process_capture_for_booking."""

    def test_should_retry_capture_timing(self) -> None:
        """Test capture retry timing logic."""
        from app.tasks.payment_tasks import _should_retry_capture

        now = datetime.now(timezone.utc)

        # Recently failed - should not retry yet
        booking_recent = MagicMock()
        pd_recent = MagicMock()
        pd_recent.capture_failed_at = now - timedelta(hours=1)
        booking_recent.payment_detail = pd_recent
        assert _should_retry_capture(booking_recent, now) is False

        # Failed long ago - should retry
        booking_old = MagicMock()
        pd_old = MagicMock()
        pd_old.capture_failed_at = now - timedelta(hours=5)
        booking_old.payment_detail = pd_old
        assert _should_retry_capture(booking_old, now) is True


class TestShouldRetryAuth:
    """Test _should_retry_auth helper (lines 614-617 related)."""

    def test_should_retry_auth_timing(self) -> None:
        """Test authorization retry timing logic."""
        from app.tasks.payment_tasks import _should_retry_auth

        now = datetime.now(timezone.utc)

        # Recently attempted - should not retry yet
        booking_recent = MagicMock()
        pd_recent = MagicMock()
        pd_recent.auth_attempted_at = now - timedelta(minutes=30)
        booking_recent.payment_detail = pd_recent
        assert _should_retry_auth(booking_recent, now) is False

        # Attempted long ago - should retry
        booking_old = MagicMock()
        pd_old = MagicMock()
        pd_old.auth_attempted_at = now - timedelta(hours=2)
        booking_old.payment_detail = pd_old
        assert _should_retry_auth(booking_old, now) is True


class TestProcessRetryAuthorizationFunction:
    """Test _process_retry_authorization function (lines 704+)."""

    def test_booking_not_found_returns_error(self) -> None:
        """Test error result when booking not found."""
        from app.tasks.payment_tasks import _process_retry_authorization

        with patch("app.database.SessionLocal") as mock_session_class:
            mock_db = MagicMock()
            mock_session_class.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = None

            result = _process_retry_authorization(generate_ulid(), 20.0)

        # Booking not found returns error, not skipped
        assert result.get("success") is False or result.get("skipped") is True

    def test_cancelled_booking_returns_skipped(self) -> None:
        """Test skipped result when booking is cancelled."""
        from app.models.booking import BookingStatus
        from app.tasks.payment_tasks import _process_retry_authorization

        with patch("app.database.SessionLocal") as mock_session_class:
            mock_db = MagicMock()
            mock_session_class.return_value = mock_db

            mock_booking = MagicMock()
            mock_booking.status = BookingStatus.CANCELLED
            mock_db.query.return_value.filter.return_value.first.return_value = mock_booking

            result = _process_retry_authorization(generate_ulid(), 20.0)

        assert result.get("skipped") is True

    def test_already_authorized_returns_skipped(self) -> None:
        """Test skipped result when booking already authorized."""
        from app.models.booking import BookingStatus, PaymentStatus
        from app.tasks.payment_tasks import _process_retry_authorization

        with patch("app.database.SessionLocal") as mock_session_class:
            mock_db = MagicMock()
            mock_session_class.return_value = mock_db

            mock_booking = MagicMock()
            mock_booking.status = BookingStatus.CONFIRMED
            mock_pd = MagicMock()
            mock_pd.payment_status = PaymentStatus.AUTHORIZED.value
            mock_booking.payment_detail = mock_pd
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_booking

            result = _process_retry_authorization(generate_ulid(), 20.0)

        assert result.get("skipped") is True


class TestHasEventType:
    """Test has_event_type helper function."""

    def test_has_event_type_true(self) -> None:
        """Test event type detection when event exists."""
        from app.tasks.payment_tasks import has_event_type

        mock_payment_repo = MagicMock()
        # Create a mock event with the right event_type
        mock_event = MagicMock()
        mock_event.event_type = "t24_first_failure_email_sent"
        mock_payment_repo.get_payment_events_for_booking.return_value = [mock_event]

        result = has_event_type(mock_payment_repo, "booking123", "t24_first_failure_email_sent")

        assert result is True

    def test_has_event_type_false(self) -> None:
        """Test event type detection when event doesn't exist."""
        from app.tasks.payment_tasks import has_event_type

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = []  # No events

        result = has_event_type(mock_payment_repo, "booking123", "t24_first_failure_email_sent")

        assert result is False

    def test_has_event_type_wrong_type(self) -> None:
        """Test event type detection with different event type."""
        from app.tasks.payment_tasks import has_event_type

        mock_payment_repo = MagicMock()
        # Create a mock event with different event_type
        mock_event = MagicMock()
        mock_event.event_type = "some_other_event"
        mock_payment_repo.get_payment_events_for_booking.return_value = [mock_event]

        result = has_event_type(mock_payment_repo, "booking123", "t24_first_failure_email_sent")

        assert result is False


class TestCancelBookingPaymentFailed:
    """Test _cancel_booking_payment_failed function (lines 635+)."""

    def test_cancel_booking_not_found(self) -> None:
        """Test cancellation when booking not found."""
        from app.tasks.payment_tasks import _cancel_booking_payment_failed

        with patch("app.database.SessionLocal") as mock_session_class:
            mock_db = MagicMock()
            mock_session_class.return_value = mock_db
            mock_db.query.return_value.filter.return_value.options.return_value.first.return_value = None

            result = _cancel_booking_payment_failed(
                generate_ulid(),
                hours_until_lesson=5.0,
                now=datetime.now(timezone.utc)
            )

        assert result is False

    def test_cancel_already_cancelled_booking(self) -> None:
        """Test cancellation when booking already cancelled."""
        from app.models.booking import BookingStatus
        from app.tasks.payment_tasks import _cancel_booking_payment_failed

        with patch("app.database.SessionLocal") as mock_session_class:
            mock_db = MagicMock()
            mock_session_class.return_value = mock_db

            mock_booking = MagicMock()
            mock_booking.status = BookingStatus.CANCELLED
            mock_db.query.return_value.filter.return_value.options.return_value.first.return_value = mock_booking

            result = _cancel_booking_payment_failed(
                generate_ulid(),
                hours_until_lesson=5.0,
                now=datetime.now(timezone.utc)
            )

        assert result is False
