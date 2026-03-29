from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from ...core.exceptions import BusinessRuleException, NotFoundException, ServiceException
from ...models.booking import Booking, PaymentStatus
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


class BookingLockMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        conflict_checker_repository: ConflictCheckerRepository
        config_service: ConfigService

        def transaction(self) -> ContextManager[None]:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
            ...

    @BaseService.measure_operation("should_trigger_lock")
    def should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
        """Public helper: check if a reschedule should activate LOCK."""
        return self._should_trigger_lock(booking, initiated_by)

    @BaseService.measure_operation("get_hours_until_start")
    def get_hours_until_start(self, booking: Booking) -> float:
        """Public helper: hours until booking start (UTC)."""
        booking_service_module = _booking_service_module()
        booking_start_utc = self._get_booking_start_utc(booking)
        return float(booking_service_module.TimezoneService.hours_until(booking_start_utc))

    def _should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
        """Return True when LOCK should activate for a reschedule."""
        booking_service_module = _booking_service_module()

        if initiated_by != "student":
            return False

        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until_start = float(
            booking_service_module.TimezoneService.hours_until(booking_start_utc)
        )
        if not (12 <= hours_until_start < 24):
            return False

        pd = booking.payment_detail
        payment_status = (pd.payment_status if pd is not None else None) or ""
        payment_status = payment_status.lower()
        if payment_status == PaymentStatus.LOCKED.value:
            return False

        return payment_status in {
            PaymentStatus.AUTHORIZED.value,
            PaymentStatus.SCHEDULED.value,
        }

    @BaseService.measure_operation("activate_reschedule_lock")
    def activate_lock_for_reschedule(self, booking_id: str) -> Dict[str, Any]:
        """Capture + reverse transfer to activate LOCK for a reschedule."""
        booking_service_module = _booking_service_module()
        activation_ctx = self._load_lock_activation_context(booking_id)
        if activation_ctx.get("result") is not None:
            return cast(Dict[str, Any], activation_ctx["result"])
        self._run_immediate_lock_authorization_if_needed(
            booking_id,
            activation_ctx["needs_authorization"],
            activation_ctx["hours_until_lesson"],
        )
        authorized_ctx = self._reload_authorized_lock_context(booking_id)
        stripe_ctx = self._execute_lock_capture_and_reversal(
            booking_id,
            authorized_ctx["payment_intent_id"],
            booking_service_module.PricingService(self.db),
        )
        return self._persist_lock_activation_result(
            booking_id=booking_id,
            payment_intent_id=authorized_ctx["payment_intent_id"],
            stripe_ctx=stripe_ctx,
        )

    def _load_lock_activation_context(self, booking_id: str) -> Dict[str, Any]:
        booking_service_module = _booking_service_module()
        with self.transaction():
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            pd = booking.payment_detail
            cur_ps = pd.payment_status if pd is not None else None
            if cur_ps == PaymentStatus.LOCKED.value:
                return {"result": {"locked": True, "already_locked": True}}

            payment_status = (cur_ps or "").lower()
            if payment_status not in {
                PaymentStatus.AUTHORIZED.value,
                PaymentStatus.SCHEDULED.value,
            }:
                raise BusinessRuleException(f"Cannot lock booking with status {cur_ps}")

            hours_until_lesson: Optional[float] = None
            needs_authorization = payment_status == PaymentStatus.SCHEDULED.value
            if needs_authorization:
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until_lesson = float(
                    booking_service_module.TimezoneService.hours_until(booking_start_utc)
                )
            return {
                "result": None,
                "needs_authorization": needs_authorization,
                "hours_until_lesson": hours_until_lesson,
            }

    def _run_immediate_lock_authorization_if_needed(
        self,
        booking_id: str,
        needs_authorization: bool,
        hours_until_lesson: Optional[float],
    ) -> None:
        if not needs_authorization:
            return
        from app.tasks.payment_tasks import _process_authorization_for_booking

        auth_result = _process_authorization_for_booking(booking_id, hours_until_lesson or 0.0)
        if not auth_result.get("success"):
            raise BusinessRuleException(
                f"Unable to authorize payment for lock: {auth_result.get('error')}"
            )
        try:
            self.db.expire_all()
        except Exception:
            logger.warning(
                "Failed to expire session state after authorizing booking %s for reschedule lock",
                booking_id,
                exc_info=True,
            )

    def _reload_authorized_lock_context(self, booking_id: str) -> Dict[str, Any]:
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found after authorization")

        pd = booking.payment_detail
        raw_pi = pd.payment_intent_id if pd is not None else None
        payment_intent_id = raw_pi if isinstance(raw_pi, str) and raw_pi.startswith("pi_") else None
        if not payment_intent_id:
            raise BusinessRuleException("No authorized payment available to lock")
        cur_ps = pd.payment_status if pd is not None else None
        if cur_ps != PaymentStatus.AUTHORIZED.value:
            raise BusinessRuleException(f"Cannot lock booking with status {cur_ps}")
        return {"booking": booking, "payment_intent_id": payment_intent_id}

    def _execute_lock_capture_and_reversal(
        self,
        booking_id: str,
        payment_intent_id: str,
        pricing_service: Any,
    ) -> Dict[str, Any]:
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        try:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=f"lock_capture_{booking_id}",
            )
        except Exception as exc:
            logger.error("Lock capture failed for booking %s: %s", booking_id, exc)
            raise BusinessRuleException("Unable to lock payment at this time") from exc

        transfer_id = capture.get("transfer_id")
        transfer_amount = capture.get("transfer_amount")
        reverse_failed = False
        reversal_id: Optional[str] = None
        reversal_error: Optional[str] = None
        if transfer_id:
            try:
                reversal = stripe_service.reverse_transfer(
                    transfer_id=transfer_id,
                    amount_cents=transfer_amount,
                    idempotency_key=f"lock_reverse_{booking_id}",
                    reason="reschedule_lock",
                )
                reversal_obj = reversal.get("reversal") if isinstance(reversal, dict) else None
                reversal_id = getattr(reversal_obj, "id", None) if reversal_obj else None
            except Exception as exc:
                reverse_failed = True
                reversal_error = str(exc)
                logger.error("Lock reversal failed for booking %s: %s", booking_id, exc)

        locked_amount = capture.get("amount_received")
        try:
            locked_amount = int(locked_amount) if locked_amount is not None else None
        except (TypeError, ValueError):
            locked_amount = None
        return {
            "locked_amount": locked_amount,
            "transfer_id": transfer_id,
            "reverse_failed": reverse_failed,
            "reversal_id": reversal_id,
            "reversal_error": reversal_error,
        }

    def _persist_lock_activation_result(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        stripe_ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        from ...repositories.payment_repository import PaymentRepository
        from ..credit_service import CreditService

        booking_service_module = _booking_service_module()
        locked_amount = stripe_ctx["locked_amount"]
        transfer_id = stripe_ctx["transfer_id"]
        reverse_failed = stripe_ctx["reverse_failed"]
        reversal_id = stripe_ctx["reversal_id"]
        reversal_error = stripe_ctx["reversal_error"]

        with self.transaction():
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after lock capture")

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)
            bp = self.repository.ensure_payment(booking.id)
            if reverse_failed:
                bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = transfer_id
                transfer_record.transfer_reversal_failed = True
                transfer_record.transfer_reversal_error = reversal_error
                transfer_record.transfer_reversal_failed_at = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                transfer_record.transfer_reversal_retry_count = (
                    int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                )
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="lock_activation_failed",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": transfer_id,
                        "reason": "transfer_reversal_failed",
                    },
                )
            else:
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking.id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for lock activation %s: %s",
                        booking.id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                bp.payment_status = PaymentStatus.LOCKED.value
                lock_record = self.repository.ensure_lock(booking.id)
                lock_record.locked_at = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                lock_record.locked_amount_cents = locked_amount
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = transfer_id
                transfer_record.transfer_reversed = True if transfer_id else False
                transfer_record.transfer_reversal_id = reversal_id
                reschedule_record = self.repository.ensure_reschedule(booking.id)
                reschedule_record.late_reschedule_used = True
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="lock_activated",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": transfer_id,
                        "locked_amount_cents": locked_amount,
                        "reason": "reschedule_in_12_24h_window",
                    },
                )
        if reverse_failed:
            raise BusinessRuleException("Unable to lock payment at this time")
        return {"locked": True, "locked_amount_cents": locked_amount}

    @BaseService.measure_operation("resolve_reschedule_lock")
    def resolve_lock_for_booking(self, locked_booking_id: str, resolution: str) -> Dict[str, Any]:
        """Resolve a LOCK based on the new lesson outcome.

        Uses a 3-phase flow to avoid holding booking row locks during Stripe API calls:
        1) Read/validate and collect context under SELECT ... FOR UPDATE
        2) Execute outbound Stripe calls with no DB transaction held
        3) Re-lock, re-validate state, and persist final lock resolution
        """
        booking_service_module = _booking_service_module()
        resolution_ctx = self._load_lock_resolution_context(
            locked_booking_id,
            booking_service_module.PricingService(self.db),
        )
        if resolution_ctx.get("result") is not None:
            return cast(Dict[str, Any], resolution_ctx["result"])
        stripe_result = self._execute_lock_resolution_stripe_step(
            locked_booking_id,
            resolution,
            cast(Dict[str, Any], resolution_ctx["resolution_ctx"]),
            booking_service_module.PricingService(self.db),
        )
        return self._persist_lock_resolution_result(
            locked_booking_id=locked_booking_id,
            resolution=resolution,
            resolution_ctx=cast(Dict[str, Any], resolution_ctx["resolution_ctx"]),
            stripe_result=stripe_result,
        )

    def _load_lock_resolution_context(
        self,
        locked_booking_id: str,
        pricing_service: Any,
    ) -> Dict[str, Any]:
        from ...repositories.payment_repository import PaymentRepository

        with self.transaction():
            locked_booking = self.repository.get_by_id_for_update(locked_booking_id)
            if not locked_booking:
                raise NotFoundException("Locked booking not found")

            lock_record = self.repository.get_lock_by_booking_id(locked_booking.id)
            if lock_record is not None and lock_record.lock_resolved_at is not None:
                return {"result": {"success": True, "skipped": True, "reason": "already_resolved"}}

            locked_pd = locked_booking.payment_detail
            locked_ps = locked_pd.payment_status if locked_pd is not None else None
            if locked_ps == PaymentStatus.SETTLED.value:
                return {"result": {"success": True, "skipped": True, "reason": "already_settled"}}
            if locked_ps != PaymentStatus.LOCKED.value:
                return {"result": {"success": False, "skipped": True, "reason": "not_locked"}}

            payment_intent_id = locked_pd.payment_intent_id if locked_pd is not None else None
            locked_amount_cents = lock_record.locked_amount_cents if lock_record else None
            lesson_price_cents = int(
                float(locked_booking.hourly_rate) * locked_booking.duration_minutes * 100 / 60
            )
            payment_repo = PaymentRepository(self.db)
            instructor_stripe_account_id = self._load_lock_instructor_account(
                locked_booking.id,
                locked_booking.instructor_id,
                payment_repo,
            )
            payout_full_cents = self._load_lock_payout_full_cents(
                locked_booking.id,
                payment_repo,
                pricing_service,
            )
            return {
                "result": None,
                "resolution_ctx": {
                    "booking_id": locked_booking.id,
                    "student_id": locked_booking.student_id,
                    "payment_intent_id": payment_intent_id,
                    "locked_amount_cents": locked_amount_cents,
                    "lesson_price_cents": lesson_price_cents,
                    "instructor_stripe_account_id": instructor_stripe_account_id,
                    "payout_full_cents": int(payout_full_cents or 0),
                },
            }

    def _load_lock_instructor_account(
        self,
        booking_id: str,
        instructor_id: str,
        payment_repo: Any,
    ) -> Optional[str]:
        try:
            instructor_profile = self.conflict_checker_repository.get_instructor_profile(
                instructor_id
            )
            if instructor_profile:
                connected_account = payment_repo.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )
                if connected_account and connected_account.stripe_account_id:
                    return cast(Optional[str], connected_account.stripe_account_id)
        except Exception as exc:
            logger.warning(
                "Failed to load instructor Stripe account for booking %s: %s",
                booking_id,
                exc,
            )
        return None

    def _load_lock_payout_full_cents(
        self,
        booking_id: str,
        payment_repo: Any,
        pricing_service: Any,
    ) -> Optional[int]:
        try:
            payment_record = payment_repo.get_payment_by_booking_id(booking_id)
            if payment_record:
                payout_value = getattr(payment_record, "instructor_payout_cents", None)
                if payout_value is not None:
                    return int(payout_value)
        except Exception:
            logger.debug(
                "Failed to load stored instructor payout for lock resolution %s",
                booking_id,
                exc_info=True,
            )
        pricing = pricing_service.compute_booking_pricing(
            booking_id=booking_id, applied_credit_cents=0
        )
        return int(pricing.get("target_instructor_payout_cents", 0))

    @staticmethod
    def _initialize_lock_resolution_result() -> Dict[str, Any]:
        return {
            "payout_success": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "refund_success": False,
            "refund_data": None,
            "error": None,
        }

    def _execute_lock_resolution_stripe_step(
        self,
        locked_booking_id: str,
        resolution: str,
        resolution_ctx: Dict[str, Any],
        pricing_service: Any,
    ) -> Dict[str, Any]:
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        stripe_result = self._initialize_lock_resolution_result()
        if resolution == "new_lesson_completed":
            self._execute_lock_resolution_payout(
                stripe_service,
                locked_booking_id,
                resolution,
                resolution_ctx,
                stripe_result,
                1.0,
            )
        elif resolution == "new_lesson_cancelled_lt12":
            self._execute_lock_resolution_payout(
                stripe_service,
                locked_booking_id,
                resolution,
                resolution_ctx,
                stripe_result,
                0.5,
            )
        elif resolution == "instructor_cancelled":
            payment_intent_id = resolution_ctx.get("payment_intent_id")
            if payment_intent_id:
                try:
                    refund = stripe_service.refund_payment(
                        payment_intent_id,
                        reverse_transfer=True,
                        refund_application_fee=True,
                        idempotency_key=f"lock_resolve_refund_{locked_booking_id}",
                    )
                    stripe_result["refund_success"] = True
                    stripe_result["refund_data"] = refund
                except Exception as exc:
                    stripe_result["error"] = str(exc)
            else:
                stripe_result["error"] = "missing_payment_intent"
        return stripe_result

    def _execute_lock_resolution_payout(
        self,
        stripe_service: Any,
        locked_booking_id: str,
        resolution: str,
        resolution_ctx: Dict[str, Any],
        stripe_result: Dict[str, Any],
        payout_ratio: float,
    ) -> None:
        try:
            instructor_account_id = resolution_ctx.get("instructor_stripe_account_id")
            if not instructor_account_id:
                raise ServiceException("missing_instructor_account")
            payout_amount_cents = int(
                round((resolution_ctx.get("payout_full_cents") or 0) * payout_ratio)
            )
            transfer_result = stripe_service.create_manual_transfer(
                booking_id=locked_booking_id,
                destination_account_id=instructor_account_id,
                amount_cents=payout_amount_cents,
                idempotency_key=(
                    f"lock_resolve_payout_{locked_booking_id}"
                    if payout_ratio == 1.0
                    else f"lock_resolve_split_{locked_booking_id}"
                ),
                metadata={"resolution": resolution},
            )
            stripe_result["payout_success"] = True
            stripe_result["payout_transfer_id"] = transfer_result.get("transfer_id")
            stripe_result["payout_amount_cents"] = payout_amount_cents
        except Exception as exc:
            stripe_result["error"] = str(exc)

    def _persist_lock_resolution_result(
        self,
        *,
        locked_booking_id: str,
        resolution: str,
        resolution_ctx: Dict[str, Any],
        stripe_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        from ...repositories.payment_repository import PaymentRepository
        from ..credit_service import CreditService

        booking_service_module = _booking_service_module()
        with self.transaction():
            locked_booking = self.repository.get_by_id_for_update(locked_booking_id)
            if not locked_booking:
                raise NotFoundException("Locked booking not found")

            stale_result = self._revalidate_lock_resolution_state(locked_booking)
            if stale_result is not None:
                return stale_result

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)
            lesson_price_cents = int(resolution_ctx.get("lesson_price_cents") or 0)
            locked_amount_cents = resolution_ctx.get("locked_amount_cents")
            locked_bp = self.repository.ensure_payment(locked_booking.id)

            if resolution == "new_lesson_completed":
                self._persist_completed_lock_resolution(locked_booking, stripe_result, locked_bp)
            elif resolution == "new_lesson_cancelled_ge12":
                self._persist_ge12_lock_resolution(
                    locked_booking,
                    locked_booking_id,
                    lesson_price_cents,
                    payment_repo,
                    credit_service,
                    locked_bp,
                )
            elif resolution == "new_lesson_cancelled_lt12":
                self._persist_lt12_lock_resolution(
                    locked_booking,
                    locked_booking_id,
                    lesson_price_cents,
                    stripe_result,
                    payment_repo,
                    credit_service,
                    locked_bp,
                )
            elif resolution == "instructor_cancelled":
                self._persist_instructor_cancelled_lock_resolution(
                    locked_booking,
                    locked_amount_cents,
                    stripe_result,
                    locked_bp,
                )

            lock_record = self.repository.ensure_lock(locked_booking.id)
            lock_record.lock_resolution = resolution
            lock_record.lock_resolved_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            payment_repo.create_payment_event(
                booking_id=locked_booking_id,
                event_type="lock_resolved",
                event_data={
                    "resolution": resolution,
                    "payout_amount_cents": locked_bp.instructor_payout_amount,
                    "student_credit_cents": locked_booking.student_credit_amount,
                    "refunded_cents": locked_booking.refunded_to_card_amount,
                    "error": stripe_result.get("error"),
                },
            )
            return {"success": True, "resolution": resolution}

    def _revalidate_lock_resolution_state(self, locked_booking: Booking) -> Dict[str, Any] | None:
        lock_record = self.repository.get_lock_by_booking_id(locked_booking.id)
        if lock_record is not None and lock_record.lock_resolved_at is not None:
            logger.info(
                "Skipping stale lock resolution for booking %s after external call: already resolved",
                locked_booking.id,
            )
            return {"success": True, "skipped": True, "reason": "already_resolved"}

        locked_pd = locked_booking.payment_detail
        locked_ps = locked_pd.payment_status if locked_pd is not None else None
        if locked_ps == PaymentStatus.SETTLED.value:
            logger.info(
                "Skipping stale lock resolution for booking %s after external call: already settled",
                locked_booking.id,
            )
            return {"success": True, "skipped": True, "reason": "already_settled"}
        if locked_ps != PaymentStatus.LOCKED.value:
            logger.warning(
                "Skipping stale lock resolution for booking %s after external call: payment status=%s",
                locked_booking.id,
                locked_ps,
            )
            return {"success": False, "skipped": True, "reason": "not_locked"}
        return None

    def _lock_credit_already_issued(self, payment_repo: Any, booking_id: str) -> bool:
        booking_service_module = _booking_service_module()
        try:
            credits = payment_repo.get_credits_issued_for_source(booking_id)
        except Exception as exc:
            logger.warning(
                "Failed to check existing credits for booking %s: %s",
                booking_id,
                exc,
            )
            return False
        return any(
            getattr(credit, "reason", None) in booking_service_module.CANCELLATION_CREDIT_REASONS
            or getattr(credit, "source_type", None)
            in booking_service_module.CANCELLATION_CREDIT_REASONS
            for credit in credits
        )

    def _record_lock_payout_failure(self, booking_id: str, error: Optional[str]) -> BookingTransfer:
        booking_service_module = _booking_service_module()
        transfer_record = self._ensure_transfer_record(booking_id)
        transfer_record.payout_transfer_failed_at = booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        transfer_record.payout_transfer_error = error
        transfer_record.payout_transfer_retry_count = (
            int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
        )
        transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
        transfer_record.transfer_error = transfer_record.payout_transfer_error
        transfer_record.transfer_retry_count = (
            int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
        )
        return transfer_record

    def _persist_completed_lock_resolution(
        self,
        locked_booking: Booking,
        stripe_result: Dict[str, Any],
        locked_bp: Any,
    ) -> None:
        locked_bp.settlement_outcome = "lesson_completed_full_payout"
        locked_booking.student_credit_amount = 0
        locked_bp.instructor_payout_amount = stripe_result.get("payout_amount_cents")
        locked_booking.refunded_to_card_amount = 0
        locked_bp.credits_reserved_cents = 0
        if stripe_result.get("payout_success"):
            locked_bp.payment_status = PaymentStatus.SETTLED.value
            transfer_record = self._ensure_transfer_record(locked_booking.id)
            transfer_record.payout_transfer_id = stripe_result.get("payout_transfer_id")
        else:
            locked_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            self._record_lock_payout_failure(locked_booking.id, stripe_result.get("error"))

    def _persist_ge12_lock_resolution(
        self,
        locked_booking: Booking,
        locked_booking_id: str,
        lesson_price_cents: int,
        payment_repo: Any,
        credit_service: Any,
        locked_bp: Any,
    ) -> None:
        credit_amount = lesson_price_cents
        if not self._lock_credit_already_issued(payment_repo, locked_booking_id):
            credit_service.issue_credit(
                user_id=locked_booking.student_id,
                amount_cents=credit_amount,
                source_type="locked_cancel_ge12",
                reason="Locked cancellation >=12 hours (lesson price credit)",
                source_booking_id=locked_booking_id,
                use_transaction=False,
            )
        locked_bp.settlement_outcome = "locked_cancel_ge12_full_credit"
        locked_booking.student_credit_amount = credit_amount
        locked_bp.instructor_payout_amount = 0
        locked_booking.refunded_to_card_amount = 0
        locked_bp.credits_reserved_cents = 0
        locked_bp.payment_status = PaymentStatus.SETTLED.value

    def _persist_lt12_lock_resolution(
        self,
        locked_booking: Booking,
        locked_booking_id: str,
        lesson_price_cents: int,
        stripe_result: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        locked_bp: Any,
    ) -> None:
        credit_amount = int(round(lesson_price_cents * 0.5))
        if not self._lock_credit_already_issued(payment_repo, locked_booking_id):
            credit_service.issue_credit(
                user_id=locked_booking.student_id,
                amount_cents=credit_amount,
                source_type="locked_cancel_lt12",
                reason="Locked cancellation <12 hours (50% lesson price credit)",
                source_booking_id=locked_booking_id,
                use_transaction=False,
            )
        locked_bp.settlement_outcome = "locked_cancel_lt12_split_50_50"
        locked_booking.student_credit_amount = credit_amount
        locked_bp.instructor_payout_amount = stripe_result.get("payout_amount_cents")
        locked_booking.refunded_to_card_amount = 0
        locked_bp.credits_reserved_cents = 0
        if stripe_result.get("payout_success"):
            locked_bp.payment_status = PaymentStatus.SETTLED.value
            transfer_record = self._ensure_transfer_record(locked_booking.id)
            transfer_record.payout_transfer_id = stripe_result.get("payout_transfer_id")
        else:
            locked_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            self._record_lock_payout_failure(locked_booking.id, stripe_result.get("error"))

    def _persist_instructor_cancelled_lock_resolution(
        self,
        locked_booking: Booking,
        locked_amount_cents: Any,
        stripe_result: Dict[str, Any],
        locked_bp: Any,
    ) -> None:
        booking_service_module = _booking_service_module()
        refund_data = stripe_result.get("refund_data") or {}
        refund_amount = refund_data.get("amount_refunded")
        if refund_amount is not None:
            try:
                refund_amount = int(refund_amount)
            except (TypeError, ValueError):
                refund_amount = None
        locked_bp.settlement_outcome = "instructor_cancel_full_refund"
        locked_booking.student_credit_amount = 0
        locked_bp.instructor_payout_amount = 0
        locked_booking.refunded_to_card_amount = (
            refund_amount if refund_amount is not None else locked_amount_cents or 0
        )
        if stripe_result.get("refund_success"):
            transfer_record = self._ensure_transfer_record(locked_booking.id)
            transfer_record.refund_id = refund_data.get("refund_id")
        locked_bp.credits_reserved_cents = 0
        locked_bp.payment_status = (
            PaymentStatus.SETTLED.value
            if stripe_result.get("refund_success")
            else PaymentStatus.MANUAL_REVIEW.value
        )
        if not stripe_result.get("refund_success"):
            transfer_record = self._ensure_transfer_record(locked_booking.id)
            transfer_record.refund_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            transfer_record.refund_error = stripe_result.get("error")
            transfer_record.refund_retry_count = (
                int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
            )
