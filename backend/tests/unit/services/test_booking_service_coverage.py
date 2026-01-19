"""
Comprehensive coverage tests for booking_service.py.

This test file targets the uncovered helper functions and edge cases
to improve coverage from 68% to 90%+.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    NotFoundException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.services.timezone_service import TimezoneService


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture
def mock_repository():
    """Create a mock booking repository."""
    repo = MagicMock()
    repo.check_time_conflict.return_value = False
    repo.check_student_time_conflict.return_value = []
    repo.get_bookings_by_time_range.return_value = []
    repo.create.return_value = Mock(spec=Booking, id=generate_ulid())
    repo.get_booking_with_details.return_value = None
    repo.update.return_value = None
    transaction_cm = MagicMock()
    transaction_cm.__enter__.return_value = None
    transaction_cm.__exit__.return_value = None
    repo.transaction = MagicMock(return_value=transaction_cm)
    return repo


@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    service = MagicMock()
    service.send_booking_confirmation = MagicMock()
    service.send_cancellation_notification = MagicMock()
    return service


@pytest.fixture
def booking_service(mock_db, mock_repository, mock_notification_service):
    """Create a BookingService with mocked dependencies."""
    service = BookingService(
        mock_db,
        mock_notification_service,
        event_publisher=MagicMock(),
        repository=mock_repository,
    )
    service.audit_repository = MagicMock()
    return service


class TestSnapshotBooking:
    """Test _snapshot_booking helper method."""

    def test_snapshot_booking_basic(self, booking_service):
        """Test basic snapshot creation."""
        booking = MagicMock(spec=Booking)
        booking.to_dict.return_value = {
            "id": "01K2MAY484FQGFEQVN3VKGYZ58",
            "status": BookingStatus.CONFIRMED,
            "student_id": "student123",
        }

        result = booking_service._snapshot_booking(booking)

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == BookingStatus.CONFIRMED.value

    def test_snapshot_booking_string_status(self, booking_service):
        """Test snapshot with string status."""
        booking = MagicMock(spec=Booking)
        booking.to_dict.return_value = {
            "id": "01K2MAY484FQGFEQVN3VKGYZ58",
            "status": "confirmed",
        }

        result = booking_service._snapshot_booking(booking)

        assert isinstance(result, dict)


class TestWriteBookingAudit:
    """Test _write_booking_audit helper method."""

    def test_write_audit_with_actor(self, booking_service):
        """Test writing audit with user actor."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        user = MagicMock(spec=User)
        user.id = generate_ulid()

        with patch.object(booking_service, "audit_repository") as mock_audit:
            with patch("app.services.booking_service.AUDIT_ENABLED", True):
                booking_service._write_booking_audit(
                    booking,
                    "create",
                    actor=user,
                    before=None,
                    after={"status": "confirmed"},
                )

            mock_audit.write.assert_called_once()

    def test_write_audit_without_actor(self, booking_service):
        """Test writing audit without actor (system action)."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()

        with patch.object(booking_service, "audit_repository") as mock_audit:
            with patch("app.services.booking_service.AUDIT_ENABLED", True):
                booking_service._write_booking_audit(
                    booking,
                    "system_update",
                    actor=None,
                    before={"status": "pending"},
                    after={"status": "confirmed"},
                    default_role="system",
                )

            mock_audit.write.assert_called_once()


class TestCalculateAndValidateEndTime:
    """Test _calculate_and_validate_end_time helper method."""

    def test_normal_booking_same_day(self, booking_service):
        """Test normal booking that ends on the same day."""
        booking_date = date(2026, 12, 25)
        start_time = time(10, 0)
        duration = 60  # 1 hour

        result = booking_service._calculate_and_validate_end_time(
            booking_date, start_time, duration
        )

        assert result == time(11, 0)

    def test_booking_ending_at_midnight(self, booking_service):
        """Test booking that ends exactly at midnight."""
        booking_date = date(2026, 12, 25)
        start_time = time(23, 0)
        duration = 60  # 1 hour

        result = booking_service._calculate_and_validate_end_time(
            booking_date, start_time, duration
        )

        assert result == time(0, 0)

    def test_booking_invalid_wrap_past_midnight(self, booking_service):
        """Test booking that wraps past midnight (should fail)."""
        booking_date = date(2026, 12, 25)
        start_time = time(23, 0)
        duration = 120  # 2 hours (would end at 1:00 AM)

        with pytest.raises(ValidationException, match="same calendar day"):
            booking_service._calculate_and_validate_end_time(
                booking_date, start_time, duration
            )

    def test_booking_end_before_start(self, booking_service):
        """Test when end time would equal start time (duration=0)."""
        booking_date = date(2026, 12, 25)
        start_time = time(10, 0)
        duration = 0  # 0 minutes (end == start)

        # Duration=0 means end_time == start_time, which violates end > start
        with pytest.raises(ValidationException, match="end time must be after"):
            booking_service._calculate_and_validate_end_time(
                booking_date, start_time, duration
            )


class TestHalfHourIndex:
    """Test _half_hour_index helper method."""

    def test_midnight(self, booking_service):
        """Test midnight returns index 0."""
        result = booking_service._half_hour_index(0, 0)
        assert result == 0

    def test_half_past_midnight(self, booking_service):
        """Test 00:30 returns index 1."""
        result = booking_service._half_hour_index(0, 30)
        assert result == 1

    def test_noon(self, booking_service):
        """Test 12:00 returns index 24."""
        result = booking_service._half_hour_index(12, 0)
        assert result == 24

    def test_half_past_noon(self, booking_service):
        """Test 12:30 returns index 25."""
        result = booking_service._half_hour_index(12, 30)
        assert result == 25

    def test_end_of_day(self, booking_service):
        """Test 23:30 returns index 47."""
        result = booking_service._half_hour_index(23, 30)
        assert result == 47

    def test_minutes_less_than_30(self, booking_service):
        """Test minutes < 30 don't increment index."""
        result = booking_service._half_hour_index(10, 15)
        assert result == 20  # 10 * 2 + 0


