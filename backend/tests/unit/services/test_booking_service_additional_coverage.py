"""Additional coverage tests for booking_service.py remaining branches."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.enums import RoleName
from app.core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
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

    assert booking.transfer_reversal_failed is True
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
    assert booking.payout_transfer_failed_at is not None


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
    assert booking.refund_id == "rf_1"
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
    service = SimpleNamespace()
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
