from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy.exc import IntegrityError, OperationalError

from ...core.exceptions import BookingConflictException, RepositoryException
from ...models.booking import Booking, BookingStatus
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingRescheduleExecutionMixin:
    if TYPE_CHECKING:
        repository: BookingRepository

        def log_operation(self, operation: str, **kwargs: Any) -> None:
            ...

        def _validate_rescheduled_booking_inputs(
            self,
            student: User,
            booking_data: BookingCreate,
            selected_duration: int,
            original_booking_id: str,
        ) -> tuple[InstructorService, InstructorProfile, Booking]:
            ...

        def _create_rescheduled_booking_with_locked_funds_in_transaction(
            self,
            *,
            student: User,
            booking_data: BookingCreate,
            selected_duration: int,
            original_booking_id: str,
            service: InstructorService,
            instructor_profile: InstructorProfile,
        ) -> tuple[Booking, Booking]:
            ...

        def _create_rescheduled_booking_with_existing_payment_in_transaction(
            self,
            *,
            student: User,
            booking_data: BookingCreate,
            selected_duration: int,
            original_booking_id: str,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            payment_intent_id: str,
            payment_status: Optional[str],
            payment_method_id: Optional[str],
        ) -> tuple[Booking, Booking]:
            ...

        def _cancel_booking_without_stripe_in_transaction(
            self,
            booking_id: str,
            user: User,
            reason: Optional[str] = None,
            *,
            clear_payment_intent: bool = False,
        ) -> tuple[Booking, str]:
            ...

        def _resolve_integrity_conflict_message(
            self,
            exc: IntegrityError,
        ) -> tuple[str, str | None]:
            ...

        def _build_conflict_details(
            self,
            booking_data: BookingCreate,
            student_id: str,
        ) -> dict[str, Any]:
            ...

        def _is_deadlock_error(self, exc: OperationalError) -> bool:
            ...

        def _raise_conflict_from_repo_error(
            self,
            exc: RepositoryException,
            booking_data: BookingCreate,
            student_id: str,
        ) -> None:
            ...

        def _handle_post_booking_tasks(
            self,
            booking: Booking,
            is_reschedule: bool = False,
            old_booking: Optional[Booking] = None,
        ) -> None:
            ...

        def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
            ...

        def transaction(self) -> Any:
            ...

        def cancel_booking(
            self,
            booking_id: str,
            user: User,
            reason: Optional[str] = None,
        ) -> Booking:
            ...

    def _reschedule_with_lock(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
    ) -> Booking:
        """Handle the LOCK reschedule path with one transaction for create + cancel."""
        booking_service_module = _booking_service_module()

        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    def _reschedule_with_existing_payment(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """Handle the payment-reuse reschedule path with one transaction for create + cancel."""
        booking_service_module = _booking_service_module()

        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                    clear_payment_intent=True,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    @BaseService.measure_operation("create_rescheduled_booking_with_existing_payment")
    def create_rescheduled_booking_with_existing_payment(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """Create a rescheduled booking that reuses an existing PaymentIntent."""
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_rescheduled_booking_with_existing_payment",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        return booking

    def _rollback_reschedule_replacement(self, booking: Booking, user: User) -> None:
        """Best-effort rollback of a replacement booking when the original cannot be cancelled."""
        try:
            if booking.status == BookingStatus.PENDING:
                if self.abort_pending_booking(booking.id):
                    return
            self.cancel_booking(
                booking.id,
                user,
                "Reschedule failed - replacement booking cancelled",
            )
        except Exception as exc:  # pragma: no cover - defensive failure path
            logger.critical(
                "Failed to rollback replacement booking %s after reschedule failure: %s",
                booking.id,
                exc,
                exc_info=True,
            )

    @BaseService.measure_operation("abort_pending_booking")
    def abort_pending_booking(self, booking_id: str) -> bool:
        """Abort a pending booking used when reschedule payment confirmation fails."""
        try:
            booking = self.repository.get_by_id(booking_id)
            if not booking:
                return False

            if booking.status != BookingStatus.PENDING:
                logger.warning(
                    "Cannot abort booking %s - status is %s, not pending_payment",
                    booking_id,
                    booking.status,
                )
                return False

            with self.transaction():
                self.repository.delete(booking.id)

            logger.info("Aborted pending booking %s", booking_id)
            return True
        except Exception as e:
            logger.error("Failed to abort pending booking %s: %s", booking_id, e)
            return False

    @BaseService.measure_operation("create_rescheduled_booking_with_locked_funds")
    def create_rescheduled_booking_with_locked_funds(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
    ) -> Booking:
        """Create a rescheduled booking when LOCK is active."""
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_rescheduled_booking_with_locked_funds",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        return booking
