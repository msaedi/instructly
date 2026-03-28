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

    from ...events import EventPublisher
    from ...integrations.hundredms_client import HundredMsClient
    from ...models.booking_transfer import BookingTransfer
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..config_service import ConfigService
    from ..system_message_service import SystemMessageService

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
        event_publisher: EventPublisher
        system_message_service: SystemMessageService

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
        """
        Cancel a booking.

        Architecture Note (v123): Uses 3-phase pattern to avoid holding DB locks
        during Stripe network calls:
        - Phase 1: Read/validate booking, determine scenario (~5ms)
        - Phase 2: Execute Stripe calls based on scenario (no transaction, 100-500ms)
        - Phase 3: Update booking status, create events (~5ms)

        Args:
            booking_id: ID of booking to cancel
            user: User performing cancellation
            reason: Optional cancellation reason

        Returns:
            Cancelled booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot cancel
            BusinessRuleException: If booking not cancellable
        """
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        # ========== PHASE 1: Read/validate (quick transaction) ==========
        with self.transaction():
            # Defense-in-depth: filter by participant at DB level (AUTHZ-VULN-01)
            booking = self.repository.get_booking_for_participant_for_update(booking_id, user.id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status == BookingStatus.CANCELLED:
                return booking

            if not booking.is_cancellable:
                raise BusinessRuleException(
                    f"Booking cannot be cancelled - current status: {booking.status}"
                )

            cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
            lock_ctx: Optional[Dict[str, Any]] = None

            if (
                getattr(booking, "has_locked_funds", False) is True
                and booking.rescheduled_from_booking_id
            ):
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until = booking_service_module.TimezoneService.hours_until(booking_start_utc)
                if cancelled_by_role == "instructor":
                    resolution = "instructor_cancelled"
                elif hours_until >= 12:
                    resolution = "new_lesson_cancelled_ge12"
                else:
                    resolution = "new_lesson_cancelled_lt12"

                lock_ctx = {
                    "locked_booking_id": booking.rescheduled_from_booking_id,
                    "resolution": resolution,
                    "cancelled_by_role": cancelled_by_role,
                    "default_role": (
                        RoleName.STUDENT.value
                        if cancelled_by_role == "student"
                        else RoleName.INSTRUCTOR.value
                    ),
                }
            elif (
                getattr(booking.payment_detail, "payment_status", None)
                == PaymentStatus.LOCKED.value
            ):
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until = booking_service_module.TimezoneService.hours_until(booking_start_utc)
                if cancelled_by_role == "instructor":
                    resolution = "instructor_cancelled"
                elif hours_until >= 12:
                    resolution = "new_lesson_cancelled_ge12"
                else:
                    resolution = "new_lesson_cancelled_lt12"
                lock_ctx = {
                    "locked_booking_id": booking.id,
                    "resolution": resolution,
                    "cancelled_by_role": cancelled_by_role,
                    "default_role": (
                        RoleName.STUDENT.value
                        if cancelled_by_role == "student"
                        else RoleName.INSTRUCTOR.value
                    ),
                }

            if lock_ctx:
                cancel_ctx = lock_ctx
            else:
                # Extract data needed for Phase 2 (avoid holding ORM objects)
                cancel_ctx = self._build_cancellation_context(booking, user)

        # ========== PHASE 2: Stripe calls (NO transaction) ==========
        stripe_results: Dict[str, Any] = {}
        if "locked_booking_id" in cancel_ctx:
            stripe_results = self.resolve_lock_for_booking(
                cancel_ctx["locked_booking_id"],
                cancel_ctx["resolution"],
            )
        else:
            stripe_service = _stripe_service_class()(
                self.db,
                config_service=self.config_service,
                pricing_service=booking_service_module.PricingService(self.db),
            )
            stripe_results = self._execute_cancellation_stripe_calls(cancel_ctx, stripe_service)

        # ========== PHASE 3: Write results (quick transaction) ==========
        with self.transaction():
            # Re-fetch booking to avoid stale ORM object
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after Stripe calls")

            payment_repo = PaymentRepository(self.db)
            audit_before = self._snapshot_booking(booking)

            if "locked_booking_id" in cancel_ctx:
                # LOCK-driven cancellation: no direct Stripe updates on this booking
                if stripe_results.get("success") or stripe_results.get("skipped"):
                    bp = self.repository.ensure_payment(booking.id)
                    bp.payment_status = PaymentStatus.SETTLED.value
            else:
                # Finalize cancellation with Stripe results
                self._finalize_cancellation(booking, cancel_ctx, stripe_results, payment_repo)

            # Cancel the booking
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

        cancelled_by_role = cancel_ctx["cancelled_by_role"]

        # Post-transaction: Publish events and notifications
        self._post_cancellation_actions(booking, cancelled_by_role)

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
        """
        Cancel a booking without invoking Stripe or cancellation policy logic.

        This is intended for reschedule flows where the existing payment is reused.
        """
        with self.transaction():
            booking, cancelled_by_role = self._cancel_booking_without_stripe_in_transaction(
                booking_id,
                user,
                reason,
                clear_payment_intent=clear_payment_intent,
            )
        self._post_cancellation_actions(booking, cancelled_by_role)

        return booking

    def _mark_video_session_terminal_on_cancellation(self, booking: Booking) -> None:
        """Mark booking video session state as terminal on cancellation."""
        booking_service_module = _booking_service_module()

        video_session = getattr(booking, "video_session", None)
        if video_session is None:
            return

        ended_at = booking.cancelled_at or booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        if video_session.session_ended_at is None:
            video_session.session_ended_at = ended_at

        if (
            video_session.session_duration_seconds is None
            and isinstance(video_session.session_started_at, booking_service_module.datetime)
            and isinstance(video_session.session_ended_at, booking_service_module.datetime)
        ):
            duration_seconds = int(
                (video_session.session_ended_at - video_session.session_started_at).total_seconds()
            )
            video_session.session_duration_seconds = max(duration_seconds, 0)

    def _build_hundredms_client_for_cleanup(self) -> HundredMsClient | None:
        """Create a 100ms client for post-cancellation cleanup, when configured."""
        booking_service_module = _booking_service_module()
        config = booking_service_module.settings

        if not config.hundredms_enabled:
            return None

        access_key = (config.hundredms_access_key or "").strip()
        raw_secret = config.hundredms_app_secret
        if raw_secret is None:
            if config.site_mode == "prod":
                raise RuntimeError("HUNDREDMS_APP_SECRET is required in production")
            app_secret = str()
        elif hasattr(raw_secret, "get_secret_value"):
            app_secret = str(raw_secret.get_secret_value()).strip()
        else:
            app_secret = str(raw_secret).strip()

        if not access_key or not app_secret:
            logger.warning(
                "Skipping 100ms room disable for cancellation cleanup due to missing credentials"
            )
            return None

        client = booking_service_module.HundredMsClient(
            access_key=access_key,
            app_secret=app_secret,
            base_url=config.hundredms_base_url,
            template_id=(config.hundredms_template_id or "").strip() or None,
        )
        return cast("HundredMsClient", client)

    def _disable_video_room_after_cancellation(self, booking: Booking) -> None:
        """Best-effort 100ms room disable after cancellation commit."""
        booking_service_module = _booking_service_module()

        video_session = getattr(booking, "video_session", None)
        room_id = getattr(video_session, "room_id", None)
        if not room_id:
            return

        client = self._build_hundredms_client_for_cleanup()
        if client is None:
            return

        try:
            client.disable_room(room_id)
        except booking_service_module.HundredMsError as exc:
            logger.warning(
                "Best-effort 100ms room disable failed for booking %s room %s: %s",
                booking.id,
                room_id,
                exc.message,
                extra={"status_code": exc.status_code},
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error during 100ms room disable for booking %s room %s: %s",
                booking.id,
                room_id,
                exc,
            )

    def _build_cancellation_context(self, booking: Booking, user: User) -> Dict[str, Any]:
        """
        Build context for cancellation (Phase 1 helper).
        Extracts all data needed for Stripe calls and finalization.
        """
        booking_service_module = _booking_service_module()

        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until = booking_service_module.TimezoneService.hours_until(booking_start_utc)

        pd = booking.payment_detail
        raw_payment_intent_id = pd.payment_intent_id if pd is not None else None
        payment_intent_id = (
            raw_payment_intent_id
            if isinstance(raw_payment_intent_id, str) and raw_payment_intent_id.startswith("pi_")
            else None
        )

        # Part 4b: Fair Reschedule Loophole Fix
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
                hours_from_original_value = (original_dt - reschedule_time).total_seconds() / 3600
                hours_from_original = hours_from_original_value
                was_gaming_reschedule = hours_from_original_value < 24

        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"

        # Determine cancellation scenario
        cur_ps = pd.payment_status if pd is not None else None
        is_pending_payment = (
            booking.status == BookingStatus.PENDING
            or cur_ps == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        ) and payment_intent_id is None
        if is_pending_payment:
            scenario = "pending_payment"
        elif cancelled_by_role == "instructor":
            if hours_until >= 24:
                scenario = "instructor_cancel_over_24h"
            else:
                scenario = "instructor_cancel_under_24h"
        else:
            if hours_until >= 24:
                scenario = "over_24h_gaming" if was_gaming_reschedule else "over_24h_regular"
            elif 12 <= hours_until < 24:
                scenario = "between_12_24h"
            else:
                scenario = "under_12h" if payment_intent_id else "under_12h_no_pi"

            if scenario == "over_24h_gaming" and cur_ps != PaymentStatus.AUTHORIZED.value:
                raise BusinessRuleException(
                    "Gaming reschedule cancellations require an authorized payment"
                )

        # Calculate lesson price for credit scenarios
        lesson_price_cents = int(float(booking.hourly_rate) * booking.duration_minutes * 100 / 60)

        default_role = (
            RoleName.STUDENT.value if user.id == booking.student_id else RoleName.INSTRUCTOR.value
        )

        instructor_stripe_account_id: Optional[str] = None
        try:
            from ...repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            try:
                instructor_profile = self.conflict_checker_repository.get_instructor_profile(
                    booking.instructor_id
                )
                if instructor_profile:
                    connected_account = payment_repo.get_connected_account_by_instructor_id(
                        instructor_profile.id
                    )
                    if connected_account and connected_account.stripe_account_id:
                        instructor_stripe_account_id = connected_account.stripe_account_id
            except Exception as exc:
                logger.warning(
                    "Failed to load instructor Stripe account for booking %s: %s",
                    booking.id,
                    exc,
                )
        except Exception as exc:
            logger.warning(
                "Failed to load instructor Stripe account for booking %s: %s",
                booking.id,
                exc,
            )

        return {
            "booking_id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "payment_intent_id": payment_intent_id,
            "payment_status": cur_ps,
            "scenario": scenario,
            "hours_until": hours_until,
            "hours_from_original": hours_from_original,
            "was_gaming_reschedule": was_gaming_reschedule,
            "lesson_price_cents": lesson_price_cents,
            "instructor_stripe_account_id": instructor_stripe_account_id,
            "rescheduled_from_booking_id": booking.rescheduled_from_booking_id,
            "original_lesson_datetime": original_lesson_datetime,
            "default_role": default_role,
            "cancelled_by_role": cancelled_by_role,
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
        }

    def _execute_cancellation_stripe_calls(
        self, ctx: Dict[str, Any], stripe_service: Any
    ) -> Dict[str, Any]:
        """
        Execute Stripe calls for cancellation (Phase 2).
        No transaction held during network calls.
        """
        results: Dict[str, Any] = {
            "cancel_pi_success": False,
            "capture_success": False,
            "reverse_success": False,
            "reverse_attempted": False,
            "reverse_failed": False,
            "reverse_reversal_id": None,
            "refund_success": False,
            "refund_failed": False,
            "refund_data": None,
            "payout_success": False,
            "payout_failed": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "capture_data": None,
            "error": None,
        }

        scenario = ctx["scenario"]
        payment_intent_id = ctx["payment_intent_id"]
        booking_id = ctx["booking_id"]
        payment_status = (ctx.get("payment_status") or "").lower()
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }

        if scenario == "over_24h_gaming":
            # Capture payment intent, then reverse transfer to retain fee and issue credit.
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_resched_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_resched_{booking_id}",
                                reason="gaming_reschedule_cancel",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario in ("over_24h_regular",):
            # Cancel payment intent (release authorization)
            if payment_intent_id:
                try:
                    stripe_service.cancel_payment_intent(
                        payment_intent_id, idempotency_key=f"cancel_{booking_id}"
                    )
                    results["cancel_pi_success"] = True
                except Exception as e:
                    logger.warning("Cancel PI failed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            if payment_intent_id:
                if already_captured:
                    try:
                        refund = stripe_service.refund_payment(
                            payment_intent_id,
                            reverse_transfer=True,
                            refund_application_fee=True,
                            idempotency_key=f"refund_instructor_cancel_{booking_id}",
                        )
                        results["refund_success"] = True
                        results["refund_data"] = refund
                    except Exception as e:
                        logger.warning(
                            "Instructor refund failed for booking %s: %s",
                            booking_id,
                            e,
                        )
                        results["refund_failed"] = True
                        results["error"] = str(e)
                else:
                    try:
                        stripe_service.cancel_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"cancel_instructor_{booking_id}",
                        )
                        results["cancel_pi_success"] = True
                    except Exception as e:
                        logger.warning("Cancel PI failed for booking %s: %s", booking_id, e)
                        results["error"] = str(e)

        elif scenario == "between_12_24h":
            # Capture payment intent, then reverse transfer
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_cancel_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    # Reverse transfer if available
                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_{booking_id}",
                                reason="student_cancel_12-24h",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario == "under_12h":
            # Capture payment intent, reverse transfer, and create 50% payout transfer
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_late_cancel_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "amount_received": capture.get("amount_received"),
                        "transfer_id": capture.get("transfer_id"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")

                    if transfer_id:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_lt12_{booking_id}",
                                reason="student_cancel_under_12h",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                    else:
                        results["reverse_failed"] = True
                        logger.error(
                            "Missing transfer_id for under-12h cancellation booking %s",
                            booking_id,
                        )

                    if results["reverse_success"]:
                        payout_full_cents = transfer_amount
                        if payout_full_cents is None:
                            try:
                                payout_ctx = stripe_service.build_charge_context(
                                    booking_id=booking_id, requested_credit_cents=None
                                )
                                payout_full_cents = int(
                                    getattr(payout_ctx, "target_instructor_payout_cents", 0) or 0
                                )
                            except Exception as exc:
                                logger.warning(
                                    "Failed to resolve instructor payout for booking %s: %s",
                                    booking_id,
                                    exc,
                                )
                                payout_full_cents = None

                        if payout_full_cents is None:
                            results["payout_failed"] = True
                            results["error"] = "missing_payout_amount"
                        else:
                            payout_amount_cents = int(round(payout_full_cents * 0.5))
                            results["payout_amount_cents"] = payout_amount_cents
                            if payout_amount_cents <= 0:
                                results["payout_success"] = True
                            else:
                                destination_account_id = ctx.get("instructor_stripe_account_id")
                                if not destination_account_id:
                                    results["payout_failed"] = True
                                    results["error"] = "missing_instructor_account"
                                else:
                                    try:
                                        transfer_result = stripe_service.create_manual_transfer(
                                            booking_id=booking_id,
                                            destination_account_id=destination_account_id,
                                            amount_cents=payout_amount_cents,
                                            idempotency_key=f"payout_lt12_{booking_id}",
                                        )
                                        results["payout_success"] = True
                                        results["payout_transfer_id"] = transfer_result.get(
                                            "transfer_id"
                                        )
                                    except Exception as e:
                                        results["payout_failed"] = True
                                        results["error"] = str(e)
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        # scenario == "under_12h_no_pi" - no Stripe calls needed

        return results

    def _finalize_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
    ) -> None:
        """
        Finalize cancellation with Stripe results (Phase 3 helper).
        Creates payment events and updates booking status.
        """
        from ..credit_service import CreditService

        booking_service_module = _booking_service_module()

        scenario = ctx["scenario"]
        booking_id = ctx["booking_id"]
        credit_service = CreditService(self.db)
        bp = self.repository.ensure_payment(booking.id)

        def _cancellation_credit_already_issued() -> bool:
            try:
                credits = payment_repo.get_credits_issued_for_source(booking_id)
            except Exception as exc:
                logger.warning(
                    "Failed to check existing credits for booking %s: %s",
                    booking_id,
                    exc,
                )
                return False
            cancellation_credit_reasons = booking_service_module.CANCELLATION_CREDIT_REASONS
            return any(
                getattr(credit, "reason", None) in cancellation_credit_reasons
                or getattr(credit, "source_type", None) in cancellation_credit_reasons
                for credit in credits
            )

        def _apply_settlement(
            outcome: str,
            *,
            student_credit_cents: Optional[int] = None,
            instructor_payout_cents: Optional[int] = None,
            refunded_cents: Optional[int] = None,
        ) -> None:
            bp.settlement_outcome = outcome
            booking.student_credit_amount = student_credit_cents
            bp.instructor_payout_amount = instructor_payout_cents
            booking.refunded_to_card_amount = refunded_cents

        def _mark_capture_failed(error: Optional[str]) -> None:
            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp.capture_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
            if error:
                bp.auth_last_error = error
                bp.capture_error = error

        def _mark_manual_review(reason: Optional[str]) -> None:
            bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            if reason:
                bp.auth_last_error = reason

        def _transfer_record() -> BookingTransfer:
            return self._ensure_transfer_record(booking_id)

        if scenario == "over_24h_gaming":
            if stripe_results["capture_success"]:
                capture_data = stripe_results.get("capture_data") or {}
                transfer_record = _transfer_record()
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    transfer_record.transfer_reversal_failed_at = (
                        booking_service_module.datetime.now(booking_service_module.timezone.utc)
                    )
                    transfer_record.transfer_reversal_retry_count = (
                        int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_reversal_error = stripe_results.get("error")
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return
                if stripe_results.get("reverse_reversal_id"):
                    transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")
                credit_amount_cents = ctx["lesson_price_cents"]
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_amount_cents,
                            source_type="cancel_credit_12_24",
                            reason="Rescheduled booking cancellation (lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create credit for gaming reschedule %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_gaming_reschedule_cancel",
                        event_data={
                            "hours_before_new": round(ctx["hours_until"], 2),
                            "hours_from_original": round(ctx["hours_from_original"], 2)
                            if ctx["hours_from_original"] is not None
                            else None,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "credit_issued_cents": credit_amount_cents,
                            "rescheduled_from": ctx["rescheduled_from_booking_id"],
                            "original_lesson_datetime": ctx["original_lesson_datetime"].isoformat()
                            if ctx["original_lesson_datetime"]
                            else None,
                        },
                    )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "student_cancel_12_24_full_credit",
                    student_credit_cents=credit_amount_cents,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_gaming_reschedule_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "over_24h_regular":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_released",
                event_data={
                    "hours_before": round(ctx["hours_until"], 2),
                    "payment_intent_id": ctx["payment_intent_id"],
                },
            )
            if ctx.get("payment_intent_id") and not stripe_results.get("cancel_pi_success"):
                _mark_manual_review(stripe_results.get("error"))
            else:
                bp.payment_status = PaymentStatus.SETTLED.value
            _apply_settlement(
                "student_cancel_gt24_no_charge",
                student_credit_cents=0,
                instructor_payout_cents=0,
                refunded_cents=0,
            )

        elif scenario == "between_12_24h":
            capture_data = stripe_results.get("capture_data") or {}
            transfer_record = _transfer_record()
            transfer_record.stripe_transfer_id = capture_data.get("transfer_id")

            if stripe_results["reverse_success"]:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="transfer_reversed_late_cancel",
                    event_data={
                        "transfer_id": capture_data.get("transfer_id"),
                        "amount": capture_data.get("transfer_amount"),
                        "original_charge_amount": capture_data.get("amount_received"),
                    },
                )
                if stripe_results.get("reverse_reversal_id"):
                    transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")

            if stripe_results["capture_success"]:
                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    transfer_record.transfer_reversal_failed_at = (
                        booking_service_module.datetime.now(booking_service_module.timezone.utc)
                    )
                    transfer_record.transfer_reversal_retry_count = (
                        int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_reversal_error = stripe_results.get("error")
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return
                credit_amount_cents = ctx["lesson_price_cents"]
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_amount_cents,
                            source_type="cancel_credit_12_24",
                            reason="Cancellation 12-24 hours before lesson (lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create platform credit for booking %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_late_cancel",
                        event_data={
                            "amount": credit_amount_cents,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "total_charged_cents": capture_data.get("amount_received"),
                        },
                    )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "student_cancel_12_24_full_credit",
                    student_credit_cents=credit_amount_cents,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_late_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "under_12h":
            if stripe_results["capture_success"]:
                capture_data = stripe_results.get("capture_data") or {}
                transfer_record = _transfer_record()
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="captured_last_minute_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "amount": capture_data.get("amount_received"),
                    },
                )

                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return

                if stripe_results.get("reverse_success"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversed_last_minute_cancel",
                        event_data={
                            "transfer_id": capture_data.get("transfer_id"),
                            "amount": capture_data.get("transfer_amount"),
                            "original_charge_amount": capture_data.get("amount_received"),
                        },
                    )
                    if stripe_results.get("reverse_reversal_id"):
                        transfer_record.transfer_reversal_id = stripe_results.get(
                            "reverse_reversal_id"
                        )

                if stripe_results.get("payout_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="payout_failed_last_minute_cancel",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                            "error": stripe_results.get("error"),
                        },
                    )
                    transfer_record.payout_transfer_failed_at = booking_service_module.datetime.now(
                        booking_service_module.timezone.utc
                    )
                    transfer_record.payout_transfer_error = stripe_results.get("error")
                    transfer_record.payout_transfer_retry_count = (
                        int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
                    transfer_record.transfer_error = transfer_record.payout_transfer_error
                    transfer_record.transfer_retry_count = (
                        int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
                    )
                    _mark_manual_review(stripe_results.get("error"))

                if stripe_results.get("payout_success"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="payout_created_last_minute_cancel",
                        event_data={
                            "transfer_id": stripe_results.get("payout_transfer_id"),
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                        },
                    )
                    transfer_record.payout_transfer_id = stripe_results.get("payout_transfer_id")

                credit_return_cents = int(round(ctx["lesson_price_cents"] * 0.5))
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_return_cents,
                            source_type="cancel_credit_lt12",
                            reason="Cancellation <12 hours before lesson (50% lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create platform credit for booking %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_last_minute_cancel",
                        event_data={
                            "amount": credit_return_cents,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "total_charged_cents": capture_data.get("amount_received"),
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                        },
                    )
                if bp.payment_status != PaymentStatus.MANUAL_REVIEW.value:
                    bp.payment_status = PaymentStatus.SETTLED.value
                payout_amount_cents = stripe_results.get("payout_amount_cents")
                if payout_amount_cents is not None:
                    try:
                        payout_amount_cents = int(payout_amount_cents)
                    except (TypeError, ValueError):
                        payout_amount_cents = None
                _apply_settlement(
                    "student_cancel_lt12_split_50_50",
                    student_credit_cents=credit_return_cents,
                    instructor_payout_cents=payout_amount_cents or 0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_last_minute_cancel",
                    event_data={"payment_intent_id": ctx["payment_intent_id"]},
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "under_12h_no_pi":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_skipped_no_intent",
                event_data={"reason": "<12h cancellation without payment_intent"},
            )
            _mark_manual_review("missing_payment_intent")

        elif scenario == "pending_payment":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="cancelled_before_payment",
                event_data={"reason": "pending_payment_method"},
            )
            bp.payment_status = PaymentStatus.SETTLED.value
            _apply_settlement(
                "student_cancel_gt24_no_charge",
                student_credit_cents=0,
                instructor_payout_cents=0,
                refunded_cents=0,
            )

        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            if stripe_results.get("refund_success"):
                refund_data = stripe_results.get("refund_data") or {}
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancel_refunded",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                        "refund_id": refund_data.get("refund_id"),
                        "amount_refunded": refund_data.get("amount_refunded"),
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                transfer_record = _transfer_record()
                transfer_record.refund_id = refund_data.get("refund_id")
                refund_amount = refund_data.get("amount_refunded")
                if refund_amount is not None:
                    try:
                        refund_amount = int(refund_amount)
                    except (TypeError, ValueError):
                        refund_amount = None
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=refund_amount or 0,
                )
            elif stripe_results.get("refund_failed"):
                transfer_record = _transfer_record()
                transfer_record.refund_failed_at = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                transfer_record.refund_error = stripe_results.get("error")
                transfer_record.refund_retry_count = (
                    int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
                )
                _mark_manual_review(stripe_results.get("error"))
            elif stripe_results.get("cancel_pi_success"):
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancelled",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            elif not ctx.get("payment_intent_id"):
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancelled",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "reason": "no_payment_intent",
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancel_refund_failed",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_manual_review(stripe_results.get("error"))

    def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
        """
        Post-transaction actions for cancellation.
        Handles event publishing, notifications, and cache invalidation.
        """
        booking_service_module = _booking_service_module()

        # Publish cancellation event
        try:
            self.event_publisher.publish(
                booking_service_module.BookingCancelled(
                    booking_id=booking.id,
                    cancelled_by=cancelled_by_role,
                    cancelled_at=booking.cancelled_at
                    or booking_service_module.datetime.now(booking_service_module.timezone.utc),
                    refund_amount=None,
                )
            )
        except Exception as e:
            logger.error("Failed to send cancellation notification event: %s", str(e))

        # Create system message in conversation
        try:
            self.system_message_service.create_booking_cancelled_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                cancelled_by=cancelled_by_role,
            )
        except Exception as e:
            logger.error(
                "Failed to create cancellation system message for booking %s: %s",
                booking.id,
                str(e),
            )

        self._send_cancellation_notifications(booking, cancelled_by_role)

        # Invalidate caches
        self._invalidate_booking_caches(booking)

        # Process refund hooks
        refund_hook_outcomes = {
            "student_cancel_gt24_no_charge",
            "instructor_cancel_full_refund",
            "instructor_no_show_full_refund",
            "student_wins_dispute_full_refund",
            "admin_refund",
        }
        pd = booking.payment_detail
        if (pd is not None and pd.payment_status == PaymentStatus.SETTLED.value) and (
            pd is not None and pd.settlement_outcome in refund_hook_outcomes
        ):
            try:
                credit_service = booking_service_module.StudentCreditService(self.db)
                credit_service.process_refund_hooks(booking=booking)
            except Exception as exc:
                logger.error(
                    "Failed to adjust student credits for cancelled booking %s: %s",
                    booking.id,
                    exc,
                )

        self._disable_video_room_after_cancellation(booking)