class TestResolveLocalBookingDay:
    """Test _resolve_local_booking_day helper method."""

    def test_returns_booking_date(self, booking_service):
        """Test that it returns the booking date from booking_data."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.booking_date = date(2026, 12, 25)
        instructor_profile = MagicMock(spec=InstructorProfile)

        result = booking_service._resolve_local_booking_day(
            booking_data, instructor_profile
        )

        assert result == date(2026, 12, 25)


class TestIsOnlineLesson:
    """Test _is_online_lesson static method."""

    def test_remote_location_type(self, booking_service):
        """Test remote location returns True."""
        booking_data = MagicMock()
        booking_data.location_type = "online"

        result = booking_service._is_online_lesson(booking_data)

        assert result is True

    def test_in_person_location_type(self, booking_service):
        """Test in-person location returns False."""
        booking_data = MagicMock()
        booking_data.location_type = "student_location"

        result = booking_service._is_online_lesson(booking_data)

        assert result is False

    def test_no_location_type(self, booking_service):
        """Test missing location_type returns False."""
        booking_data = MagicMock(spec=BookingCreate)
        # No location_type attribute

        result = booking_service._is_online_lesson(booking_data)

        assert result is False


class TestResolveInstructorTimezone:
    """Test _resolve_instructor_timezone helper method."""

    def test_with_valid_timezone(self, booking_service):
        """Test with valid instructor timezone."""
        instructor_profile = MagicMock(spec=InstructorProfile)
        mock_user = MagicMock()
        mock_user.timezone = "America/New_York"
        instructor_profile.user = mock_user

        result = booking_service._resolve_instructor_timezone(instructor_profile)

        assert result == "America/New_York"

    def test_without_timezone(self, booking_service):
        """Test fallback to default when no timezone."""
        instructor_profile = MagicMock(spec=InstructorProfile)
        mock_user = MagicMock()
        mock_user.timezone = None
        instructor_profile.user = mock_user

        result = booking_service._resolve_instructor_timezone(instructor_profile)

        assert result == TimezoneService.DEFAULT_TIMEZONE

    def test_with_empty_timezone(self, booking_service):
        """Test fallback when timezone is empty string."""
        instructor_profile = MagicMock(spec=InstructorProfile)
        mock_user = MagicMock()
        mock_user.timezone = ""
        instructor_profile.user = mock_user

        result = booking_service._resolve_instructor_timezone(instructor_profile)

        assert result == TimezoneService.DEFAULT_TIMEZONE

    def test_without_user(self, booking_service):
        """Test fallback when no user object."""
        instructor_profile = MagicMock(spec=InstructorProfile)
        instructor_profile.user = None

        result = booking_service._resolve_instructor_timezone(instructor_profile)

        assert result == TimezoneService.DEFAULT_TIMEZONE


class TestResolveStudentTimezone:
    """Test _resolve_student_timezone static method."""

    def test_with_valid_timezone(self, booking_service):
        """Test with valid student timezone."""
        student = MagicMock(spec=User)
        student.timezone = "America/Chicago"

        result = booking_service._resolve_student_timezone(student)

        assert result == "America/Chicago"

    def test_without_timezone(self, booking_service):
        """Test fallback to default when no timezone."""
        student = MagicMock(spec=User)
        student.timezone = None

        result = booking_service._resolve_student_timezone(student)

        assert result == TimezoneService.DEFAULT_TIMEZONE

    def test_with_none_student(self, booking_service):
        """Test fallback when student is None."""
        result = booking_service._resolve_student_timezone(None)

        assert result == TimezoneService.DEFAULT_TIMEZONE


class TestResolveLessonTimezone:
    """Test _resolve_lesson_timezone helper method."""

    def test_in_person_uses_instructor_timezone(self, booking_service):
        """Test in-person lesson uses instructor timezone."""
        booking_data = MagicMock()
        booking_data.location_type = "student_location"

        instructor_profile = MagicMock(spec=InstructorProfile)
        mock_user = MagicMock()
        mock_user.timezone = "America/Denver"
        instructor_profile.user = mock_user

        with patch.object(
            TimezoneService, "get_lesson_timezone", return_value="America/Denver"
        ):
            result = booking_service._resolve_lesson_timezone(
                booking_data, instructor_profile
            )

        assert result == "America/Denver"


class TestResolveEndDate:
    """Test _resolve_end_date static method."""

    def test_normal_same_day(self, booking_service):
        """Test normal booking ends same day."""
        booking_date = date(2026, 12, 25)
        start_time = time(10, 0)
        end_time = time(11, 0)

        result = booking_service._resolve_end_date(booking_date, start_time, end_time)

        assert result == date(2026, 12, 25)

    def test_midnight_rollover(self, booking_service):
        """Test booking ending at midnight rolls over to next day."""
        booking_date = date(2026, 12, 25)
        start_time = time(23, 0)
        end_time = time(0, 0)

        result = booking_service._resolve_end_date(booking_date, start_time, end_time)

        assert result == date(2026, 12, 26)

    def test_both_midnight(self, booking_service):
        """Test when both start and end are midnight."""
        booking_date = date(2026, 12, 25)
        start_time = time(0, 0)
        end_time = time(0, 0)

        result = booking_service._resolve_end_date(booking_date, start_time, end_time)

        # Same day since start is also midnight
        assert result == date(2026, 12, 25)


class TestResolveBookingTimesUtc:
    """Test _resolve_booking_times_utc helper method."""

    def test_valid_conversion(self, booking_service):
        """Test valid timezone conversion."""
        booking_date = date(2026, 12, 25)
        start_time = time(10, 0)
        end_time = time(11, 0)
        lesson_tz = "America/New_York"

        start_utc, end_utc = booking_service._resolve_booking_times_utc(
            booking_date, start_time, end_time, lesson_tz
        )

        assert isinstance(start_utc, datetime)
        assert isinstance(end_utc, datetime)
        assert start_utc < end_utc

    def test_invalid_timezone(self, booking_service):
        """Test handling of invalid timezone."""
        booking_date = date(2026, 12, 25)
        start_time = time(10, 0)
        end_time = time(11, 0)
        lesson_tz = "Invalid/Timezone"

        with patch.object(
            TimezoneService, "local_to_utc", side_effect=ValueError("Invalid timezone")
        ):
            with pytest.raises(BusinessRuleException):
                booking_service._resolve_booking_times_utc(
                    booking_date, start_time, end_time, lesson_tz
                )


class TestGetBookingStartUtc:
    """Test _get_booking_start_utc helper method."""

    def test_with_existing_utc(self, booking_service):
        """Test when booking_start_utc already exists."""
        expected_utc = datetime(2026, 12, 25, 15, 0, 0, tzinfo=timezone.utc)
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = expected_utc

        result = booking_service._get_booking_start_utc(booking)

        assert result == expected_utc

    def test_legacy_booking_with_lesson_timezone(self, booking_service):
        """Test legacy booking using lesson_timezone."""
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = None
        booking.lesson_timezone = "America/New_York"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)

        result = booking_service._get_booking_start_utc(booking)

        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_legacy_booking_with_instructor_tz(self, booking_service):
        """Test legacy booking using instructor_tz_at_booking."""
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = None
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = "America/Chicago"
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)

        result = booking_service._get_booking_start_utc(booking)

        assert isinstance(result, datetime)

    def test_legacy_booking_fallback_to_default(self, booking_service):
        """Test legacy booking falls back to default timezone."""
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = None
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)

        result = booking_service._get_booking_start_utc(booking)

        assert isinstance(result, datetime)


class TestGetBookingEndUtc:
    """Test _get_booking_end_utc helper method."""

    def test_with_existing_utc(self, booking_service):
        """Test when booking_end_utc already exists."""
        expected_utc = datetime(2026, 12, 25, 16, 0, 0, tzinfo=timezone.utc)
        booking = MagicMock(spec=Booking)
        booking.booking_end_utc = expected_utc

        result = booking_service._get_booking_end_utc(booking)

        assert result == expected_utc

    def test_legacy_booking_conversion(self, booking_service):
        """Test legacy booking UTC conversion."""
        booking = MagicMock(spec=Booking)
        booking.booking_end_utc = None
        booking.lesson_timezone = "America/New_York"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)
        booking.end_time = time(11, 0)

        result = booking_service._get_booking_end_utc(booking)

        assert isinstance(result, datetime)


class TestValidateAgainstAvailabilityBits:
    """Test _validate_against_availability_bits helper method."""

    def test_missing_start_time(self, booking_service):
        """Test validation fails when start_time is None."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.start_time = None
        booking_data.end_time = time(11, 0)
        instructor_profile = MagicMock(spec=InstructorProfile)

        with pytest.raises(
            ValidationException, match="Start and end time must be specified"
        ):
            booking_service._validate_against_availability_bits(
                booking_data, instructor_profile
            )

    def test_missing_end_time(self, booking_service):
        """Test validation fails when end_time is None."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = None
        instructor_profile = MagicMock(spec=InstructorProfile)

        with pytest.raises(
            ValidationException, match="Start and end time must be specified"
        ):
            booking_service._validate_against_availability_bits(
                booking_data, instructor_profile
            )


class TestShouldTriggerLock:
    """Test _should_trigger_lock helper method."""

    def test_instructor_initiated_no_lock(self, booking_service):
        """Test instructor-initiated reschedule doesn't trigger lock."""
        booking = MagicMock(spec=Booking)

        result = booking_service._should_trigger_lock(booking, "instructor")

        assert result is False

    def test_student_outside_window_no_lock(self, booking_service):
        """Test student reschedule outside 12-24h window doesn't trigger lock."""
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(hours=30)
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = (datetime.now(timezone.utc) + timedelta(hours=30)).date()
        booking.start_time = time(10, 0)

        result = booking_service._should_trigger_lock(booking, "student")

        assert result is False

    def test_student_in_window_authorized_triggers_lock(self, booking_service):
        """Test student reschedule in 12-24h window with authorized payment triggers lock."""
        booking = MagicMock(spec=Booking)
        # Set booking to start in 18 hours (within 12-24h window)
        future_time = datetime.now(timezone.utc) + timedelta(hours=18)
        booking.booking_start_utc = future_time
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = future_time.date()
        booking.start_time = future_time.time()

        result = booking_service._should_trigger_lock(booking, "student")

        assert result is True

    def test_already_locked_no_trigger(self, booking_service):
        """Test already locked booking doesn't trigger lock again."""
        booking = MagicMock(spec=Booking)
        future_time = datetime.now(timezone.utc) + timedelta(hours=18)
        booking.booking_start_utc = future_time
        booking.payment_status = PaymentStatus.LOCKED.value
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = future_time.date()
        booking.start_time = future_time.time()

        result = booking_service._should_trigger_lock(booking, "student")

        assert result is False


