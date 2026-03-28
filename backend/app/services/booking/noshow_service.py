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
    from ..config_service import ConfigService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


def _is_mock_like(value: object) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def _stripe_service_class() -> Any:
    booking_service_module = _booking_service_module()
    from .. import stripe_service as stripe_service_module

    facade_cls = booking_service_module.StripeService
    source_cls = stripe_service_module.StripeService
    if _is_mock_like(facade_cls):
        return facade_cls
    if _is_mock_like(source_cls):
        return source_cls
    return facade_cls


class BookingNoShowMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService

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

        def _ensure_transfer_record(self, booking_id: str) -> Any:
            ...

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def resolve_lock_for_booking(
            self, locked_booking_id: str, resolution: str
        ) -> Dict[str, Any]:
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
        """
        Report a no-show and freeze payment automation.

        Reporting window: lesson_start <= now <= lesson_end + 24h
        """
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            is_admin = self._user_has_role(reporter, RoleName.ADMIN)
            is_student = reporter.id == booking.student_id
            is_instructor = reporter.id == booking.instructor_id

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
                if is_student
                else (RoleName.INSTRUCTOR.value if is_instructor else RoleName.ADMIN.value)
            )
            self._write_booking_audit(
                booking,
                "no_show_reported",
                actor=reporter,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

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
        """System-initiated no-show report from video attendance detection.

        No User reporter needed — actor=None with default_role="system".
        """
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

    @BaseService.measure_operation("resolve_no_show")
    def resolve_no_show(
        self,
        *,
        booking_id: str,
        resolution: str,
        resolved_by: Optional[User],
        admin_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a no-show report and apply settlement.
        """
        from ...repositories.payment_repository import PaymentRepository
        from ..credit_service import CreditService

        booking_service_module = _booking_service_module()

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is None or no_show_record.no_show_reported_at is None:
                raise BusinessRuleException("No no-show report exists")

            if no_show_record.no_show_resolved_at is not None:
                raise BusinessRuleException("No-show already resolved")

            no_show_type = no_show_record.no_show_type
            resolve_pd = booking.payment_detail
            payment_status = (resolve_pd.payment_status if resolve_pd is not None else None) or ""
            raw_resolve_pi = resolve_pd.payment_intent_id if resolve_pd is not None else None
            payment_intent_id = (
                raw_resolve_pi
                if isinstance(raw_resolve_pi, str) and raw_resolve_pi.startswith("pi_")
                else None
            )
            has_locked_funds = (
                getattr(booking, "has_locked_funds", False) is True
                and booking.rescheduled_from_booking_id is not None
            )
            locked_booking_id = booking.rescheduled_from_booking_id if has_locked_funds else None

            payment_repo = PaymentRepository(self.db)
            if payment_status == PaymentStatus.MANUAL_REVIEW.value:
                payment_record = payment_repo.get_payment_by_booking_id(booking.id)
                if payment_record and isinstance(payment_record.status, str):
                    payment_status = payment_record.status
            else:
                payment_record = payment_repo.get_payment_by_booking_id(booking.id)

            lesson_price_cents = int(
                float(booking.hourly_rate) * booking.duration_minutes * 100 / 60
            )
            instructor_payout_cents = None
            student_pay_cents = None
            if payment_record:
                if payment_record.amount is not None:
                    try:
                        student_pay_cents = int(payment_record.amount)
                    except (TypeError, ValueError):
                        student_pay_cents = None
                payout_value = getattr(payment_record, "instructor_payout_cents", None)
                if payout_value is not None:
                    try:
                        instructor_payout_cents = int(payout_value)
                    except (TypeError, ValueError):
                        instructor_payout_cents = None
                if instructor_payout_cents is None:
                    amount_value = getattr(payment_record, "amount", None)
                    fee_value = getattr(payment_record, "application_fee", None)
                    if amount_value is not None and fee_value is not None:
                        try:
                            instructor_payout_cents = max(0, int(amount_value) - int(fee_value))
                        except (TypeError, ValueError):
                            instructor_payout_cents = None
                if instructor_payout_cents is None:
                    base_price_value = getattr(payment_record, "base_price_cents", None)
                    tier_value = getattr(payment_record, "instructor_tier_pct", None)
                    if base_price_value is not None and tier_value is not None:
                        try:
                            instructor_payout_cents = int(
                                booking_service_module.Decimal(base_price_value)
                                * (
                                    booking_service_module.Decimal("1")
                                    - booking_service_module.Decimal(str(tier_value))
                                )
                            )
                        except (TypeError, ValueError, ArithmeticError):
                            instructor_payout_cents = None

            if instructor_payout_cents is None:
                try:
                    default_tier = max(
                        booking_service_module.Decimal(str(tier["pct"]))
                        for tier in booking_service_module.PRICING_DEFAULTS.get(
                            "instructor_tiers", []
                        )
                        if "pct" in tier
                    )
                except (ValueError, TypeError):
                    default_tier = booking_service_module.Decimal("0")
                instructor_payout_cents = int(
                    booking_service_module.Decimal(lesson_price_cents)
                    * (booking_service_module.Decimal("1") - default_tier)
                )

            if student_pay_cents is None:
                try:
                    student_fee_pct = booking_service_module.Decimal(
                        str(booking_service_module.PRICING_DEFAULTS.get("student_fee_pct", 0))
                    )
                except (TypeError, ValueError):
                    student_fee_pct = booking_service_module.Decimal("0")
                student_fee_cents = int(
                    (booking_service_module.Decimal(lesson_price_cents) * student_fee_pct).quantize(
                        booking_service_module.Decimal("1"),
                        rounding=booking_service_module.ROUND_HALF_UP,
                    )
                )
                student_pay_cents = lesson_price_cents + student_fee_cents

            audit_before = self._snapshot_booking(booking)

        stripe_result: Dict[str, Any] = {}

        if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
            if no_show_type == "instructor":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "instructor_cancelled"
                    )
                else:
                    stripe_service = _stripe_service_class()(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=booking_service_module.PricingService(self.db),
                    )
                    stripe_result = self._refund_for_instructor_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            elif no_show_type == "mutual":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "instructor_cancelled"
                    )
                else:
                    stripe_service = _stripe_service_class()(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=booking_service_module.PricingService(self.db),
                    )
                    stripe_result = self._refund_for_instructor_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            elif no_show_type == "student":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "new_lesson_completed"
                    )
                else:
                    stripe_service = _stripe_service_class()(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=booking_service_module.PricingService(self.db),
                    )
                    stripe_result = self._payout_for_student_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            else:
                raise BusinessRuleException("Invalid no-show type")

        elif resolution == "dispute_upheld":
            if locked_booking_id:
                stripe_result = self.resolve_lock_for_booking(
                    locked_booking_id, "new_lesson_completed"
                )
            else:
                stripe_service = _stripe_service_class()(
                    self.db,
                    config_service=self.config_service,
                    pricing_service=booking_service_module.PricingService(self.db),
                )
                stripe_result = self._payout_for_student_no_show(
                    stripe_service=stripe_service,
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                )

        elif resolution == "cancelled":
            stripe_result = {"skipped": True}
        else:
            raise ValidationException("Invalid no-show resolution")

        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after resolution")

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)

            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_resolved_at = now
            no_show_record.no_show_resolution = resolution

            if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
                booking.status = BookingStatus.NO_SHOW
                if no_show_type in {"instructor", "mutual"}:
                    self._finalize_instructor_no_show(
                        booking=booking,
                        stripe_result=stripe_result,
                        credit_service=credit_service,
                        refunded_cents=student_pay_cents,
                        locked_booking_id=locked_booking_id,
                    )
                    if no_show_type == "mutual":
                        mutual_bp = self.repository.ensure_payment(booking.id)
                        mutual_bp.settlement_outcome = "mutual_no_show_full_refund"
                else:
                    self._finalize_student_no_show(
                        booking=booking,
                        stripe_result=stripe_result,
                        credit_service=credit_service,
                        payout_cents=instructor_payout_cents,
                        locked_booking_id=locked_booking_id,
                    )

            elif resolution == "dispute_upheld":
                booking.status = BookingStatus.COMPLETED
                self._finalize_student_no_show(
                    booking=booking,
                    stripe_result=stripe_result,
                    credit_service=credit_service,
                    payout_cents=instructor_payout_cents,
                    locked_booking_id=locked_booking_id,
                )
                upheld_bp = self.repository.ensure_payment(booking.id)
                upheld_bp.settlement_outcome = "lesson_completed_full_payout"
                upheld_bp.payment_status = PaymentStatus.SETTLED.value

            elif resolution == "cancelled":
                self._cancel_no_show_report(booking)

            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_resolved",
                event_data={
                    "resolution": resolution,
                    "resolved_by": resolved_by.id if resolved_by else "system",
                    "admin_notes": admin_notes,
                },
            )

            audit_after = self._snapshot_booking(booking)
            default_role = (
                RoleName.ADMIN.value
                if resolved_by and self._user_has_role(resolved_by, RoleName.ADMIN)
                else "system"
            )
            self._write_booking_audit(
                booking,
                "no_show_resolved",
                actor=resolved_by,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "resolution": resolution,
            "settlement_outcome": getattr(booking.payment_detail, "settlement_outcome", None),
        }

    def _refund_for_instructor_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Refund full amount for instructor no-show or release authorization."""
        result: Dict[str, Any] = {"refund_success": False, "cancel_success": False, "error": None}
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        if already_captured:
            try:
                refund = stripe_service.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_instructor_noshow_{booking_id}",
                )
                result["refund_success"] = True
                result["refund_data"] = refund
            except Exception as exc:
                result["error"] = str(exc)
        else:
            try:
                stripe_service.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"cancel_instructor_noshow_{booking_id}",
                )
                result["cancel_success"] = True
            except Exception as exc:
                result["error"] = str(exc)

        return result

    def _payout_for_student_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Capture payment if needed for student no-show."""
        result: Dict[str, Any] = {
            "capture_success": False,
            "already_captured": False,
            "error": None,
        }
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if already_captured:
            result["already_captured"] = True
            return result
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        try:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=f"capture_student_noshow_{booking_id}",
            )
            result["capture_success"] = True
            result["capture_data"] = capture
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def _finalize_instructor_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        refunded_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist instructor no-show settlement."""
        booking_service_module = _booking_service_module()

        credit_service.release_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "instructor_no_show_full_refund"
        booking.student_credit_amount = 0
        bp.instructor_payout_amount = 0

        if locked_booking_id:
            booking.refunded_to_card_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        refund_data = stripe_result.get("refund_data") or {}
        refund_amount = refund_data.get("amount_refunded")
        if refund_amount is not None:
            try:
                refund_amount = int(refund_amount)
            except (TypeError, ValueError):
                refund_amount = None
        booking.refunded_to_card_amount = (
            refund_amount if refund_amount is not None else refunded_cents
        )

        if stripe_result.get("refund_success") or stripe_result.get("cancel_success"):
            if stripe_result.get("refund_success"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.refund_id = refund_data.get("refund_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            transfer_record = self._ensure_transfer_record(booking.id)
            transfer_record.refund_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            transfer_record.refund_error = stripe_result.get("error")
            transfer_record.refund_retry_count = (
                int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
            )
            bp.payment_status = PaymentStatus.MANUAL_REVIEW.value

    def _finalize_student_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        payout_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist student no-show settlement."""
        booking_service_module = _booking_service_module()

        credit_service.forfeit_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "student_no_show_full_payout"
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0

        if locked_booking_id:
            bp.instructor_payout_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        bp.instructor_payout_amount = payout_cents
        if stripe_result.get("capture_success") or stripe_result.get("already_captured"):
            capture_data = stripe_result.get("capture_data") or {}
            if capture_data.get("transfer_id"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp.capture_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
            bp.capture_error = stripe_result.get("error")

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
        """
        Mark a booking as no-show (instructor only).

        A no-show indicates the student did not attend the scheduled lesson.

        Args:
            booking_id: ID of booking to mark as no-show
            instructor: Instructor marking as no-show

        Returns:
            Booking marked as no-show

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be marked as no-show
        """
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as no-show")

        with self.transaction():
            # Load and validate booking
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

            # Mark as no-show using model method
            booking.mark_no_show()

            # Flush to persist status change
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

        # External operations outside transaction
        # Reload booking with details for cache invalidation
        refreshed_booking = self.repository.get_booking_with_details(booking_id)
        if refreshed_booking is None:
            raise NotFoundException("Booking not found")
        self._invalidate_booking_caches(refreshed_booking)

        return refreshed_booking
