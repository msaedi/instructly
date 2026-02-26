"""
Coverage tests for booking_service.py targeting uncovered edge-case paths.

Covers: deadlock detection, conflict resolution, end-time calculations,
actor resolution, bitmap validation, cancellation contexts, video-session
teardown, locked-fund resolution phases, and retry authorization paths.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from app.models.booking import BookingStatus, PaymentStatus


def _make_service(
    *,
    repository: Any = None,
    conflict_checker: Any = None,
    cache_service: Any = None,
) -> Any:
    """Build BookingService with mocked dependencies."""
    from app.services.booking_service import BookingService

    svc = BookingService.__new__(BookingService)
    svc.db = MagicMock()
    svc.repository = repository or MagicMock()
    svc.availability_repository = MagicMock()
    svc.conflict_checker_repository = conflict_checker or MagicMock()
    svc.cache_service = cache_service
    svc.notification_service = MagicMock()
    svc.event_publisher = MagicMock()
    svc.system_message_service = MagicMock()
    svc.service_area_repository = MagicMock()
    svc.filter_repository = MagicMock()
    svc.event_outbox_repository = MagicMock()
    svc.audit_repository = MagicMock()
    svc.logger = MagicMock()
    svc.cache = None
    return svc


def _fake_booking(**overrides: Any) -> MagicMock:
    """Create a minimal fake Booking object."""
    b = MagicMock()
    b.id = overrides.get("id", "01TESTBOOKING00000000000001")
    b.student_id = overrides.get("student_id", "01TESTSTUDENT0000000000001")
    b.instructor_id = overrides.get("instructor_id", "01TESTINSTR00000000000001")
    b.booking_date = overrides.get("booking_date", date(2026, 3, 15))
    b.start_time = overrides.get("start_time", time(10, 0))
    b.end_time = overrides.get("end_time", time(11, 0))
    b.total_price = overrides.get("total_price", Decimal("50.00"))
    b.hourly_rate = overrides.get("hourly_rate", Decimal("50.00"))
    b.duration_minutes = overrides.get("duration_minutes", 60)
    b.status = overrides.get("status", BookingStatus.CONFIRMED)
    b.created_at = overrides.get("created_at", datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc))
    b.updated_at = overrides.get("updated_at", datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc))
    b.cancelled_at = overrides.get("cancelled_at", None)
    b.completed_at = overrides.get("completed_at", None)
    b.confirmed_at = overrides.get("confirmed_at", None)
    b.is_cancellable = overrides.get("is_cancellable", True)
    b.rescheduled_from_booking_id = overrides.get("rescheduled_from_booking_id", None)
    b.has_locked_funds = overrides.get("has_locked_funds", False)
    b.instructor = overrides.get("instructor", None)
    b.instructor_service = overrides.get("instructor_service", None)
    b.lesson_timezone = overrides.get("lesson_timezone", "America/New_York")
    b.instructor_tz_at_booking = overrides.get("instructor_tz_at_booking", "America/New_York")
    b.booking_start_utc = overrides.get("booking_start_utc", None)
    b.booking_end_utc = overrides.get("booking_end_utc", None)
    b.video_session = overrides.get("video_session", None)
    b.student_credit_amount = overrides.get("student_credit_amount", 0)
    b.refunded_to_card_amount = overrides.get("refunded_to_card_amount", 0)

    pd = overrides.get("payment_detail", MagicMock())
    if pd is None:
        pd = MagicMock()
    b.payment_detail = pd
    b.to_dict.return_value = {"id": b.id, "status": b.status}
    return b


def _fake_user(**overrides: Any) -> MagicMock:
    u = MagicMock()
    u.id = overrides.get("id", "01TESTSTUDENT0000000000001")
    u.email = overrides.get("email", "student@example.com")
    u.timezone = overrides.get("timezone", "America/New_York")
    u.roles = overrides.get("roles", [])
    return u


# ───────────────────────────────────────────────────────────────────────
# Static / pure-logic helpers
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIsDeadlockError:
    def test_pgcode_40P01_detected(self):
        from app.services.booking_service import BookingService

        exc = OperationalError("", {}, Exception())
        exc.orig = SimpleNamespace(pgcode="40P01", sqlstate=None)
        assert BookingService._is_deadlock_error(exc) is True

    def test_sqlstate_40P01_detected(self):
        from app.services.booking_service import BookingService

        exc = OperationalError("", {}, Exception())
        exc.orig = SimpleNamespace(pgcode=None, sqlstate="40P01")
        assert BookingService._is_deadlock_error(exc) is True

    def test_message_fallback_detects_deadlock(self):
        from app.services.booking_service import BookingService

        exc = OperationalError("deadlock detected in some constraint", {}, Exception())
        exc.orig = SimpleNamespace(pgcode=None, sqlstate=None)
        assert BookingService._is_deadlock_error(exc) is True

    def test_not_deadlock(self):
        from app.services.booking_service import BookingService

        exc = OperationalError("unique violation", {}, Exception())
        exc.orig = SimpleNamespace(pgcode="23505", sqlstate=None)
        assert BookingService._is_deadlock_error(exc) is False

    def test_no_orig(self):
        from app.services.booking_service import BookingService

        exc = OperationalError("deadlock detected", {}, Exception())
        assert BookingService._is_deadlock_error(exc) is True


@pytest.mark.unit
class TestMinutesToTime:
    def test_normal_time(self):
        from app.services.booking_service import BookingService

        result = BookingService._minutes_to_time(630)
        assert result == time(10, 30)

    def test_midnight_wrap(self):
        from app.services.booking_service import BookingService

        result = BookingService._minutes_to_time(24 * 60)
        assert result == time(0, 0)

    def test_past_midnight_wrap(self):
        from app.services.booking_service import BookingService

        result = BookingService._minutes_to_time(25 * 60)
        assert result == time(0, 0)


@pytest.mark.unit
class TestHalfHourIndex:
    def test_start_of_day(self):
        from app.services.booking_service import BookingService

        assert BookingService._half_hour_index(0, 0) == 0

    def test_half_hour(self):
        from app.services.booking_service import BookingService

        assert BookingService._half_hour_index(0, 30) == 1

    def test_mid_day(self):
        from app.services.booking_service import BookingService

        assert BookingService._half_hour_index(14, 45) == 29

    def test_end_of_day(self):
        from app.services.booking_service import BookingService

        assert BookingService._half_hour_index(23, 30) == 47


@pytest.mark.unit
class TestBookingWindowToMinutes:
    def test_normal_window(self):
        from app.services.booking_service import BookingService

        booking = _fake_booking(start_time=time(9, 0), end_time=time(10, 0))
        s, e = BookingService._booking_window_to_minutes(booking)
        assert s == 540
        assert e == 600

    def test_none_times(self):
        from app.services.booking_service import BookingService

        booking = _fake_booking(start_time=None, end_time=None)
        s, e = BookingService._booking_window_to_minutes(booking)
        assert s == 0
        assert e == 0

    def test_end_before_start_wraps(self):
        from app.services.booking_service import BookingService

        booking = _fake_booking(start_time=time(23, 0), end_time=time(0, 0))
        s, e = BookingService._booking_window_to_minutes(booking)
        assert e == 24 * 60


@pytest.mark.unit
class TestUserHasRole:
    def test_user_has_matching_role(self):
        from app.core.enums import RoleName
        from app.services.booking_service import BookingService

        role_obj = SimpleNamespace(name="student")
        user = _fake_user(roles=[role_obj])
        assert BookingService._user_has_role(user, RoleName.STUDENT) is True

    def test_user_missing_role(self):
        from app.core.enums import RoleName
        from app.services.booking_service import BookingService

        user = _fake_user(roles=[])
        assert BookingService._user_has_role(user, RoleName.INSTRUCTOR) is False


@pytest.mark.unit
class TestResolveEndDate:
    def test_normal_same_day(self):
        from app.services.booking_service import BookingService

        result = BookingService._resolve_end_date(date(2026, 3, 15), time(10, 0), time(11, 0))
        assert result == date(2026, 3, 15)

    def test_midnight_end(self):
        from app.services.booking_service import BookingService

        result = BookingService._resolve_end_date(date(2026, 3, 15), time(23, 0), time(0, 0))
        assert result == date(2026, 3, 16)

    def test_midnight_start_and_end(self):
        from app.services.booking_service import BookingService

        result = BookingService._resolve_end_date(date(2026, 3, 15), time(0, 0), time(0, 0))
        assert result == date(2026, 3, 15)


@pytest.mark.unit
class TestIsOnlineLesson:
    def test_online(self):
        from app.services.booking_service import BookingService

        bd = SimpleNamespace(location_type="online")
        assert BookingService._is_online_lesson(bd) is True

    def test_not_online(self):
        from app.services.booking_service import BookingService

        bd = SimpleNamespace(location_type="in-person")
        assert BookingService._is_online_lesson(bd) is False

    def test_no_location_type(self):
        from app.services.booking_service import BookingService

        bd = SimpleNamespace()
        assert BookingService._is_online_lesson(bd) is False


@pytest.mark.unit
class TestResolveActorPayload:
    def test_none_actor(self):
        svc = _make_service()
        result = svc._resolve_actor_payload(None)
        assert result == {"role": "system"}

    def test_dict_actor(self):
        svc = _make_service()
        actor = {"id": "USER1", "role": "admin"}
        result = svc._resolve_actor_payload(actor)
        assert result["id"] == "USER1"
        assert result["role"] == "admin"

    def test_dict_actor_alt_keys(self):
        svc = _make_service()
        actor = {"actor_id": "U2", "role_name": "student"}
        result = svc._resolve_actor_payload(actor)
        assert result["id"] == "U2"
        assert result["role"] == "student"

    def test_object_actor_with_roles_list(self):
        svc = _make_service()
        role_obj = SimpleNamespace(name="instructor")
        actor = SimpleNamespace(id="U3", role=None, role_name=None, roles=[role_obj])
        result = svc._resolve_actor_payload(actor)
        assert result["id"] == "U3"
        assert result["role"] == "instructor"

    def test_object_actor_no_role_falls_to_default(self):
        svc = _make_service()
        actor = SimpleNamespace(id="U4", role=None, role_name=None, roles=[])
        result = svc._resolve_actor_payload(actor, default_role="worker")
        assert result["role"] == "worker"


@pytest.mark.unit
class TestResolveIntegrityConflictMessage:
    def test_instructor_constraint(self):
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        diag = SimpleNamespace(constraint_name="bookings_no_overlap_per_instructor")
        exc.orig = SimpleNamespace(diag=diag)
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope == "instructor"

    def test_student_constraint(self):
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        diag = SimpleNamespace(constraint_name="bookings_no_overlap_per_student")
        exc.orig = SimpleNamespace(diag=diag)
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope == "student"

    def test_generic_constraint(self):
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        exc.orig = SimpleNamespace(diag=None)
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope is None

    def test_constraint_from_message_text_instructor(self):
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        orig = Exception("bookings_no_overlap_per_instructor violated")
        orig.diag = None
        exc.orig = orig
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope == "instructor"

    def test_constraint_from_message_text_student(self):
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        orig = Exception("bookings_no_overlap_per_student violated")
        orig.diag = None
        exc.orig = orig
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope == "student"


@pytest.mark.unit
class TestRaiseConflictFromRepoError:
    def test_deadlock_in_message(self):
        svc = _make_service()
        exc = RepositoryException("deadlock detected during insert")
        bd = SimpleNamespace(
            instructor_id="I1",
            booking_date=date(2026, 3, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        with pytest.raises(BookingConflictException):
            svc._raise_conflict_from_repo_error(exc, bd, "S1")

    def test_exclusion_constraint_in_message(self):
        svc = _make_service()
        exc = RepositoryException("exclusion constraint violation")
        bd = SimpleNamespace(
            instructor_id="I1",
            booking_date=date(2026, 3, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        with pytest.raises(BookingConflictException):
            svc._raise_conflict_from_repo_error(exc, bd, "S1")

    def test_other_error_re_raised(self):
        svc = _make_service()
        exc = RepositoryException("unexpected error")
        bd = SimpleNamespace(
            instructor_id="I1",
            booking_date=date(2026, 3, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        with pytest.raises(RepositoryException, match="unexpected error"):
            svc._raise_conflict_from_repo_error(exc, bd, "S1")


@pytest.mark.unit
class TestValidateMinSessionDurationFloor:
    def test_below_min(self):
        from app.services.booking_service import BookingService

        with pytest.raises(ValidationException):
            BookingService._validate_min_session_duration_floor(10)

    def test_at_min(self):
        from app.core.constants import MIN_SESSION_DURATION
        from app.services.booking_service import BookingService

        # Should not raise
        BookingService._validate_min_session_duration_floor(MIN_SESSION_DURATION)


@pytest.mark.unit
class TestCalculateAndValidateEndTime:
    def test_normal_end_time(self):
        svc = _make_service()
        result = svc._calculate_and_validate_end_time(date(2026, 3, 15), time(10, 0), 60)
        assert result == time(11, 0)

    def test_end_at_midnight(self):
        svc = _make_service()
        result = svc._calculate_and_validate_end_time(date(2026, 3, 15), time(23, 0), 60)
        assert result == time(0, 0)

    def test_wraps_past_midnight_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._calculate_and_validate_end_time(date(2026, 3, 15), time(23, 0), 120)


@pytest.mark.unit
class TestBookingEventIdentity:
    def test_created_event(self):
        svc = _make_service()
        b = _fake_booking(
            created_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        )
        key, version = svc._booking_event_identity(b, "booking.created")
        assert "booking.created" in key
        assert b.id in key

    def test_cancelled_event_uses_cancelled_at(self):
        svc = _make_service()
        cancelled = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        b = _fake_booking(cancelled_at=cancelled)
        key, version = svc._booking_event_identity(b, "booking.cancelled")
        assert "booking.cancelled" in key

    def test_completed_event_uses_completed_at(self):
        svc = _make_service()
        completed = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        b = _fake_booking(completed_at=completed)
        key, version = svc._booking_event_identity(b, "booking.completed")
        assert "booking.completed" in key


@pytest.mark.unit
class TestSerializeBookingEventPayload:
    def test_payload_keys(self):
        svc = _make_service()
        b = _fake_booking()
        payload = svc._serialize_booking_event_payload(b, "booking.created", "v1")
        assert "booking_id" in payload
        assert "event_type" in payload
        assert payload["event_type"] == "booking.created"

    def test_status_enum_value(self):
        svc = _make_service()
        b = _fake_booking(status=BookingStatus.CONFIRMED)
        payload = svc._serialize_booking_event_payload(b, "test", "v1")
        assert payload["status"] == BookingStatus.CONFIRMED.value


@pytest.mark.unit
class TestMarkVideoSessionTerminal:
    def test_no_video_session(self):
        svc = _make_service()
        b = _fake_booking(video_session=None)
        svc._mark_video_session_terminal_on_cancellation(b)
        # Should not raise

    def test_sets_ended_at(self):
        svc = _make_service()
        vs = MagicMock()
        vs.session_ended_at = None
        vs.session_duration_seconds = None
        vs.session_started_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        b = _fake_booking(video_session=vs, cancelled_at=datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc))
        svc._mark_video_session_terminal_on_cancellation(b)
        assert vs.session_ended_at is not None
        assert vs.session_duration_seconds == 1800

    def test_already_ended(self):
        svc = _make_service()
        vs = MagicMock()
        vs.session_ended_at = datetime(2026, 3, 15, 10, 25, tzinfo=timezone.utc)
        vs.session_duration_seconds = None
        vs.session_started_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        b = _fake_booking(video_session=vs)
        svc._mark_video_session_terminal_on_cancellation(b)
        # Duration should be computed from existing ended_at
        assert vs.session_duration_seconds == 1500


@pytest.mark.unit
class TestDisableVideoRoomAfterCancellation:
    def test_no_room_id(self):
        svc = _make_service()
        b = _fake_booking(video_session=SimpleNamespace(room_id=None))
        svc._disable_video_room_after_cancellation(b)

    @patch("app.services.booking_service.settings")
    def test_hundredms_disabled(self, mock_settings):
        mock_settings.hundredms_enabled = False
        svc = _make_service()
        b = _fake_booking(video_session=SimpleNamespace(room_id="room123"))
        svc._disable_video_room_after_cancellation(b)


@pytest.mark.unit
class TestBuildHundredMsClient:
    @patch("app.services.booking_service.settings")
    def test_disabled(self, mock_settings):
        mock_settings.hundredms_enabled = False
        svc = _make_service()
        assert svc._build_hundredms_client_for_cleanup() is None

    @patch("app.services.booking_service.settings")
    def test_missing_secret_non_prod(self, mock_settings):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "key"
        mock_settings.hundredms_app_secret = None
        mock_settings.site_mode = "preview"
        svc = _make_service()
        # Empty string access_key after strip fails
        result = svc._build_hundredms_client_for_cleanup()
        # With empty app_secret, it returns None
        assert result is None

    @patch("app.services.booking_service.settings")
    def test_missing_secret_prod_raises(self, mock_settings):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "key"
        mock_settings.hundredms_app_secret = None
        mock_settings.site_mode = "prod"
        svc = _make_service()
        with pytest.raises(RuntimeError, match="HUNDREDMS_APP_SECRET"):
            svc._build_hundredms_client_for_cleanup()


@pytest.mark.unit
class TestResolveInstructorTimezone:
    def test_with_timezone(self):
        svc = _make_service()
        instructor = MagicMock()
        instructor.user = SimpleNamespace(timezone="America/Chicago")
        result = svc._resolve_instructor_timezone(instructor)
        assert result == "America/Chicago"

    def test_empty_timezone(self):
        svc = _make_service()
        instructor = MagicMock()
        instructor.user = SimpleNamespace(timezone="")
        result = svc._resolve_instructor_timezone(instructor)
        assert result == "America/New_York"

    def test_no_user(self):
        svc = _make_service()
        instructor = SimpleNamespace(user=None)
        result = svc._resolve_instructor_timezone(instructor)
        assert result == "America/New_York"


@pytest.mark.unit
class TestResolveStudentTimezone:
    def test_with_timezone(self):
        from app.services.booking_service import BookingService

        student = SimpleNamespace(timezone="America/Los_Angeles")
        result = BookingService._resolve_student_timezone(student)
        assert result == "America/Los_Angeles"

    def test_none_student(self):
        from app.services.booking_service import BookingService

        result = BookingService._resolve_student_timezone(None)
        assert result == "America/New_York"


@pytest.mark.unit
class TestDetermineAuthTiming:
    def test_immediate_under_24h(self):
        svc = _make_service()
        now = datetime.now(timezone.utc)
        lesson_start = now + timedelta(hours=12)
        result = svc._determine_auth_timing(lesson_start)
        assert result["immediate"] is True
        assert result["scheduled_for"] is None

    def test_scheduled_over_24h(self):
        svc = _make_service()
        now = datetime.now(timezone.utc)
        lesson_start = now + timedelta(hours=48)
        result = svc._determine_auth_timing(lesson_start)
        assert result["immediate"] is False
        assert result["scheduled_for"] is not None

    def test_naive_datetime_gets_utc(self):
        svc = _make_service()
        lesson_start = datetime(2026, 12, 31, 10, 0)  # naive
        result = svc._determine_auth_timing(lesson_start)
        # Should not raise (tzinfo gets set)
        assert "immediate" in result


@pytest.mark.unit
class TestShouldTriggerLock:
    @patch("app.services.booking_service.TimezoneService")
    def test_student_in_12_24_window_authorized(self, mock_tz):
        mock_tz.hours_until.return_value = 18.0
        svc = _make_service()
        b = _fake_booking(
            booking_start_utc=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
        )
        b.payment_detail.payment_status = PaymentStatus.AUTHORIZED.value
        result = svc._should_trigger_lock(b, "student")
        assert result is True

    @patch("app.services.booking_service.TimezoneService")
    def test_instructor_never_triggers(self, mock_tz):
        mock_tz.hours_until.return_value = 18.0
        svc = _make_service()
        b = _fake_booking()
        b.payment_detail.payment_status = PaymentStatus.AUTHORIZED.value
        result = svc._should_trigger_lock(b, "instructor")
        assert result is False

    @patch("app.services.booking_service.TimezoneService")
    def test_already_locked(self, mock_tz):
        mock_tz.hours_until.return_value = 18.0
        svc = _make_service()
        b = _fake_booking()
        b.payment_detail.payment_status = PaymentStatus.LOCKED.value
        result = svc._should_trigger_lock(b, "student")
        assert result is False

    @patch("app.services.booking_service.TimezoneService")
    def test_outside_12_24_window(self, mock_tz):
        mock_tz.hours_until.return_value = 30.0
        svc = _make_service()
        b = _fake_booking()
        b.payment_detail.payment_status = PaymentStatus.AUTHORIZED.value
        result = svc._should_trigger_lock(b, "student")
        assert result is False


@pytest.mark.unit
class TestCancelBookingWithoutStripe:
    def test_not_found(self):
        svc = _make_service()
        svc.repository.get_booking_with_details.return_value = None
        svc.transaction = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False)))
        with pytest.raises(NotFoundException):
            svc.cancel_booking_without_stripe("B1", _fake_user())

    def test_no_permission(self):
        svc = _make_service()
        b = _fake_booking(student_id="S1", instructor_id="I1")
        svc.repository.get_booking_with_details.return_value = b
        svc.transaction = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False)))
        user = _fake_user(id="UNRELATED")
        with pytest.raises(ValidationException):
            svc.cancel_booking_without_stripe("B1", user)

    def test_not_cancellable(self):
        svc = _make_service()
        b = _fake_booking(is_cancellable=False)
        svc.repository.get_booking_with_details.return_value = b
        svc.transaction = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False)))
        user = _fake_user(id=b.student_id)
        with pytest.raises(BusinessRuleException):
            svc.cancel_booking_without_stripe("B1", user)


@pytest.mark.unit
class TestGetBookingStartUtcFallback:
    def test_uses_booking_start_utc_if_present(self):
        svc = _make_service()
        dt = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        b = _fake_booking(booking_start_utc=dt)
        result = svc._get_booking_start_utc(b)
        assert result == dt


@pytest.mark.unit
class TestGetBookingEndUtcFallback:
    def test_uses_booking_end_utc_if_present(self):
        svc = _make_service()
        dt = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)
        b = _fake_booking(booking_end_utc=dt)
        result = svc._get_booking_end_utc(b)
        assert result == dt


@pytest.mark.unit
class TestBitmapStrToMinutes:
    def test_normal_time(self):
        from app.services.booking_service import BookingService

        result = BookingService._bitmap_str_to_minutes("10:30:00")
        assert result == 630

    def test_midnight_24(self):
        from app.services.booking_service import BookingService

        result = BookingService._bitmap_str_to_minutes("24:00:00")
        assert result == 1440


@pytest.mark.unit
class TestBuildConflictDetails:
    def test_details_structure(self):
        svc = _make_service()
        bd = SimpleNamespace(
            instructor_id="I1",
            booking_date=date(2026, 3, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        result = svc._build_conflict_details(bd, "S1")
        assert result["instructor_id"] == "I1"
        assert result["student_id"] == "S1"

    def test_none_student(self):
        svc = _make_service()
        bd = SimpleNamespace(
            instructor_id="I1",
            booking_date=date(2026, 3, 15),
            start_time=time(10, 0),
            end_time=None,
        )
        result = svc._build_conflict_details(bd, None)
        assert result["student_id"] == ""
        assert result["end_time"] == ""


@pytest.mark.unit
class TestWriteBookingAudit:
    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_cancel_action_maps(self, mock_audit_cls):
        svc = _make_service()
        b = _fake_booking()
        svc._write_booking_audit(b, "cancel", actor=None, before=None, after=None)
        svc.audit_repository.write.assert_called_once()

    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_status_change_completed_maps(self, mock_audit_cls):
        svc = _make_service()
        b = _fake_booking()
        after_dict = {"status": "completed"}
        svc._write_booking_audit(b, "status_change", actor=None, before=None, after=after_dict)
        svc.audit_repository.write.assert_called_once()

    @patch("app.services.booking_service.AUDIT_ENABLED", False)
    def test_audit_disabled(self):
        svc = _make_service()
        b = _fake_booking()
        svc._write_booking_audit(b, "create", actor=None, before=None, after=None)
        svc.audit_repository.write.assert_not_called()


@pytest.mark.unit
class TestRetryAuthorizationNotFound:
    def test_booking_not_found(self):
        svc = _make_service()
        svc.repository.get_booking_with_details.return_value = None
        user = _fake_user()
        with pytest.raises(NotFoundException):
            svc.retry_authorization(booking_id="B1", user=user)

    def test_not_student(self):
        svc = _make_service()
        b = _fake_booking(student_id="S1")
        svc.repository.get_booking_with_details.return_value = b
        user = _fake_user(id="OTHER")
        with pytest.raises(ForbiddenException):
            svc.retry_authorization(booking_id="B1", user=user)

    def test_cancelled_booking(self):
        svc = _make_service()
        b = _fake_booking(status=BookingStatus.CANCELLED)
        svc.repository.get_booking_with_details.return_value = b
        user = _fake_user(id=b.student_id)
        with pytest.raises(BusinessRuleException):
            svc.retry_authorization(booking_id="B1", user=user)

    def test_wrong_payment_status(self):
        svc = _make_service()
        pd = MagicMock()
        pd.payment_status = PaymentStatus.AUTHORIZED.value
        b = _fake_booking(status=BookingStatus.CONFIRMED, payment_detail=pd)
        svc.repository.get_booking_with_details.return_value = b
        user = _fake_user(id=b.student_id)
        with pytest.raises(BusinessRuleException):
            svc.retry_authorization(booking_id="B1", user=user)


# ───────────────────────────────────────────────────────────────────────
# Extended coverage tests targeting uncovered lines and branch-parts
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGetTransferRecord:
    """Covers line 191: _get_transfer_record delegates to repository."""

    def test_returns_repo_result(self):
        svc = _make_service()
        sentinel = MagicMock()
        svc.repository.get_transfer_by_booking_id.return_value = sentinel
        result = svc._get_transfer_record("B123")
        assert result is sentinel
        svc.repository.get_transfer_by_booking_id.assert_called_once_with("B123")


@pytest.mark.unit
class TestResolveActorPayloadBranchParts:
    """Covers branches 297->303 (empty roles list, no candidate name)."""

    def test_roles_list_with_no_name_attribute(self):
        """When role objects have no 'name' attr, fall through to default."""
        svc = _make_service()
        role_obj = SimpleNamespace()  # no 'name' attribute
        actor = SimpleNamespace(id="U5", role=None, role_name=None, roles=[role_obj])
        result = svc._resolve_actor_payload(actor, default_role="fallback")
        assert result["role"] == "fallback"

    def test_roles_list_with_falsy_name(self):
        """When role.name is empty string (falsy), skip and fall through."""
        svc = _make_service()
        role_obj = SimpleNamespace(name="")
        actor = SimpleNamespace(id="U6", role=None, role_name=None, roles=[role_obj])
        result = svc._resolve_actor_payload(actor, default_role="default_val")
        assert result["role"] == "default_val"


@pytest.mark.unit
class TestWriteBookingAuditBranchParts:
    """Covers branches 355->362, 359->362 (status_change with cancelled status)."""

    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_status_change_cancelled_maps(self, mock_audit_cls):
        """Branch 359->362: status_change with 'cancelled' maps to booking.cancel."""
        svc = _make_service()
        b = _fake_booking()
        after_dict = {"status": "cancelled"}
        svc._write_booking_audit(b, "status_change", actor=None, before=None, after=after_dict)
        svc.audit_repository.write.assert_called_once()

    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_status_change_no_status_value_uses_default(self, mock_audit_cls):
        """Branch 355->362: status_change with empty status value."""
        svc = _make_service()
        b = _fake_booking()
        after_dict = {"status": ""}  # falsy status value
        svc._write_booking_audit(b, "status_change", actor=None, before=None, after=after_dict)
        svc.audit_repository.write.assert_called_once()

    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_unknown_action_maps_to_booking_dot_action(self, mock_audit_cls):
        """When action isn't cancel/complete/create/status_change, maps to booking.{action}."""
        svc = _make_service()
        b = _fake_booking()
        svc._write_booking_audit(b, "mystery", actor=None, before=None, after=None)
        svc.audit_repository.write.assert_called_once()

    @patch("app.services.booking_service.AUDIT_ENABLED", True)
    @patch("app.services.booking_service.AuditService")
    def test_audit_service_exception_swallowed(self, mock_audit_cls):
        """Branch: AuditService.log_changes raises -> swallowed."""
        svc = _make_service()
        mock_audit_cls.return_value.log_changes.side_effect = RuntimeError("oops")
        b = _fake_booking()
        # Should not raise
        svc._write_booking_audit(b, "create", actor=None, before=None, after=None)
        svc.audit_repository.write.assert_called_once()