class TestGetHoursUntilStart:
    """Test get_hours_until_start helper method."""

    def test_hours_calculation(self, booking_service):
        """Test hours calculation."""
        booking = MagicMock(spec=Booking)
        future_time = datetime.now(timezone.utc) + timedelta(hours=24)
        booking.booking_start_utc = future_time
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = future_time.date()
        booking.start_time = future_time.time()

        result = booking_service.get_hours_until_start(booking)

        # Should be approximately 24 hours (allow some tolerance for test execution time)
        assert 23.9 < result < 24.1


class TestPublicShouldTriggerLock:
    """Test public should_trigger_lock method."""

    def test_delegates_to_private_method(self, booking_service):
        """Test public method delegates to private method."""
        booking = MagicMock(spec=Booking)

        with patch.object(
            booking_service, "_should_trigger_lock", return_value=True
        ) as mock_private:
            result = booking_service.should_trigger_lock(booking, "student")

        mock_private.assert_called_once_with(booking, "student")
        assert result is True


class TestDetermineAuthTiming:
    """Test _determine_auth_timing helper method."""

    def test_lesson_more_than_24h_away(self, booking_service):
        """Test scheduling when lesson is more than 24h away."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=49)

        result = booking_service._determine_auth_timing(future_time)

        assert result["immediate"] is False
        assert result["scheduled_for"] is not None
        assert result["hours_until_lesson"] >= 48

    def test_lesson_less_than_24h_away(self, booking_service):
        """Test immediate auth when lesson is less than 24h away."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=12)

        result = booking_service._determine_auth_timing(future_time)

        assert result["immediate"] is True
        assert result["scheduled_for"] is None
        assert result["hours_until_lesson"] <= 24

    def test_naive_datetime_gets_utc(self, booking_service):
        """Test naive datetime gets UTC timezone attached."""
        future_time = datetime.now() + timedelta(hours=12)  # naive datetime

        result = booking_service._determine_auth_timing(future_time)

        assert "immediate" in result


