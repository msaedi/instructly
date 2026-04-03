"""
Coverage gap tests for reschedule_execution.py and reschedule_service.py.

Targets uncovered exception handlers in:
- BookingRescheduleExecutionMixin._reschedule_with_lock (IntegrityError, OperationalError, RepositoryException)
- BookingRescheduleExecutionMixin._reschedule_with_existing_payment (same)
- BookingRescheduleExecutionMixin.create_rescheduled_booking_with_existing_payment (same)
- BookingRescheduleExecutionMixin.create_rescheduled_booking_with_locked_funds (same)
- BookingRescheduleMixin._normalize_reschedule_location_type (invalid type)
- BookingRescheduleMixin._ensure_reschedule_slot_available (unavailable / exception fallback)
- BookingRescheduleMixin._resolve_reschedule_student (not found)
- BookingRescheduleMixin.reschedule_booking (not found)
- BookingRescheduleMixin._reschedule_with_new_payment (no payment method, confirmation failure)
- BookingRescheduleMixin.reschedule_booking (payment status "succeeded" normalization)
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import (
    BookingConflictException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRescheduleRequest
from app.services.booking_service import BookingService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ulid() -> str:
    return generate_ulid()


def _make_user(**overrides: Any) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = overrides.get("id", _make_ulid())
    user.first_name = overrides.get("first_name", "Test")
    user.last_name = overrides.get("last_name", "User")
    return user


def _make_booking(**overrides: Any) -> MagicMock:
    booking = MagicMock(spec=Booking)
    booking.id = overrides.get("id", _make_ulid())
    booking.student_id = overrides.get("student_id", _make_ulid())
    booking.instructor_id = overrides.get("instructor_id", _make_ulid())
    booking.instructor_service_id = overrides.get("instructor_service_id", _make_ulid())
    booking.status = overrides.get("status", BookingStatus.CONFIRMED)
    booking.location_type = overrides.get("location_type", "online")
    booking.student_note = overrides.get("student_note", None)
    booking.meeting_location = overrides.get("meeting_location", None)
    booking.location_address = overrides.get("location_address", None)
    booking.location_lat = overrides.get("location_lat", None)
    booking.location_lng = overrides.get("location_lng", None)
    booking.location_place_id = overrides.get("location_place_id", None)
    # payment_detail
    payment_detail = overrides.get("payment_detail", None)
    if payment_detail is None:
        payment_detail = MagicMock()
        payment_detail.payment_intent_id = overrides.get("payment_intent_id", None)
        payment_detail.payment_status = overrides.get("payment_status", None)
        payment_detail.payment_method_id = overrides.get("payment_method_id", None)
    booking.payment_detail = payment_detail
    return booking


def _make_booking_create(**overrides: Any) -> BookingCreate:
    defaults: dict[str, Any] = {
        "instructor_id": _make_ulid(),
        "instructor_service_id": _make_ulid(),
        "booking_date": date(2026, 5, 1),
        "start_time": time(10, 0),
        "selected_duration": 60,
        "location_type": "online",
    }
    defaults.update(overrides)
    return BookingCreate(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db() -> MagicMock:
    db = MagicMock()
    return db


@pytest.fixture()
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.check_time_conflict.return_value = False
    repo.check_student_time_conflict.return_value = []
    repo.get_bookings_by_time_range.return_value = []
    repo.create.return_value = Mock(spec=Booking, id=_make_ulid())
    repo.get_booking_with_details.return_value = None
    repo.update.return_value = None
    repo.ensure_payment.return_value = MagicMock(
        payment_status=None,
        payment_intent_id=None,
        payment_method_id=None,
        credits_reserved_cents=0,
        settlement_outcome=None,
        instructor_payout_amount=None,
        auth_last_error=None,
        capture_failed_at=None,
        capture_retry_count=0,
    )
    transaction_cm = MagicMock()
    transaction_cm.__enter__ = MagicMock(return_value=None)
    transaction_cm.__exit__ = MagicMock(return_value=False)
    repo.transaction = MagicMock(return_value=transaction_cm)
    return repo


@pytest.fixture()
def service(mock_db: MagicMock, mock_repository: MagicMock) -> BookingService:
    svc = BookingService(
        mock_db,
        notification_service=MagicMock(),
        event_publisher=MagicMock(),
        repository=mock_repository,
    )
    svc.audit_repository = MagicMock()
    svc.conflict_checker = MagicMock()
    svc.conflict_checker.check_time_conflicts.return_value = False
    svc.conflict_checker.check_student_time_conflicts.return_value = False
    svc.conflict_checker.check_booking_conflicts.return_value = []
    svc.conflict_checker.check_student_booking_conflicts.return_value = []
    return svc


# ---------------------------------------------------------------------------
# Shared mock-wiring helpers
# ---------------------------------------------------------------------------

def _stub_validate_inputs(svc: BookingService) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Stub _validate_rescheduled_booking_inputs to return plausible triples."""
    mock_service = MagicMock(spec=InstructorService)
    mock_profile = MagicMock(spec=InstructorProfile)
    mock_existing = _make_booking()
    svc._validate_rescheduled_booking_inputs = MagicMock(  # type: ignore[assignment]
        return_value=(mock_service, mock_profile, mock_existing),
    )
    return mock_service, mock_profile, mock_existing


