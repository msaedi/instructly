from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...core.enums import RoleName
from ...core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from ...models.booking import Booking, PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..config_service import ConfigService


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


class BookingNoShowResolutionMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService

        def transaction(self) -> Any:
            ...

        @staticmethod
        def _user_has_role(user: User, role: RoleName) -> bool:
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

        def resolve_lock_for_booking(
            self, locked_booking_id: str, resolution: str
        ) -> Dict[str, Any]:
            ...

        def _refund_for_instructor_no_show(
            self,
            *,
            stripe_service: Any,
            booking_id: str,
            payment_intent_id: Optional[str],
            payment_status: str,
        ) -> Dict[str, Any]:
            ...

        def _payout_for_student_no_show(
            self,
            *,
            stripe_service: Any,
            booking_id: str,
            payment_intent_id: Optional[str],
            payment_status: str,
        ) -> Dict[str, Any]:
            ...

        def _finalize_instructor_no_show(
            self,
            *,
            booking: Booking,
            stripe_result: Dict[str, Any],
            credit_service: Any,
            refunded_cents: int,
            locked_booking_id: Optional[str],
        ) -> None:
            ...

        def _finalize_student_no_show(
            self,
            *,
            booking: Booking,
            stripe_result: Dict[str, Any],
            credit_service: Any,
            payout_cents: int,
            locked_booking_id: Optional[str],
        ) -> None:
            ...

        def _cancel_no_show_report(self, booking: Booking) -> None:
            ...

    @BaseService.measure_operation("resolve_no_show")
    def resolve_no_show(
        self,
        *,
        booking_id: str,
        resolution: str,
        resolved_by: Optional[User],
        admin_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a no-show report and apply settlement."""
        booking_service_module = _booking_service_module()
        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        resolution_ctx = self._load_no_show_resolution_context(booking_id, now)
        stripe_result = self._execute_no_show_resolution_settlement(
            booking_id=booking_id,
            resolution=resolution,
            resolution_ctx=resolution_ctx,
            pricing_service=booking_service_module.PricingService(self.db),
        )
        booking = self._persist_no_show_resolution(
            booking_id=booking_id,
            resolution=resolution,
            resolved_by=resolved_by,
            admin_notes=admin_notes,
            now=now,
            resolution_ctx=resolution_ctx,
            stripe_result=stripe_result,
        )
        self._invalidate_booking_caches(booking)
        return self._build_no_show_resolution_response(booking_id, resolution, booking)

    def _load_no_show_resolution_context(self, booking_id: str, now: Any) -> Dict[str, Any]:
        from ...repositories.payment_repository import PaymentRepository

        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is None or no_show_record.no_show_reported_at is None:
                raise BusinessRuleException("No no-show report exists")
            if no_show_record.no_show_resolved_at is not None:
                raise BusinessRuleException("No-show already resolved")

            payment_repo = PaymentRepository(self.db)
            payment_context = self._resolve_no_show_payment_context(booking, payment_repo)
            amount_context = self._resolve_no_show_amounts(
                booking,
                payment_context["payment_record"],
            )
            return {
                "booking_id": booking.id,
                "no_show_type": no_show_record.no_show_type,
                "payment_status": payment_context["payment_status"],
                "payment_intent_id": payment_context["payment_intent_id"],
                "locked_booking_id": payment_context["locked_booking_id"],
                "student_pay_cents": amount_context["student_pay_cents"],
                "instructor_payout_cents": amount_context["instructor_payout_cents"],
                "audit_before": self._snapshot_booking(booking),
            }

    def _resolve_no_show_payment_context(
        self,
        booking: Booking,
        payment_repo: Any,
    ) -> Dict[str, Any]:
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
        if payment_status == PaymentStatus.MANUAL_REVIEW.value:
            payment_record = payment_repo.get_payment_by_booking_id(booking.id)
            if payment_record and isinstance(payment_record.status, str):
                payment_status = payment_record.status
        else:
            payment_record = payment_repo.get_payment_by_booking_id(booking.id)
        return {
            "payment_status": payment_status,
            "payment_intent_id": payment_intent_id,
            "locked_booking_id": locked_booking_id,
            "payment_record": payment_record,
        }

    def _resolve_no_show_amounts(
        self,
        booking: Booking,
        payment_record: Any,
    ) -> Dict[str, int]:
        booking_service_module = _booking_service_module()
        lesson_price_cents = int(float(booking.hourly_rate) * booking.duration_minutes * 100 / 60)
        instructor_payout_cents: Optional[int] = None
        student_pay_cents: Optional[int] = None
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
            instructor_payout_cents = self._default_no_show_payout_cents(lesson_price_cents)
        if student_pay_cents is None:
            student_pay_cents = self._default_no_show_student_pay_cents(lesson_price_cents)
        return {
            "student_pay_cents": student_pay_cents,
            "instructor_payout_cents": instructor_payout_cents,
        }

    def _default_no_show_payout_cents(self, lesson_price_cents: int) -> int:
        booking_service_module = _booking_service_module()
        try:
            default_tier = max(
                booking_service_module.Decimal(str(tier["pct"]))
                for tier in booking_service_module.PRICING_DEFAULTS.get("instructor_tiers", [])
                if "pct" in tier
            )
        except (ValueError, TypeError):
            default_tier = booking_service_module.Decimal("0")
        return int(
            booking_service_module.Decimal(lesson_price_cents)
            * (booking_service_module.Decimal("1") - default_tier)
        )

    def _default_no_show_student_pay_cents(self, lesson_price_cents: int) -> int:
        booking_service_module = _booking_service_module()
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
        return lesson_price_cents + student_fee_cents

    def _execute_no_show_resolution_settlement(
        self,
        *,
        booking_id: str,
        resolution: str,
        resolution_ctx: Dict[str, Any],
        pricing_service: Any,
    ) -> Dict[str, Any]:
        no_show_type = resolution_ctx["no_show_type"]
        locked_booking_id = resolution_ctx["locked_booking_id"]
        payment_intent_id = resolution_ctx["payment_intent_id"]
        payment_status = resolution_ctx["payment_status"]
        if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
            if no_show_type in {"instructor", "mutual"}:
                return self._execute_no_show_lock_or_stripe_resolution(
                    locked_booking_id=locked_booking_id,
                    lock_resolution="instructor_cancelled",
                    pricing_service=pricing_service,
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    mode="refund",
                )
            if no_show_type == "student":
                return self._execute_no_show_lock_or_stripe_resolution(
                    locked_booking_id=locked_booking_id,
                    lock_resolution="new_lesson_completed",
                    pricing_service=pricing_service,
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    mode="payout",
                )
            raise BusinessRuleException("Invalid no-show type")
        if resolution == "dispute_upheld":
            return self._execute_no_show_lock_or_stripe_resolution(
                locked_booking_id=locked_booking_id,
                lock_resolution="new_lesson_completed",
                pricing_service=pricing_service,
                booking_id=booking_id,
                payment_intent_id=payment_intent_id,
                payment_status=payment_status,
                mode="payout",
            )
        if resolution == "cancelled":
            return {"skipped": True}
        raise ValidationException("Invalid no-show resolution")

    def _execute_no_show_lock_or_stripe_resolution(
        self,
        *,
        locked_booking_id: Optional[str],
        lock_resolution: str,
        pricing_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
        mode: str,
    ) -> Dict[str, Any]:
        if locked_booking_id:
            return self.resolve_lock_for_booking(locked_booking_id, lock_resolution)
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        if mode == "refund":
            return self._refund_for_instructor_no_show(
                stripe_service=stripe_service,
                booking_id=booking_id,
                payment_intent_id=payment_intent_id,
                payment_status=payment_status,
            )
        return self._payout_for_student_no_show(
            stripe_service=stripe_service,
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            payment_status=payment_status,
        )

    def _persist_no_show_resolution(
        self,
        *,
        booking_id: str,
        resolution: str,
        resolved_by: Optional[User],
        admin_notes: Optional[str],
        now: Any,
        resolution_ctx: Dict[str, Any],
        stripe_result: Dict[str, Any],
    ) -> Booking:
        from ...repositories.payment_repository import PaymentRepository
        from ..credit_service import CreditService

        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after resolution")

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)
            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_resolved_at = now
            no_show_record.no_show_resolution = resolution
            self._apply_no_show_resolution_outcome(
                booking=booking,
                resolution=resolution,
                resolution_ctx=resolution_ctx,
                stripe_result=stripe_result,
                credit_service=credit_service,
            )
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
                before=resolution_ctx["audit_before"],
                after=audit_after,
                default_role=default_role,
            )
            return booking

    def _apply_no_show_resolution_outcome(
        self,
        *,
        booking: Booking,
        resolution: str,
        resolution_ctx: Dict[str, Any],
        stripe_result: Dict[str, Any],
        credit_service: Any,
    ) -> None:
        no_show_type = resolution_ctx["no_show_type"]
        if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
            booking.mark_no_show()
            if no_show_type in {"instructor", "mutual"}:
                self._finalize_instructor_no_show(
                    booking=booking,
                    stripe_result=stripe_result,
                    credit_service=credit_service,
                    refunded_cents=resolution_ctx["student_pay_cents"],
                    locked_booking_id=resolution_ctx["locked_booking_id"],
                )
                if no_show_type == "mutual":
                    mutual_bp = self.repository.ensure_payment(booking.id)
                    mutual_bp.settlement_outcome = "mutual_no_show_full_refund"
            else:
                self._finalize_student_no_show(
                    booking=booking,
                    stripe_result=stripe_result,
                    credit_service=credit_service,
                    payout_cents=resolution_ctx["instructor_payout_cents"],
                    locked_booking_id=resolution_ctx["locked_booking_id"],
                )
            return
        if resolution == "dispute_upheld":
            booking.mark_completed(completed_at=booking.completed_at)
            self._finalize_student_no_show(
                booking=booking,
                stripe_result=stripe_result,
                credit_service=credit_service,
                payout_cents=resolution_ctx["instructor_payout_cents"],
                locked_booking_id=resolution_ctx["locked_booking_id"],
            )
            upheld_bp = self.repository.ensure_payment(booking.id)
            upheld_bp.settlement_outcome = "lesson_completed_full_payout"
            upheld_bp.payment_status = PaymentStatus.SETTLED.value
            return
        self._cancel_no_show_report(booking)
        booking.mark_confirmed(confirmed_at=booking.confirmed_at)

    def _build_no_show_resolution_response(
        self,
        booking_id: str,
        resolution: str,
        booking: Booking,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "booking_id": booking_id,
            "resolution": resolution,
            "settlement_outcome": getattr(booking.payment_detail, "settlement_outcome", None),
        }