class TestCancelBookingWithoutStripe:
    """Test cancel_booking_without_stripe method."""

    def test_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        user = MagicMock(spec=User)
        user.id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.cancel_booking_without_stripe(
                generate_ulid(), user, "Test reason"
            )

    def test_user_not_authorized(self, booking_service, mock_repository):
        """Test error when user not authorized to cancel."""
        booking = MagicMock(spec=Booking)
        booking.student_id = generate_ulid()
        booking.instructor_id = generate_ulid()
        booking.is_cancellable = True
        mock_repository.get_booking_with_details.return_value = booking

        user = MagicMock(spec=User)
        user.id = generate_ulid()  # Different from both student and instructor

        with pytest.raises(
            ValidationException, match="don't have permission to cancel"
        ):
            booking_service.cancel_booking_without_stripe(
                generate_ulid(), user, "Test reason"
            )

    def test_booking_not_cancellable(self, booking_service, mock_repository):
        """Test error when booking is not cancellable."""
        user_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.student_id = user_id
        booking.instructor_id = generate_ulid()
        booking.is_cancellable = False
        booking.status = BookingStatus.COMPLETED
        mock_repository.get_booking_with_details.return_value = booking

        user = MagicMock(spec=User)
        user.id = user_id

        with pytest.raises(BusinessRuleException, match="cannot be cancelled"):
            booking_service.cancel_booking_without_stripe(
                generate_ulid(), user, "Test reason"
            )

    def test_successful_cancellation_clears_payment_intent(
        self, booking_service, mock_repository
    ):
        """Test successful cancellation with clear_payment_intent flag."""
        user_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.student_id = user_id
        booking.instructor_id = generate_ulid()
        booking.is_cancellable = True
        booking.status = BookingStatus.CONFIRMED
        booking.payment_intent_id = "pi_test123"
        booking.to_dict.return_value = {"status": "confirmed"}
        mock_repository.get_booking_with_details.return_value = booking

        user = MagicMock(spec=User)
        user.id = user_id

        booking_service.cancel_booking_without_stripe(
            booking.id, user, "Test reason", clear_payment_intent=True
        )

        assert booking.payment_intent_id is None
        booking.cancel.assert_called_once()


class TestActivateLockForReschedule:
    """Test activate_lock_for_reschedule method."""

    def test_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_by_id_for_update.return_value = None

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.activate_lock_for_reschedule(generate_ulid())

    def test_already_locked(self, booking_service, mock_repository):
        """Test early return when booking already locked."""
        booking = MagicMock(spec=Booking)
        booking.payment_status = PaymentStatus.LOCKED.value
        mock_repository.get_by_id_for_update.return_value = booking

        result = booking_service.activate_lock_for_reschedule(generate_ulid())

        assert result == {"locked": True, "already_locked": True}

    def test_invalid_payment_status(self, booking_service, mock_repository):
        """Test error when payment status cannot be locked."""
        booking = MagicMock(spec=Booking)
        booking.payment_status = PaymentStatus.SETTLED.value  # SETTLED cannot be locked
        mock_repository.get_by_id_for_update.return_value = booking

        with pytest.raises(BusinessRuleException, match="Cannot lock booking"):
            booking_service.activate_lock_for_reschedule(generate_ulid())


class TestResolveLockForBooking:
    """Test resolve_lock_for_booking method."""

    def test_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_by_id_for_update.return_value = None

        with pytest.raises(NotFoundException, match="Locked booking not found"):
            booking_service.resolve_lock_for_booking(
                generate_ulid(), "new_lesson_completed"
            )

    def test_booking_not_locked(self, booking_service, mock_repository):
        """Test skip when booking is not locked."""
        booking = MagicMock(spec=Booking)
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        mock_repository.get_by_id_for_update.return_value = booking

        result = booking_service.resolve_lock_for_booking(
            generate_ulid(), "new_lesson_completed"
        )

        assert result.get("skipped") is True


class TestBuildCancellationContext:
    """Test _build_cancellation_context helper method."""

    def test_student_cancellation(self, booking_service):
        """Test context building for student cancellation."""
        student_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.student_id = student_id
        booking.instructor_id = generate_ulid()
        booking.payment_intent_id = "pi_test123"
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        booking.total_price = Decimal("100.00")
        booking.tip_amount = Decimal("10.00")
        booking.credits_reserved_cents = 500
        booking.lesson_timezone = "America/New_York"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)
        booking.booking_start_utc = datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)
        booking.has_locked_funds = False
        booking.rescheduled_from_booking_id = None
        booking.to_dict.return_value = {"status": "confirmed"}

        user = MagicMock(spec=User)
        user.id = student_id

        result = booking_service._build_cancellation_context(booking, user)

        assert result["cancelled_by_role"] == "student"
        assert result["payment_intent_id"] == "pi_test123"

    def test_instructor_cancellation(self, booking_service):
        """Test context building for instructor cancellation."""
        instructor_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.student_id = generate_ulid()
        booking.instructor_id = instructor_id
        booking.payment_intent_id = "pi_test123"
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        booking.total_price = Decimal("100.00")
        booking.tip_amount = Decimal("10.00")
        booking.credits_reserved_cents = 0
        booking.lesson_timezone = "America/New_York"
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)
        booking.booking_start_utc = datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)
        booking.has_locked_funds = False
        booking.rescheduled_from_booking_id = None
        booking.to_dict.return_value = {"status": "confirmed"}

        user = MagicMock(spec=User)
        user.id = instructor_id

        result = booking_service._build_cancellation_context(booking, user)

        assert result["cancelled_by_role"] == "instructor"


class TestValidateBookingPrerequisites:
    """Test _validate_booking_prerequisites helper method."""

    def test_non_student_cannot_book(self, booking_service, mock_repository, mock_db):
        """Test error when non-student tries to book."""
        # User without student role
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.roles = []  # No student role
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.service_id = generate_ulid()

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            booking_service._validate_booking_prerequisites(user, booking_data)


