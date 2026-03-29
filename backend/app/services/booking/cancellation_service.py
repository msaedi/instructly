from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from ...core.enums import RoleName
from ...core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...models.booking_transfer import BookingTransfer
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
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


class BookingCancellationMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        conflict_checker_repository: ConflictCheckerRepository
        config_service: ConfigService

        def transaction(self) -> ContextManager[None]:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
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

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
            ...

        def resolve_lock_for_booking(
            self,
            locked_booking_id: str,
            resolution: str,
        ) -> dict[str, Any]:
            ...

        def _send_cancellation_notifications(
            self,
            booking: Booking,
            cancelled_by_role: str,
        ) -> None:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

        def _mark_video_session_terminal_on_cancellation(self, booking: Booking) -> None:
            ...

        def _execute_cancellation_stripe_calls(
            self, ctx: Dict[str, Any], stripe_service: Any
        ) -> Dict[str, Any]:
            ...

        def _finalize_cancellation(
            self,
            booking: Booking,
            ctx: Dict[str, Any],
            stripe_results: Dict[str, Any],
            payment_repo: Any,
        ) -> None:
            ...

        def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
            ...

    def _cancel_booking_without_stripe_in_transaction(
        self,
        booking_id: str,
        user: User,
        reason: Optional[str] = None,
        *,
        clear_payment_intent: bool = False,
    ) -> tuple[Booking, str]:
        """Apply a no-Stripe cancellation inside an active transaction."""
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")

        if user.id not in [booking.student_id, booking.instructor_id]:
            raise ValidationException("You don't have permission to cancel this booking")

        if not booking.is_cancellable:
            raise BusinessRuleException(
                f"Booking cannot be cancelled - current status: {booking.status}"
            )

        audit_before = self._snapshot_booking(booking)

        if clear_payment_intent:
            bp = self.repository.ensure_payment(booking.id)
            bp.payment_intent_id = None

        booking.cancel(user.id, reason)
        self._mark_video_session_terminal_on_cancellation(booking)
        self._enqueue_booking_outbox_event(booking, "booking.cancelled")
        audit_after = self._snapshot_booking(booking)
        default_role = (
            RoleName.STUDENT.value if user.id == booking.student_id else RoleName.INSTRUCTOR.value
        )
        self._write_booking_audit(
            booking,
            "cancel",
            actor=user,
            before=audit_before,
            after=audit_after,
            default_role=default_role,
        )

        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
        return booking, cancelled_by_role

    @BaseService.measure_operation("cancel_booking")
    def cancel_booking(self, booking_id: str, user: User, reason: Optional[str] = None) -> Booking:
        """Cancel a booking using the 3-phase Stripe-safe cancellation flow."""
        booking_service_module = _booking_service_module()
        execution_ctx = self._load_cancellation_execution_context(booking_id, user)
        existing_booking = execution_ctx.get("existing_booking")
        if existing_booking is not None:
            return cast(Booking, existing_booking)

        cancel_ctx = cast(Dict[str, Any], execution_ctx["cancel_ctx"])
        stripe_results = self._execute_cancellation_financial_resolution(
            cancel_ctx,
            booking_service_module.PricingService(self.db),
        )
        booking = self._persist_cancellation_result(
            booking_id=booking_id,
            user=user,
            reason=reason,
            cancel_ctx=cancel_ctx,
            stripe_results=stripe_results,
        )
        self._post_cancellation_actions(booking, cancel_ctx["cancelled_by_role"])
        return booking

    def _load_cancellation_execution_context(self, booking_id: str, user: User) -> Dict[str, Any]:
        with self.transaction():
            booking = self.repository.get_booking_for_participant_for_update(booking_id, user.id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status == BookingStatus.CANCELLED:
                return {"existing_booking": booking}

            if not booking.is_cancellable:
                raise BusinessRuleException(
                    f"Booking cannot be cancelled - current status: {booking.status}"
                )

            cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
            cancel_ctx = self._resolve_locked_cancellation_context(booking, cancelled_by_role)
            if cancel_ctx is None:
                cancel_ctx = self._build_cancellation_context(booking, user)

            return {"cancel_ctx": cancel_ctx}

    def _resolve_locked_cancellation_context(
        self,
        booking: Booking,
        cancelled_by_role: str,
    ) -> Dict[str, Any] | None:
        locked_booking_id: str | None = None
        if (
            getattr(booking, "has_locked_funds", False) is True
            and booking.rescheduled_from_booking_id
        ):
            locked_booking_id = booking.rescheduled_from_booking_id
        elif getattr(booking.payment_detail, "payment_status", None) == PaymentStatus.LOCKED.value:
            locked_booking_id = booking.id

        if not locked_booking_id:
            return None

        booking_service_module = _booking_service_module()
        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until = booking_service_module.TimezoneService.hours_until(booking_start_utc)
        if cancelled_by_role == "instructor":
            resolution = "instructor_cancelled"
        elif hours_until >= 12:
            resolution = "new_lesson_cancelled_ge12"
        else:
            resolution = "new_lesson_cancelled_lt12"

        return {
            "locked_booking_id": locked_booking_id,
            "resolution": resolution,
            "cancelled_by_role": cancelled_by_role,
            "default_role": (
                RoleName.STUDENT.value
                if cancelled_by_role == "student"
                else RoleName.INSTRUCTOR.value
            ),
        }

    def _execute_cancellation_financial_resolution(
        self,
        cancel_ctx: Dict[str, Any],
        pricing_service: Any,
    ) -> Dict[str, Any]:
        if "locked_booking_id" in cancel_ctx:
            return self.resolve_lock_for_booking(
                cancel_ctx["locked_booking_id"],
                cancel_ctx["resolution"],
            )

        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        return self._execute_cancellation_stripe_calls(cancel_ctx, stripe_service)

    def _persist_cancellation_result(
        self,
        *,
        booking_id: str,
        user: User,
        reason: Optional[str],
        cancel_ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
    ) -> Booking:
        from ...repositories.payment_repository import PaymentRepository

        with self.transaction():
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after Stripe calls")

            payment_repo = PaymentRepository(self.db)
            audit_before = self._snapshot_booking(booking)
            if "locked_booking_id" in cancel_ctx:
                if stripe_results.get("success") or stripe_results.get("skipped"):
                    bp = self.repository.ensure_payment(booking.id)
                    bp.payment_status = PaymentStatus.SETTLED.value
            else:
                self._finalize_cancellation(booking, cancel_ctx, stripe_results, payment_repo)

            booking.cancel(user.id, reason)
            self._mark_video_session_terminal_on_cancellation(booking)
            self._enqueue_booking_outbox_event(booking, "booking.cancelled")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "cancel",
                actor=user,
                before=audit_before,
                after=audit_after,
                default_role=cancel_ctx["default_role"],
            )
            return booking

    @BaseService.measure_operation("cancel_booking_without_stripe")
    def cancel_booking_without_stripe(
        self,
        booking_id: str,
        user: User,
        reason: Optional[str] = None,
        *,
        clear_payment_intent: bool = False,
    ) -> Booking:
        """Cancel a booking without Stripe or policy settlement, for payment-reuse flows."""
        with self.transaction():
            booking, cancelled_by_role = self._cancel_booking_without_stripe_in_transaction(
                booking_id,
                user,
                reason,
                clear_payment_intent=clear_payment_intent,
            )
        self._post_cancellation_actions(booking, cancelled_by_role)

        return booking

    def _build_cancellation_context(self, booking: Booking, user: User) -> Dict[str, Any]:
        """Build the read-only context needed for cancellation execution and finalization."""
        hours_until = self._resolve_cancellation_time_context(booking)
        payment_context = self._resolve_cancellation_payment_context(booking)
        gaming_context = self._resolve_gaming_reschedule_context(booking)
        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
        scenario = self._determine_cancellation_scenario(
            booking=booking,
            cancelled_by_role=cancelled_by_role,
            hours_until=hours_until,
            payment_intent_id=payment_context["payment_intent_id"],
            payment_status=payment_context["payment_status"],
            was_gaming_reschedule=gaming_context["was_gaming_reschedule"],
        )
        instructor_stripe_account_id = self._load_cancellation_instructor_account(booking)
        return self._assemble_cancellation_context(
            booking=booking,
            cancelled_by_role=cancelled_by_role,
            hours_until=hours_until,
            scenario=scenario,
            payment_context=payment_context,
            gaming_context=gaming_context,
            instructor_stripe_account_id=instructor_stripe_account_id,
        )

    def _resolve_cancellation_time_context(self, booking: Booking) -> float:
        booking_service_module = _booking_service_module()
        booking_start_utc = self._get_booking_start_utc(booking)
        return float(booking_service_module.TimezoneService.hours_until(booking_start_utc))

    def _resolve_cancellation_payment_context(self, booking: Booking) -> Dict[str, Any]:
        pd = booking.payment_detail
        raw_payment_intent_id = pd.payment_intent_id if pd is not None else None
        payment_intent_id = (
            raw_payment_intent_id
            if isinstance(raw_payment_intent_id, str) and raw_payment_intent_id.startswith("pi_")
            else None
        )
        return {
            "payment_intent_id": payment_intent_id,
            "payment_status": pd.payment_status if pd is not None else None,
        }

    def _resolve_gaming_reschedule_context(self, booking: Booking) -> Dict[str, Any]:
        booking_service_module = _booking_service_module()
        was_gaming_reschedule = False
        hours_from_original: Optional[float] = None
        reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
        original_lesson_datetime = (
            reschedule_record.original_lesson_datetime if reschedule_record else None
        )
        if booking.rescheduled_from_booking_id and original_lesson_datetime:
            original_dt = original_lesson_datetime
            if original_dt.tzinfo is None:
                original_dt = original_dt.replace(tzinfo=booking_service_module.timezone.utc)
            reschedule_time = booking.created_at
            if reschedule_time is not None:
                if reschedule_time.tzinfo is None:
                    reschedule_time = reschedule_time.replace(
                        tzinfo=booking_service_module.timezone.utc
                    )
                hours_from_original = (original_dt - reschedule_time).total_seconds() / 3600
                was_gaming_reschedule = hours_from_original is not None and hours_from_original < 24

        return {
            "hours_from_original": hours_from_original,
            "was_gaming_reschedule": was_gaming_reschedule,
            "original_lesson_datetime": original_lesson_datetime,
        }

    def _determine_cancellation_scenario(
        self,
        *,
        booking: Booking,
        cancelled_by_role: str,
        hours_until: float,
        payment_intent_id: Optional[str],
        payment_status: Any,
        was_gaming_reschedule: bool,
    ) -> str:
        is_pending_payment = (
            booking.status == BookingStatus.PENDING
            or payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        ) and payment_intent_id is None
        if is_pending_payment:
            return "pending_payment"

        if cancelled_by_role == "instructor":
            return (
                "instructor_cancel_over_24h" if hours_until >= 24 else "instructor_cancel_under_24h"
            )

        if hours_until >= 24:
            scenario = "over_24h_gaming" if was_gaming_reschedule else "over_24h_regular"
        elif 12 <= hours_until < 24:
            scenario = "between_12_24h"
        else:
            scenario = "under_12h" if payment_intent_id else "under_12h_no_pi"

        if scenario == "over_24h_gaming" and payment_status != PaymentStatus.AUTHORIZED.value:
            raise BusinessRuleException(
                "Gaming reschedule cancellations require an authorized payment"
            )
        return scenario

    def _load_cancellation_instructor_account(self, booking: Booking) -> Optional[str]:
        try:
            from ...repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            instructor_profile = self.conflict_checker_repository.get_instructor_profile(
                booking.instructor_id
            )
            if not instructor_profile:
                return None
            connected_account = payment_repo.get_connected_account_by_instructor_id(
                instructor_profile.id
            )
            if connected_account and connected_account.stripe_account_id:
                return cast(Optional[str], connected_account.stripe_account_id)
        except Exception as exc:
            logger.warning(
                "Failed to load instructor Stripe account for booking %s: %s",
                booking.id,
                exc,
            )
        return None

    def _assemble_cancellation_context(
        self,
        *,
        booking: Booking,
        cancelled_by_role: str,
        hours_until: float,
        scenario: str,
        payment_context: Dict[str, Any],
        gaming_context: Dict[str, Any],
        instructor_stripe_account_id: Optional[str],
    ) -> Dict[str, Any]:
        default_role = (
            RoleName.STUDENT.value if cancelled_by_role == "student" else RoleName.INSTRUCTOR.value
        )
        lesson_price_cents = int(float(booking.hourly_rate) * booking.duration_minutes * 100 / 60)
        return {
            "booking_id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "payment_intent_id": payment_context["payment_intent_id"],
            "payment_status": payment_context["payment_status"],
            "scenario": scenario,
            "hours_until": hours_until,
            "hours_from_original": gaming_context["hours_from_original"],
            "was_gaming_reschedule": gaming_context["was_gaming_reschedule"],
            "lesson_price_cents": lesson_price_cents,
            "instructor_stripe_account_id": instructor_stripe_account_id,
            "rescheduled_from_booking_id": booking.rescheduled_from_booking_id,
            "original_lesson_datetime": gaming_context["original_lesson_datetime"],
            "default_role": default_role,
            "cancelled_by_role": cancelled_by_role,
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
        }
