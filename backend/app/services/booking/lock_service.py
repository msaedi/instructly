from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from ...core.exceptions import BusinessRuleException, NotFoundException
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
        if transfer_id is None:
            reverse_failed = True
            reversal_error = f"Missing transfer_id for lock booking {booking_id}"
            logger.error("Missing transfer_id for lock booking %s", booking_id)
        else:
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