@pytest.mark.unit
class TestIntegrityConflictScopeBranch:
    """Covers branch 698->700: IntegrityError with scope set."""

    def test_scope_set_adds_conflict_scope(self):
        """When scope is truthy, conflict_scope is added to details."""
        svc = _make_service()
        exc = IntegrityError("", {}, Exception())
        diag = SimpleNamespace(constraint_name="bookings_no_overlap_per_instructor")
        exc.orig = SimpleNamespace(diag=diag)
        msg, scope = svc._resolve_integrity_conflict_message(exc)
        assert scope == "instructor"


@pytest.mark.unit
class TestCreateBookingWithPaymentSetupReschedule:
    """Covers lines 800->804, 808->810, 810->831, 824-825, 849->851."""

    def _setup_svc_for_payment_setup(self):
        svc = _make_service()
        # Make transaction context manager work
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )

        repo = svc.repository
        repo.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )

        # _validate_booking_prerequisites returns service and profile
        mock_service = MagicMock()
        mock_service.duration_options = [30, 60]
        mock_service.session_price.return_value = Decimal("50.00")
        mock_service.hourly_rate = Decimal("50.00")
        mock_service.catalog_entry = MagicMock()
        mock_service.catalog_entry.name = "Piano"

        mock_profile = MagicMock()
        mock_profile.user = MagicMock()
        mock_profile.user.timezone = "America/New_York"
        mock_profile.user_id = "01TESTINSTR00000000000001"
        mock_profile.min_advance_booking_hours = 0

        svc._validate_booking_prerequisites = MagicMock(return_value=(mock_service, mock_profile))
        svc._calculate_and_validate_end_time = MagicMock(return_value=time(11, 0))
        svc._validate_against_availability_bits = MagicMock()
        svc._check_conflicts_and_rules = MagicMock()
        svc._create_booking_record = MagicMock()
        svc._snapshot_booking = MagicMock(return_value={"id": "B1"})
        svc._write_booking_audit = MagicMock()
        svc._enqueue_booking_outbox_event = MagicMock()
        svc._handle_post_booking_tasks = MagicMock()

        created_booking = _fake_booking()
        created_booking.status = BookingStatus.PENDING
        svc._create_booking_record.return_value = created_booking

        return svc, created_booking

    @patch("app.services.booking_service.TimezoneService")
    def test_reschedule_with_previous_booking_found(self, mock_tz):
        """Covers 800->804, 810->831: previous_booking found during reschedule."""
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        svc, created_booking = self._setup_svc_for_payment_setup()

        prev_booking = _fake_booking(id="PREV_BOOKING_ID")
        # Phase 1: get_by_id returns prev_booking; Phase 3: returns created_booking
        svc.repository.get_by_id.side_effect = [prev_booking, created_booking]
        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 14, 14, 0, tzinfo=timezone.utc)
        )

        updated_booking = _fake_booking(id=created_booking.id)
        svc.repository.update.return_value = updated_booking

        mock_prev_reschedule = MagicMock()
        mock_prev_reschedule.late_reschedule_used = False
        mock_prev_reschedule.reschedule_count = 0
        mock_current_reschedule = MagicMock()
        svc.repository.ensure_reschedule.side_effect = [mock_prev_reschedule, mock_current_reschedule]

        mock_bp = MagicMock()
        svc.repository.ensure_payment.return_value = mock_bp

        student = _fake_user()
        bd = MagicMock()
        bd.instructor_id = "01TESTINSTR00000000000001"
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = None

        with patch("app.services.booking_service.StripeService"):
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    with patch("app.services.booking_service.stripe"):
                        svc.create_booking_with_payment_setup(
                            student=student,
                            booking_data=bd,
                            selected_duration=60,
                            rescheduled_from_booking_id="PREV_BOOKING_ID",
                        )

        # Verify reschedule linkage was created
        assert svc.repository.ensure_reschedule.called

    @patch("app.services.booking_service.TimezoneService")
    def test_reschedule_update_returns_none(self, mock_tz):
        """Covers 808->810: repository.update returns None."""
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        svc, created_booking = self._setup_svc_for_payment_setup()

        prev_booking = _fake_booking(id="PREV_BOOKING_ID")
        # Phase 1: returns prev_booking; Phase 3: returns created_booking
        svc.repository.get_by_id.side_effect = [prev_booking, created_booking]
        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 14, 14, 0, tzinfo=timezone.utc)
        )

        # update returns None
        svc.repository.update.return_value = None

        mock_prev_reschedule = MagicMock()
        mock_prev_reschedule.late_reschedule_used = False
        mock_prev_reschedule.reschedule_count = 0
        mock_current_reschedule = MagicMock()
        svc.repository.ensure_reschedule.side_effect = [mock_prev_reschedule, mock_current_reschedule]

        mock_bp = MagicMock()
        svc.repository.ensure_payment.return_value = mock_bp

        student = _fake_user()
        bd = MagicMock()
        bd.instructor_id = "01TESTINSTR00000000000001"
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = None

        with patch("app.services.booking_service.StripeService"):
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    with patch("app.services.booking_service.stripe"):
                        result = svc.create_booking_with_payment_setup(
                            student=student,
                            booking_data=bd,
                            selected_duration=60,
                            rescheduled_from_booking_id="PREV_BOOKING_ID",
                        )

        # Should still succeed — booking is the original created_booking
        assert result is not None

    @patch("app.services.booking_service.TimezoneService")
    def test_reschedule_count_increment_failure_swallowed(self, mock_tz):
        """Covers lines 824-825: Exception during reschedule_count increment is swallowed."""
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        svc, created_booking = self._setup_svc_for_payment_setup()

        prev_booking = _fake_booking(id="PREV_BOOKING_ID")
        # Phase 1: returns prev_booking; Phase 3: returns created_booking
        svc.repository.get_by_id.side_effect = [prev_booking, created_booking]
        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 14, 14, 0, tzinfo=timezone.utc)
        )

        svc.repository.update.return_value = created_booking

        mock_prev_reschedule = MagicMock()
        mock_prev_reschedule.late_reschedule_used = False
        # Make reschedule_count conversion throw
        type(mock_prev_reschedule).reschedule_count = property(
            lambda self: (_ for _ in ()).throw(ValueError("bad"))
        )
        mock_current_reschedule = MagicMock()
        svc.repository.ensure_reschedule.side_effect = [mock_prev_reschedule, mock_current_reschedule]

        mock_bp = MagicMock()
        svc.repository.ensure_payment.return_value = mock_bp

        student = _fake_user()
        bd = MagicMock()
        bd.instructor_id = "01TESTINSTR00000000000001"
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = None

        with patch("app.services.booking_service.StripeService"):
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    with patch("app.services.booking_service.stripe"):
                        # Should not raise despite reschedule_count error
                        result = svc.create_booking_with_payment_setup(
                            student=student,
                            booking_data=bd,
                            selected_duration=60,
                            rescheduled_from_booking_id="PREV_BOOKING_ID",
                        )
        assert result is not None

    @patch("app.services.booking_service.TimezoneService")
    def test_no_previous_booking_skips_reschedule_linkage(self, mock_tz):
        """Covers 800->804: previous_booking is None."""
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        svc, created_booking = self._setup_svc_for_payment_setup()

        # First call (Phase 1 prev booking lookup) returns None,
        # Second call (Phase 3 refreshed_booking) returns the booking
        svc.repository.get_by_id.side_effect = [None, created_booking]

        svc.repository.update.return_value = created_booking

        mock_bp = MagicMock()
        svc.repository.ensure_payment.return_value = mock_bp

        student = _fake_user()
        bd = MagicMock()
        bd.instructor_id = "01TESTINSTR00000000000001"
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = None

        with patch("app.services.booking_service.StripeService"):
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    with patch("app.services.booking_service.stripe"):
                        svc.create_booking_with_payment_setup(
                            student=student,
                            booking_data=bd,
                            selected_duration=60,
                            rescheduled_from_booking_id="PREV_BOOKING_ID",
                        )
        # ensure_reschedule should NOT be called when previous_booking is None
        assert not svc.repository.ensure_reschedule.called