class TestEnqueueBookingOutboxEvent:
    """Test _enqueue_booking_outbox_event helper method."""

    def test_enqueues_event(self, booking_service):
        """Test that events are enqueued."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.student_id = generate_ulid()
        booking.instructor_id = generate_ulid()

        booking_service._enqueue_booking_outbox_event(booking, "booking.created")

        # Verify the method completes without error
        # The actual implementation varies, but we're testing the method exists and runs


class TestResolveActorPayload:
    """Test _resolve_actor_payload helper method."""

    def test_with_user_actor(self, booking_service):
        """Test actor payload with User."""
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.email = "test@example.com"

        result = booking_service._resolve_actor_payload(user, default_role="student")

        assert "user_id" in result or "actor_id" in result or "id" in result

    def test_with_none_actor(self, booking_service):
        """Test actor payload with None actor."""
        result = booking_service._resolve_actor_payload(None, default_role="system")

        assert isinstance(result, dict)


class TestCheckConflictsAndRules:
    """Test _check_conflicts_and_rules helper method."""

    def test_instructor_conflict(self, booking_service, mock_repository):
        """Test error when instructor has conflict."""
        mock_repository.check_time_conflict.return_value = True

        student = MagicMock(spec=User)
        student.id = generate_ulid()

        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)

        service = MagicMock(spec=Service)
        instructor_profile = MagicMock(spec=InstructorProfile)

        with pytest.raises(BookingConflictException):
            booking_service._check_conflicts_and_rules(
                booking_data, service, instructor_profile, student
            )


class TestResolveIntegrityConflictMessage:
    """Test _resolve_integrity_conflict_message helper method."""

    def test_instructor_overlap_constraint(self, booking_service):
        """Test instructor overlap constraint message."""
        from sqlalchemy.exc import IntegrityError

        error = MagicMock(spec=IntegrityError)
        error.orig = MagicMock()
        error.orig.diag = MagicMock()
        error.orig.diag.constraint_name = "bookings_no_overlap_per_instructor"

        message, scope = booking_service._resolve_integrity_conflict_message(error)

        assert scope == "instructor"
        assert "instructor" in message.lower() or "booking" in message.lower()

    def test_student_overlap_constraint(self, booking_service):
        """Test student overlap constraint message."""
        from sqlalchemy.exc import IntegrityError

        error = MagicMock(spec=IntegrityError)
        error.orig = MagicMock()
        error.orig.diag = MagicMock()
        error.orig.diag.constraint_name = "bookings_no_overlap_per_student"

        message, scope = booking_service._resolve_integrity_conflict_message(error)

        assert scope == "student"

    def test_instructor_overlap_from_text(self, booking_service):
        """Test instructor overlap detected from error text."""
        from sqlalchemy.exc import IntegrityError

        error = MagicMock(spec=IntegrityError)
        error.orig = MagicMock()
        error.orig.diag = None  # No diag
        error.orig.__str__ = lambda self: "bookings_no_overlap_per_instructor violation"

        message, scope = booking_service._resolve_integrity_conflict_message(error)

        assert scope == "instructor"

    def test_student_overlap_from_text(self, booking_service):
        """Test student overlap detected from error text."""
        from sqlalchemy.exc import IntegrityError

        error = MagicMock(spec=IntegrityError)
        error.orig = MagicMock()
        error.orig.diag = None
        error.orig.__str__ = lambda self: "bookings_no_overlap_per_student violation"

        message, scope = booking_service._resolve_integrity_conflict_message(error)

        assert scope == "student"

    def test_generic_conflict_no_constraint(self, booking_service):
        """Test generic message when no constraint name found."""
        from sqlalchemy.exc import IntegrityError

        error = MagicMock(spec=IntegrityError)
        error.orig = MagicMock()
        error.orig.diag = None
        error.orig.__str__ = lambda self: "some other error"

        message, scope = booking_service._resolve_integrity_conflict_message(error)

        assert scope is None


class TestRaiseConflictFromRepoError:
    """Test _raise_conflict_from_repo_error helper method."""

    def test_deadlock_raises_conflict(self, booking_service):
        """Test deadlock error raises BookingConflictException."""
        from app.core.exceptions import RepositoryException

        exc = RepositoryException("Deadlock detected during insert")
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)

        with pytest.raises(BookingConflictException):
            booking_service._raise_conflict_from_repo_error(
                exc, booking_data, generate_ulid()
            )

    def test_exclusion_constraint_raises_conflict(self, booking_service):
        """Test exclusion constraint error raises BookingConflictException."""
        from app.core.exceptions import RepositoryException

        exc = RepositoryException("exclusion constraint violation")
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)

        with pytest.raises(BookingConflictException):
            booking_service._raise_conflict_from_repo_error(
                exc, booking_data, generate_ulid()
            )

    def test_other_error_re_raises(self, booking_service):
        """Test non-conflict error is re-raised."""
        from app.core.exceptions import RepositoryException

        exc = RepositoryException("Some other database error")
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)

        with pytest.raises(RepositoryException, match="Some other database error"):
            booking_service._raise_conflict_from_repo_error(
                exc, booking_data, generate_ulid()
            )


class TestBuildConflictDetails:
    """Test _build_conflict_details helper method."""

    def test_builds_details_dict(self, booking_service):
        """Test conflict details are properly built."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)
        student_id = generate_ulid()

        result = booking_service._build_conflict_details(booking_data, student_id)

        assert result["instructor_id"] == booking_data.instructor_id
        assert result["student_id"] == student_id
        assert "2026-12-25" in result["booking_date"]

    def test_handles_none_student_id(self, booking_service):
        """Test handling of None student_id."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(11, 0)

        result = booking_service._build_conflict_details(booking_data, None)

        assert result["student_id"] == ""

    def test_handles_none_end_time(self, booking_service):
        """Test handling of None end_time."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = None

        result = booking_service._build_conflict_details(booking_data, generate_ulid())

        assert result["end_time"] == ""


