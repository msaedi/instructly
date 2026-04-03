"""
Coverage-gap tests targeting uncovered lines in:
- detail_query_mixin.py  (lines 23, 27-32, 156, 177-180)
- status_mutation_mixin.py  (lines 135, 148-152)
- booking_repository.py  (lines 58, 64, 68-69)
- availability_rules.py  (lines 59-60, 145->150, 192-198, 239-240)
- database_safety.py  (lines 21-22, 28, 52)
- bitmap_base64.py  (line 16)
"""

from __future__ import annotations

import base64
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    BusinessRuleException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from app.utils.bitmap_base64 import decode_bitmap_bytes
from app.utils.database_safety import (
    check_hosted_database,
    get_database_hostname,
    is_hosted_database_hostname,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    mock_db = Mock()
    mock_db.query = Mock()
    mock_db.flush = Mock()
    mock_db.commit = Mock()
    mock_db.rollback = Mock()
    mock_db.begin_nested = Mock()
    return mock_db


@pytest.fixture
def booking_repo(db):
    from app.repositories.booking_repository import BookingRepository

    repo = BookingRepository(db)
    return repo


@pytest.fixture
def booking_service(db):
    from app.services.booking_service import BookingService

    svc = BookingService(db)
    return svc


# ===========================================================================
# database_safety.py
# ===========================================================================


class TestGetDatabaseHostname:
    def test_malformed_url_returns_empty(self):
        """Line 21-22: unparseable URL triggers the except branch and returns ''."""
        result = get_database_hostname("://\x00not-a-url")
        assert result == ""

    def test_none_like_url_returns_empty(self):
        """Another path exercising the except branch."""
        # Passing an object that causes urlparse to blow up
        result = get_database_hostname(None)  # type: ignore[arg-type]
        assert result == ""


class TestIsHostedDatabaseHostname:
    def test_empty_string_returns_false(self):
        """Line 28: empty hostname returns False."""
        assert is_hosted_database_hostname("") is False

    def test_none_returns_false(self):
        """Line 28: None coerced to empty string returns False."""
        assert is_hosted_database_hostname(None) is False  # type: ignore[arg-type]

    def test_whitespace_only_returns_false(self):
        """Line 28: whitespace-only hostname returns False."""
        assert is_hosted_database_hostname("   ") is False


class TestCheckHostedDatabase:
    def test_non_prod_non_int_non_stg_env_returns_silently(self):
        """Line 52: env='dev' with hosted URL returns without error."""
        # Should not raise; covers the `if env != 'prod': return` branch
        check_hosted_database("dev", "postgresql://user:pw@db.supabase.com:5432/test")

    def test_non_hosted_url_returns_silently(self):
        """Non-hosted URL returns early at line 39 (not is_hosted)."""
        check_hosted_database("prod", "postgresql://user:pw@localhost:5432/test")

    def test_int_with_hosted_raises_system_exit(self):
        """env=int with hosted URL raises SystemExit."""
        with pytest.raises(SystemExit, match="misconfiguration"):
            check_hosted_database("int", "postgresql://user:pw@db.supabase.com:5432/test")

    def test_stg_with_hosted_logs_warning(self):
        """env=stg with hosted URL logs warning and returns."""
        with patch("app.utils.database_safety.log_warn") as mock_warn:
            check_hosted_database("stg", "postgresql://user:pw@db.supabase.com:5432/test")
            mock_warn.assert_called_once()


# ===========================================================================
# bitmap_base64.py
# ===========================================================================


class TestDecodeBitmapBytes:
    def test_wrong_decoded_length_raises_value_error(self):
        """Line 16: valid base64 but wrong length raises ValueError."""
        valid_data = base64.b64encode(b"\x00" * 10).decode("ascii")
        with pytest.raises(ValueError, match="decoded bitmap length must be 36"):
            decode_bitmap_bytes(valid_data, expected_length=36)

    def test_correct_length_succeeds(self):
        """Baseline: correct length succeeds."""
        data = b"\xff" * 36
        encoded = base64.b64encode(data).decode("ascii")
        result = decode_bitmap_bytes(encoded, expected_length=36)
        assert result == data


# ===========================================================================
# detail_query_mixin.py
# ===========================================================================


class TestDetailQueryMixinGetByIds:
    def test_empty_ids_returns_empty_list(self, booking_repo):
        """Line 23: empty ids list triggers early return []."""
        result = booking_repo.get_by_ids([])
        assert result == []

    def test_all_falsy_ids_returns_empty_list(self, booking_repo):
        """Line 23: all-falsy ids filtered down to empty triggers early return."""
        result = booking_repo.get_by_ids(["", "", ""])
        assert result == []

    def test_query_exception_raises_repository_exception(self, booking_repo, db):
        """Lines 27-32: exception during query raises RepositoryException."""
        db.query.side_effect = RuntimeError("DB failure")
        with pytest.raises(RepositoryException, match="Failed to retrieve Booking list"):
            booking_repo.get_by_ids(["01AAAAAAAAAAAAAAAAAAAAAAAA"])


class TestDetailQueryMixinGetBookingForParticipantForUpdate:
    def test_savepoint_rollback_on_existing_active_savepoint(self, booking_repo, db):
        """Line 156: existing active savepoint gets rolled back before creating new one."""
        existing_savepoint = MagicMock()
        existing_savepoint.is_active = True
        booking_repo._external_call_lock_savepoint = existing_savepoint

        # Make the query succeed and return None
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.first.return_value = None
        db.query.return_value = mock_query
        db.begin_nested.return_value = MagicMock()

        result = booking_repo.get_booking_for_participant_for_update(
            booking_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
            user_id="01BBBBBBBBBBBBBBBBBBBBBBBB",
            lock_scope_for_external_call=True,
            load_relationships=False,
            populate_existing=False,
        )
        assert result is None
        existing_savepoint.rollback.assert_called_once()

    def test_exception_with_lock_scope_rolls_back_savepoint(self, booking_repo, db):
        """Lines 177-180: exception with lock_scope_for_external_call rolls back savepoint."""
        savepoint = MagicMock()
        savepoint.is_active = True
        db.begin_nested.return_value = savepoint
        booking_repo._external_call_lock_savepoint = None

        # Make query blow up after savepoint is created
        db.query.side_effect = RuntimeError("Query blew up")

        with pytest.raises(RepositoryException, match="Failed to get booking for participant"):
            booking_repo.get_booking_for_participant_for_update(
                booking_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
                user_id="01BBBBBBBBBBBBBBBBBBBBBBBB",
                lock_scope_for_external_call=True,
            )
        savepoint.rollback.assert_called_once()


# ===========================================================================
# status_mutation_mixin.py
# ===========================================================================


class TestStatusMutationMixinMarkPaymentFailed:
    def test_booking_not_found_raises_not_found(self, booking_repo, db):
        """Line 135: booking not found raises NotFoundException."""
        # BaseRepository.get_by_id returns None
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.first.return_value = None
        db.query.return_value = mock_query

        with pytest.raises(NotFoundException, match="not found"):
            booking_repo.mark_payment_failed("01NONEXISTENT0000000000000")

    def test_unexpected_error_raises_repository_exception(self, booking_repo, db):
        """Lines 148-152: unexpected error during mark_payment_failed raises RepositoryException."""
        # Make get_by_id succeed but mark_payment_failed blow up
        mock_booking = MagicMock()
        mock_booking.id = "01AAAAAAAAAAAAAAAAAAAAAAAA"
        mock_booking.student_id = "01BBBBBBBBBBBBBBBBBBBBBBBB"
        mock_booking.instructor_id = "01CCCCCCCCCCCCCCCCCCCCCCCC"
        mock_booking.mark_payment_failed.side_effect = RuntimeError("Unexpected")

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.first.return_value = mock_booking
        db.query.return_value = mock_query

        with pytest.raises(RepositoryException, match="Failed to mark booking as payment failed"):
            booking_repo.mark_payment_failed("01AAAAAAAAAAAAAAAAAAAAAAAA")


class TestStatusMutationMixinGetNoShowReportsDueForResolution:
    def test_query_error_raises_repository_exception(self, booking_repo, db):
        """Lines 178-180 (status_mutation_mixin): exception raises RepositoryException."""
        db.query.side_effect = RuntimeError("DB error")

        with pytest.raises(RepositoryException, match="Failed to load no-show reports"):
            booking_repo.get_no_show_reports_due_for_resolution(
                reported_before=datetime(2025, 1, 1)
            )


# ===========================================================================
# booking_repository.py
# ===========================================================================


class TestBookingRepositoryCreate:
    def test_integrity_error_is_unwrapped(self, db):
        """Line 57-58: RepositoryException wrapping IntegrityError unwraps to IntegrityError."""
        from app.repositories.booking_repository import BookingRepository

        repo = BookingRepository(db)
        integrity_err = IntegrityError("dup", params={}, orig=Exception("conflict"))
        repo_err = RepositoryException("Integrity constraint violated")
        repo_err.__cause__ = integrity_err

        # Patch the parent class create to raise RepositoryException wrapping IntegrityError
        with patch(
            "app.repositories.base_repository.BaseRepository.create",
            side_effect=repo_err,
        ):
            with pytest.raises(IntegrityError):
                repo.create(id="01AAAAAAAAAAAAAAAAAAAAAAAA")

    def test_non_integrity_repo_exception_is_re_raised(self, db):
        """Line 58: RepositoryException without IntegrityError cause is re-raised as-is."""
        from app.repositories.booking_repository import BookingRepository

        repo = BookingRepository(db)
        repo_err = RepositoryException("Some other error")
        repo_err.__cause__ = RuntimeError("not integrity")

        with patch(
            "app.repositories.base_repository.BaseRepository.create",
            side_effect=repo_err,
        ):
            with pytest.raises(RepositoryException, match="Some other error"):
                repo.create(id="01AAAAAAAAAAAAAAAAAAAAAAAA")


class TestBookingRepositoryAdvisoryLock:
    def test_no_get_bind_returns_silently(self, booking_repo, db):
        """Line 64: get_bind not callable returns early."""
        # db has no get_bind attribute by default from Mock, but let's be explicit
        del db.get_bind  # remove if auto-created by Mock
        booking_repo.acquire_transaction_advisory_lock(12345)
        # No exception = success

    def test_get_bind_raises_returns_silently(self, db):
        """Lines 68-69: get_bind() raises -> returns silently."""
        from app.repositories.booking_repository import BookingRepository

        repo = BookingRepository(db)
        db.get_bind = MagicMock(side_effect=RuntimeError("no bind"))

        # Should not raise
        repo.acquire_transaction_advisory_lock(12345)


# ===========================================================================
# availability_rules.py
# ===========================================================================


class TestAvailabilityRulesFormatAdvanceNotice:
    def test_non_hour_aligned_minutes(self, booking_service):
        """Lines 59-60: minutes not divisible by 60 returns minute-based string."""
        result = booking_service._format_advance_notice(45)
        assert result == "45 minutes"

    def test_single_minute(self, booking_service):
        """Lines 59-60: singular 'minute' when minutes=1."""
        result = booking_service._format_advance_notice(1)
        assert result == "1 minute"


class TestAvailabilityRulesServiceAreaForAvailabilityCheck:
    def test_neutral_location_not_using_service_area_returns_early(self, booking_service):
        """Lines 144-146 (145->150 branch): neutral_location with offers_at_location returns early."""
        service = SimpleNamespace(
            offers_at_location=True,
            offers_travel=False,
        )
        # Should return without calling is_location_in_service_area
        booking_service._validate_service_area_for_availability_check(
            instructor_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
            service=service,
            location_type="neutral_location",
            location_lat=40.75,
            location_lng=-73.99,
        )

    def test_non_travel_location_type_returns_early(self, booking_service):
        """Lines 147-148: non-student/non-neutral location type returns early."""
        service = SimpleNamespace(offers_at_location=True, offers_travel=False)
        booking_service._validate_service_area_for_availability_check(
            instructor_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
            service=service,
            location_type="online",
            location_lat=40.75,
            location_lng=-73.99,
        )

    def test_missing_coordinates_returns_early(self, booking_service):
        """Lines 150-151: missing coordinates returns early without raising."""
        service = SimpleNamespace(offers_at_location=False, offers_travel=True)
        booking_service._validate_service_area_for_availability_check(
            instructor_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
            service=service,
            location_type="neutral_location",
            location_lat=None,
            location_lng=None,
        )


class TestAvailabilityRulesValidateSelectedDuration:
    def test_duration_not_in_options_raises(self, booking_service):
        """Lines 187-190: selected_duration not in duration_options raises ValidationException."""
        service = SimpleNamespace(duration_options=[30, 60])
        with pytest.raises(ValidationException, match="Invalid duration"):
            booking_service._validate_selected_duration_for_service(
                service=service,
                booking_date=date(2025, 6, 1),
                start_time=time(9, 0),
                end_time=time(9, 45),
                selected_duration=45,
            )

    def test_calculated_end_time_mismatch_raises(self, booking_service):
        """Lines 192-198: duration matches options but calculated end_time differs."""
        service = SimpleNamespace(duration_options=[30, 60])

        # Mock the helper that calculates end time
        booking_service._calculate_and_validate_end_time = MagicMock(
            return_value=time(10, 0)
        )
        booking_service._validate_min_session_duration_floor = MagicMock()

        with pytest.raises(ValidationException, match="does not match the requested time range"):
            booking_service._validate_selected_duration_for_service(
                service=service,
                booking_date=date(2025, 6, 1),
                start_time=time(9, 0),
                end_time=time(9, 30),  # Doesn't match calculated 10:00
                selected_duration=60,
            )

    def test_none_duration_returns_early(self, booking_service):
        """Lines 175-176: selected_duration=None returns immediately."""
        service = SimpleNamespace(duration_options=[30, 60])
        # Should not raise
        booking_service._validate_selected_duration_for_service(
            service=service,
            booking_date=date(2025, 6, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),
            selected_duration=None,
        )


class TestAvailabilityRulesValidateLocationCapability:
    def test_format_for_booking_raises_business_rule_converts_to_validation(
        self, booking_service
    ):
        """Lines 239-240: BusinessRuleException from format_for_booking_location_type
        is caught and re-raised as ValidationException.
        """
        service = SimpleNamespace(
            offers_travel=True,
            offers_at_location=True,
            offers_online=True,
        )
        service.format_for_booking_location_type = MagicMock(
            side_effect=BusinessRuleException("no pricing for that format")
        )

        with pytest.raises(ValidationException) as exc_info:
            booking_service._validate_location_capability(service, "online")

        assert exc_info.value.code == "LOCATION_TYPE_PRICING_NOT_FOUND"


class TestOvernightProtection:
    def test_protection_disabled_returns_early(self, booking_service):
        """Line 71: overnight_protection_enabled=False returns early."""
        profile = SimpleNamespace(overnight_protection_enabled=False)
        booking_service.config_service = MagicMock()

        # Should not raise
        booking_service._check_overnight_protection(
            booking_time_local=datetime(2025, 6, 1, 23, 30),
            lesson_start_local=datetime(2025, 6, 2, 5, 0),
            location_type="online",
            instructor_profile=profile,
        )

    def test_booking_outside_overnight_window_returns_early(self, booking_service):
        """Line 82: booking hour is not in overnight window -> early return."""
        profile = SimpleNamespace(overnight_protection_enabled=True)
        mock_config = MagicMock()
        mock_config.get_overnight_window_hours.return_value = (22, 7)
        mock_config.get_overnight_earliest_hour.return_value = 7
        booking_service.config_service = mock_config

        # Booking at 15:00 - not in overnight window (not >= 22 and not < 7)
        booking_service._check_overnight_protection(
            booking_time_local=datetime(2025, 6, 1, 15, 0),
            lesson_start_local=datetime(2025, 6, 2, 5, 0),
            location_type="online",
            instructor_profile=profile,
        )

    def test_lesson_date_mismatch_returns_early(self, booking_service):
        """Line 84-85: lesson date doesn't match protected_lesson_date -> returns."""
        profile = SimpleNamespace(overnight_protection_enabled=True)
        mock_config = MagicMock()
        mock_config.get_overnight_window_hours.return_value = (22, 7)
        mock_config.get_overnight_earliest_hour.return_value = 7
        booking_service.config_service = mock_config

        # Booking at 23:00 on June 1 -> protected_lesson_date = June 2
        # But lesson is on June 3 -> date mismatch -> return
        booking_service._check_overnight_protection(
            booking_time_local=datetime(2025, 6, 1, 23, 0),
            lesson_start_local=datetime(2025, 6, 3, 5, 0),
            location_type="online",
            instructor_profile=profile,
        )