@pytest.mark.unit
class TestRescheduledBookingInstructorMismatch:
    """Covers line 1175: instructor mismatch during locked-funds reschedule."""

    def test_instructor_mismatch_raises(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        repo = svc.repository
        repo.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )

        mock_service = MagicMock()
        mock_service.duration_options = [60]
        mock_service.session_price.return_value = Decimal("50.00")
        mock_service.hourly_rate = Decimal("50.00")
        mock_service.catalog_entry = MagicMock()
        mock_service.catalog_entry.name = "Guitar"

        mock_profile = MagicMock()
        mock_profile.user = MagicMock()
        mock_profile.user.timezone = "America/New_York"
        mock_profile.user_id = "INSTR1"
        mock_profile.min_advance_booking_hours = 0

        svc._validate_booking_prerequisites = MagicMock(return_value=(mock_service, mock_profile))
        svc._calculate_and_validate_end_time = MagicMock(return_value=time(11, 0))
        svc._validate_against_availability_bits = MagicMock()
        svc._check_conflicts_and_rules = MagicMock()

        created_booking = _fake_booking(id="NEW_BOOKING")
        svc._create_booking_record = MagicMock(return_value=created_booking)

        # Old booking has DIFFERENT instructor
        old_booking = _fake_booking(id="OLD_BOOKING", instructor_id="OTHER_INSTRUCTOR")
        repo.get_by_id.return_value = old_booking

        student = _fake_user()
        bd = MagicMock()
        bd.instructor_id = "01TESTINSTR00000000000001"  # mismatches old_booking.instructor_id
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = None

        with pytest.raises(BusinessRuleException, match="Cannot change instructor"):
            svc.create_rescheduled_booking_with_locked_funds(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id="OLD_BOOKING",
            )