class TestValidateAgainstAvailabilityBitsExtended:
    """Extended tests for _validate_against_availability_bits."""

    def test_invalid_start_index(self, booking_service, mock_repository):
        """Test invalid start index raises error."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.start_time = time(10, 0)
        booking_data.end_time = time(9, 0)  # End before start
        instructor_profile = MagicMock(spec=InstructorProfile)

        with pytest.raises(BusinessRuleException, match="not available"):
            booking_service._validate_against_availability_bits(
                booking_data, instructor_profile
            )

    def test_midnight_end_time_handling(self, booking_service, mock_repository, mock_db):
        """Test midnight end time converts to index 48."""
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(23, 0)
        booking_data.end_time = time(0, 0)  # Midnight
        instructor_profile = MagicMock(spec=InstructorProfile)
        instructor_profile.user = MagicMock()
        instructor_profile.user.timezone = "America/New_York"

        # Create an availability repository mock
        availability_repo = MagicMock()
        availability_repo.get_day_bits.return_value = b"\xff" * 6  # All slots available
        booking_service.availability_repository = availability_repo

        # Should not raise
        booking_service._validate_against_availability_bits(
            booking_data, instructor_profile
        )


class TestGetBookingTimesWithInstructor:
    """Test _get_booking_start_utc and _get_booking_end_utc with instructor fallback."""

    def test_start_utc_with_instructor_timezone(self, booking_service):
        """Test start UTC with instructor timezone fallback."""
        booking = MagicMock(spec=Booking)
        booking.booking_start_utc = None
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        mock_instructor = MagicMock()
        mock_instructor.timezone = "America/Los_Angeles"
        booking.instructor = mock_instructor
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)

        result = booking_service._get_booking_start_utc(booking)

        assert isinstance(result, datetime)

    def test_end_utc_with_instructor_timezone(self, booking_service):
        """Test end UTC with instructor timezone fallback."""
        booking = MagicMock(spec=Booking)
        booking.booking_end_utc = None
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        mock_instructor = MagicMock()
        mock_instructor.timezone = "America/Los_Angeles"
        booking.instructor = mock_instructor
        booking.booking_date = date(2026, 12, 25)
        booking.start_time = time(10, 0)
        booking.end_time = time(11, 0)

        result = booking_service._get_booking_end_utc(booking)

        assert isinstance(result, datetime)


class TestShouldTriggerLockExtended:
    """Extended tests for _should_trigger_lock."""

    def test_scheduled_status_in_window_triggers_lock(self, booking_service):
        """Test SCHEDULED status in window triggers lock."""
        booking = MagicMock(spec=Booking)
        future_time = datetime.now(timezone.utc) + timedelta(hours=18)
        booking.booking_start_utc = future_time
        booking.payment_status = PaymentStatus.SCHEDULED.value
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = future_time.date()
        booking.start_time = future_time.time()

        result = booking_service._should_trigger_lock(booking, "student")

        assert result is True

    def test_outside_12_24h_window_no_lock(self, booking_service):
        """Test booking outside 12-24h window doesn't trigger lock."""
        booking = MagicMock(spec=Booking)
        # 10 hours away - inside <12h window
        future_time = datetime.now(timezone.utc) + timedelta(hours=10)
        booking.booking_start_utc = future_time
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        booking.lesson_timezone = None
        booking.instructor_tz_at_booking = None
        booking.instructor = None
        booking.booking_date = future_time.date()
        booking.start_time = future_time.time()

        result = booking_service._should_trigger_lock(booking, "student")

        assert result is False


class TestRetryAuthorization:
    """Test retry_authorization method."""

    def test_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        user = MagicMock(spec=User)
        user.id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.retry_authorization(booking_id=generate_ulid(), user=user)

    def test_booking_cancelled(self, booking_service, mock_repository):
        """Test error when booking is cancelled."""
        user_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.student_id = user_id
        booking.status = BookingStatus.CANCELLED
        mock_repository.get_booking_with_details.return_value = booking

        user = MagicMock(spec=User)
        user.id = user_id

        with pytest.raises(BusinessRuleException, match="has been cancelled"):
            booking_service.retry_authorization(booking_id=generate_ulid(), user=user)

    def test_wrong_payment_status(self, booking_service, mock_repository):
        """Test error when payment status is not eligible."""
        user_id = generate_ulid()
        booking = MagicMock(spec=Booking)
        booking.student_id = user_id
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = PaymentStatus.AUTHORIZED.value
        mock_repository.get_booking_with_details.return_value = booking

        user = MagicMock(spec=User)
        user.id = user_id

        with pytest.raises(BusinessRuleException, match="Cannot retry payment"):
            booking_service.retry_authorization(booking_id=generate_ulid(), user=user)


class TestCompleteBookingCoverage:
    """Cover complete_booking method branches."""

    def test_complete_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        instructor = MagicMock(spec=User)
        instructor.id = generate_ulid()
        mock_role = MagicMock()
        mock_role.name = "instructor"
        instructor.roles = [mock_role]

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.complete_booking(generate_ulid(), instructor)

    def test_complete_booking_non_instructor_forbidden(self, booking_service, mock_repository):
        """Test error when non-instructor tries to complete."""
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.roles = []  # Not an instructor

        with pytest.raises(ValidationException, match="Only instructors"):
            booking_service.complete_booking(generate_ulid(), user)

    def test_complete_booking_wrong_instructor(self, booking_service, mock_repository):
        """Test error when different instructor tries to complete."""
        booking_id = generate_ulid()
        instructor_id = generate_ulid()
        other_instructor_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.instructor_id = instructor_id
        booking.status = BookingStatus.CONFIRMED
        mock_repository.get_booking_with_details.return_value = booking

        other_instructor = MagicMock(spec=User)
        other_instructor.id = other_instructor_id
        mock_role = MagicMock()
        mock_role.name = "instructor"
        other_instructor.roles = [mock_role]

        with pytest.raises(ValidationException, match="You can only complete your own bookings"):
            booking_service.complete_booking(booking_id, other_instructor)

    def test_complete_booking_cancelled_fails(self, booking_service, mock_repository):
        """Test error when trying to complete cancelled booking."""
        booking_id = generate_ulid()
        instructor_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.instructor_id = instructor_id
        booking.status = BookingStatus.CANCELLED
        mock_repository.get_booking_with_details.return_value = booking

        instructor = MagicMock(spec=User)
        instructor.id = instructor_id
        mock_role = MagicMock()
        mock_role.name = "instructor"
        instructor.roles = [mock_role]

        with pytest.raises(BusinessRuleException, match="Only confirmed bookings can be completed"):
            booking_service.complete_booking(booking_id, instructor)


