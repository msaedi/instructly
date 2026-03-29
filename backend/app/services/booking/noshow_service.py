from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from ...core.enums import RoleName
from ...core.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingNoShowMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository

        def transaction(self) -> ContextManager[None]:
            ...

        @staticmethod
        def _user_has_role(user: User, role: RoleName) -> bool:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _get_booking_end_utc(self, booking: Booking) -> Any:
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

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

    @BaseService.measure_operation("report_no_show")
    def report_no_show(
        self,
        *,
        booking_id: str,
        reporter: User,
        no_show_type: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Report a no-show and freeze payment automation."""
        booking_service_module = _booking_service_module()

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        with self.transaction():
            report_ctx = self._load_no_show_report_context(
                booking_id=booking_id,
                reporter=reporter,
                no_show_type=no_show_type,
            )
            self._validate_no_show_report_request(
                booking=report_ctx["booking"],
                reporter=reporter,
                no_show_type=no_show_type,
                now=now,
                report_ctx=report_ctx,
            )
            booking = self._persist_no_show_report(
                booking=report_ctx["booking"],
                reporter=reporter,
                no_show_type=no_show_type,
                reason=reason,
                now=now,
                report_ctx=report_ctx,
            )

        self._invalidate_booking_caches(booking)
        return self._build_no_show_report_response(booking_id, no_show_type, now)

    def _load_no_show_report_context(
        self,
        *,
        booking_id: str,
        reporter: User,
        no_show_type: str,
    ) -> Dict[str, Any]:
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")
        return {
            "booking": booking,
            "is_admin": self._user_has_role(reporter, RoleName.ADMIN),
            "is_student": reporter.id == booking.student_id,
            "is_instructor": reporter.id == booking.instructor_id,
            "no_show_type": no_show_type,
        }

    def _validate_no_show_report_request(
        self,
        *,
        booking: Booking,
        reporter: User,
        no_show_type: str,
        now: Any,
        report_ctx: Dict[str, Any],
    ) -> None:
        booking_service_module = _booking_service_module()
        is_admin = report_ctx["is_admin"]
        is_student = report_ctx["is_student"]
        if no_show_type == "instructor":
            if not (is_student or is_admin):
                raise ForbiddenException(
                    "Only the student or admin can report an instructor no-show"
                )
        elif no_show_type == "student":
            if not is_admin:
                raise ForbiddenException("Only admin can report a student no-show")
        else:
            raise ValidationException("Invalid no_show_type")

        booking_start_utc = self._get_booking_start_utc(booking)
        booking_end_utc = self._get_booking_end_utc(booking)
        window_end = booking_end_utc + booking_service_module.timedelta(hours=24)
        if not (booking_start_utc <= now <= window_end):
            raise BusinessRuleException(
                "No-show can only be reported between lesson start and 24 hours after lesson end"
            )
        if booking.status == BookingStatus.CANCELLED:
            raise BusinessRuleException("Cannot report no-show for cancelled booking")
        no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
        if no_show_record is not None and no_show_record.no_show_reported_at is not None:
            raise BusinessRuleException("No-show already reported for this booking")

    def _persist_no_show_report(
        self,
        *,
        booking: Booking,
        reporter: User,
        no_show_type: str,
        reason: Optional[str],
        now: Any,
        report_ctx: Dict[str, Any],
    ) -> Booking:
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()
        audit_before = self._snapshot_booking(booking)
        noshow_bp = self.repository.ensure_payment(booking.id)
        previous_payment_status = noshow_bp.payment_status

        noshow_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
        no_show_record = self.repository.ensure_no_show(booking.id)
        no_show_record.no_show_reported_by = reporter.id
        no_show_record.no_show_reported_at = now
        no_show_record.no_show_type = no_show_type
        no_show_record.no_show_disputed = False
        no_show_record.no_show_disputed_at = None
        no_show_record.no_show_dispute_reason = None
        no_show_record.no_show_resolved_at = None
        no_show_record.no_show_resolution = None

        payment_repo = PaymentRepository(self.db)
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="no_show_reported",
            event_data={
                "type": no_show_type,
                "reported_by": reporter.id,
                "reason": reason,
                "previous_payment_status": previous_payment_status,
                "dispute_window_ends": (
                    now + booking_service_module.timedelta(hours=24)
                ).isoformat(),
            },
        )

        audit_after = self._snapshot_booking(booking)
        default_role = (
            RoleName.STUDENT.value
            if report_ctx["is_student"]
            else (
                RoleName.INSTRUCTOR.value if report_ctx["is_instructor"] else RoleName.ADMIN.value
            )
        )
        self._write_booking_audit(
            booking,
            "no_show_reported",
            actor=reporter,
            before=audit_before,
            after=audit_after,
            default_role=default_role,
        )
        return booking

    def _build_no_show_report_response(
        self,
        booking_id: str,
        no_show_type: str,
        now: Any,
    ) -> Dict[str, Any]:
        booking_service_module = _booking_service_module()
        return {
            "success": True,
            "booking_id": booking_id,
            "no_show_type": no_show_type,
            "payment_status": PaymentStatus.MANUAL_REVIEW.value,
            "dispute_window_ends": (now + booking_service_module.timedelta(hours=24)).isoformat(),
        }

    @BaseService.measure_operation("report_automated_no_show")
    def report_automated_no_show(
        self,
        *,
        booking_id: str,
        no_show_type: str,
        reason: str,
    ) -> Dict[str, Any]:
        """System-initiated no-show report from video attendance detection."""
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status != BookingStatus.CONFIRMED.value:
                raise ValidationException(
                    f"Cannot report no-show for booking in status {booking.status}"
                )

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is not None and no_show_record.no_show_reported_at is not None:
                raise BusinessRuleException("No-show already reported for this booking")

            audit_before = self._snapshot_booking(booking)
            noshow_bp = self.repository.ensure_payment(booking.id)
            previous_payment_status = noshow_bp.payment_status

            noshow_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_reported_by = None
            no_show_record.no_show_reported_at = now
            no_show_record.no_show_type = no_show_type
            no_show_record.no_show_disputed = False
            no_show_record.no_show_disputed_at = None
            no_show_record.no_show_dispute_reason = None
            no_show_record.no_show_resolved_at = None
            no_show_record.no_show_resolution = None

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_reported",
                event_data={
                    "type": no_show_type,
                    "reported_by": None,
                    "reason": reason,
                    "automated": True,
                    "previous_payment_status": previous_payment_status,
                    "dispute_window_ends": (
                        now + booking_service_module.timedelta(hours=24)
                    ).isoformat(),
                },
            )

            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "no_show_reported_automated",
                actor=None,
                before=audit_before,
                after=audit_after,
                default_role="system",
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "no_show_type": no_show_type,
            "payment_status": PaymentStatus.MANUAL_REVIEW.value,
            "dispute_window_ends": (now + booking_service_module.timedelta(hours=24)).isoformat(),
        }

    @BaseService.measure_operation("dispute_no_show")
    def dispute_no_show(
        self,
        *,
        booking_id: str,
        disputer: User,
        reason: str,
    ) -> Dict[str, Any]:
        """Dispute a no-show report within the allowed window."""
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is None or no_show_record.no_show_reported_at is None:
                raise BusinessRuleException("No no-show report exists for this booking")

            if no_show_record.no_show_disputed:
                raise BusinessRuleException("No-show already disputed")

            if no_show_record.no_show_resolved_at is not None:
                raise BusinessRuleException("No-show already resolved")

            if no_show_record.no_show_type == "instructor":
                if disputer.id != booking.instructor_id:
                    raise ForbiddenException("Only the accused instructor can dispute")
            elif no_show_record.no_show_type == "student":
                if disputer.id != booking.student_id:
                    raise ForbiddenException("Only the accused student can dispute")
            elif no_show_record.no_show_type == "mutual":
                if disputer.id not in {booking.student_id, booking.instructor_id}:
                    raise ForbiddenException("Only lesson participants can dispute")
            else:
                raise BusinessRuleException("Invalid no-show type")

            reported_at = no_show_record.no_show_reported_at
            if reported_at.tzinfo is None:
                reported_at = reported_at.replace(tzinfo=booking_service_module.timezone.utc)
            dispute_deadline = reported_at + booking_service_module.timedelta(hours=24)
            if now > dispute_deadline:
                raise BusinessRuleException(
                    f"Dispute window closed at {dispute_deadline.isoformat()}"
                )

            audit_before = self._snapshot_booking(booking)
            no_show_record.no_show_disputed = True
            no_show_record.no_show_disputed_at = now
            no_show_record.no_show_dispute_reason = reason

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_disputed",
                event_data={
                    "type": no_show_record.no_show_type,
                    "disputed_by": disputer.id,
                    "reason": reason,
                },
            )

            audit_after = self._snapshot_booking(booking)
            default_role = (
                RoleName.STUDENT.value
                if disputer.id == booking.student_id
                else RoleName.INSTRUCTOR.value
            )
            self._write_booking_audit(
                booking,
                "no_show_disputed",
                actor=disputer,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "disputed": True,
            "requires_platform_review": True,
        }

    def _cancel_no_show_report(self, booking: Booking) -> None:
        """Cancel a no-show report and restore payment status."""
        from ...repositories.payment_repository import PaymentRepository

        payment_repo = PaymentRepository(self.db)
        bp = self.repository.ensure_payment(booking.id)
        payment_record = payment_repo.get_payment_by_booking_id(booking.id)
        if payment_record and isinstance(payment_record.status, str):
            status = payment_record.status
            if status == "succeeded":
                bp.payment_status = PaymentStatus.SETTLED.value
            elif status in {"requires_capture", "authorized"}:
                bp.payment_status = PaymentStatus.AUTHORIZED.value
            else:
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        else:
            bp.payment_status = PaymentStatus.AUTHORIZED.value if bp.payment_intent_id else None

        bp.settlement_outcome = None
        booking.student_credit_amount = None
        bp.instructor_payout_amount = None
        booking.refunded_to_card_amount = None

    @BaseService.measure_operation("mark_no_show")
    def mark_no_show(self, booking_id: str, instructor: User) -> Booking:
        """Mark a booking as no-show (instructor only)."""
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as no-show")

        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")
            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only mark your own bookings as no-show")
            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Only confirmed bookings can be marked as no-show - current status: {booking.status}"
                )

            audit_before = self._snapshot_booking(booking)
            booking.mark_no_show()
            self.repository.flush()
            self._enqueue_booking_outbox_event(booking, "booking.no_show")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "no_show",
                actor=instructor,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )

        refreshed_booking = self.repository.get_booking_with_details(booking_id)
        if refreshed_booking is None:
            raise NotFoundException("Booking not found")
        self._invalidate_booking_caches(refreshed_booking)
        return refreshed_booking