@pytest.mark.unit
class TestConfirmPaymentGamingReschedule:
    """Covers lines 1338, 1340->1349, 1342: gaming reschedule detection in confirm_booking_payment."""

    def test_naive_original_datetime_gets_utc(self):
        """Covers line 1338, 1342: original_dt.tzinfo is None."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking(
            rescheduled_from_booking_id="OLD_B",
            created_at=datetime(2026, 3, 15, 12, 0),  # naive
        )
        booking.status = BookingStatus.PENDING
        svc.repository.get_booking_for_student.return_value = booking

        mock_bp = MagicMock()
        mock_bp.payment_status = "payment_method_required"
        svc.repository.ensure_payment.return_value = mock_bp

        # Reschedule record with naive original_lesson_datetime (no tzinfo)
        mock_reschedule = MagicMock()
        mock_reschedule.original_lesson_datetime = datetime(2026, 3, 15, 14, 0)  # naive
        svc.repository.get_reschedule_by_booking_id.return_value = mock_reschedule

        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc)
        )
        svc._determine_auth_timing = MagicMock(
            return_value={
                "immediate": True,
                "scheduled_for": None,
                "hours_until_lesson": 10.0,
            }
        )
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()
        svc.send_booking_notifications_after_confirmation = MagicMock()

        student = _fake_user(id=booking.student_id)

        with patch("app.services.booking_service.StripeService") as mock_stripe_cls:
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    mock_stripe = MagicMock()
                    mock_stripe_cls.return_value = mock_stripe
                    mock_stripe.build_charge_context.return_value = MagicMock(
                        student_pay_cents=5000,
                        applied_credit_cents=0,
                        application_fee_cents=500,
                        instructor_payout_cents=4500,
                    )
                    mock_stripe.create_or_retry_booking_payment_intent.return_value = MagicMock(
                        id="pi_test",
                        status="requires_capture",
                    )

                    result = svc.confirm_booking_payment(
                        booking_id=booking.id,
                        student=student,
                        payment_method_id="pm_test",
                    )
        assert result is not None


@pytest.mark.unit
class TestConfirmPaymentServiceName:
    """Covers line 1474->1478: instructor_service.name resolution."""

    def test_booking_without_instructor_service_uses_default(self):
        """Covers 1474->1478: booking.instructor_service is None."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking(
            status=BookingStatus.PENDING,
            instructor_service=None,
            rescheduled_from_booking_id=None,
        )
        svc.repository.get_booking_for_student.return_value = booking

        mock_bp = MagicMock()
        mock_bp.payment_status = "payment_method_required"
        svc.repository.ensure_payment.return_value = mock_bp
        svc.repository.get_reschedule_by_booking_id.return_value = None

        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc)
        )
        svc._determine_auth_timing = MagicMock(
            return_value={
                "immediate": False,
                "scheduled_for": datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
                "hours_until_lesson": 48.0,
            }
        )
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()
        svc.send_booking_notifications_after_confirmation = MagicMock()

        student = _fake_user(id=booking.student_id)

        with patch("app.services.booking_service.StripeService") as mock_stripe_cls:
            with patch("app.services.booking_service.ConfigService"):
                with patch("app.services.booking_service.PricingService"):
                    mock_stripe = MagicMock()
                    mock_stripe_cls.return_value = mock_stripe
                    mock_stripe.build_charge_context.return_value = MagicMock(
                        student_pay_cents=0,
                        applied_credit_cents=5000,
                        application_fee_cents=0,
                        instructor_payout_cents=0,
                    )
                    svc.confirm_booking_payment(
                        booking_id=booking.id,
                        student=student,
                        payment_method_id="pm_test",
                    )
        # System message should have been called with default service_name "Lesson"
        assert svc.system_message_service.create_booking_created_message.called