def _make_integrity_error() -> IntegrityError:
    return IntegrityError("INSERT ...", params={}, orig=Exception("duplicate key"))


def _make_operational_error(*, deadlock: bool = True) -> OperationalError:
    msg = "deadlock detected" if deadlock else "connection reset"
    return OperationalError("UPDATE ...", params={}, orig=Exception(msg))


def _make_transaction_raise(repo_mock: MagicMock, exc: Exception) -> None:
    """Configure the repo transaction context manager to raise *exc* on __enter__."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(side_effect=exc)
    cm.__exit__ = MagicMock(return_value=False)
    repo_mock.transaction.return_value = cm


# ===================================================================
# reschedule_execution.py — _reschedule_with_lock exception handlers
# ===================================================================


class TestRescheduleWithLockIntegrityErrorWithScope:
    """Lines 169-178: IntegrityError with conflict_scope."""

    def test_raises_conflict_with_scope(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_integrity_error())

        service._resolve_integrity_conflict_message = MagicMock(  # type: ignore[assignment]
            return_value=("Duplicate booking", "instructor"),
        )
        service._build_conflict_details = MagicMock(  # type: ignore[assignment]
            return_value={"date": "2026-05-01"},
        )

        original = _make_booking()
        student = _make_user()
        current = _make_user()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException) as exc_info:
            service._reschedule_with_lock(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=current,
                reschedule_student=student,
            )
        assert exc_info.value.details.get("conflict_scope") == "instructor"


class TestRescheduleWithLockIntegrityErrorWithoutScope:
    """Lines 169-178: IntegrityError without scope."""

    def test_raises_conflict_without_scope(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_integrity_error())

        service._resolve_integrity_conflict_message = MagicMock(  # type: ignore[assignment]
            return_value=("Conflict detected", None),
        )
        service._build_conflict_details = MagicMock(  # type: ignore[assignment]
            return_value={"date": "2026-05-01"},
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException) as exc_info:
            service._reschedule_with_lock(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
            )
        assert "conflict_scope" not in exc_info.value.details


class TestRescheduleWithLockDeadlock:
    """Lines 180-188: OperationalError that IS a deadlock."""

    def test_raises_conflict_on_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=True))

        service._is_deadlock_error = MagicMock(return_value=True)  # type: ignore[assignment]
        service._build_conflict_details = MagicMock(  # type: ignore[assignment]
            return_value={"date": "2026-05-01"},
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException):
            service._reschedule_with_lock(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
            )


class TestRescheduleWithLockNonDeadlock:
    """Lines 180-189: OperationalError that is NOT a deadlock — re-raised."""

    def test_reraises_non_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        op_err = _make_operational_error(deadlock=False)
        _make_transaction_raise(mock_repository, op_err)

        service._is_deadlock_error = MagicMock(return_value=False)  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(OperationalError):
            service._reschedule_with_lock(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
            )


class TestRescheduleWithLockRepositoryException:
    """Lines 190-191: RepositoryException → _raise_conflict_from_repo_error."""

    def test_delegates_to_raise_conflict(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        repo_exc = RepositoryException("constraint violation")
        _make_transaction_raise(mock_repository, repo_exc)

        service._raise_conflict_from_repo_error = MagicMock(  # type: ignore[assignment]
            side_effect=BookingConflictException(message="conflict"),
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException):
            service._reschedule_with_lock(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
            )
        service._raise_conflict_from_repo_error.assert_called_once()


# ===================================================================
# reschedule_execution.py — _reschedule_with_existing_payment exception handlers
# ===================================================================


class TestRescheduleWithExistingPaymentIntegrityError:
    """Lines 249-259: IntegrityError with scope in existing-payment path."""

    def test_raises_conflict_with_scope(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_integrity_error())

        service._resolve_integrity_conflict_message = MagicMock(  # type: ignore[assignment]
            return_value=("Overlap", "student"),
        )
        service._build_conflict_details = MagicMock(  # type: ignore[assignment]
            return_value={},
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException) as exc_info:
            service._reschedule_with_existing_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
                payment_intent_id="pi_test123",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test123",
            )
        assert exc_info.value.details.get("conflict_scope") == "student"


class TestRescheduleWithExistingPaymentDeadlock:
    """Lines 260-268: OperationalError deadlock in existing-payment path."""

    def test_raises_conflict_on_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=True))

        service._is_deadlock_error = MagicMock(return_value=True)  # type: ignore[assignment]
        service._build_conflict_details = MagicMock(return_value={})  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException):
            service._reschedule_with_existing_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
                payment_intent_id="pi_test123",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test123",
            )


class TestRescheduleWithExistingPaymentNonDeadlock:
    """Lines 260-269: OperationalError non-deadlock re-raised."""

    def test_reraises_non_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=False))

        service._is_deadlock_error = MagicMock(return_value=False)  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(OperationalError):
            service._reschedule_with_existing_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
                payment_intent_id="pi_test123",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test123",
            )


class TestRescheduleWithExistingPaymentRepoException:
    """Lines 270-271: RepositoryException in existing-payment path."""

    def test_delegates_to_raise_conflict(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, RepositoryException("constraint"))

        service._raise_conflict_from_repo_error = MagicMock(  # type: ignore[assignment]
            side_effect=BookingConflictException(message="conflict"),
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException):
            service._reschedule_with_existing_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
                payment_intent_id="pi_test123",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test123",
            )
        service._raise_conflict_from_repo_error.assert_called_once()


# ===================================================================
# reschedule_execution.py — create_rescheduled_booking_with_existing_payment
# ===================================================================


class TestCreateRescheduledBookingExistingPaymentIntegrityWithScope:
    """Lines 327-335: IntegrityError with scope in standalone method."""

    def test_raises_conflict_with_scope(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_integrity_error())

        service._resolve_integrity_conflict_message = MagicMock(  # type: ignore[assignment]
            return_value=("Overlap", "instructor"),
        )
        service._build_conflict_details = MagicMock(return_value={})  # type: ignore[assignment]

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(BookingConflictException) as exc_info:
            service.create_rescheduled_booking_with_existing_payment(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
                payment_intent_id="pi_test",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test",
            )
        assert exc_info.value.details.get("conflict_scope") == "instructor"


class TestCreateRescheduledBookingExistingPaymentNonDeadlockReraise:
    """Line 343: OperationalError non-deadlock gets re-raised."""

    def test_reraises_non_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=False))

        service._is_deadlock_error = MagicMock(return_value=False)  # type: ignore[assignment]

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(OperationalError):
            service.create_rescheduled_booking_with_existing_payment(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
                payment_intent_id="pi_test",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test",
            )


class TestCreateRescheduledBookingExistingPaymentRepoException:
    """Lines 344-345: RepositoryException in standalone method."""

    def test_delegates_to_raise_conflict(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, RepositoryException("constraint"))

        service._raise_conflict_from_repo_error = MagicMock(  # type: ignore[assignment]
            side_effect=BookingConflictException(message="conflict"),
        )

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(BookingConflictException):
            service.create_rescheduled_booking_with_existing_payment(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
                payment_intent_id="pi_test",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_test",
            )


# ===================================================================
# reschedule_execution.py — create_rescheduled_booking_with_locked_funds
# ===================================================================


class TestCreateRescheduledBookingLockedFundsIntegrityWithScope:
    """Lines 438-446: IntegrityError with scope in locked-funds path."""

    def test_raises_conflict_with_scope(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_integrity_error())

        service._resolve_integrity_conflict_message = MagicMock(  # type: ignore[assignment]
            return_value=("Overlap", "instructor"),
        )
        service._build_conflict_details = MagicMock(return_value={})  # type: ignore[assignment]

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(BookingConflictException) as exc_info:
            service.create_rescheduled_booking_with_locked_funds(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
            )
        assert exc_info.value.details.get("conflict_scope") == "instructor"


class TestCreateRescheduledBookingLockedFundsDeadlock:
    """Lines 447-453: OperationalError deadlock in locked-funds path."""

    def test_raises_conflict_on_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=True))

        service._is_deadlock_error = MagicMock(return_value=True)  # type: ignore[assignment]
        service._build_conflict_details = MagicMock(return_value={})  # type: ignore[assignment]

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(BookingConflictException):
            service.create_rescheduled_booking_with_locked_funds(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
            )


class TestCreateRescheduledBookingLockedFundsNonDeadlock:
    """Lines 447-454: OperationalError non-deadlock re-raised."""

    def test_reraises_non_deadlock(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, _make_operational_error(deadlock=False))

        service._is_deadlock_error = MagicMock(return_value=False)  # type: ignore[assignment]

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(OperationalError):
            service.create_rescheduled_booking_with_locked_funds(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
            )


class TestCreateRescheduledBookingLockedFundsRepoException:
    """Lines 455-456: RepositoryException in locked-funds path."""

    def test_delegates_to_raise_conflict(self, service: BookingService, mock_repository: MagicMock) -> None:
        _stub_validate_inputs(service)
        _make_transaction_raise(mock_repository, RepositoryException("constraint"))

        service._raise_conflict_from_repo_error = MagicMock(  # type: ignore[assignment]
            side_effect=BookingConflictException(message="conflict"),
        )

        student = _make_user()
        bd = _make_booking_create()

        with pytest.raises(BookingConflictException):
            service.create_rescheduled_booking_with_locked_funds(
                student=student,
                booking_data=bd,
                selected_duration=60,
                original_booking_id=_make_ulid(),
            )


# ===================================================================
# reschedule_service.py — _normalize_reschedule_location_type
# ===================================================================


class TestNormalizeRescheduleLocationTypeInvalid:
    """Lines 166-168: Invalid location_type string raises ValidationException."""

    def test_raises_for_invalid_type(self, service: BookingService) -> None:
        booking = _make_booking(location_type="invalid_type")

        with pytest.raises(ValidationException, match="Invalid location_type"):
            service._normalize_reschedule_location_type(booking)


class TestNormalizeRescheduleLocationTypeNone:
    """Line 169: Non-string location_type defaults to 'online'."""

    def test_defaults_to_online_when_none(self, service: BookingService) -> None:
        booking = _make_booking()
        booking.location_type = None

        result = service._normalize_reschedule_location_type(booking)
        assert result == "online"


# ===================================================================
# reschedule_service.py — _ensure_reschedule_slot_available
# ===================================================================


class TestEnsureRescheduleSlotUnavailable:
    """Line 251: Slot not available raises BookingConflictException."""

    def test_raises_conflict_when_unavailable(self, service: BookingService) -> None:
        service.check_availability = MagicMock(  # type: ignore[assignment]
            return_value={"available": False, "reason": "Time conflict"},
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException, match="Time conflict"):
            service._ensure_reschedule_slot_available(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                student_id=_make_ulid(),
            )


class TestEnsureRescheduleSlotExceptionInCheck:
    """Lines 244-248: Non-dict availability with exception falls back to False."""

    def test_non_dict_falsy_raises_conflict(self, service: BookingService) -> None:
        # check_availability returns a non-dict falsy value that bool() handles
        service.check_availability = MagicMock(return_value=False)  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException, match="Requested time is unavailable"):
            service._ensure_reschedule_slot_available(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                student_id=_make_ulid(),
            )

    def test_non_dict_exception_in_bool_falls_back(self, service: BookingService) -> None:
        """When bool() raises on the result, is_available becomes False (lines 246-247)."""

        class BadBool:
            def __bool__(self) -> bool:
                raise TypeError("no bool")

        service.check_availability = MagicMock(return_value=BadBool())  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(BookingConflictException, match="Requested time is unavailable"):
            service._ensure_reschedule_slot_available(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                student_id=_make_ulid(),
            )


# ===================================================================
# reschedule_service.py — _resolve_reschedule_student
# ===================================================================


class TestResolveRescheduleStudentNotFound:
    """Line 266: Student not found raises NotFoundException."""

    @patch("app.services.booking.reschedule_service._booking_service_module")
    def test_raises_not_found(self, mock_mod: MagicMock, service: BookingService) -> None:
        booking = _make_booking()
        # Ensure the relationship attribute doesn't match so it falls through
        booking.student = None

        mock_user_repo = MagicMock()
        mock_user_repo.get_by_id.return_value = None

        module = MagicMock()
        module.RepositoryFactory.create_user_repository.return_value = mock_user_repo
        mock_mod.return_value = module

        with pytest.raises(NotFoundException, match="Student not found"):
            service._resolve_reschedule_student(booking)


# ===================================================================
# reschedule_service.py — reschedule_booking
# ===================================================================


class TestRescheduleBookingNotFound:
    """Line 280: Booking not found raises NotFoundException."""

    def test_raises_not_found(self, service: BookingService) -> None:
        service.get_booking_for_user = MagicMock(return_value=None)  # type: ignore[assignment]

        with pytest.raises(NotFoundException, match="Booking not found"):
            service.reschedule_booking(
                booking_id=_make_ulid(),
                payload=BookingRescheduleRequest(
                    booking_date=date(2026, 5, 1),
                    start_time=time(10, 0),
                    selected_duration=60,
                ),
                current_user=_make_user(),
            )


# ===================================================================
# reschedule_service.py — payment status normalization ("succeeded")
# ===================================================================


class TestReschedulePaymentStatusSucceededNormalized:
    """Line 302: payment_status 'succeeded' normalized to SETTLED.value → reuse path."""

    def test_succeeded_normalized_to_settled(self, service: BookingService) -> None:
        student = _make_user()
        original = _make_booking(
            student_id=student.id,
            payment_intent_id="pi_test_abc",
            payment_status="succeeded",
            payment_method_id="pm_test_abc",
        )

        service.get_booking_for_user = MagicMock(return_value=original)  # type: ignore[assignment]
        service.validate_reschedule_allowed = MagicMock()  # type: ignore[assignment]
        service._resolve_reschedule_student = MagicMock(return_value=student)  # type: ignore[assignment]
        service._build_reschedule_booking_data = MagicMock(  # type: ignore[assignment]
            return_value=_make_booking_create(instructor_id=original.instructor_id),
        )
        service._ensure_reschedule_slot_available = MagicMock()  # type: ignore[assignment]
        service.get_hours_until_start = MagicMock(return_value=48.0)  # type: ignore[assignment]
        service.should_trigger_lock = MagicMock(return_value=False)  # type: ignore[assignment]

        replacement = _make_booking()
        service._reschedule_with_existing_payment = MagicMock(return_value=replacement)  # type: ignore[assignment]

        result = service.reschedule_booking(
            booking_id=original.id,
            payload=BookingRescheduleRequest(
                booking_date=date(2026, 5, 1),
                start_time=time(10, 0),
                selected_duration=60,
            ),
            current_user=student,
        )

        assert result is replacement
        call_kwargs = service._reschedule_with_existing_payment.call_args[1]
        assert call_kwargs["payment_status"] == PaymentStatus.SETTLED.value
        assert call_kwargs["payment_intent_id"] == "pi_test_abc"


# ===================================================================
# reschedule_service.py — _reschedule_with_new_payment
# ===================================================================


class TestRescheduleWithNewPaymentNoMethod:
    """Line 363: No payment method raises ValidationException."""

    def test_raises_validation_when_no_payment_method(self, service: BookingService) -> None:
        service.validate_reschedule_payment_method = MagicMock(  # type: ignore[assignment]
            return_value=(False, None),
        )

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)
        student = _make_user()

        with pytest.raises(ValidationException) as exc_info:
            service._reschedule_with_new_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=student,
            )
        assert exc_info.value.code == "payment_method_required_for_reschedule"


class TestRescheduleWithNewPaymentConfirmationFailure:
    """Lines 382-392: Payment confirmation fails → abort + ValidationException."""

    def test_aborts_and_raises_on_confirm_failure(self, service: BookingService) -> None:
        service.validate_reschedule_payment_method = MagicMock(  # type: ignore[assignment]
            return_value=(True, "pm_test_xyz"),
        )
        replacement = _make_booking(status=BookingStatus.PENDING)
        service.create_booking_with_payment_setup = MagicMock(  # type: ignore[assignment]
            return_value=replacement,
        )
        service.confirm_booking_payment = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("Stripe declined"),
        )
        service.abort_pending_booking = MagicMock(return_value=True)  # type: ignore[assignment]

        original = _make_booking()
        bd = _make_booking_create(instructor_id=original.instructor_id)

        with pytest.raises(ValidationException) as exc_info:
            service._reschedule_with_new_payment(
                original_booking=original,
                booking_data=bd,
                selected_duration=60,
                current_user=_make_user(),
                reschedule_student=_make_user(),
            )
        assert exc_info.value.code == "payment_confirmation_failed"
        service.abort_pending_booking.assert_called_once_with(replacement.id)


# ===================================================================
# reschedule_service.py — _stripe_service_class (line 49)
# ===================================================================


class TestStripeServiceClassSourceIsMock:
    """Line 49: source_cls is mock but facade is not."""

    def test_returns_source_when_source_is_mock(self) -> None:
        from app.services.booking.reschedule_service import _stripe_service_class

        # facade_cls must NOT be mock-like: type(facade_cls).__module__ != "unittest.mock"
        facade_cls = type("RealStripeService", (), {})

        # source_cls must BE mock-like: type(source_cls).__module__ starts with "unittest.mock"
        source_cls = MagicMock(name="MockStripeService")

        booking_module = SimpleNamespace(StripeService=facade_cls)
        stripe_module = SimpleNamespace(StripeService=source_cls)

        with patch(
            "app.services.booking.reschedule_service._booking_service_module",
            return_value=booking_module,
        ), patch(
            "app.services.stripe_service",
            stripe_module,
            create=True,
        ):
            result = _stripe_service_class()

        assert result is source_cls
