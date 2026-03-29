from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any

from ...core.enums import RoleName
from ...core.exceptions import BusinessRuleException, NotFoundException
from ...models.booking import Booking
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingRescheduleCreationMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository

        def _acquire_booking_create_advisory_lock(
            self,
            instructor_id: str,
            booking_date: Any,
        ) -> None:
            ...

        def _check_conflicts_and_rules(
            self,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            student: User,
        ) -> None:
            ...

        def _create_booking_record(
            self,
            student: User,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            selected_duration: int,
        ) -> Booking:
            ...

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def _snapshot_booking(self, booking: Booking) -> dict[str, Any]:
            ...

        def _write_booking_audit(
            self,
            booking: Booking,
            action: str,
            *,
            actor: Any | None,
            before: dict[str, Any] | None,
            after: dict[str, Any] | None,
            default_role: str = "system",
        ) -> None:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

    def _create_rescheduled_booking_base_in_transaction(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
    ) -> tuple[Booking, Booking, Any, Any]:
        """Create a replacement booking and reschedule linkage inside an active transaction."""
        self._acquire_booking_create_advisory_lock(
            booking_data.instructor_id,
            booking_data.booking_date,
        )
        self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
        booking = self._create_booking_record(
            student, booking_data, service, instructor_profile, selected_duration
        )

        old_booking = self.repository.get_by_id(original_booking_id)
        if not old_booking:
            raise NotFoundException("Original booking not found")
        if booking_data.instructor_id != old_booking.instructor_id:
            raise BusinessRuleException(
                "Cannot change instructor during reschedule. Please cancel and create a new booking."
            )

        original_lesson_dt = self._get_booking_start_utc(old_booking)
        booking.rescheduled_from_booking_id = old_booking.id
        old_reschedule = self.repository.ensure_reschedule(old_booking.id)
        current_reschedule = self.repository.ensure_reschedule(booking.id)
        current_reschedule.original_lesson_datetime = original_lesson_dt
        old_reschedule.rescheduled_to_booking_id = booking.id
        previous_count = int(old_reschedule.reschedule_count or 0)
        new_count = previous_count + 1
        old_reschedule.reschedule_count = new_count
        current_reschedule.reschedule_count = new_count
        if bool(old_reschedule.late_reschedule_used):
            current_reschedule.late_reschedule_used = True

        self._enqueue_booking_outbox_event(booking, "booking.created")
        audit_after = self._snapshot_booking(booking)
        self._write_booking_audit(
            booking,
            "create",
            actor=student,
            before=None,
            after=audit_after,
            default_role=RoleName.STUDENT.value,
        )

        return booking, old_booking, old_reschedule, current_reschedule

    def _apply_existing_payment_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        old_booking: Booking,
        *,
        payment_intent_id: str,
        payment_status: str | None,
        payment_method_id: str | None,
    ) -> None:
        """Copy reusable payment state from the original booking onto the replacement booking."""
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        bp = self.repository.ensure_payment(booking.id)
        bp.payment_intent_id = payment_intent_id
        if isinstance(payment_method_id, str):
            bp.payment_method_id = payment_method_id
        if isinstance(payment_status, str):
            bp.payment_status = payment_status

        try:
            credit_repo = booking_service_module.RepositoryFactory.create_credit_repository(self.db)
            reserved_credits = credit_repo.get_reserved_credits_for_booking(
                booking_id=old_booking.id
            )
            reserved_total = 0
            for credit in reserved_credits:
                reserved_total += int(credit.reserved_amount_cents or credit.amount_cents or 0)
                credit.reserved_for_booking_id = booking.id
            if reserved_total > 0:
                bp.credits_reserved_cents = reserved_total
                old_bp = self.repository.ensure_payment(old_booking.id)
                old_bp.credits_reserved_cents = 0
        except Exception as exc:
            logger.warning(
                "Failed to transfer reserved credits from booking %s: %s",
                old_booking.id,
                exc,
            )

        payment_repo = PaymentRepository(self.db)
        payment_record = payment_repo.get_payment_by_intent_id(payment_intent_id)
        if payment_record:
            payment_record.booking_id = booking.id

    def _apply_locked_funds_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        current_reschedule: Any,
    ) -> None:
        """Mark a replacement booking as carrying locked funds."""
        from ...models.booking import PaymentStatus

        booking.has_locked_funds = True
        bp = self.repository.ensure_payment(booking.id)
        bp.payment_status = PaymentStatus.LOCKED.value
        current_reschedule.late_reschedule_used = True

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
        payment_status: str | None,
        payment_method_id: str | None,
    ) -> tuple[Booking, Booking]:
        """Create a replacement booking and copy the original payment within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            _current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_existing_payment_to_rescheduled_booking_in_transaction(
            booking,
            old_booking,
            payment_intent_id=payment_intent_id,
            payment_status=payment_status,
            payment_method_id=payment_method_id,
        )
        return booking, old_booking

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
        """Create a replacement booking that inherits a reschedule lock within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_locked_funds_to_rescheduled_booking_in_transaction(booking, current_reschedule)
        return booking, old_booking