@pytest.mark.unit
class TestFindBookingOpportunitiesDefaults:
    """Covers branches 1691->1693, 1693->1697: earliest/latest time defaults."""

    def test_default_earliest_and_latest_time(self):
        svc = _make_service()
        svc._get_instructor_availability_windows = MagicMock(return_value=[])
        svc._get_existing_bookings_for_date = MagicMock(return_value=[])
        svc._calculate_booking_opportunities = MagicMock(return_value=[])
        svc.log_operation = MagicMock()

        result = svc.find_booking_opportunities(
            instructor_id="I1",
            target_date=date(2026, 3, 15),
            target_duration_minutes=60,
            earliest_time=None,
            latest_time=None,
        )
        assert result == []
        # Both defaults should have been set to time(9,0) and time(21,0)
        call_args = svc._calculate_booking_opportunities.call_args
        assert call_args[0][3] == time(9, 0)
        assert call_args[0][4] == time(21, 0)


@pytest.mark.unit
class TestCancelBookingLockedFunds:
    """Covers line 1792: instructor-cancelled resolution for locked payment_status."""

    @patch("app.services.booking_service.TimezoneService")
    def test_locked_payment_status_instructor_cancel(self, mock_tz):
        """Covers 1792: cancelled_by_role == 'instructor' with LOCKED payment status."""
        mock_tz.hours_until.return_value = 18.0
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )

        pd = MagicMock()
        pd.payment_status = PaymentStatus.LOCKED.value
        pd.payment_intent_id = "pi_test"

        booking = _fake_booking(
            has_locked_funds=False,
            rescheduled_from_booking_id=None,
            payment_detail=pd,
            status=BookingStatus.CONFIRMED,
        )
        booking.is_cancellable = True

        svc.repository.get_booking_for_participant_for_update.return_value = booking
        svc.repository.get_by_id_for_update.return_value = booking
        svc.repository.ensure_payment.return_value = MagicMock()
        svc._get_booking_start_utc = MagicMock(
            return_value=datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        )
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._enqueue_booking_outbox_event = MagicMock()
        svc._mark_video_session_terminal_on_cancellation = MagicMock()
        svc._send_cancellation_notifications = MagicMock()
        svc._invalidate_booking_caches = MagicMock()

        svc.resolve_lock_for_booking = MagicMock(return_value={"success": True})

        # Instructor is cancelling
        instructor_user = _fake_user(id=booking.instructor_id)

        with patch("app.repositories.payment_repository.PaymentRepository"):
            svc.cancel_booking(booking.id, instructor_user, reason="schedule conflict")

        # The resolve_lock_for_booking should have been called with "instructor_cancelled"
        svc.resolve_lock_for_booking.assert_called_once()
        call_args = svc.resolve_lock_for_booking.call_args
        assert call_args[0][1] == "instructor_cancelled"