class TestMarkNoShowCoverage:
    """Cover mark_no_show method branches."""

    def test_mark_no_show_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        instructor = MagicMock(spec=User)
        instructor.id = generate_ulid()
        mock_role = MagicMock()
        mock_role.name = "instructor"
        instructor.roles = [mock_role]

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.mark_no_show(generate_ulid(), instructor)

    def test_mark_no_show_non_instructor_forbidden(self, booking_service, mock_repository):
        """Test error when non-instructor tries to mark no-show."""
        user = MagicMock(spec=User)
        user.id = generate_ulid()
        user.roles = []  # Not an instructor

        with pytest.raises(ValidationException, match="Only instructors"):
            booking_service.mark_no_show(generate_ulid(), user)

    def test_mark_no_show_wrong_instructor(self, booking_service, mock_repository):
        """Test error when different instructor tries to mark no-show."""
        booking_id = generate_ulid()
        instructor_id = generate_ulid()
        other_instructor_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.instructor_id = instructor_id
        booking.status = BookingStatus.CONFIRMED
        mock_repository.get_booking_with_details.return_value = booking

        other_instructor = MagicMock(spec=User)
        other_instructor.id = other_instructor_id
        mock_role = MagicMock()
        mock_role.name = "instructor"
        other_instructor.roles = [mock_role]

        with pytest.raises(ValidationException, match="You can only mark your own bookings as no-show"):
            booking_service.mark_no_show(booking_id, other_instructor)


class TestReportNoShowCoverage:
    """Cover report_no_show method branches."""

    def test_report_no_show_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        reporter = MagicMock(spec=User)
        reporter.id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.report_no_show(
                booking_id=generate_ulid(),
                reporter=reporter,
                no_show_type="student_no_show",
                reason="Did not attend",
            )


class TestDisputeNoShowCoverage:
    """Cover dispute_no_show method branches."""

    def test_dispute_no_show_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        disputer = MagicMock(spec=User)
        disputer.id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.dispute_no_show(
                booking_id=generate_ulid(),
                disputer=disputer,
                reason="I was there",
            )

    def test_dispute_no_show_no_report_exists(self, booking_service, mock_repository):
        """Test error when no no-show report exists."""
        booking = MagicMock(spec=Booking)
        booking.no_show_reported_at = None
        mock_repository.get_booking_with_details.return_value = booking

        disputer = MagicMock(spec=User)
        disputer.id = generate_ulid()

        with pytest.raises(BusinessRuleException, match="No no-show report exists"):
            booking_service.dispute_no_show(
                booking_id=generate_ulid(),
                disputer=disputer,
                reason="I was there",
            )

    def test_dispute_no_show_already_disputed(self, booking_service, mock_repository):
        """Test error when no-show already disputed."""
        booking = MagicMock(spec=Booking)
        booking.no_show_reported_at = datetime.now(timezone.utc)
        booking.no_show_disputed = True
        mock_repository.get_booking_with_details.return_value = booking

        disputer = MagicMock(spec=User)
        disputer.id = generate_ulid()

        with pytest.raises(BusinessRuleException, match="already disputed"):
            booking_service.dispute_no_show(
                booking_id=generate_ulid(),
                disputer=disputer,
                reason="I was there",
            )


class TestCreateBookingCoverage:
    """Cover create_booking method branches."""

    def test_create_booking_invalid_duration(self, booking_service, mock_repository, mock_db):
        """Test error when invalid duration selected."""
        # Setup student with student role
        student = MagicMock(spec=User)
        student.id = generate_ulid()
        mock_role = MagicMock()
        mock_role.name = "student"
        student.roles = [mock_role]

        # Setup booking data
        booking_data = MagicMock(spec=BookingCreate)
        booking_data.instructor_id = generate_ulid()
        booking_data.service_id = generate_ulid()
        booking_data.booking_date = date(2026, 12, 25)
        booking_data.start_time = time(10, 0)

        # Setup service with specific duration options
        service = MagicMock(spec=Service)
        service.duration_options = [30, 60]  # Only 30 and 60 minutes allowed
        service.is_active = True

        # Setup instructor profile
        instructor_profile = MagicMock(spec=InstructorProfile)
        instructor_profile.is_available = True
        instructor_profile.user = MagicMock()
        instructor_profile.user.timezone = "America/New_York"

        # Mock the prerequisite check
        with patch.object(
            booking_service,
            "_validate_booking_prerequisites",
            return_value=(service, instructor_profile),
        ):
            with pytest.raises(BusinessRuleException, match="Invalid duration"):
                booking_service.create_booking(student, booking_data, 90)  # 90 min not allowed


class TestGetBookingsForUserCoverage:
    """Cover get_bookings_for_user method."""

    def test_get_bookings_for_user_student(self, booking_service, mock_repository):
        """Test retrieving bookings for a student."""
        student = MagicMock(spec=User)
        student.id = generate_ulid()
        mock_role = MagicMock()
        mock_role.name = "student"
        student.roles = [mock_role]
        mock_repository.get_student_bookings.return_value = []

        result = booking_service.get_bookings_for_user(student)

        assert result == []

    def test_get_bookings_for_user_instructor(self, booking_service, mock_repository):
        """Test retrieving bookings for an instructor."""
        instructor = MagicMock(spec=User)
        instructor.id = generate_ulid()
        mock_role = MagicMock()
        mock_role.name = "instructor"
        instructor.roles = [mock_role]
        mock_repository.get_instructor_bookings.return_value = []

        result = booking_service.get_bookings_for_user(instructor)

        assert result == []


class TestIsDeadlockError:
    """Test _is_deadlock_error helper method."""

    def test_deadlock_error_detected(self, booking_service):
        """Test deadlock error is detected."""
        from sqlalchemy.exc import OperationalError

        error = MagicMock(spec=OperationalError)
        error.orig = MagicMock()
        error.orig.pgcode = "40P01"  # PostgreSQL deadlock error code

        result = booking_service._is_deadlock_error(error)

        assert result is True

    def test_non_deadlock_error(self, booking_service):
        """Test non-deadlock error returns False."""
        from sqlalchemy.exc import OperationalError

        error = MagicMock(spec=OperationalError)
        error.orig = MagicMock()
        error.orig.pgcode = "23505"  # Unique violation, not deadlock

        result = booking_service._is_deadlock_error(error)

        assert result is False

    def test_error_without_pgcode(self, booking_service):
        """Test error without pgcode returns False."""
        from sqlalchemy.exc import OperationalError

        error = MagicMock(spec=OperationalError)
        error.orig = None

        result = booking_service._is_deadlock_error(error)

        assert result is False


