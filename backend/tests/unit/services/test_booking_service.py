"""Additional core booking_service coverage focused on helper flows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.exceptions import BusinessRuleException, ValidationException
from app.core.ulid_helper import generate_ulid
from app.models.booking import BookingStatus, PaymentStatus
from app.services.booking_service import BookingService

REAL_DATETIME = datetime


def _transaction_cm() -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    return cm


def _freeze_time(monkeypatch: pytest.MonkeyPatch, target: datetime) -> None:
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return target.astimezone(tz)
            if target.tzinfo:
                return target.replace(tzinfo=None)
            return target

        @classmethod
        def combine(cls, *args, **kwargs):
            return REAL_DATETIME.combine(*args, **kwargs)

    monkeypatch.setattr("app.services.booking_service.datetime", _FixedDateTime)


def make_booking(**overrides: object) -> SimpleNamespace:
    booking = SimpleNamespace(
        id=overrides.get("id", generate_ulid()),
        student_id=overrides.get("student_id", generate_ulid()),
        instructor_id=overrides.get("instructor_id", generate_ulid()),
        status=overrides.get("status", BookingStatus.CONFIRMED),
        payment_status=overrides.get("payment_status", PaymentStatus.AUTHORIZED.value),
        booking_date=overrides.get("booking_date", date(2030, 1, 1)),
        start_time=overrides.get("start_time", time(10, 0)),
        end_time=overrides.get("end_time", time(11, 0)),
        created_at=overrides.get("created_at", datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)),
        instructor_service=overrides.get("instructor_service", None),
        student=overrides.get("student", None),
        instructor=overrides.get("instructor", None),
        payment_intent_id=overrides.get("payment_intent_id", "pi_123"),
    )
    for key, value in overrides.items():
        setattr(booking, key, value)
    return booking


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.check_time_conflict.return_value = False
    repo.check_student_time_conflict.return_value = []
    repo.get_by_id.return_value = None
    return repo


@pytest.fixture
def booking_service(mock_db: MagicMock, mock_repository: MagicMock) -> BookingService:
    service = BookingService(
        mock_db,
        notification_service=MagicMock(),
        event_publisher=MagicMock(),
        repository=mock_repository,
        conflict_checker_repository=MagicMock(),
        system_message_service=MagicMock(),
    )
    service.transaction = MagicMock(return_value=_transaction_cm())
    service.cache_service = MagicMock()
    service.service_area_repository = MagicMock()
    return service


# --- check_availability ---

def test_check_availability_conflict_returns_unavailable(booking_service: BookingService) -> None:
    booking_service.repository.check_time_conflict.return_value = True

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=generate_ulid(),
    )

    assert result["available"] is False
    assert "conflicts" in result["reason"].lower()


def test_check_availability_missing_service_id_returns_unavailable(
    booking_service: BookingService,
) -> None:
    booking_service.repository.check_time_conflict.return_value = False

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=None,
        instructor_service_id=None,
    )

    assert result["available"] is False
    assert "service" in result["reason"].lower()


def test_check_availability_instructor_profile_missing(booking_service: BookingService) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = SimpleNamespace()
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = None

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=generate_ulid(),
    )

    assert result["available"] is False
    assert "profile" in result["reason"].lower()


def test_check_availability_booking_time_validation_error(
    booking_service: BookingService,
) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = SimpleNamespace()
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = SimpleNamespace(
        min_advance_booking_hours=0,
        user=SimpleNamespace(timezone="UTC"),
    )
    booking_service._resolve_booking_times_utc = Mock(
        side_effect=BusinessRuleException("invalid time")
    )

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=generate_ulid(),
    )

    assert result["available"] is False
    assert result["reason"] == "invalid time"


def test_check_availability_min_advance_over_24(booking_service: BookingService, monkeypatch: pytest.MonkeyPatch) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = SimpleNamespace()
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = SimpleNamespace(
        min_advance_booking_hours=24,
        user=SimpleNamespace(timezone="UTC"),
    )

    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    _freeze_time(monkeypatch, fixed_now)
    booking_start = fixed_now + timedelta(hours=23)
    booking_service._resolve_booking_times_utc = Mock(return_value=(booking_start, booking_start))

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=generate_ulid(),
    )

    assert result["available"] is False
    assert "at least 24" in result["reason"].lower()


def test_check_availability_min_advance_under_24(booking_service: BookingService) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = SimpleNamespace()
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = SimpleNamespace(
        min_advance_booking_hours=2,
        user=SimpleNamespace(timezone="UTC"),
    )
    booking_service._resolve_booking_times_utc = Mock(
        return_value=(datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc), datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc))
    )

    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=1):
        result = booking_service.check_availability(
            instructor_id=generate_ulid(),
            booking_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_id=generate_ulid(),
        )

    assert result["available"] is False
    assert "at least 2" in result["reason"].lower()


def test_check_availability_available_true(booking_service: BookingService) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = SimpleNamespace()
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = SimpleNamespace(
        min_advance_booking_hours=0,
        user=SimpleNamespace(timezone="UTC"),
    )
    booking_service._resolve_booking_times_utc = Mock(
        return_value=(datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc), datetime(2030, 1, 1, 11, 0, tzinfo=timezone.utc))
    )

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=generate_ulid(),
    )

    assert result["available"] is True
    assert result["time_info"]["date"] == "2030-01-01"


# --- location capability ---

@pytest.mark.parametrize(
    ("location_type", "flags", "code"),
    [
        ("student_location", {"offers_travel": False}, "TRAVEL_NOT_OFFERED"),
        ("neutral_location", {"offers_travel": False}, "TRAVEL_NOT_OFFERED"),
        ("instructor_location", {"offers_at_location": False}, "AT_LOCATION_NOT_OFFERED"),
        (None, {"offers_online": False}, "ONLINE_NOT_OFFERED"),
    ],
)
def test_validate_location_capability_errors(
    booking_service: BookingService, location_type: str | None, flags: dict[str, bool], code: str
) -> None:
    service = SimpleNamespace(
        offers_travel=flags.get("offers_travel", True),
        offers_at_location=flags.get("offers_at_location", True),
        offers_online=flags.get("offers_online", True),
    )

    with pytest.raises(ValidationException) as exc_info:
        booking_service._validate_location_capability(service, location_type)

    assert exc_info.value.code == code


# --- conflict checks ---


def test_check_conflicts_and_rules_min_advance_over_24(
    booking_service: BookingService, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking_data = SimpleNamespace(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        location_type="online",
    )
    service = SimpleNamespace()
    instructor_profile = SimpleNamespace(min_advance_booking_hours=24, user=SimpleNamespace(timezone="UTC"))
    student = SimpleNamespace(id=generate_ulid())

    booking_service._validate_location_capability = Mock()
    booking_service._validate_service_area = Mock()
    booking_service._resolve_lesson_timezone = Mock(return_value="UTC")

    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    _freeze_time(monkeypatch, fixed_now)
    booking_start = fixed_now + timedelta(hours=23)
    booking_service._resolve_booking_times_utc = Mock(return_value=(booking_start, booking_start))

    with pytest.raises(BusinessRuleException):
        booking_service._check_conflicts_and_rules(
            booking_data, service, instructor_profile, student
        )


def test_check_conflicts_and_rules_min_advance_under_24(booking_service: BookingService) -> None:
    booking_data = SimpleNamespace(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        location_type="online",
    )
    service = SimpleNamespace()
    instructor_profile = SimpleNamespace(min_advance_booking_hours=3, user=SimpleNamespace(timezone="UTC"))
    student = SimpleNamespace(id=generate_ulid())

    booking_service._validate_location_capability = Mock()
    booking_service._validate_service_area = Mock()
    booking_service._resolve_lesson_timezone = Mock(return_value="UTC")
    booking_service._resolve_booking_times_utc = Mock(
        return_value=(datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc), datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc))
    )

    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=1):
        with pytest.raises(BusinessRuleException):
            booking_service._check_conflicts_and_rules(
                booking_data, service, instructor_profile, student
            )


# --- availability windows/opportunities ---


def test_get_instructor_availability_windows_filters_by_range(
    booking_service: BookingService,
) -> None:
    with patch(
        "app.repositories.availability_day_repository.AvailabilityDayRepository"
    ) as repo_cls, patch(
        "app.utils.bitset.windows_from_bits"
    ) as windows_from_bits:
        repo_cls.return_value.get_day_bits.return_value = b"\xff"
        windows_from_bits.return_value = [
            ("06:00:00", "08:00:00"),
            ("09:00:00", "11:00:00"),
            ("22:00:00", "23:00:00"),
        ]

        result = booking_service._get_instructor_availability_windows(
            instructor_id=generate_ulid(),
            target_date=date(2030, 1, 1),
            earliest_time=time(8, 0),
            latest_time=time(21, 0),
        )

    assert len(result) == 1
    assert result[0]["start_time"] == time(9, 0)


def test_calculate_booking_opportunities_skips_empty_slot(
    booking_service: BookingService,
) -> None:
    booking_service._find_opportunities_in_slot = Mock(return_value=[{"slot": "ok"}])

    windows = [
        {"_start_minutes": 600, "_end_minutes": 590},
        {"_start_minutes": 540, "_end_minutes": 660},
    ]

    result = booking_service._calculate_booking_opportunities(
        availability_windows=windows,
        existing_bookings=[],
        target_duration_minutes=60,
        earliest_time=time(9, 0),
        latest_time=time(11, 0),
        instructor_id=generate_ulid(),
        target_date=date(2030, 1, 1),
    )

    assert result == [{"slot": "ok"}]


def test_find_opportunities_in_slot_advances_after_conflict(
    booking_service: BookingService,
) -> None:
    existing = [SimpleNamespace(start_time=time(10, 0), end_time=time(11, 0))]

    result = booking_service._find_opportunities_in_slot(
        slot_start=540,
        slot_end=720,
        existing_bookings=existing,
        target_duration_minutes=60,
        instructor_id=generate_ulid(),
        target_date=date(2030, 1, 1),
    )

    assert [slot["start_time"] for slot in result] == ["09:00:00", "11:00:00"]


# --- summary/format helpers ---


def test_determine_service_area_summary_formats_boroughs(booking_service: BookingService) -> None:
    areas = [
        SimpleNamespace(
            neighborhood=SimpleNamespace(parent_region="Queens", region_metadata={})
        ),
        SimpleNamespace(
            neighborhood=SimpleNamespace(parent_region="Brooklyn", region_metadata={"borough": "Brooklyn"})
        ),
        SimpleNamespace(
            neighborhood=SimpleNamespace(parent_region="Manhattan", region_metadata={"borough": "Manhattan"})
        ),
    ]
    booking_service.service_area_repository.list_for_instructor.return_value = areas

    summary = booking_service._determine_service_area_summary(generate_ulid())

    assert summary == "Brooklyn + 2 more"


def test_determine_service_area_summary_empty(booking_service: BookingService) -> None:
    booking_service.service_area_repository.list_for_instructor.return_value = []

    assert booking_service._determine_service_area_summary(generate_ulid()) == ""


def test_format_helpers() -> None:
    user = SimpleNamespace(first_name="Ada", last_name="Lovelace")
    booking = SimpleNamespace(
        booking_date=date(2030, 1, 2),
        start_time=time(9, 0),
        service_name=None,
        instructor_service=SimpleNamespace(name="Piano"),
    )

    assert BookingService._format_user_display_name(user) == "Ada L."
    assert BookingService._format_booking_date(booking) == "January 2"
    assert BookingService._format_booking_time(booking) == "9:00 AM"
    assert BookingService._resolve_service_name(booking) == "Piano"


def test_resolve_service_name_default() -> None:
    booking = SimpleNamespace(service_name=None, instructor_service=None)

    assert BookingService._resolve_service_name(booking) == "Lesson"


# --- notifications ---


def test_send_booking_notifications_skips_reschedule(booking_service: BookingService) -> None:
    booking_service.notification_service.notify_user_best_effort = Mock()
    booking = make_booking()

    booking_service._send_booking_notifications(booking, is_reschedule=True)

    booking_service.notification_service.notify_user_best_effort.assert_not_called()


def test_send_booking_notifications_success(booking_service: BookingService) -> None:
    booking_service.notification_service.notify_user_best_effort = Mock()
    booking = make_booking(
        student=SimpleNamespace(first_name="Ada", last_name="Lovelace"),
        instructor=SimpleNamespace(first_name="Alan", last_name="Turing"),
        instructor_service=SimpleNamespace(name="Piano"),
    )

    booking_service._send_booking_notifications(booking, is_reschedule=False)

    assert booking_service.notification_service.notify_user_best_effort.call_count == 2


def test_send_booking_notifications_after_confirmation_handles_errors(
    booking_service: BookingService,
) -> None:
    booking = make_booking()
    booking_service.repository.get_booking_with_details.return_value = booking
    booking_service._send_booking_notifications = Mock()
    booking_service.notification_service.send_booking_confirmation.side_effect = Exception("boom")

    booking_service.send_booking_notifications_after_confirmation(booking.id)

    booking_service._send_booking_notifications.assert_called_once_with(booking, False)


def test_send_booking_notifications_after_confirmation_no_service(booking_service: BookingService) -> None:
    booking_service.notification_service = None

    booking_service.send_booking_notifications_after_confirmation(generate_ulid())


def test_send_cancellation_notifications_student_role(booking_service: BookingService) -> None:
    booking = make_booking(student=None, instructor=None)
    details = make_booking(
        id=booking.id,
        student=SimpleNamespace(first_name="Student", last_name="One"),
        instructor=SimpleNamespace(first_name="Instructor", last_name="Two"),
    )
    booking_service.repository.get_booking_with_details.return_value = details
    booking_service.notification_service.notify_user_best_effort = Mock()

    booking_service._send_cancellation_notifications(booking, "student")

    booking_service.notification_service.notify_user_best_effort.assert_called_once()


def test_send_cancellation_notifications_instructor_role(booking_service: BookingService) -> None:
    booking = make_booking(student=None, instructor=None)
    details = make_booking(
        id=booking.id,
        student=SimpleNamespace(first_name="Student", last_name="One"),
        instructor=SimpleNamespace(first_name="Instructor", last_name="Two"),
    )
    booking_service.repository.get_booking_with_details.return_value = details
    booking_service.notification_service.notify_user_best_effort = Mock()

    booking_service._send_cancellation_notifications(booking, "instructor")

    booking_service.notification_service.notify_user_best_effort.assert_called_once()


# --- post booking tasks ---


def test_handle_post_booking_tasks_confirmed_booking(booking_service: BookingService) -> None:
    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        instructor_service=SimpleNamespace(name="Piano"),
    )
    booking_service.event_publisher.publish = Mock()
    booking_service.system_message_service.create_booking_created_message = Mock()
    booking_service._send_booking_notifications = Mock()
    booking_service._invalidate_booking_caches = Mock()

    booking_service._handle_post_booking_tasks(booking, is_reschedule=False)

    booking_service.event_publisher.publish.assert_called_once()
    booking_service.system_message_service.create_booking_created_message.assert_called_once()
    booking_service._send_booking_notifications.assert_called_once_with(booking, False)


def test_handle_post_booking_tasks_reschedule_path(booking_service: BookingService) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    old_booking = make_booking()

    booking_service.system_message_service.create_booking_rescheduled_message = Mock()
    booking_service.system_message_service.create_booking_created_message = Mock()
    booking_service._send_booking_notifications = Mock()
    booking_service._invalidate_booking_caches = Mock()

    booking_service._handle_post_booking_tasks(
        booking, is_reschedule=True, old_booking=old_booking
    )

    booking_service.system_message_service.create_booking_rescheduled_message.assert_called_once()
    booking_service.system_message_service.create_booking_created_message.assert_not_called()


def test_handle_post_booking_tasks_system_message_failure(booking_service: BookingService) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    booking_service.event_publisher.publish = Mock()
    booking_service.system_message_service.create_booking_created_message.side_effect = Exception(
        "boom"
    )
    booking_service._send_booking_notifications = Mock()
    booking_service._invalidate_booking_caches = Mock()

    booking_service._handle_post_booking_tasks(booking, is_reschedule=False)

    booking_service._send_booking_notifications.assert_called_once()


# --- cache invalidation ---


def test_invalidate_booking_caches_handles_errors(booking_service: BookingService) -> None:
    booking = make_booking()
    cache = MagicMock()
    cache.invalidate_instructor_availability.side_effect = Exception("cache")
    cache.delete_pattern.side_effect = Exception("pattern")
    booking_service.cache_service = cache

    booking_service._invalidate_booking_caches(booking)

    cache.invalidate_instructor_availability.assert_called_once()
    cache.delete_pattern.assert_called()


def test_invalidate_booking_cache_id_missing(booking_service: BookingService) -> None:
    booking_service.repository.get_by_id.return_value = None
    booking_service._invalidate_booking_caches = Mock()

    booking_service.invalidate_booking_cache(generate_ulid())

    booking_service._invalidate_booking_caches.assert_not_called()


def test_invalidate_booking_cache_object(booking_service: BookingService) -> None:
    booking = make_booking()
    booking_service._invalidate_booking_caches = Mock()
    booking_service.repository.get_by_id.return_value = booking

    booking_service.invalidate_booking_cache(booking.id)

    booking_service._invalidate_booking_caches.assert_called_once_with(booking)


# --- pricing preview / payment summary ---


def test_get_booking_pricing_preview_missing_booking(booking_service: BookingService) -> None:
    booking_service.repository.get_by_id.return_value = None

    assert (
        booking_service.get_booking_pricing_preview(generate_ulid(), generate_ulid()) is None
    )


def test_get_booking_pricing_preview_access_denied(booking_service: BookingService) -> None:
    booking = make_booking(student_id="student", instructor_id="instructor")
    booking_service.repository.get_by_id.return_value = booking

    result = booking_service.get_booking_pricing_preview(booking.id, "other")

    assert result == {"error": "access_denied"}


def test_get_booking_pricing_preview_success(booking_service: BookingService) -> None:
    booking = make_booking(student_id="student", instructor_id="instructor")
    booking_service.repository.get_by_id.return_value = booking

    with patch("app.services.pricing_service.PricingService") as pricing_cls:
        pricing_cls.return_value.compute_booking_pricing.return_value = {"total": 100}
        result = booking_service.get_booking_pricing_preview(booking.id, "student", 0)

    assert result == {"total": 100}


def test_get_booking_with_payment_summary_not_found(booking_service: BookingService) -> None:
    booking_service.get_booking_for_user = Mock(return_value=None)
    user = SimpleNamespace(id=generate_ulid())

    assert booking_service.get_booking_with_payment_summary(generate_ulid(), user) is None


def test_get_booking_with_payment_summary_non_student(booking_service: BookingService) -> None:
    booking = make_booking(student_id="student")
    booking_service.get_booking_for_user = Mock(return_value=booking)
    user = SimpleNamespace(id="other")

    result = booking_service.get_booking_with_payment_summary(booking.id, user)

    assert result == (booking, None)


def test_get_booking_with_payment_summary_student(booking_service: BookingService) -> None:
    booking = make_booking(student_id="student")
    booking_service.get_booking_for_user = Mock(return_value=booking)
    user = SimpleNamespace(id="student")

    with patch("app.services.config_service.ConfigService") as config_cls, patch(
        "app.repositories.factory.RepositoryFactory"
    ) as repo_factory, patch(
        "app.repositories.review_repository.ReviewTipRepository"
    ) as tip_repo_cls, patch(
        "app.services.payment_summary_service.build_student_payment_summary"
    ) as build_summary:
        config_cls.return_value.get_pricing_config.return_value = ({"fees": True}, None)
        repo_factory.create_payment_repository.return_value = MagicMock()
        tip_repo_cls.return_value = MagicMock()
        build_summary.return_value = {"summary": True}

        result = booking_service.get_booking_with_payment_summary(booking.id, user)

    assert result == (booking, {"summary": True})


# --- misc helpers ---


def test_check_student_time_conflict_returns_false_on_exception(
    booking_service: BookingService,
) -> None:
    booking_service.repository.check_student_time_conflict.side_effect = Exception("boom")

    assert (
        booking_service.check_student_time_conflict(
            student_id=generate_ulid(),
            booking_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        is False
    )


def test_abort_pending_booking_handles_exception(booking_service: BookingService) -> None:
    booking_service.repository.get_by_id.side_effect = Exception("boom")

    assert booking_service.abort_pending_booking(generate_ulid()) is False
