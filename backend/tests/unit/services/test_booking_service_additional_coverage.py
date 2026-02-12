"""Additional coverage tests for booking_service.py remaining branches."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.enums import RoleName
from app.core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import BookingStatus, PaymentStatus
from app.schemas.booking import BookingUpdate
from app.services.booking_service import GENERIC_CONFLICT_MESSAGE, BookingService


def _transaction_cm() -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    return cm


def _role(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def make_user(*role_names: str, **kwargs: str) -> SimpleNamespace:
    user = SimpleNamespace(
        id=kwargs.get("id", generate_ulid()),
        roles=[_role(name) for name in role_names],
    )
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user


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
        duration_minutes=overrides.get("duration_minutes", 60),
        hourly_rate=overrides.get("hourly_rate", 100),
        total_price=overrides.get("total_price", 100),
        is_cancellable=overrides.get("is_cancellable", True),
        student=overrides.get("student", None),
        instructor=overrides.get("instructor", None),
        instructor_service=overrides.get("instructor_service", None),
        rescheduled_from_booking_id=overrides.get("rescheduled_from_booking_id", None),
        original_lesson_datetime=overrides.get("original_lesson_datetime", None),
        created_at=overrides.get("created_at", datetime(2030, 1, 1, 8, 0, 0)),
        payment_intent_id=overrides.get("payment_intent_id", None),
        meeting_location=overrides.get("meeting_location", None),
        location_type=overrides.get("location_type", None),
        student_note=overrides.get("student_note", None),
        credits_reserved_cents=overrides.get("credits_reserved_cents", 0),
        confirmed_at=overrides.get("confirmed_at", None),
        cancelled_at=overrides.get("cancelled_at", None),
        completed_at=overrides.get("completed_at", None),
        booking_start_utc=overrides.get("booking_start_utc", None),
        booking_end_utc=overrides.get("booking_end_utc", None),
        lesson_timezone=overrides.get("lesson_timezone", None),
        instructor_tz_at_booking=overrides.get("instructor_tz_at_booking", None),
        lock_resolved_at=overrides.get("lock_resolved_at", None),
        lock_resolution=overrides.get("lock_resolution", None),
        locked_amount_cents=overrides.get("locked_amount_cents", None),
        locked_at=overrides.get("locked_at", None),
    )
    for key, value in overrides.items():
        setattr(booking, key, value)
    booking.cancel = Mock()
    booking.mark_no_show = Mock()
    booking.to_dict = Mock(return_value={"status": booking.status})
    booking.is_upcoming = Mock(return_value=False)
    return booking


def make_booking_data(**overrides: object) -> SimpleNamespace:
    data = SimpleNamespace(
        instructor_id=overrides.get("instructor_id", generate_ulid()),
        instructor_service_id=overrides.get("instructor_service_id", generate_ulid()),
        booking_date=overrides.get("booking_date", date(2030, 1, 1)),
        start_time=overrides.get("start_time", time(10, 0)),
        end_time=overrides.get("end_time", None),
        meeting_location=overrides.get("meeting_location", None),
        location_type=overrides.get("location_type", "online"),
        location_address=overrides.get("location_address", None),
        location_lat=overrides.get("location_lat", None),
        location_lng=overrides.get("location_lng", None),
        location_place_id=overrides.get("location_place_id", None),
        student_note=overrides.get("student_note", None),
    )
    return data


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.transaction.return_value = _transaction_cm()
    repo.get_booking_with_details.return_value = None
    repo.get_by_id.return_value = None
    repo.get_by_id_for_update.return_value = None
    repo.update.return_value = None
    repo.complete_booking.return_value = None
    repo.flush.return_value = None
    repo.get_bookings_by_time_range.return_value = []
    repo.check_time_conflict.return_value = False
    repo.check_student_time_conflict.return_value = []
    repo.ensure_transfer.return_value = SimpleNamespace(
        stripe_transfer_id=None,
        transfer_reversal_failed=False,
        transfer_reversal_retry_count=0,
        transfer_reversal_error=None,
        payout_transfer_failed_at=None,
        payout_transfer_error=None,
        payout_transfer_retry_count=0,
        transfer_failed_at=None,
        transfer_error=None,
        transfer_retry_count=0,
        refund_id=None,
        refund_failed_at=None,
        refund_error=None,
        refund_retry_count=0,
    )
    repo.get_transfer_by_booking_id.return_value = repo.ensure_transfer.return_value
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
    service.audit_repository = MagicMock()
    service.cache_service = MagicMock()
    service.service_area_repository = MagicMock()
    return service


def test_write_booking_audit_skips_when_disabled(booking_service: BookingService) -> None:
    booking = make_booking()
    with patch("app.services.booking_service.AUDIT_ENABLED", False):
        booking_service.audit_repository.write = MagicMock()
        booking_service._write_booking_audit(
            booking,
            "create",
            actor=None,
            before=None,
            after={"status": "confirmed"},
        )
    booking_service.audit_repository.write.assert_not_called()


def test_write_booking_audit_status_change_maps_terminal_actions(
    booking_service: BookingService,
) -> None:
    booking = make_booking()
    booking_service.audit_repository.write = Mock()

    with patch("app.services.booking_service.AUDIT_ENABLED", True):
        with patch("app.services.booking_service.AuditService") as audit_service_cls:
            booking_service._write_booking_audit(
                booking,
                "status_change",
                actor=None,
                before={"status": "confirmed"},
                after={"status": "completed"},
            )
            booking_service._write_booking_audit(
                booking,
                "status_change",
                actor=None,
                before={"status": "confirmed"},
                after={"status": "cancelled"},
            )

    actions = [
        call.kwargs["action"]
        for call in audit_service_cls.return_value.log_changes.call_args_list
    ]
    assert actions == ["booking.complete", "booking.cancel"]


def test_create_booking_integrity_error_with_scope(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._resolve_integrity_conflict_message = Mock(
        return_value=("conflict", "student")
    )

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=IntegrityError("stmt", "params", Exception("boom"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_booking(student, booking_data, selected_duration=60)

    assert exc_info.value.details.get("conflict_scope") == "student"


def test_create_booking_deadlock_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._is_deadlock_error = Mock(return_value=True)

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("deadlock"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_booking(student, booking_data, selected_duration=60)

    assert exc_info.value.message == GENERIC_CONFLICT_MESSAGE


def test_create_booking_repository_exception(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._raise_conflict_from_repo_error = Mock(
        side_effect=BookingConflictException(message="conflict", details={})
    )

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(side_effect=RepositoryException("repo"))

    with pytest.raises(BookingConflictException):
        booking_service.create_booking(student, booking_data, selected_duration=60)


def test_create_booking_with_payment_setup_reschedule_linkage(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.SCHEDULED.value,
        total_price=150,
    )
    updated_booking = make_booking(id=booking.id)
    previous_booking = make_booking(
        id=generate_ulid(),
        reschedule_count=1,
        late_reschedule_used=True,
    )

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._get_booking_start_utc = Mock(return_value=datetime(2030, 1, 1, 10, 0, 0))

    mock_repository.transaction.return_value = _transaction_cm()
    mock_repository.get_by_id.side_effect = [previous_booking, booking]
    mock_repository.update.return_value = updated_booking
    booking_service._create_booking_record = Mock(return_value=booking)

    with patch("app.services.stripe_service.StripeService") as mock_stripe_service:
        stripe_service = mock_stripe_service.return_value
        stripe_service.get_or_create_customer.return_value = SimpleNamespace(
            stripe_customer_id="cus_123"
        )
        with patch(
            "app.services.booking_service.stripe.SetupIntent.create",
            side_effect=Exception("boom"),
        ):
            with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
                payment_repo.return_value.create_payment_event = Mock()
                booking_service.create_booking_with_payment_setup(
                    student,
                    booking_data,
                    selected_duration=60,
                    rescheduled_from_booking_id=previous_booking.id,
                )

    assert updated_booking.reschedule_count == 2
    assert updated_booking.late_reschedule_used is True


def test_create_booking_with_payment_setup_refresh_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    booking = make_booking(total_price=100)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)

    mock_repository.transaction.return_value = _transaction_cm()
    mock_repository.get_by_id.return_value = None

    with patch("app.services.stripe_service.StripeService") as mock_stripe_service:
        stripe_service = mock_stripe_service.return_value
        stripe_service.get_or_create_customer.return_value = SimpleNamespace(
            stripe_customer_id="cus_123"
        )
        with patch("app.services.booking_service.stripe.SetupIntent.create"):
            with pytest.raises(NotFoundException):
                booking_service.create_booking_with_payment_setup(
                    student, booking_data, selected_duration=60
                )


def test_create_booking_with_payment_setup_deadlock_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=True)
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("deadlock"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_booking_with_payment_setup(student, booking_data, 60)

    assert exc_info.value.message == GENERIC_CONFLICT_MESSAGE


def test_create_rescheduled_booking_with_existing_payment_missing_original_in_tx(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking = make_booking()
    existing_booking = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)

    mock_repository.get_by_id.side_effect = [existing_booking, None]
    mock_repository.transaction.return_value = _transaction_cm()

    with pytest.raises(NotFoundException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing_booking.id,
            payment_intent_id="pi_123",
            payment_status=None,
            payment_method_id=None,
        )


def test_create_rescheduled_booking_with_existing_payment_instructor_mismatch_in_tx(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data(instructor_id=generate_ulid())
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    booking = make_booking()

    existing_booking = make_booking(instructor_id=generate_ulid())

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)

    mock_repository.get_by_id.side_effect = [existing_booking, existing_booking]
    mock_repository.transaction.return_value = _transaction_cm()

    with pytest.raises(BusinessRuleException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing_booking.id,
            payment_intent_id="pi_123",
            payment_status="requires_capture",
            payment_method_id="pm_123",
        )


def test_create_rescheduled_booking_with_existing_payment_credit_transfer_exception(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking = make_booking()
    old_booking = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)

    mock_repository.get_by_id.side_effect = [old_booking, old_booking]
    mock_repository.transaction.return_value = _transaction_cm()

    with patch("app.services.booking_service.RepositoryFactory.create_credit_repository") as credit_repo:
        credit_repo.return_value.get_reserved_credits_for_booking.side_effect = Exception("boom")
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
            payment_repo.return_value.get_payment_by_intent_id.return_value = None
            booking_service.create_rescheduled_booking_with_existing_payment(
                student,
                booking_data,
                selected_duration=60,
                original_booking_id=old_booking.id,
                payment_intent_id="pi_123",
                payment_status="requires_capture",
                payment_method_id="pm_123",
            )

    assert booking.payment_method_id == "pm_123"
    assert booking.payment_status == "requires_capture"


def test_create_rescheduled_booking_with_existing_payment_integrity_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._resolve_integrity_conflict_message = Mock(
        return_value=("conflict", "student")
    )

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=IntegrityError("stmt", "params", Exception("boom"))
    )
    mock_repository.get_by_id.return_value = make_booking(
        instructor_id=booking_data.instructor_id
    )

    with pytest.raises(BookingConflictException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=generate_ulid(),
            payment_intent_id="pi_123",
            payment_status=None,
            payment_method_id=None,
        )


def test_create_rescheduled_booking_with_locked_funds_missing_original_in_tx(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    booking = make_booking()

    existing_booking = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)

    mock_repository.get_by_id.side_effect = [existing_booking, None]
    mock_repository.transaction.return_value = _transaction_cm()

    with pytest.raises(NotFoundException):
        booking_service.create_rescheduled_booking_with_locked_funds(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing_booking.id,
        )


def test_confirm_booking_payment_gaming_reschedule_immediate_auth_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking = make_booking(
        status=BookingStatus.PENDING,
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        rescheduled_from_booking_id=generate_ulid(),
        original_lesson_datetime=datetime(2030, 1, 2, 10, 0, 0),
        created_at=datetime(2030, 1, 1, 12, 0, 0),
    )
    student.id = booking.student_id

    mock_repository.get_by_id.return_value = booking
    booking_service._get_booking_start_utc = Mock(return_value=datetime(2030, 1, 2, 10, 0, 0))
    booking_service._determine_auth_timing = Mock(
        return_value={
            "immediate": True,
            "scheduled_for": None,
            "initial_payment_status": PaymentStatus.SCHEDULED.value,
            "hours_until_lesson": 5.0,
        }
    )

    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.create_payment_event = Mock()
        with patch(
            "app.tasks.payment_tasks._process_authorization_for_booking",
            side_effect=Exception("boom"),
        ):
            with patch.object(booking_service.repository, "refresh", side_effect=Exception("no")):
                booking_service.confirm_booking_payment(
                    booking_id=booking.id,
                    student=student,
                    payment_method_id="pm_123",
                )


def test_confirm_booking_payment_system_message_fallback_and_cache_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking = make_booking(
        status=BookingStatus.PENDING,
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        rescheduled_from_booking_id=generate_ulid(),
    )
    booking.instructor_service = SimpleNamespace(name="Piano")
    student.id = booking.student_id

    mock_repository.get_by_id.return_value = booking
    booking_service._get_booking_start_utc = Mock(return_value=datetime(2030, 1, 2, 10, 0, 0))
    booking_service._determine_auth_timing = Mock(
        return_value={
            "immediate": False,
            "scheduled_for": datetime(2030, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            "initial_payment_status": PaymentStatus.SCHEDULED.value,
            "hours_until_lesson": 30.0,
        }
    )
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    booking_service.system_message_service.create_booking_created_message.side_effect = Exception(
        "boom"
    )
    booking_service._invalidate_booking_caches = Mock(side_effect=Exception("cache"))

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.create_payment_event = Mock()
        booking_service.confirm_booking_payment(
            booking_id=booking.id,
            student=student,
            payment_method_id="pm_123",
        )


def test_retry_authorization_credit_only_success(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value)
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    mock_repository.get_booking_with_details.return_value = booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with patch("app.services.stripe_service.StripeService") as stripe_service:
        stripe_service.return_value.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=0,
            applied_credit_cents=500,
        )
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
            payment_repo.return_value.get_default_payment_method.return_value = SimpleNamespace(
                stripe_payment_method_id="pm_123"
            )
            payment_repo.return_value.create_payment_event = Mock()

            result = booking_service.retry_authorization(booking_id=booking.id, user=user)

    assert result["success"] is True
    assert booking.payment_status == PaymentStatus.AUTHORIZED.value


def test_retry_authorization_credit_only_booking_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    user = make_user(RoleName.STUDENT.value)
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    mock_repository.get_booking_with_details.return_value = make_booking(
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    )

    with patch("app.services.stripe_service.StripeService") as stripe_service:
        stripe_service.return_value.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=0,
            applied_credit_cents=0,
        )
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
            payment_repo.return_value.get_default_payment_method.return_value = SimpleNamespace(
                stripe_payment_method_id="pm_123"
            )
            payment_repo.return_value.create_payment_event = Mock()
            mock_repository.get_booking_with_details.return_value = None
            with pytest.raises(NotFoundException):
                booking_service.retry_authorization(booking_id=generate_ulid(), user=user)


def test_retry_authorization_non_credit_missing_booking_in_transaction(
    booking_service: BookingService,
    mock_repository: MagicMock,
) -> None:
    booking = make_booking(
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_intent_id=None,
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    # First read succeeds, transactional refresh misses.
    mock_repository.get_booking_with_details.side_effect = [booking, None]

    with patch("app.services.stripe_service.StripeService") as stripe_service:
        stripe_service.return_value.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=2500,
            application_fee_cents=200,
        )
        stripe_service.return_value.create_or_retry_booking_payment_intent.return_value = (
            SimpleNamespace(id="pi_new", status="requires_capture")
        )
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
            payment_repo.return_value.get_default_payment_method.return_value = SimpleNamespace(
                stripe_payment_method_id="pm_123"
            )
            payment_repo.return_value.create_payment_event = Mock()

            with pytest.raises(NotFoundException):
                booking_service.retry_authorization(booking_id=booking.id, user=user)


def test_find_booking_opportunities_defaults(booking_service: BookingService) -> None:
    booking_service._get_instructor_availability_windows = Mock(return_value=[])
    booking_service._get_existing_bookings_for_date = Mock(return_value=[])
    booking_service._calculate_booking_opportunities = Mock(return_value=[])

    booking_service.find_booking_opportunities(
        instructor_id=generate_ulid(),
        target_date=date(2030, 1, 1),
        earliest_time=None,
        latest_time=None,
    )

    booking_service._get_instructor_availability_windows.assert_called_once()
    args = booking_service._get_instructor_availability_windows.call_args[0]
    assert args[2] == time(9, 0)
    assert args[3] == time(21, 0)


def test_cancel_booking_locked_reschedule_student_lt12(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.AUTHORIZED.value,
        has_locked_funds=True,
        rescheduled_from_booking_id=generate_ulid(),
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    booking_service._get_booking_start_utc = Mock(return_value=datetime(2030, 1, 1, 10, 0, 0))
    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=10):
        booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})
        booking_service._snapshot_booking = Mock(return_value={})
        booking_service._write_booking_audit = Mock()
        booking_service._enqueue_booking_outbox_event = Mock()
        booking_service._post_cancellation_actions = Mock()

        mock_repository.get_by_id_for_update.side_effect = [booking, booking]
        mock_repository.transaction.return_value = _transaction_cm()

        booking_service.cancel_booking(booking.id, user)

    assert booking.payment_status == PaymentStatus.SETTLED.value


def test_cancel_booking_not_found_after_stripe(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    booking_service._build_cancellation_context = Mock(return_value={
        "default_role": RoleName.STUDENT.value,
        "cancelled_by_role": "student",
    })
    booking_service._execute_cancellation_stripe_calls = Mock(return_value={})

    mock_repository.get_by_id_for_update.side_effect = [booking, None]
    mock_repository.transaction.return_value = _transaction_cm()

    with pytest.raises(NotFoundException):
        booking_service.cancel_booking(booking.id, user)


def test_cancel_booking_without_stripe_clear_payment_intent(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(payment_intent_id="pi_123")
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    mock_repository.get_booking_with_details.return_value = booking
    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._post_cancellation_actions = Mock()

    booking_service.cancel_booking_without_stripe(
        booking.id, user, clear_payment_intent=True
    )

    assert booking.payment_intent_id is None


def test_activate_lock_for_reschedule_expire_all_error(
    booking_service: BookingService, mock_repository: MagicMock, mock_db: MagicMock
) -> None:
    booking = make_booking(payment_status=PaymentStatus.SCHEDULED.value, payment_intent_id="pi_123")
    mock_repository.get_by_id_for_update.return_value = booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    mock_db.expire_all.side_effect = Exception("boom")
    booking_service.db = mock_db

    with patch("app.tasks.payment_tasks._process_authorization_for_booking") as auth_task:
        auth_task.return_value = {"success": True}
        with patch("app.services.stripe_service.StripeService") as stripe_service:
            stripe_service.return_value.capture_payment_intent.return_value = {
                "transfer_id": "tr_123",
                "amount_received": 1000,
                "transfer_amount": 800,
            }
            stripe_service.return_value.reverse_transfer.return_value = {"reversal": {"id": "rv"}}
            with patch("app.services.credit_service.CreditService") as credit_service:
                credit_service.return_value.forfeit_credits_for_booking = Mock()
                with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
                    payment_repo.return_value.create_payment_event = Mock()
                    mock_repository.get_booking_with_details.return_value = make_booking(
                        payment_status=PaymentStatus.AUTHORIZED.value,
                        payment_intent_id="pi_123",
                    )
                    booking_service.activate_lock_for_reschedule(booking.id)


def test_resolve_lock_for_booking_cancelled_ge12_credit(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    locked_booking = make_booking(payment_status=PaymentStatus.LOCKED.value)
    mock_repository.get_by_id_for_update.return_value = locked_booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with patch("app.services.booking_service.StripeService") as stripe_service:
        stripe_service.return_value = MagicMock()
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
            payment_repo.return_value.create_payment_event = Mock()
            payment_repo.return_value.get_credits_issued_for_source.side_effect = Exception("boom")
            with patch("app.services.credit_service.CreditService") as credit_service:
                credit_service.return_value.issue_credit = Mock()
                result = booking_service.resolve_lock_for_booking(
                    locked_booking.id, "new_lesson_cancelled_ge12"
                )

    assert result["resolution"] == "new_lesson_cancelled_ge12"


def test_build_cancellation_context_timezone_handling(booking_service: BookingService) -> None:
    booking = make_booking(
        rescheduled_from_booking_id=generate_ulid(),
        original_lesson_datetime=datetime(2030, 1, 2, 10, 0, 0),
        created_at=datetime(2030, 1, 1, 12, 0, 0),
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    booking_service._get_booking_start_utc = Mock(return_value=datetime(2030, 1, 2, 10, 0, 0))
    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=10):
        ctx = booking_service._build_cancellation_context(booking, user)

    assert ctx["was_gaming_reschedule"] is True


def test_execute_cancellation_stripe_calls_scenarios(booking_service: BookingService) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_123",
        "amount_received": 1000,
        "transfer_amount": 800,
    }
    stripe_service.get_payment_intent_capture_details.return_value = {
        "transfer_id": "tr_123",
        "amount_received": 1000,
        "transfer_amount": 800,
    }
    stripe_service.reverse_transfer.side_effect = Exception("reverse failed")
    stripe_service.cancel_payment_intent = Mock()
    stripe_service.refund_payment = Mock(return_value={"refund_id": "re_1", "amount_refunded": 10})
    stripe_service.build_charge_context.return_value = SimpleNamespace(
        target_instructor_payout_cents=0
    )
    stripe_service.create_manual_transfer.side_effect = Exception("payout failed")

    base_ctx = {
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_123",
        "payment_status": PaymentStatus.SETTLED.value,
        "lesson_price_cents": 1000,
        "instructor_stripe_account_id": None,
    }

    for scenario in [
        "over_24h_gaming",
        "over_24h_regular",
        "instructor_cancel_over_24h",
        "between_12_24h",
        "under_12h",
    ]:
        ctx = dict(base_ctx, scenario=scenario)
        booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)


def test_execute_cancellation_stripe_calls_over_24h_gaming_reverse_success(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.get_payment_intent_capture_details.return_value = {
        "transfer_id": "tr_123",
        "amount_received": 1000,
        "transfer_amount": 800,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": SimpleNamespace(id="rv_123")}

    ctx = {
        "scenario": "over_24h_gaming",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_123",
        "payment_status": PaymentStatus.SETTLED.value,
        "lesson_price_cents": 1000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["reverse_success"] is True
    assert results["reverse_reversal_id"] == "rv_123"


def test_execute_cancellation_stripe_calls_between_12_24h_reverse_success(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_456",
        "amount_received": 2000,
        "transfer_amount": 1600,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_456"}}

    ctx = {
        "scenario": "between_12_24h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_456",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "lesson_price_cents": 2000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["reverse_success"] is True
    assert results["reverse_reversal_id"] == "rv_456"


def test_execute_cancellation_stripe_calls_under_12h_missing_transfer_id(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": None,
        "amount_received": 1000,
        "transfer_amount": None,
    }

    ctx = {
        "scenario": "under_12h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_789",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "lesson_price_cents": 1000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["reverse_failed"] is True
    assert results["payout_success"] is False


def test_execute_cancellation_stripe_calls_under_12h_zero_payout_success(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_789",
        "amount_received": 1000,
        "transfer_amount": 0,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_789"}}

    ctx = {
        "scenario": "under_12h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_789",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "lesson_price_cents": 1000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["payout_success"] is True
    assert results["payout_amount_cents"] == 0


def test_execute_cancellation_stripe_calls_under_12h_missing_instructor_account(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_901",
        "amount_received": 2000,
        "transfer_amount": 1000,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_901"}}

    ctx = {
        "scenario": "under_12h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_901",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "lesson_price_cents": 2000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["payout_failed"] is True
    assert results["error"] == "missing_instructor_account"


def test_execute_cancellation_stripe_calls_under_12h_missing_payout_amount(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_123",
        "amount_received": 1000,
        "transfer_amount": None,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_1"}}
    stripe_service.build_charge_context.side_effect = Exception("no payout")

    ctx = {
        "scenario": "under_12h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_123",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "lesson_price_cents": 1000,
        "instructor_stripe_account_id": None,
    }

    results = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert results["payout_failed"] is True
    assert results["error"] == "missing_payout_amount"


def test_finalize_cancellation_over_24h_gaming_reverse_failed(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "over_24h_gaming",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "lesson_price_cents": 1200,
        "student_id": booking.student_id,
        "hours_until": 30.0,
        "hours_from_original": None,
        "rescheduled_from_booking_id": None,
        "original_lesson_datetime": None,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_failed": True,
        "error": "reverse_failed",
        "capture_data": {"transfer_id": "tr_123"},
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.forfeit_credits_for_booking = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    transfer_record = booking_service.repository.ensure_transfer.return_value
    assert transfer_record.transfer_reversal_failed is True
    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value


def test_finalize_cancellation_over_24h_gaming_credit_issued(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "over_24h_gaming",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "lesson_price_cents": 1500,
        "student_id": booking.student_id,
        "hours_until": 30.0,
        "hours_from_original": 50.0,
        "rescheduled_from_booking_id": generate_ulid(),
        "original_lesson_datetime": None,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_failed": False,
        "reverse_reversal_id": "rv_1",
        "capture_data": {"transfer_id": "tr_123"},
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.forfeit_credits_for_booking = Mock()
        credit_service.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.settlement_outcome == "student_cancel_12_24_full_credit"
    assert booking.student_credit_amount == 1500


def test_finalize_cancellation_between_12_24h_credit_issued(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "between_12_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_456",
        "lesson_price_cents": 2000,
        "student_id": booking.student_id,
        "hours_until": 18.0,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_success": True,
        "reverse_failed": False,
        "capture_data": {
            "transfer_id": "tr_456",
            "amount_received": 2000,
            "transfer_amount": 1600,
        },
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.forfeit_credits_for_booking = Mock()
        credit_service.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.settlement_outcome == "student_cancel_12_24_full_credit"


def test_finalize_cancellation_under_12h_payout_failed(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "under_12h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_789",
        "lesson_price_cents": 1800,
        "student_id": booking.student_id,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_success": True,
        "reverse_failed": False,
        "payout_failed": True,
        "payout_amount_cents": 900,
        "error": "payout_failed",
        "capture_data": {
            "transfer_id": "tr_789",
            "amount_received": 1800,
            "transfer_amount": 1400,
        },
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.forfeit_credits_for_booking = Mock()
        credit_service.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value
    transfer_record = booking_service.repository.ensure_transfer.return_value
    assert transfer_record.payout_transfer_failed_at is not None


def test_finalize_cancellation_under_12h_credit_already_issued(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "under_12h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_999",
        "lesson_price_cents": 2000,
        "student_id": booking.student_id,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_success": True,
        "reverse_failed": False,
        "payout_success": True,
        "payout_amount_cents": 1000,
        "payout_transfer_id": "tr_payout",
        "capture_data": {
            "transfer_id": "tr_999",
            "amount_received": 2000,
            "transfer_amount": 1500,
        },
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = [
        SimpleNamespace(reason="cancel_credit_lt12", source_type=None)
    ]

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.forfeit_credits_for_booking = Mock()
        credit_service.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    credit_service.return_value.issue_credit.assert_not_called()
    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.settlement_outcome == "student_cancel_lt12_split_50_50"


def test_finalize_cancellation_pending_payment(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "pending_payment",
        "booking_id": booking.id,
        "payment_intent_id": None,
        "hours_until": 48.0,
        "lesson_price_cents": 1200,
    }
    stripe_results = {}
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.release_credits_for_booking = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.settlement_outcome == "student_cancel_gt24_no_charge"


def test_finalize_cancellation_instructor_refund_success(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "instructor_cancel_over_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_refund",
        "hours_until": 40.0,
    }
    stripe_results = {
        "refund_success": True,
        "refund_data": {"refund_id": "rf_1", "amount_refunded": "1000"},
    }
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.release_credits_for_booking = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    transfer_record = booking_service.repository.ensure_transfer.return_value
    assert transfer_record.refund_id == "rf_1"
    assert booking.settlement_outcome == "instructor_cancel_full_refund"


def test_finalize_cancellation_instructor_refund_failed(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "instructor_cancel_under_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_refund",
        "hours_until": 10.0,
    }
    stripe_results = {
        "refund_success": False,
        "refund_failed": False,
        "cancel_pi_success": False,
        "error": "refund_failed",
    }
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.release_credits_for_booking = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value


def test_finalize_cancellation_under_12h_no_pi(booking_service: BookingService) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "under_12h_no_pi",
        "booking_id": booking.id,
        "payment_intent_id": None,
        "hours_until": 5.0,
        "lesson_price_cents": 1000,
    }
    stripe_results = {}

    with patch("app.services.credit_service.CreditService") as credit_service:
        credit_service.return_value.release_credits_for_booking.side_effect = Exception("boom")
        payment_repo = MagicMock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value


def test_update_booking_refreshed_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(instructor_id=generate_ulid())
    user = make_user(RoleName.INSTRUCTOR.value, id=booking.instructor_id)

    mock_repository.get_booking_with_details.side_effect = [booking, None]
    mock_repository.update.return_value = booking

    with pytest.raises(NotFoundException):
        booking_service.update_booking(booking.id, user, BookingUpdate(instructor_note="x"))


def test_complete_booking_refresh_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    instructor = make_user(RoleName.INSTRUCTOR.value, id=booking.instructor_id)

    mock_repository.get_booking_with_details.return_value = booking
    mock_repository.complete_booking.return_value = booking
    mock_repository.get_booking_with_details.side_effect = [booking, None]
    booking_service._enqueue_booking_outbox_event = Mock()

    with pytest.raises(NotFoundException):
        booking_service.complete_booking(booking.id, instructor)


def test_check_availability_missing_service(booking_service: BookingService) -> None:
    booking_service.repository.check_time_conflict.return_value = False
    booking_service.conflict_checker_repository.get_active_service.return_value = None

    result = booking_service.check_availability(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_id=None,
    )

    assert result["available"] is False


def test_validate_booking_prerequisites_instructor_status_other(
    booking_service: BookingService,
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(instructor_profile_id="profile")
    instructor_profile = SimpleNamespace(id="profile", bgc_status=None)

    booking_service.conflict_checker_repository.get_active_service.return_value = service
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = (
        instructor_profile
    )

    user_repo = MagicMock()
    user_repo.get_by_id.return_value = SimpleNamespace(account_status="other")

    with patch("app.services.booking_service.RepositoryFactory.create_base_repository") as repo:
        repo.return_value = user_repo
        with pytest.raises(BusinessRuleException):
            booking_service._validate_booking_prerequisites(student, booking_data)


def test_check_conflicts_and_rules_missing_end_time(booking_service: BookingService) -> None:
    booking_data = make_booking_data(end_time=None)
    service = SimpleNamespace()
    instructor_profile = SimpleNamespace()

    with pytest.raises(ValidationException):
        booking_service._check_conflicts_and_rules(booking_data, service, instructor_profile)


def test_check_conflicts_and_rules_student_conflict(booking_service: BookingService) -> None:
    booking_data = make_booking_data(end_time=time(11, 0))
    service = SimpleNamespace(offers_online=True)
    instructor_profile = SimpleNamespace(min_advance_booking_hours=0)
    student = make_user(RoleName.STUDENT.value)

    booking_service.repository.check_time_conflict.return_value = False
    booking_service.repository.check_student_time_conflict.return_value = ["conflict"]
    booking_service._resolve_lesson_timezone = Mock(return_value=timezone.utc)
    booking_service._resolve_booking_times_utc = Mock(
        return_value=(datetime(2030, 1, 1, 10, 0, 0, tzinfo=timezone.utc), None)
    )

    with pytest.raises(BookingConflictException):
        booking_service._check_conflicts_and_rules(booking_data, service, instructor_profile, student)


def test_create_booking_record_missing_end_time(booking_service: BookingService) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data(end_time=None)
    service = SimpleNamespace(hourly_rate=100, session_price=lambda duration: 100, catalog_entry=None)
    instructor_profile = SimpleNamespace(user_id=generate_ulid())

    with pytest.raises(ValidationException):
        booking_service._create_booking_record(
            student,
            booking_data,
            service,
            instructor_profile,
            selected_duration=60,
        )


def test_determine_service_area_summary_formats(booking_service: BookingService) -> None:
    area_one = SimpleNamespace(
        neighborhood=SimpleNamespace(
            parent_region="Manhattan",
            region_metadata={"borough": "Brooklyn"},
        )
    )
    area_two = SimpleNamespace(
        neighborhood=SimpleNamespace(parent_region="Queens", region_metadata=None)
    )
    area_three = SimpleNamespace(
        neighborhood=SimpleNamespace(parent_region="Bronx", region_metadata=None)
    )
    booking_service.service_area_repository.list_for_instructor.return_value = [
        area_one,
        area_two,
        area_three,
    ]

    summary = booking_service._determine_service_area_summary(generate_ulid())

    assert "+" in summary


def test_send_booking_notifications_after_confirmation_missing_booking(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    mock_repository.get_booking_with_details.return_value = None

    booking_service.send_booking_notifications_after_confirmation(generate_ulid())


def test_get_booking_pricing_preview_access_denied(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking()
    mock_repository.get_by_id.return_value = booking

    result = booking_service.get_booking_pricing_preview(booking.id, generate_ulid())

    assert result == {"error": "access_denied"}


def test_check_student_time_conflict_exception(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    mock_repository.check_student_time_conflict.side_effect = Exception("boom")

    assert (
        booking_service.check_student_time_conflict(
            student_id=generate_ulid(),
            booking_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        is False
    )


def test_determine_service_area_summary_empty(booking_service: BookingService) -> None:
    booking_service.service_area_repository.list_for_instructor.return_value = []

    assert booking_service._determine_service_area_summary(generate_ulid()) == ""


def test_determine_service_area_summary_two_boroughs(booking_service: BookingService) -> None:
    area_one = SimpleNamespace(
        neighborhood=SimpleNamespace(parent_region="Queens", region_metadata=None)
    )
    area_two = SimpleNamespace(
        neighborhood=SimpleNamespace(parent_region="Bronx", region_metadata=None)
    )
    booking_service.service_area_repository.list_for_instructor.return_value = [
        area_one,
        area_two,
    ]

    summary = booking_service._determine_service_area_summary(generate_ulid())

    assert summary == "Bronx, Queens"


def test_format_user_display_name_variants() -> None:
    assert BookingService._format_user_display_name(None) == "Someone"

    full = SimpleNamespace(first_name="Ada", last_name="Lovelace")
    assert BookingService._format_user_display_name(full) == "Ada L."

    first_only = SimpleNamespace(first_name="Ada", last_name="")
    assert BookingService._format_user_display_name(first_only) == "Ada"

    last_only = SimpleNamespace(first_name="", last_name="Lovelace")
    assert BookingService._format_user_display_name(last_only) == "Someone"


def test_format_booking_date_and_time() -> None:
    booking = SimpleNamespace(
        booking_date=date(2030, 1, 1),
        start_time=time(9, 5),
    )
    assert BookingService._format_booking_date(booking) == "January 1"
    assert BookingService._format_booking_time(booking) == "9:05 AM"

    booking = SimpleNamespace(booking_date="someday", start_time="10am")
    assert BookingService._format_booking_date(booking) == "someday"
    assert BookingService._format_booking_time(booking) == "10am"


def test_resolve_service_name_fallbacks() -> None:
    booking = SimpleNamespace(service_name="Piano", instructor_service=None)
    assert BookingService._resolve_service_name(booking) == "Piano"

    booking = SimpleNamespace(service_name=" ", instructor_service=SimpleNamespace(name="Guitar"))
    assert BookingService._resolve_service_name(booking) == "Guitar"

    booking = SimpleNamespace(service_name=None, instructor_service=None)
    assert BookingService._resolve_service_name(booking) == "Lesson"


def test_abort_pending_booking_non_pending(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    mock_repository.get_by_id.return_value = booking

    assert booking_service.abort_pending_booking(booking.id) is False


def test_create_booking_operational_error_non_deadlock_reraises(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=False)
    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("other-op"))
    )

    with pytest.raises(OperationalError):
        booking_service.create_booking(student, booking_data, selected_duration=60)


def test_create_rescheduled_booking_with_locked_funds_integrity_error_with_scope(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    existing = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._resolve_integrity_conflict_message = Mock(
        return_value=("conflict", "student")
    )

    mock_repository.get_by_id.return_value = existing
    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=IntegrityError("stmt", "params", Exception("boom"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_rescheduled_booking_with_locked_funds(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing.id,
        )

    assert exc_info.value.details.get("conflict_scope") == "student"


def test_create_rescheduled_booking_with_locked_funds_deadlock_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    existing = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._is_deadlock_error = Mock(return_value=True)

    mock_repository.get_by_id.return_value = existing
    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("deadlock"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_rescheduled_booking_with_locked_funds(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing.id,
        )

    assert exc_info.value.message == GENERIC_CONFLICT_MESSAGE


def test_cancel_booking_locked_payment_status_uses_lock_context_lt12(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.LOCKED.value,
        has_locked_funds=False,
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)

    mock_repository.get_by_id_for_update.side_effect = [booking, booking]
    booking_service.transaction = MagicMock(return_value=_transaction_cm())
    booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._post_cancellation_actions = Mock()
    booking_service._get_booking_start_utc = Mock(
        return_value=datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
    )

    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=5.0):
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
            payment_repo_cls.return_value = MagicMock()
            result = booking_service.cancel_booking(booking.id, user)

    assert result is booking
    booking_service.resolve_lock_for_booking.assert_called_once_with(
        booking.id, "new_lesson_cancelled_lt12"
    )


def test_resolve_lock_for_booking_instructor_cancel_invalid_refund_amount_fallback(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    locked_booking = make_booking(
        payment_status=PaymentStatus.LOCKED.value,
        payment_intent_id="pi_123",
        locked_amount_cents=777,
        hourly_rate=120,
        duration_minutes=60,
    )
    mock_repository.get_by_id_for_update.return_value = locked_booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = None

    with patch("app.services.booking_service.StripeService") as stripe_cls:
        stripe_cls.return_value.refund_payment.return_value = {
            "refund_id": "rf_1",
            "amount_refunded": "not-a-number",
        }
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
            payment_repo = payment_repo_cls.return_value
            payment_repo.get_payment_by_booking_id.return_value = None
            payment_repo.get_credits_issued_for_source.return_value = []
            payment_repo.create_payment_event = Mock()
            with patch("app.services.booking_service.PricingService") as pricing_cls:
                pricing_cls.return_value.compute_booking_pricing.return_value = {
                    "target_instructor_payout_cents": 0
                }
                result = booking_service.resolve_lock_for_booking(
                    locked_booking.id, "instructor_cancelled"
                )

    assert result["success"] is True
    assert locked_booking.refunded_to_card_amount == 777


def test_build_cancellation_context_handles_inner_and_outer_stripe_lookup_errors(
    booking_service: BookingService,
) -> None:
    booking = make_booking(
        booking_start_utc=datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc),
        hourly_rate=100,
        duration_minutes=60,
        payment_intent_id="pi_123",
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)
    booking_service._get_booking_start_utc = Mock(return_value=booking.booking_start_utc)

    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=20.0):
        with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
            payment_repo_cls.return_value.get_connected_account_by_instructor_id.return_value = None
            booking_service.conflict_checker_repository.get_instructor_profile.side_effect = (
                RuntimeError("profile lookup failed")
            )
            ctx = booking_service._build_cancellation_context(booking, user)
            assert ctx["instructor_stripe_account_id"] is None

    booking_service.conflict_checker_repository.get_instructor_profile.side_effect = None
    booking_service.conflict_checker_repository.get_instructor_profile.return_value = None
    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=20.0):
        with patch(
            "app.repositories.payment_repository.PaymentRepository",
            side_effect=RuntimeError("payment repo init failed"),
        ):
            ctx = booking_service._build_cancellation_context(booking, user)
            assert ctx["instructor_stripe_account_id"] is None


def test_execute_cancellation_stripe_calls_instructor_cancel_cancel_error(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.cancel_payment_intent.side_effect = RuntimeError("cancel-failed")
    ctx = {
        "scenario": "instructor_cancel_under_24h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_123",
        "payment_status": PaymentStatus.AUTHORIZED.value,
    }

    result = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert result["cancel_pi_success"] is False
    assert result["error"] == "cancel-failed"


def test_execute_cancellation_stripe_calls_under_12h_capture_and_payout_errors(
    booking_service: BookingService,
) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.side_effect = RuntimeError("capture-failed")

    ctx = {
        "scenario": "under_12h",
        "booking_id": generate_ulid(),
        "payment_intent_id": "pi_1",
        "payment_status": PaymentStatus.AUTHORIZED.value,
        "instructor_stripe_account_id": "acct_1",
    }
    result = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)
    assert result["error"] == "capture-failed"

    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "transfer_id": "tr_1",
        "amount_received": 2000,
        "transfer_amount": 1200,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_1"}}
    stripe_service.create_manual_transfer.side_effect = RuntimeError("payout-failed")

    result = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)
    assert result["payout_failed"] is True
    assert result["error"] == "payout-failed"


def test_finalize_cancellation_exception_paths_for_credit_and_release(
    booking_service: BookingService,
) -> None:
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    between_ctx = {
        "scenario": "between_12_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_1",
        "lesson_price_cents": 2000,
        "student_id": booking.student_id,
        "hours_until": 18.0,
    }
    between_stripe = {
        "capture_success": True,
        "reverse_success": True,
        "capture_data": {"transfer_id": "tr_1", "amount_received": 2000, "transfer_amount": 1000},
    }
    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.forfeit_credits_for_booking.side_effect = RuntimeError("forfeit")
        credit_cls.return_value.issue_credit.side_effect = RuntimeError("issue-credit")
        booking_service._finalize_cancellation(booking, between_ctx, between_stripe, payment_repo)

    under12_booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    under12_ctx = {
        "scenario": "under_12h",
        "booking_id": under12_booking.id,
        "payment_intent_id": "pi_2",
        "lesson_price_cents": 2000,
        "student_id": under12_booking.student_id,
    }
    under12_stripe = {
        "capture_success": True,
        "reverse_success": True,
        "payout_success": True,
        "payout_amount_cents": 1000,
        "payout_transfer_id": "tr_payout",
        "capture_data": {"transfer_id": "tr_2", "amount_received": 2000, "transfer_amount": 1500},
    }
    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.forfeit_credits_for_booking = Mock()
        credit_cls.return_value.issue_credit.side_effect = RuntimeError("issue-credit")
        booking_service._finalize_cancellation(
            under12_booking,
            under12_ctx,
            under12_stripe,
            payment_repo,
        )

    pending_booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    pending_ctx = {
        "scenario": "pending_payment",
        "booking_id": pending_booking.id,
        "payment_intent_id": None,
        "hours_until": 24.0,
        "lesson_price_cents": 1200,
    }
    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking.side_effect = RuntimeError(
            "release-failed"
        )
        booking_service._finalize_cancellation(pending_booking, pending_ctx, {}, payment_repo)

    instructor_booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    instructor_ctx = {
        "scenario": "instructor_cancel_under_24h",
        "booking_id": instructor_booking.id,
        "payment_intent_id": "pi_3",
        "hours_until": 8.0,
    }
    instructor_stripe = {
        "refund_success": True,
        "refund_data": {"refund_id": "rf_3", "amount_refunded": "300"},
    }
    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking.side_effect = RuntimeError(
            "release-failed"
        )
        booking_service._finalize_cancellation(
            instructor_booking,
            instructor_ctx,
            instructor_stripe,
            payment_repo,
        )


def test_post_cancellation_actions_handles_refund_hook_failures(booking_service: BookingService) -> None:
    booking = make_booking(
        status=BookingStatus.CANCELLED,
        payment_status=PaymentStatus.SETTLED.value,
        settlement_outcome="admin_refund",
    )
    booking_service.event_publisher.publish = Mock()
    booking_service.system_message_service.create_booking_cancelled_message = Mock()
    booking_service._send_cancellation_notifications = Mock()
    booking_service._invalidate_booking_caches = Mock()

    with patch("app.services.booking_service.StudentCreditService") as credit_cls:
        credit_cls.return_value.process_refund_hooks.side_effect = RuntimeError("hook-failed")
        booking_service._post_cancellation_actions(booking, "student")

    booking_service._invalidate_booking_caches.assert_called_once_with(booking)
    credit_cls.return_value.process_refund_hooks.assert_called_once()


def test_instructor_mark_complete_handles_category_chain_attribute_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR.value)

    class _BrokenInstructorService:
        @property
        def catalog_entry(self) -> object:
            raise AttributeError("broken category chain")

    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        instructor_id=instructor.id,
        instructor_service=_BrokenInstructorService(),
    )
    mock_repository.get_by_id.side_effect = [booking, booking]

    now = datetime.now(timezone.utc)
    booking_service._get_booking_end_utc = Mock(return_value=now - timedelta(minutes=30))

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
        payment_repo_cls.return_value.create_payment_event = Mock()
        with patch("app.services.badge_award_service.BadgeAwardService") as badge_cls:
            badge_cls.return_value.check_and_award_on_lesson_completed = Mock()
            with patch("app.services.referral_service.ReferralService") as referral_cls:
                referral_cls.return_value.on_instructor_lesson_completed = Mock()
                result = booking_service.instructor_mark_complete(booking.id, instructor)

    assert result is booking
    kwargs = badge_cls.return_value.check_and_award_on_lesson_completed.call_args.kwargs
    assert kwargs["category_name"] is None


def test_create_rescheduled_booking_with_existing_payment_instructor_mismatch_inside_tx(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    existing = make_booking(instructor_id=booking_data.instructor_id)
    mismatched = make_booking(instructor_id=generate_ulid())
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    created = make_booking(instructor_id=booking_data.instructor_id)

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._create_booking_record = Mock(return_value=created)

    mock_repository.get_by_id.side_effect = [existing, mismatched]
    mock_repository.transaction.return_value = _transaction_cm()

    with pytest.raises(BusinessRuleException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing.id,
            payment_intent_id="pi_123",
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_method_id="pm_123",
        )


def test_create_rescheduled_booking_with_existing_payment_deadlock_and_repo_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    existing = make_booking(instructor_id=booking_data.instructor_id)
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._build_conflict_details = Mock(return_value={"conflict": True})
    booking_service._is_deadlock_error = Mock(return_value=True)
    mock_repository.transaction.return_value = _transaction_cm()
    mock_repository.get_by_id.return_value = existing
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("deadlock"))
    )

    with pytest.raises(BookingConflictException) as exc_info:
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing.id,
            payment_intent_id="pi_123",
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_method_id="pm_123",
        )
    assert exc_info.value.message == GENERIC_CONFLICT_MESSAGE

    booking_service._create_booking_record = Mock(side_effect=RepositoryException("repo boom"))
    booking_service._raise_conflict_from_repo_error = Mock(
        side_effect=BookingConflictException(message="conflict", details={})
    )
    with pytest.raises(BookingConflictException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing.id,
            payment_intent_id="pi_123",
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_method_id="pm_123",
        )


def test_retry_payment_authorization_credit_only_booking_missing_on_refetch(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        student_id=generate_ulid(),
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_booking",
    )
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)
    mock_repository.get_booking_with_details.side_effect = [booking, None]
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
        payment_repo = payment_repo_cls.return_value
        payment_repo.get_default_payment_method.return_value = SimpleNamespace(
            stripe_payment_method_id="pm_default"
        )
        with patch("app.services.stripe_service.StripeService") as stripe_cls:
            stripe_service = stripe_cls.return_value
            stripe_service.build_charge_context.return_value = SimpleNamespace(
                student_pay_cents=0,
                applied_credit_cents=1000,
                application_fee_cents=0,
            )
            with pytest.raises(NotFoundException):
                booking_service.retry_authorization(booking_id=booking.id, user=user)


def test_finalize_cancellation_handles_credit_lookup_failures_and_success_paths(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.side_effect = RuntimeError("lookup-failed")

    ctx = {
        "scenario": "between_12_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "lesson_price_cents": 2000,
        "student_id": booking.student_id,
        "hours_until": 18.0,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_success": True,
        "capture_data": {"transfer_id": "tr_1", "amount_received": 2000, "transfer_amount": 1000},
    }

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.forfeit_credits_for_booking = Mock()
        credit_cls.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    credit_cls.return_value.issue_credit.assert_called_once()

    # Under-12 without PI: success path should emit skipped event and set manual review.
    under12_no_pi = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    under12_ctx = {
        "scenario": "under_12h_no_pi",
        "booking_id": under12_no_pi.id,
        "payment_intent_id": None,
        "hours_until": 3.0,
        "lesson_price_cents": 1200,
    }
    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking = Mock()
        booking_service._finalize_cancellation(under12_no_pi, under12_ctx, {}, payment_repo)
    payment_repo.create_payment_event.assert_any_call(
        booking_id=under12_no_pi.id,
        event_type="capture_skipped_no_intent",
        event_data={"reason": "<12h cancellation without payment_intent"},
    )


def test_finalize_cancellation_instructor_paths_cover_release_error_and_refund_cast_failure(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "instructor_cancel_over_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_refund",
        "hours_until": 40.0,
    }
    stripe_results = {
        "refund_success": True,
        "refund_data": {"refund_id": "rf_1", "amount_refunded": "not-int"},
    }
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking.side_effect = RuntimeError(
            "release-failed"
        )
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.refunded_to_card_amount == 0


def test_create_booking_non_deadlock_operational_error_reraises(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=False)
    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("not-deadlock"))
    )

    with pytest.raises(OperationalError):
        booking_service.create_booking(student, booking_data, selected_duration=60)


def test_create_rescheduled_locked_funds_non_deadlock_and_repo_conflict(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT.value)
    booking_data = make_booking_data()
    existing_booking = make_booking(instructor_id=booking_data.instructor_id)
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=False)
    mock_repository.transaction.return_value = _transaction_cm()
    mock_repository.get_by_id.return_value = existing_booking
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("operational"))
    )

    with pytest.raises(OperationalError):
        booking_service.create_rescheduled_booking_with_locked_funds(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing_booking.id,
        )

    booking_service._create_booking_record = Mock(side_effect=RepositoryException("repo"))
    booking_service._raise_conflict_from_repo_error = Mock(
        side_effect=BookingConflictException(message="conflict", details={})
    )
    with pytest.raises(BookingConflictException):
        booking_service.create_rescheduled_booking_with_locked_funds(
            student,
            booking_data,
            selected_duration=60,
            original_booking_id=existing_booking.id,
        )


def test_cancel_booking_rejects_non_cancellable_booking(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(is_cancellable=False, status=BookingStatus.CONFIRMED)
    user = make_user(RoleName.STUDENT.value, id=booking.student_id)
    mock_repository.get_by_id_for_update.return_value = booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with pytest.raises(BusinessRuleException, match="cannot be cancelled"):
        booking_service.cancel_booking(booking.id, user)


def test_cancel_booking_locked_context_instructor_and_ge12_resolution_paths(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking_locked_reschedule = make_booking(
        id=generate_ulid(),
        payment_status=PaymentStatus.LOCKED.value,
        status=BookingStatus.CONFIRMED,
        has_locked_funds=True,
        rescheduled_from_booking_id=generate_ulid(),
    )
    instructor_user = make_user(RoleName.INSTRUCTOR.value, id=booking_locked_reschedule.instructor_id)

    booking_locked_direct = make_booking(
        id=generate_ulid(),
        payment_status=PaymentStatus.LOCKED.value,
        status=BookingStatus.CONFIRMED,
        has_locked_funds=False,
        rescheduled_from_booking_id=None,
    )
    student_user = make_user(RoleName.STUDENT.value, id=booking_locked_direct.student_id)

    mock_repository.get_by_id_for_update.side_effect = [
        booking_locked_reschedule,
        booking_locked_reschedule,
        booking_locked_direct,
        booking_locked_direct,
    ]
    booking_service.transaction = MagicMock(return_value=_transaction_cm())
    booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})
    booking_service._snapshot_booking = Mock(return_value={"status": BookingStatus.CONFIRMED.value})
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._post_cancellation_actions = Mock()
    booking_service._get_booking_start_utc = Mock(
        return_value=datetime.now(timezone.utc) + timedelta(hours=15)
    )

    with patch("app.services.booking_service.TimezoneService.hours_until", return_value=15.0):
        booking_service.cancel_booking(booking_locked_reschedule.id, instructor_user)
        booking_service.cancel_booking(booking_locked_direct.id, student_user)

    assert booking_service.resolve_lock_for_booking.call_args_list[0].args == (
        booking_locked_reschedule.rescheduled_from_booking_id,
        "instructor_cancelled",
    )
    assert booking_service.resolve_lock_for_booking.call_args_list[1].args == (
        booking_locked_direct.id,
        "new_lesson_cancelled_ge12",
    )


def test_activate_lock_for_reschedule_status_guard_and_missing_booking_after_capture(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking_phase1 = make_booking(
        id=generate_ulid(),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_guard",
    )
    booking_refreshed_wrong_status = make_booking(
        id=booking_phase1.id,
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_intent_id="pi_guard",
    )
    mock_repository.get_by_id_for_update.return_value = booking_phase1
    mock_repository.get_booking_with_details.return_value = booking_refreshed_wrong_status
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with pytest.raises(BusinessRuleException, match="Cannot lock booking with status"):
        booking_service.activate_lock_for_reschedule(booking_phase1.id)

    booking_phase2 = make_booking(
        id=generate_ulid(),
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_lock",
    )
    mock_repository.get_by_id_for_update.side_effect = [booking_phase2, None]
    mock_repository.get_booking_with_details.return_value = booking_phase2

    with patch("app.services.stripe_service.StripeService") as stripe_cls:
        stripe_cls.return_value.capture_payment_intent.return_value = {
            "transfer_id": None,
            "transfer_amount": None,
            "amount_received": 1000,
        }
        with pytest.raises(NotFoundException, match="after lock capture"):
            booking_service.activate_lock_for_reschedule(booking_phase2.id)


def test_execute_cancellation_stripe_calls_under_12h_uses_charge_context_for_payout(
    booking_service: BookingService,
) -> None:
    ctx = {
        "scenario": "under_12h",
        "booking_id": "booking_under12",
        "payment_intent_id": "pi_123",
        "already_captured": False,
    }
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.return_value = {
        "amount_received": 2200,
        "transfer_id": "tr_123",
        "transfer_amount": None,
    }
    stripe_service.reverse_transfer.return_value = {"reversal": {"id": "trr_1"}}
    stripe_service.build_charge_context.return_value = SimpleNamespace(
        target_instructor_payout_cents=1200
    )

    result = booking_service._execute_cancellation_stripe_calls(ctx, stripe_service)

    assert result["reverse_success"] is True
    assert result["payout_amount_cents"] == 600
    assert result["payout_failed"] is True
    assert result["error"] == "missing_instructor_account"


def test_dispute_no_show_student_branch_forbidden_user(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
        no_show_type="student",
        no_show_disputed=False,
        no_show_resolved_at=None,
    )
    mock_repository.get_booking_with_details.return_value = booking
    booking_service.transaction = MagicMock(return_value=_transaction_cm())

    with pytest.raises(ForbiddenException):
        booking_service.dispute_no_show(
            booking_id=booking.id,
            disputer=make_user(RoleName.STUDENT.value, id=generate_ulid()),
            reason="not me",
        )


def test_resolve_no_show_locked_dispute_upheld_and_cancelled_paths(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    locked_booking = make_booking(
        id=generate_ulid(),
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=2),
        no_show_resolved_at=None,
        no_show_type="student",
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
        payment_intent_id="pi_lock",
        has_locked_funds=True,
        rescheduled_from_booking_id=generate_ulid(),
        hourly_rate=100,
        duration_minutes=60,
    )
    mock_repository.get_booking_with_details.side_effect = [locked_booking, locked_booking]
    booking_service.transaction = MagicMock(return_value=_transaction_cm())
    booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})
    booking_service._finalize_student_no_show = Mock()
    booking_service._snapshot_booking = Mock(return_value={"status": "manual_review"})
    booking_service._write_booking_audit = Mock()
    booking_service._invalidate_booking_caches = Mock()
    booking_service._cancel_no_show_report = Mock()

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
        payment_repo = payment_repo_cls.return_value
        payment_repo.get_payment_by_booking_id.return_value = SimpleNamespace(
            status=PaymentStatus.AUTHORIZED.value,
            amount="12000",
            instructor_payout_cents=None,
            application_fee=1000,
            base_price_cents="10000",
            instructor_tier_pct="0.25",
        )
        with patch("app.services.credit_service.CreditService"):
            result = booking_service.resolve_no_show(
                booking_id=locked_booking.id,
                resolution="dispute_upheld",
                resolved_by=None,
                admin_notes="reviewed",
            )

    assert result["success"] is True
    booking_service.resolve_lock_for_booking.assert_called_with(
        locked_booking.rescheduled_from_booking_id,
        "new_lesson_completed",
    )

    cancelled_booking = make_booking(
        id=generate_ulid(),
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=2),
        no_show_resolved_at=None,
        no_show_type="student",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_cancel",
        has_locked_funds=False,
        rescheduled_from_booking_id=None,
        hourly_rate=100,
        duration_minutes=60,
        settlement_outcome=None,
    )
    mock_repository.get_booking_with_details.side_effect = [cancelled_booking, cancelled_booking]
    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo_cls:
        payment_repo = payment_repo_cls.return_value
        payment_repo.get_payment_by_booking_id.return_value = SimpleNamespace(
            status=PaymentStatus.AUTHORIZED.value,
            amount=12000,
            instructor_payout_cents=9000,
            application_fee=1000,
            base_price_cents=None,
            instructor_tier_pct=None,
        )
        with patch("app.services.credit_service.CreditService"):
            booking_service.resolve_no_show(
                booking_id=cancelled_booking.id,
                resolution="cancelled",
                resolved_by=None,
                admin_notes=None,
            )

    booking_service._cancel_no_show_report.assert_called_once_with(cancelled_booking)