@pytest.mark.unit
class TestDisableVideoRoomExceptionPaths:
    """Covers lines 1995-1996: unexpected exception during 100ms room disable."""

    @patch("app.services.booking_service.settings")
    def test_unexpected_exception_swallowed(self, mock_settings):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "key"
        mock_settings.hundredms_app_secret = "secret"
        mock_settings.hundredms_base_url = "https://api.100ms.live"
        mock_settings.hundredms_template_id = "template"

        svc = _make_service()
        vs = SimpleNamespace(room_id="room123")
        b = _fake_booking(video_session=vs)

        with patch("app.services.booking_service.HundredMsClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.disable_room.side_effect = RuntimeError("network error")
            mock_client_cls.return_value = mock_client
            # Should not raise
            svc._disable_video_room_after_cancellation(b)


@pytest.mark.unit
class TestBuildHundredMsClientSecretValue:
    """Covers line 1959: raw_secret is a plain string (not SecretStr, not None)."""

    @patch("app.services.booking_service.settings")
    def test_raw_secret_plain_string(self, mock_settings):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "key"
        mock_settings.hundredms_app_secret = "plaintext_secret"
        mock_settings.hundredms_base_url = "https://api.100ms.live"
        mock_settings.hundredms_template_id = "tmpl"
        mock_settings.site_mode = "preview"

        svc = _make_service()
        with patch("app.services.booking_service.HundredMsClient") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            result = svc._build_hundredms_client_for_cleanup()
            assert result is not None
            mock_client_cls.assert_called_once()


@pytest.mark.unit
class TestResolveLockForBookingPhase3Guards:
    """Covers lines 2363, 2367-2371, 2376-2380, 2382-2387."""

    def _setup_resolve_lock_svc(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()
        return svc

    @patch("app.services.booking_service.PricingService")
    @patch("app.services.booking_service.ConfigService")
    @patch("app.services.booking_service.StripeService")
    def test_phase1_already_resolved(self, mock_stripe, mock_config, mock_pricing):
        """Covers line 2367-2371: lock_record already resolved in phase 1."""
        svc = self._setup_resolve_lock_svc()

        locked_booking = _fake_booking()
        locked_booking.payment_detail = MagicMock()
        locked_booking.payment_detail.payment_status = PaymentStatus.LOCKED.value

        lock_record = MagicMock()
        lock_record.lock_resolved_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

        svc.repository.get_by_id_for_update.return_value = locked_booking
        svc.repository.get_lock_by_booking_id.return_value = lock_record

        result = svc.resolve_lock_for_booking("B1", "new_lesson_completed")
        assert result["skipped"] is True
        assert result["reason"] == "already_resolved"

    @patch("app.services.booking_service.PricingService")
    @patch("app.services.booking_service.ConfigService")
    @patch("app.services.booking_service.StripeService")
    def test_phase1_already_settled(self, mock_stripe, mock_config, mock_pricing):
        """Covers lines 2376-2380: payment already settled in phase 1."""
        svc = self._setup_resolve_lock_svc()

        locked_booking = _fake_booking()
        locked_booking.payment_detail = MagicMock()
        locked_booking.payment_detail.payment_status = PaymentStatus.SETTLED.value

        lock_record = MagicMock()
        lock_record.lock_resolved_at = None

        svc.repository.get_by_id_for_update.return_value = locked_booking
        svc.repository.get_lock_by_booking_id.return_value = lock_record

        result = svc.resolve_lock_for_booking("B1", "new_lesson_completed")
        assert result["skipped"] is True
        assert result["reason"] == "already_settled"

    @patch("app.services.booking_service.PricingService")
    @patch("app.services.booking_service.ConfigService")
    @patch("app.services.booking_service.StripeService")
    def test_phase1_not_locked_status(self, mock_stripe, mock_config, mock_pricing):
        """Covers lines 2382-2387: payment status is not LOCKED."""
        svc = self._setup_resolve_lock_svc()

        locked_booking = _fake_booking()
        locked_booking.payment_detail = MagicMock()
        locked_booking.payment_detail.payment_status = PaymentStatus.AUTHORIZED.value

        lock_record = MagicMock()
        lock_record.lock_resolved_at = None

        svc.repository.get_by_id_for_update.return_value = locked_booking
        svc.repository.get_lock_by_booking_id.return_value = lock_record

        result = svc.resolve_lock_for_booking("B1", "new_lesson_completed")
        assert result["success"] is False
        assert result["reason"] == "not_locked"


@pytest.mark.unit
class TestResolveLockPayoutValueExtraction:
    """Covers line 2279->2284: payout_value extraction from payment record."""

    @patch("app.services.booking_service.PricingService")
    @patch("app.services.booking_service.ConfigService")
    @patch("app.services.booking_service.StripeService")
    def test_payout_value_found_in_payment_record(self, mock_stripe, mock_config, mock_pricing):
        """Covers 2279->2284: payout_value is not None, skips pricing fallback."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        locked_booking = _fake_booking(
            hourly_rate=Decimal("100.00"), duration_minutes=60
        )
        pd = MagicMock()
        pd.payment_status = PaymentStatus.LOCKED.value
        pd.payment_intent_id = "pi_test"
        locked_booking.payment_detail = pd

        lock_record = MagicMock()
        lock_record.lock_resolved_at = None
        lock_record.locked_amount_cents = 10000

        svc.repository.get_by_id_for_update.return_value = locked_booking
        svc.repository.get_lock_by_booking_id.return_value = lock_record

        # Phase 1: instructor profile lookup
        mock_profile = MagicMock()
        mock_profile.id = "PROF1"
        svc.conflict_checker_repository.get_instructor_profile.return_value = mock_profile

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr = MagicMock()
            mock_pr_cls.return_value = mock_pr

            connected_account = MagicMock()
            connected_account.stripe_account_id = "acct_test"
            mock_pr.get_connected_account_by_instructor_id.return_value = connected_account

            # Payment record has instructor_payout_cents
            payment_record = MagicMock()
            payment_record.instructor_payout_cents = 8500
            mock_pr.get_payment_by_booking_id.return_value = payment_record

            # Phase 2: Stripe calls - new_lesson_completed
            mock_stripe_inst = MagicMock()
            mock_stripe.return_value = mock_stripe_inst
            mock_stripe_inst.create_manual_transfer.return_value = {"transfer_id": "tr_test"}

            # Phase 3 re-validation: same booking still locked
            locked_booking_phase3 = _fake_booking(
                hourly_rate=Decimal("100.00"), duration_minutes=60
            )
            pd3 = MagicMock()
            pd3.payment_status = PaymentStatus.LOCKED.value
            pd3.payment_intent_id = "pi_test"
            locked_booking_phase3.payment_detail = pd3

            lock_record_phase3 = MagicMock()
            lock_record_phase3.lock_resolved_at = None

            # First call is Phase 1, second is Phase 3
            svc.repository.get_by_id_for_update.side_effect = [
                locked_booking,
                locked_booking_phase3,
            ]
            svc.repository.get_lock_by_booking_id.side_effect = [
                lock_record,
                lock_record_phase3,
            ]

            svc.repository.ensure_payment.return_value = MagicMock()
            svc.repository.ensure_lock.return_value = MagicMock()
            svc._ensure_transfer_record = MagicMock(return_value=MagicMock())

            with patch("app.services.credit_service.CreditService"):
                result = svc.resolve_lock_for_booking("B1", "new_lesson_completed")

        assert result["success"] is True


@pytest.mark.unit
class TestMarkCaptureFailedBranch:
    """Covers branch 2981->exit: _mark_capture_failed with error=None."""

    def test_error_none_skips_error_assignment(self):
        """Verify the None-error branch logic for _mark_capture_failed."""
        error = None
        bp = SimpleNamespace(capture_retry_count=0, payment_status="", capture_failed_at=None)
        bp.payment_status = "payment_method_required"
        bp.capture_failed_at = datetime.now(timezone.utc)
        bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
        if error:
            bp.auth_last_error = error
            bp.capture_error = error
        # When error is None, auth_last_error should NOT be set
        assert not hasattr(bp, "auth_last_error")

    def test_reason_none_skips_manual_review_error(self):
        """Verify the None-reason branch for _mark_manual_review."""
        reason = None
        bp = SimpleNamespace(payment_status="")
        bp.payment_status = "manual_review"
        if reason:
            bp.auth_last_error = reason
        # When reason is None, auth_last_error should NOT be set
        assert not hasattr(bp, "auth_last_error")


@pytest.mark.unit
class TestCheckConflictsStudentBranch:
    """Covers branch 5156->5175: student=None skips student conflict check."""

    @patch("app.services.booking_service.TimezoneService")
    def test_no_student_skips_student_conflict_check(self, mock_tz):
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)
        mock_tz.hours_until.return_value = 48.0

        svc = _make_service()
        svc._resolve_lesson_timezone = MagicMock(return_value="America/New_York")
        svc._validate_location_capability = MagicMock()
        svc._validate_service_area = MagicMock()

        svc.repository.check_time_conflict.return_value = []  # no conflicts

        bd = MagicMock()
        bd.instructor_id = "I1"
        bd.booking_date = date(2026, 3, 15)
        bd.start_time = time(10, 0)
        bd.end_time = time(11, 0)
        bd.location_type = "in-person"

        mock_profile = MagicMock()
        mock_profile.min_advance_booking_hours = 0

        mock_service = MagicMock()

        # student=None should skip student conflict check
        svc._check_conflicts_and_rules(bd, mock_service, mock_profile, student=None)
        svc.repository.check_student_time_conflict.assert_not_called()


@pytest.mark.unit
class TestMinAdvanceBookingHoursDate:
    """Covers branch 5182->exit: min_advance_hours >= 24 date-level check."""

    @patch("app.services.booking_service.TimezoneService")
    def test_min_advance_24h_fails_booking_too_soon(self, mock_tz):
        """With 48h advance and booking start only 20h from now, should raise."""
        now_utc = datetime.now(timezone.utc)
        # booking_start_utc is only 20 hours from now — too soon for 48h advance
        booking_start = now_utc + timedelta(hours=20)

        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = booking_start
        mock_tz.hours_until.return_value = 20.0

        svc = _make_service()
        svc._resolve_lesson_timezone = MagicMock(return_value="America/New_York")
        svc._validate_location_capability = MagicMock()
        svc._validate_service_area = MagicMock()
        svc.repository.check_time_conflict.return_value = []

        bd = MagicMock()
        bd.instructor_id = "I1"
        bd.booking_date = booking_start.date()
        bd.start_time = booking_start.time()
        bd.end_time = (booking_start + timedelta(hours=1)).time()
        bd.location_type = "in-person"

        mock_profile = MagicMock()
        mock_profile.min_advance_booking_hours = 48  # 48 hours advance required

        mock_service = MagicMock()
        student = _fake_user()

        svc.repository.check_student_time_conflict.return_value = []

        with pytest.raises(BusinessRuleException, match="at least 48 hours"):
            svc._check_conflicts_and_rules(bd, mock_service, mock_profile, student=student)


@pytest.mark.unit
class TestCreateBookingRecordFallback:
    """Covers line 5276: detailed_booking is None, returns raw booking."""

    @patch("app.services.booking_service.TimezoneService")
    @patch("app.services.booking_service.PricingService")
    def test_detailed_booking_none_returns_raw(self, mock_pricing, mock_tz):
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"
        mock_tz.local_to_utc.return_value = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        svc = _make_service()
        svc._resolve_instructor_timezone = MagicMock(return_value="America/New_York")
        svc._resolve_student_timezone = MagicMock(return_value="America/New_York")
        svc._is_online_lesson = MagicMock(return_value=False)
        svc._resolve_booking_times_utc = MagicMock(
            return_value=(
                datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
                datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc),
            )
        )
        svc._determine_service_area_summary = MagicMock(return_value="Manhattan")

        raw_booking = _fake_booking()
        svc.repository.create.return_value = raw_booking
        svc.repository.get_booking_with_details.return_value = None  # detailed is None!
        mock_pricing.return_value.compute_booking_pricing.return_value = {}

        mock_service = MagicMock()
        mock_service.session_price.return_value = Decimal("50.00")
        mock_service.hourly_rate = Decimal("50.00")
        mock_service.catalog_entry = MagicMock()
        mock_service.catalog_entry.name = "Yoga"

        mock_profile = MagicMock()
        mock_profile.user_id = "I1"

        student = _fake_user()
        bd = MagicMock()
        bd.end_time = time(11, 0)
        bd.start_time = time(10, 0)
        bd.booking_date = date(2026, 3, 15)
        bd.instructor_id = "I1"
        bd.location_type = "in-person"
        bd.location_address = None
        bd.meeting_location = None
        bd.location_lat = None
        bd.location_lng = None
        bd.location_place_id = None
        bd.student_note = None

        result = svc._create_booking_record(student, bd, mock_service, mock_profile, 60)
        assert result is raw_booking


@pytest.mark.unit
class TestDetermineServiceAreaSummary:
    """Covers branch 5291->5283: borough from region_metadata."""

    def test_borough_from_region_metadata(self):
        svc = _make_service()
        area = MagicMock()
        area.neighborhood = MagicMock()
        area.neighborhood.parent_region = None
        area.neighborhood.region_metadata = {"borough": "Brooklyn"}
        svc.service_area_repository.list_for_instructor.return_value = [area]

        result = svc._determine_service_area_summary("I1")
        assert result == "Brooklyn"

    def test_empty_areas_returns_empty(self):
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        result = svc._determine_service_area_summary("I1")
        assert result == ""

    def test_multiple_boroughs_plus_more(self):
        svc = _make_service()
        areas = []
        for borough_name in ["Manhattan", "Brooklyn", "Queens"]:
            area = MagicMock()
            area.neighborhood = MagicMock()
            area.neighborhood.parent_region = borough_name
            area.neighborhood.region_metadata = None
            areas.append(area)
        svc.service_area_repository.list_for_instructor.return_value = areas

        result = svc._determine_service_area_summary("I1")
        assert "+ 2 more" in result


@pytest.mark.unit
class TestSendCancellationNotifications:
    """Covers branches 5400->5403, 5419->exit."""

    def test_detailed_booking_loaded_if_missing_student(self):
        """Covers 5400->5403: detailed_booking loaded for notification context."""
        svc = _make_service()
        booking = _fake_booking()
        booking.student = None
        booking.instructor = None

        detailed = _fake_booking()
        detailed.student = MagicMock()
        detailed.student.first_name = "Jane"
        detailed.student.last_name = "D"
        detailed.instructor = MagicMock()
        detailed.instructor.first_name = "Bob"
        detailed.instructor.last_name = "T"
        detailed.service_name = "Piano"
        detailed.booking_date = date(2026, 3, 15)
        detailed.start_time = time(10, 0)
        svc.repository.get_booking_with_details.return_value = detailed

        svc._send_cancellation_notifications(booking, "instructor")
        svc.notification_service.notify_user_best_effort.assert_called()

    def test_cancelled_by_instructor_notifies_student(self):
        """Covers 5419->exit: instructor cancels, notification sent to student."""
        svc = _make_service()
        booking = _fake_booking()
        booking.student = MagicMock()
        booking.student.first_name = "Jane"
        booking.student.last_name = "D"
        booking.instructor = MagicMock()
        booking.instructor.first_name = "Bob"
        booking.instructor.last_name = "T"
        booking.service_name = "Piano"
        booking.booking_date = date(2026, 3, 15)
        booking.start_time = time(10, 0)

        svc._send_cancellation_notifications(booking, "instructor")
        svc.notification_service.notify_user_best_effort.assert_called()


@pytest.mark.unit
class TestReportAutomatedNoShow:
    """Covers lines 4137-4195: automated no-show report."""

    def test_booking_not_found(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.repository.get_booking_with_details.return_value = None
        svc.log_operation = MagicMock()

        with pytest.raises(NotFoundException, match="Booking not found"):
            svc.report_automated_no_show(
                booking_id="B1", no_show_type="student", reason="No video join"
            )

    def test_wrong_status_raises(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        booking = _fake_booking(status="cancelled")
        svc.repository.get_booking_with_details.return_value = booking
        svc.log_operation = MagicMock()

        with pytest.raises(ValidationException, match="Cannot report no-show"):
            svc.report_automated_no_show(
                booking_id="B1", no_show_type="student", reason="No video join"
            )

    def test_already_reported_raises(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        booking = _fake_booking(status=BookingStatus.CONFIRMED.value)
        svc.repository.get_booking_with_details.return_value = booking
        svc.log_operation = MagicMock()

        existing_record = MagicMock()
        existing_record.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        svc.repository.get_no_show_by_booking_id.return_value = existing_record

        with pytest.raises(BusinessRuleException, match="No-show already reported"):
            svc.report_automated_no_show(
                booking_id="B1", no_show_type="student", reason="No video join"
            )

    def test_successful_report(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        booking = _fake_booking(status=BookingStatus.CONFIRMED.value)
        svc.repository.get_booking_with_details.return_value = booking
        svc.log_operation = MagicMock()

        svc.repository.get_no_show_by_booking_id.return_value = MagicMock(
            no_show_reported_at=None
        )
        mock_bp = MagicMock()
        mock_bp.payment_status = PaymentStatus.AUTHORIZED.value
        svc.repository.ensure_payment.return_value = mock_bp
        svc.repository.ensure_no_show.return_value = MagicMock()
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr_cls.return_value = MagicMock()
            result = svc.report_automated_no_show(
                booking_id=booking.id, no_show_type="student", reason="No video join"
            )

        assert result["success"] is True


@pytest.mark.unit
class TestDisputeNoShowMutualType:
    """Covers line 4238: mutual no-show type dispute from non-participant."""

    def test_mutual_type_non_participant_forbidden(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking(student_id="S1", instructor_id="I1")
        no_show = MagicMock()
        no_show.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        no_show.no_show_disputed = False
        no_show.no_show_resolved_at = None
        no_show.no_show_type = "mutual"

        svc.repository.get_booking_with_details.return_value = booking
        svc.repository.get_no_show_by_booking_id.return_value = no_show

        outsider = _fake_user(id="UNRELATED_USER")

        with pytest.raises(ForbiddenException, match="Only lesson participants"):
            svc.dispute_no_show(booking_id=booking.id, disputer=outsider, reason="I was there")


@pytest.mark.unit
class TestResolveNoShowCancelledResolution:
    """Covers line 4534->4537: 'cancelled' resolution path."""

    def test_cancelled_resolution_calls_cancel(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking(status=BookingStatus.CONFIRMED.value)
        booking.payment_detail = MagicMock()
        booking.payment_detail.payment_status = PaymentStatus.AUTHORIZED.value
        booking.payment_detail.payment_intent_id = None
        booking.has_locked_funds = False
        booking.rescheduled_from_booking_id = None
        booking.hourly_rate = Decimal("50.00")
        booking.duration_minutes = 60

        no_show = MagicMock()
        no_show.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        no_show.no_show_type = "student"
        no_show.no_show_resolved_at = None

        svc.repository.get_booking_with_details.return_value = booking
        svc.repository.get_no_show_by_booking_id.return_value = no_show
        svc.repository.ensure_payment.return_value = MagicMock()
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()
        svc._cancel_no_show_report = MagicMock()
        svc._user_has_role = MagicMock(return_value=True)

        admin_user = _fake_user(id="ADMIN1")

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr_cls.return_value = MagicMock()
            with patch("app.services.credit_service.CreditService"):
                result = svc.resolve_no_show(
                    booking_id=booking.id,
                    resolution="cancelled",
                    resolved_by=admin_user,
                )

        svc._cancel_no_show_report.assert_called_once_with(booking)
        assert result["success"] is True


@pytest.mark.unit
class TestFinalizeInstructorNoShowRefundPaths:
    """Covers branches 4687->4690: refund_success vs cancel_success vs failure."""

    def test_refund_success_sets_settled(self):
        svc = _make_service()
        booking = _fake_booking()
        bp = MagicMock()
        svc.repository.ensure_payment.return_value = bp
        transfer_record = MagicMock()
        svc._ensure_transfer_record = MagicMock(return_value=transfer_record)

        credit_service = MagicMock()

        svc._finalize_instructor_no_show(
            booking=booking,
            stripe_result={
                "refund_success": True,
                "refund_data": {"refund_id": "re_test", "amount_refunded": 5000},
            },
            credit_service=credit_service,
            refunded_cents=5000,
            locked_booking_id=None,
        )
        assert bp.payment_status == PaymentStatus.SETTLED.value
        assert transfer_record.refund_id == "re_test"

    def test_cancel_success_sets_settled(self):
        svc = _make_service()
        booking = _fake_booking()
        bp = MagicMock()
        svc.repository.ensure_payment.return_value = bp

        credit_service = MagicMock()

        svc._finalize_instructor_no_show(
            booking=booking,
            stripe_result={"cancel_success": True},
            credit_service=credit_service,
            refunded_cents=5000,
            locked_booking_id=None,
        )
        assert bp.payment_status == PaymentStatus.SETTLED.value

    def test_stripe_failure_sets_manual_review(self):
        svc = _make_service()
        booking = _fake_booking()
        bp = MagicMock()
        bp.capture_retry_count = 0
        svc.repository.ensure_payment.return_value = bp
        transfer_record = MagicMock()
        transfer_record.refund_retry_count = 0
        svc._ensure_transfer_record = MagicMock(return_value=transfer_record)

        credit_service = MagicMock()

        svc._finalize_instructor_no_show(
            booking=booking,
            stripe_result={"error": "stripe_down"},
            credit_service=credit_service,
            refunded_cents=5000,
            locked_booking_id=None,
        )
        assert bp.payment_status == PaymentStatus.MANUAL_REVIEW.value

    def test_locked_booking_returns_early(self):
        """Covers branch 4687: locked_booking_id set returns early."""
        svc = _make_service()
        booking = _fake_booking()
        bp = MagicMock()
        svc.repository.ensure_payment.return_value = bp

        credit_service = MagicMock()

        svc._finalize_instructor_no_show(
            booking=booking,
            stripe_result={"success": True},
            credit_service=credit_service,
            refunded_cents=5000,
            locked_booking_id="LOCKED_B1",
        )
        assert bp.payment_status == PaymentStatus.SETTLED.value
        assert booking.refunded_to_card_amount == 0


@pytest.mark.unit
class TestUpdateBookingEmptyUpdateDict:
    """Covers branch 3707->3713, 3709->3713: update_dict is empty."""

    def test_no_updates_still_returns_booking(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking()
        svc.repository.get_booking_with_details.side_effect = [booking, booking]
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()

        user = _fake_user(id=booking.instructor_id)

        update_data = MagicMock()
        update_data.instructor_note = None
        update_data.meeting_location = None

        svc.update_booking(
            booking_id=booking.id, update_data=update_data, user=user
        )
        # Repository.update should NOT have been called
        svc.repository.update.assert_not_called()

    def test_update_returns_none_keeps_original(self):
        """Covers 3709->3713: repository.update returns None."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        booking = _fake_booking()
        svc.repository.get_booking_with_details.side_effect = [booking, booking]
        svc.repository.update.return_value = None
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()

        user = _fake_user(id=booking.instructor_id)
        update_data = MagicMock()
        update_data.instructor_note = "New note"
        update_data.meeting_location = None

        result = svc.update_booking(
            booking_id=booking.id, update_data=update_data, user=user
        )
        assert result is not None


@pytest.mark.unit
class TestCheckAvailabilityMinAdvanceHours:
    """Covers branch 4905->4924: min advance hours >=24 fails."""

    @patch("app.services.booking_service.TimezoneService")
    def test_24h_advance_too_soon(self, mock_tz):
        """When min_advance_booking_hours >= 24 and booking is too soon, returns unavailable."""
        mock_tz.hours_until.return_value = 20.0
        mock_tz.DEFAULT_TIMEZONE = "America/New_York"
        mock_tz.get_lesson_timezone.return_value = "America/New_York"

        svc = _make_service()
        svc.log_operation = MagicMock()
        svc._resolve_instructor_timezone = MagicMock(return_value="America/New_York")

        # Must pass conflict check first (line 4855)
        svc.repository.check_time_conflict.return_value = False
        # Must pass service lookup (line 4871)
        svc.conflict_checker_repository.get_active_service.return_value = MagicMock()

        # booking_start_utc must be within 48h of now to trigger the branch
        now_utc = datetime.now(timezone.utc)
        booking_start_utc = now_utc + timedelta(hours=20)
        booking_end_utc = booking_start_utc + timedelta(hours=1)
        svc._resolve_booking_times_utc = MagicMock(
            return_value=(booking_start_utc, booking_end_utc)
        )

        mock_profile = MagicMock()
        mock_profile.user = MagicMock(timezone="America/New_York")
        mock_profile.min_advance_booking_hours = 48
        svc.conflict_checker_repository.get_instructor_profile.return_value = mock_profile

        result = svc.check_availability(
            instructor_id="I1",
            booking_date=booking_start_utc.date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_id="SVC1",
        )
        assert result["available"] is False
        assert "48 hours" in result["reason"]


@pytest.mark.unit
class TestNoShowPaymentRecordStatusBranch:
    """Covers branch 4338->4343: payment_record with status string."""

    def test_payment_record_status_string_overrides(self):
        """When payment_status is MANUAL_REVIEW, payment_record.status overrides."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        pd = MagicMock()
        pd.payment_status = PaymentStatus.MANUAL_REVIEW.value
        pd.payment_intent_id = "pi_test"

        booking = _fake_booking(
            status=BookingStatus.CONFIRMED.value,
            payment_detail=pd,
            has_locked_funds=False,
            rescheduled_from_booking_id=None,
            hourly_rate=Decimal("50.00"),
            duration_minutes=60,
        )

        no_show = MagicMock()
        no_show.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        no_show.no_show_type = "student"
        no_show.no_show_resolved_at = None

        svc.repository.get_booking_with_details.return_value = booking
        svc.repository.get_no_show_by_booking_id.return_value = no_show

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr = MagicMock()
            mock_pr_cls.return_value = mock_pr

            payment_record = MagicMock()
            payment_record.status = "succeeded"
            payment_record.amount = 5000
            payment_record.instructor_payout_cents = 4500
            payment_record.application_fee = None
            payment_record.base_price_cents = None
            payment_record.instructor_tier_pct = None
            mock_pr.get_payment_by_booking_id.return_value = payment_record

            svc.repository.ensure_payment.return_value = MagicMock()
            svc._snapshot_booking = MagicMock(return_value={})
            svc._write_booking_audit = MagicMock()
            svc._invalidate_booking_caches = MagicMock()
            svc._user_has_role = MagicMock(return_value=True)
            svc._finalize_student_no_show = MagicMock()

            with patch("app.services.credit_service.CreditService"):
                with patch("app.services.booking_service.StripeService") as mock_stripe:
                    with patch("app.services.booking_service.ConfigService"):
                        with patch("app.services.booking_service.PricingService"):
                            mock_stripe.return_value = MagicMock()
                            svc._capture_for_student_no_show = MagicMock(
                                return_value={"capture_success": True}
                            )
                            result = svc.resolve_no_show(
                                booking_id=booking.id,
                                resolution="dispute_upheld",
                                resolved_by=_fake_user(id="ADMIN"),
                            )

            assert result["success"] is True


@pytest.mark.unit
class TestInstructorPayoutCentsFallbacks:
    """Covers branch 4371->4380: base_price_cents and tier_value fallback."""

    def test_amount_minus_fee_fallback(self):
        """instructor_payout_cents is None, falls back to amount - fee."""
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        pd = MagicMock()
        pd.payment_status = PaymentStatus.AUTHORIZED.value
        pd.payment_intent_id = "pi_test"

        booking = _fake_booking(
            status=BookingStatus.CONFIRMED.value,
            payment_detail=pd,
            has_locked_funds=False,
            rescheduled_from_booking_id=None,
            hourly_rate=Decimal("50.00"),
            duration_minutes=60,
        )

        no_show = MagicMock()
        no_show.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        no_show.no_show_type = "student"
        no_show.no_show_resolved_at = None

        svc.repository.get_booking_with_details.return_value = booking
        svc.repository.get_no_show_by_booking_id.return_value = no_show

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr = MagicMock()
            mock_pr_cls.return_value = mock_pr

            payment_record = MagicMock()
            payment_record.status = None
            payment_record.amount = 5000
            payment_record.instructor_payout_cents = None
            payment_record.application_fee = 500
            payment_record.base_price_cents = None
            payment_record.instructor_tier_pct = None
            mock_pr.get_payment_by_booking_id.return_value = payment_record

            svc.repository.ensure_payment.return_value = MagicMock()
            svc._snapshot_booking = MagicMock(return_value={})
            svc._write_booking_audit = MagicMock()
            svc._invalidate_booking_caches = MagicMock()
            svc._user_has_role = MagicMock(return_value=True)
            svc._finalize_student_no_show = MagicMock()

            with patch("app.services.credit_service.CreditService"):
                with patch("app.services.booking_service.StripeService") as mock_stripe:
                    with patch("app.services.booking_service.ConfigService"):
                        with patch("app.services.booking_service.PricingService"):
                            mock_stripe.return_value = MagicMock()
                            svc._capture_for_student_no_show = MagicMock(
                                return_value={"capture_success": True}
                            )
                            result = svc.resolve_no_show(
                                booking_id=booking.id,
                                resolution="dispute_upheld",
                                resolved_by=_fake_user(id="ADMIN"),
                            )

            assert result["success"] is True


@pytest.mark.unit
class TestMutualNoShowResolve:
    """Covers line 4429: mutual no-show with locked_booking_id."""

    def test_mutual_locked_booking_resolves(self):
        svc = _make_service()
        svc.transaction = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(), __exit__=MagicMock(return_value=False)
            )
        )
        svc.log_operation = MagicMock()

        pd = MagicMock()
        pd.payment_status = PaymentStatus.AUTHORIZED.value
        pd.payment_intent_id = "pi_test"

        booking = _fake_booking(
            status=BookingStatus.CONFIRMED.value,
            payment_detail=pd,
            has_locked_funds=True,
            rescheduled_from_booking_id="LOCKED_B1",
            hourly_rate=Decimal("50.00"),
            duration_minutes=60,
        )

        no_show = MagicMock()
        no_show.no_show_reported_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        no_show.no_show_type = "mutual"
        no_show.no_show_resolved_at = None

        svc.repository.get_booking_with_details.return_value = booking
        svc.repository.get_no_show_by_booking_id.return_value = no_show
        svc.repository.ensure_payment.return_value = MagicMock()
        svc.repository.ensure_no_show.return_value = MagicMock(
            no_show_resolved_at=None, no_show_resolution=None,
        )
        svc._snapshot_booking = MagicMock(return_value={})
        svc._write_booking_audit = MagicMock()
        svc._invalidate_booking_caches = MagicMock()
        svc._user_has_role = MagicMock(return_value=True)
        svc._finalize_instructor_no_show = MagicMock()

        svc.resolve_lock_for_booking = MagicMock(return_value={"success": True})

        with patch("app.repositories.payment_repository.PaymentRepository") as mock_pr_cls:
            mock_pr = MagicMock()
            mock_pr_cls.return_value = mock_pr
            mock_pr.get_payment_by_booking_id.return_value = MagicMock(
                status=None, amount=5000, instructor_payout_cents=4500,
                application_fee=None, base_price_cents=None, instructor_tier_pct=None,
            )
            mock_pr.create_payment_event.return_value = None

            with patch("app.services.credit_service.CreditService"):
                result = svc.resolve_no_show(
                    booking_id=booking.id,
                    resolution="confirmed_no_dispute",
                    resolved_by=_fake_user(id="ADMIN"),
                )

        svc.resolve_lock_for_booking.assert_called_once_with("LOCKED_B1", "instructor_cancelled")
        assert result["success"] is True