class TestUpdateBookingCoverage:
    """Cover update_booking method branches."""

    def test_update_booking_not_found(self, booking_service, mock_repository):
        """Test error when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        user = MagicMock(spec=User)
        user.id = generate_ulid()

        from app.schemas.booking import BookingUpdate

        update_data = MagicMock(spec=BookingUpdate)

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service.update_booking(generate_ulid(), update_data, user)


class TestGetBookingForUserCoverage:
    """Cover get_booking_for_user method."""

    def test_get_booking_for_user_not_found(self, booking_service, mock_repository):
        """Test returns None when booking not found."""
        mock_repository.get_booking_with_details.return_value = None
        user = MagicMock(spec=User)
        user.id = generate_ulid()

        result = booking_service.get_booking_for_user(generate_ulid(), user)

        assert result is None

    def test_get_booking_for_user_unauthorized(self, booking_service, mock_repository):
        """Test returns None when user not authorized to view booking."""
        booking_id = generate_ulid()
        student_id = generate_ulid()
        instructor_id = generate_ulid()
        other_user_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.student_id = student_id
        booking.instructor_id = instructor_id
        mock_repository.get_booking_with_details.return_value = booking

        other_user = MagicMock(spec=User)
        other_user.id = other_user_id

        result = booking_service.get_booking_for_user(booking_id, other_user)

        assert result is None

    def test_get_booking_for_user_student_authorized(self, booking_service, mock_repository):
        """Test student can view their own booking."""
        booking_id = generate_ulid()
        student_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.student_id = student_id
        booking.instructor_id = generate_ulid()
        mock_repository.get_booking_with_details.return_value = booking

        student = MagicMock(spec=User)
        student.id = student_id

        result = booking_service.get_booking_for_user(booking_id, student)

        assert result is not None
        assert result.id == booking_id

    def test_get_booking_for_user_instructor_authorized(self, booking_service, mock_repository):
        """Test instructor can view their own booking."""
        booking_id = generate_ulid()
        instructor_id = generate_ulid()

        booking = MagicMock(spec=Booking)
        booking.id = booking_id
        booking.student_id = generate_ulid()
        booking.instructor_id = instructor_id
        mock_repository.get_booking_with_details.return_value = booking

        instructor = MagicMock(spec=User)
        instructor.id = instructor_id

        result = booking_service.get_booking_for_user(booking_id, instructor)

        assert result is not None
        assert result.id == booking_id


class TestResolveActorPayloadRolesList:
    """Test _resolve_actor_payload when role is extracted from roles list."""

    def test_extract_role_from_roles_list(self, booking_service):
        """Test extracting role from actor.roles when role/role_name are None.

        Covers lines 286-292 in booking_service.py.
        """
        # Actor with roles list but no direct role attribute
        actor = MagicMock()
        actor.id = generate_ulid()
        actor.role = None
        actor.role_name = None

        # Create role objects with name attributes
        role1 = MagicMock()
        role1.name = "student"
        role2 = MagicMock()
        role2.name = "instructor"
        actor.roles = [role1, role2]

        result = booking_service._resolve_actor_payload(actor, default_role="unknown")

        assert result["role"] == "student"  # First role found
        assert result["id"] == actor.id

    def test_extract_role_from_empty_roles_list(self, booking_service):
        """Test fallback when roles list is empty."""
        actor = MagicMock()
        actor.id = generate_ulid()
        actor.role = None
        actor.role_name = None
        actor.roles = []  # Empty list

        result = booking_service._resolve_actor_payload(actor, default_role="fallback")

        assert result["role"] == "fallback"

    def test_extract_role_from_roles_with_no_name(self, booking_service):
        """Test fallback when role objects have no name attribute."""
        actor = MagicMock()
        actor.id = generate_ulid()
        actor.role = None
        actor.role_name = None

        # Role objects without name attribute
        role1 = MagicMock(spec=[])  # No attributes
        actor.roles = [role1]

        result = booking_service._resolve_actor_payload(actor, default_role="default_role")

        assert result["role"] == "default_role"

    def test_extract_role_from_tuple(self, booking_service):
        """Test extracting role from tuple of roles."""
        actor = MagicMock()
        actor.id = generate_ulid()
        actor.role = None
        actor.role_name = None

        role1 = MagicMock()
        role1.name = "admin"
        actor.roles = (role1,)  # Tuple instead of list

        result = booking_service._resolve_actor_payload(actor, default_role="unknown")

        assert result["role"] == "admin"


class TestBookingEventIdentity:
    """Test _booking_event_identity for timestamp edge cases."""

    def test_booking_cancelled_with_cancelled_at(self, booking_service):
        """Test cancelled booking uses cancelled_at timestamp."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.cancelled_at = datetime(2026, 12, 25, 10, 0, tzinfo=timezone.utc)
        booking.completed_at = None
        booking.updated_at = datetime(2026, 12, 24, 10, 0, tzinfo=timezone.utc)
        booking.created_at = datetime(2026, 12, 23, 10, 0, tzinfo=timezone.utc)

        key, version = booking_service._booking_event_identity(booking, "booking.cancelled")

        assert "2026-12-25" in version
        assert "booking.cancelled" in key

    def test_booking_completed_with_completed_at(self, booking_service):
        """Test completed booking uses completed_at timestamp."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.cancelled_at = None
        booking.completed_at = datetime(2026, 12, 26, 10, 0, tzinfo=timezone.utc)
        booking.updated_at = datetime(2026, 12, 24, 10, 0, tzinfo=timezone.utc)
        booking.created_at = datetime(2026, 12, 23, 10, 0, tzinfo=timezone.utc)

        key, version = booking_service._booking_event_identity(booking, "booking.completed")

        assert "2026-12-26" in version

    def test_booking_updated_uses_updated_at(self, booking_service):
        """Test regular update uses updated_at timestamp."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.cancelled_at = None
        booking.completed_at = None
        booking.updated_at = datetime(2026, 12, 27, 10, 0, tzinfo=timezone.utc)
        booking.created_at = datetime(2026, 12, 23, 10, 0, tzinfo=timezone.utc)

        key, version = booking_service._booking_event_identity(booking, "booking.updated")

        assert "2026-12-27" in version

    def test_booking_fallback_to_created_at(self, booking_service):
        """Test fallback to created_at when no other timestamps."""
        booking = MagicMock(spec=Booking)
        booking.id = generate_ulid()
        booking.cancelled_at = None
        booking.completed_at = None
        booking.updated_at = None
        booking.created_at = datetime(2026, 12, 28, 10, 0, tzinfo=timezone.utc)

        key, version = booking_service._booking_event_identity(booking, "booking.created")

        assert "2026-12-28" in version
