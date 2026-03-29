from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, Optional, cast

from ...models.booking import PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


@dataclass(slots=True)
class _DisputeContext:
    dispute: dict[str, Any]
    dispute_id: Optional[str]
    payment_intent_id: str
    payment_record: Any
    booking: Any


class StripeWebhookDisputesMixin(BaseService):
    """Stripe charge, refund, and dispute webhook handling."""

    booking_repository: BookingRepository
    payment_repository: PaymentRepository
    stripe_configured: bool

    if TYPE_CHECKING:

        def reverse_transfer(
            self,
            *,
            transfer_id: str,
            idempotency_key: Optional[str] = None,
            reason: Optional[str] = None,
        ) -> dict[str, Any]:
            ...

    def _record_payment_event_safely(
        self, *, booking_id: str, event_type: str, event_data: dict[str, Any]
    ) -> None:
        try:
            self.payment_repository.create_payment_event(
                booking_id=booking_id,
                event_type=event_type,
                event_data=event_data,
            )
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)

    def _load_payment_events(self, booking_id: str) -> list[Any]:
        try:
            return list(self.payment_repository.get_payment_events_for_booking(booking_id))
        except Exception:
            return []

    def _process_charge_refunded(
        self, *, charge_data: dict[str, Any], charge_id: Optional[str]
    ) -> None:
        payment_intent_id = charge_data.get("payment_intent")
        if not payment_intent_id:
            return
        self.payment_repository.update_payment_status(payment_intent_id, "refunded")
        booking_payment = self.payment_repository.get_payment_by_intent_id(payment_intent_id)
        if not booking_payment:
            self.logger.critical(
                "Stripe refund reconciliation gap: no local payment record for "
                "payment_intent %s (charge %s)",
                payment_intent_id,
                charge_id,
            )
            return

        booking = self.booking_repository.get_by_id(booking_payment.booking_id)
        if not booking:
            self.logger.critical(
                "Stripe refund reconciliation gap: no booking %s for "
                "payment_intent %s (charge %s)",
                booking_payment.booking_id,
                payment_intent_id,
                charge_id,
            )
            return

        self.logger.info(
            "Marked booking %s payment as refunded for PI %s",
            booking.id,
            payment_intent_id,
        )
        try:
            credit_service = _stripe_service_module().StudentCreditService(self.db)
            credit_service.process_refund_hooks(booking=booking)
        except Exception as hook_exc:
            self.logger.error(
                "Failed adjusting student credits on refund for booking %s: %s",
                booking.id,
                hook_exc,
            )

    def _handle_charge_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe charge events."""
        try:
            event_type = event.get("type", "")
            if event_type == "charge.dispute.created":
                return self._handle_dispute_created(event)
            if event_type == "charge.dispute.closed":
                return self._handle_dispute_closed(event)

            charge_data = event.get("data", {}).get("object", {})
            charge_id = charge_data.get("id")
            if event_type == "charge.succeeded":
                self.logger.info("Charge %s succeeded", charge_id)
                return True
            if event_type == "charge.failed":
                self.logger.error("Charge %s failed", charge_id)
                return True
            if event_type == "charge.refunded":
                self.logger.info("Charge %s refunded", charge_id)
                try:
                    self._process_charge_refunded(charge_data=charge_data, charge_id=charge_id)
                except Exception as exc:
                    self.logger.error("Failed to process charge.refunded: %s", exc)
                return True
            return False
        except Exception as exc:
            self.logger.error("Error handling charge webhook: %s", exc)
            return False

    def _resolve_payment_intent_id_from_charge(self, charge_id: Optional[str]) -> Optional[str]:
        stripe_sdk = _stripe_service_module().stripe
        if not charge_id or not self.stripe_configured:
            return None
        try:
            charge_resource = getattr(stripe_sdk, "Charge", None)
            if charge_resource is None:
                return None
            charge = charge_resource.retrieve(charge_id)
            payment_intent_id = getattr(charge, "payment_intent", None)
            if payment_intent_id is None and hasattr(charge, "get"):
                payment_intent_id = charge.get("payment_intent")
            return cast(Optional[str], payment_intent_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to resolve payment_intent from charge %s: %s", charge_id, exc
            )
            return None

    def _load_open_dispute_context(self, event: dict[str, Any]) -> Optional[_DisputeContext]:
        dispute = event.get("data", {}).get("object", {}) or {}
        dispute_id = dispute.get("id")
        payment_intent_id = dispute.get(
            "payment_intent"
        ) or self._resolve_payment_intent_id_from_charge(dispute.get("charge"))
        if not payment_intent_id:
            self.logger.warning("Dispute %s missing payment_intent", dispute_id)
            return None

        payment_record = self.payment_repository.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            self.logger.warning(
                "Dispute %s for unknown payment_intent %s", dispute_id, payment_intent_id
            )
            return None

        booking = self.booking_repository.get_by_id(payment_record.booking_id)
        if not booking:
            self.logger.warning(
                "Dispute %s for unknown booking %s", dispute_id, payment_record.booking_id
            )
            return None

        return _DisputeContext(
            dispute=dispute,
            dispute_id=dispute_id,
            payment_intent_id=payment_intent_id,
            payment_record=payment_record,
            booking=booking,
        )

    def _attempt_dispute_transfer_reversal(
        self, *, booking_id: str, dispute_id: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        transfer = self.booking_repository.get_transfer_by_booking_id(booking_id)
        transfer_id = transfer.stripe_transfer_id if transfer else None
        if not transfer_id or (transfer.transfer_reversed if transfer else False):
            return None, None
        try:
            reversal = self.reverse_transfer(
                transfer_id=transfer_id,
                idempotency_key=f"dispute_reversal_{booking_id}",
                reason="dispute_opened",
            )
            reversal_payload = reversal.get("reversal")
            reversal_id = (
                reversal_payload.get("id")
                if isinstance(reversal_payload, dict)
                else getattr(reversal_payload, "id", None)
            )
            return cast(Optional[str], reversal_id), None
        except Exception as exc:
            return None, str(exc)

    def _mark_open_dispute_state(
        self,
        *,
        context: _DisputeContext,
        reversal_id: Optional[str],
        reversal_error: Optional[str],
    ) -> None:
        booking_payment = self.booking_repository.ensure_payment(context.booking.id)
        booking_payment.payment_status = PaymentStatus.MANUAL_REVIEW.value

        dispute_record = self.booking_repository.ensure_dispute(context.booking.id)
        dispute_record.dispute_id = context.dispute_id
        dispute_record.dispute_status = context.dispute.get("status")
        dispute_record.dispute_amount = context.dispute.get("amount")
        dispute_record.dispute_created_at = datetime.now(timezone.utc)

        if reversal_id:
            transfer_record = self.booking_repository.ensure_transfer(context.booking.id)
            transfer_record.transfer_reversed = True
            transfer_record.transfer_reversal_id = reversal_id
            return

        if reversal_error:
            transfer_record = self.booking_repository.ensure_transfer(context.booking.id)
            transfer_record.transfer_reversal_failed = True
            transfer_record.transfer_reversal_error = reversal_error
            transfer_record.transfer_reversal_failed_at = datetime.now(timezone.utc)
            transfer_record.transfer_reversal_retry_count = (
                int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
            )

    def _apply_open_dispute_credit_effects(
        self,
        *,
        context: _DisputeContext,
        reversal_id: Optional[str],
        reversal_error: Optional[str],
    ) -> None:
        from ..credit_service import CreditService

        credit_service = CreditService(self.db)
        credit_service.freeze_credits_for_booking(
            booking_id=context.booking.id,
            reason=f"Dispute opened for booking {context.booking.id}",
            use_transaction=False,
        )
        events = self._load_payment_events(context.booking.id)
        already_applied = any(
            getattr(event, "event_type", None) == "negative_balance_applied"
            and isinstance(getattr(event, "event_data", None), dict)
            and getattr(event, "event_data", {}).get("dispute_id") == context.dispute_id
            for event in events
        )
        spent_cents = credit_service.get_spent_credits_for_booking(booking_id=context.booking.id)
        if spent_cents > 0 and not already_applied:
            credit_service.apply_negative_balance(
                user_id=context.booking.student_id,
                amount_cents=spent_cents,
                reason=f"dispute_opened:{context.dispute_id}",
                use_transaction=False,
            )
            self._record_payment_event_safely(
                booking_id=context.booking.id,
                event_type="negative_balance_applied",
                event_data={"dispute_id": context.dispute_id, "amount_cents": spent_cents},
            )

        self._record_payment_event_safely(
            booking_id=context.booking.id,
            event_type="dispute_opened",
            event_data={
                "dispute_id": context.dispute_id,
                "payment_intent_id": context.payment_intent_id,
                "status": context.dispute.get("status"),
                "amount": context.dispute.get("amount"),
                "transfer_reversal_id": reversal_id,
                "transfer_reversal_error": reversal_error,
            },
        )

    def _handle_dispute_created(self, event: dict[str, Any]) -> bool:
        """Handle charge.dispute.created events."""
        context = self._load_open_dispute_context(event)
        if not context:
            return False

        booking_lock_sync = _stripe_service_module().booking_lock_sync
        with booking_lock_sync(context.booking.id) as acquired:
            if not acquired:
                self.logger.warning(
                    "Dispute %s skipped due to lock for booking %s",
                    context.dispute_id,
                    context.booking.id,
                )
                return False

            reversal_id, reversal_error = self._attempt_dispute_transfer_reversal(
                booking_id=context.booking.id,
                dispute_id=context.dispute_id,
            )
            with self.transaction():
                booking = self.booking_repository.get_by_id(context.booking.id)
                if not booking:
                    return False
                context.booking = booking
                self._mark_open_dispute_state(
                    context=context,
                    reversal_id=reversal_id,
                    reversal_error=reversal_error,
                )
                self._apply_open_dispute_credit_effects(
                    context=context,
                    reversal_id=reversal_id,
                    reversal_error=reversal_error,
                )
        return True

    def _load_closed_dispute_context(self, event: dict[str, Any]) -> Optional[_DisputeContext]:
        dispute = event.get("data", {}).get("object", {}) or {}
        dispute_id = dispute.get("id")
        payment_intent_id = dispute.get(
            "payment_intent"
        ) or self._resolve_payment_intent_id_from_charge(dispute.get("charge"))
        if not payment_intent_id:
            self.logger.warning("Dispute %s missing payment_intent", dispute_id)
            return None

        payment_record = self.payment_repository.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            self.logger.warning(
                "Dispute %s for unknown payment_intent %s", dispute_id, payment_intent_id
            )
            return None

        booking = self.booking_repository.get_by_id(payment_record.booking_id)
        if not booking:
            self.logger.warning(
                "Dispute %s for unknown booking %s", dispute_id, payment_record.booking_id
            )
            return None

        return _DisputeContext(
            dispute=dispute,
            dispute_id=dispute_id,
            payment_intent_id=payment_intent_id,
            payment_record=payment_record,
            booking=booking,
        )

    def _handle_won_dispute_outcome(
        self, *, booking: Any, booking_payment: Any, dispute_id: Optional[str]
    ) -> None:
        from ..credit_service import CreditService

        credit_service = CreditService(self.db)
        events = self._load_payment_events(booking.id)
        negative_event = next(
            (
                event
                for event in events
                if getattr(event, "event_type", None) == "negative_balance_applied"
                and isinstance(getattr(event, "event_data", None), dict)
                and getattr(event, "event_data", {}).get("dispute_id") == dispute_id
            ),
            None,
        )
        if negative_event:
            spent_cents = credit_service.get_spent_credits_for_booking(booking_id=booking.id)
            event_payload = getattr(negative_event, "event_data", None)
            if isinstance(event_payload, dict):
                try:
                    spent_cents = int(event_payload.get("amount_cents", spent_cents) or spent_cents)
                except (TypeError, ValueError):
                    pass
            credit_service.clear_negative_balance(
                user_id=booking.student_id,
                amount_cents=spent_cents,
                reason=f"dispute_won:{dispute_id}",
                use_transaction=False,
            )
            self._record_payment_event_safely(
                booking_id=booking.id,
                event_type="negative_balance_cleared",
                event_data={"dispute_id": dispute_id, "amount_cents": spent_cents},
            )
        credit_service.unfreeze_credits_for_booking(booking_id=booking.id, use_transaction=False)
        booking_payment.payment_status = PaymentStatus.SETTLED.value
        booking_payment.settlement_outcome = "dispute_won"

    def _handle_lost_dispute_outcome(
        self, *, booking: Any, booking_payment: Any, dispute_id: Optional[str]
    ) -> None:
        from ..credit_service import CreditService

        credit_service = CreditService(self.db)
        credit_service.revoke_credits_for_booking(
            booking_id=booking.id,
            reason=f"dispute_lost:{dispute_id}",
            use_transaction=False,
        )
        spent_cents = credit_service.get_spent_credits_for_booking(booking_id=booking.id)
        events = self._load_payment_events(booking.id)
        already_applied = any(
            getattr(event, "event_type", None) == "negative_balance_applied"
            and isinstance(getattr(event, "event_data", None), dict)
            and getattr(event, "event_data", {}).get("dispute_id") == dispute_id
            for event in events
        )
        if spent_cents > 0 and not already_applied:
            credit_service.apply_negative_balance(
                user_id=booking.student_id,
                amount_cents=spent_cents,
                reason=f"dispute_lost:{dispute_id}",
                use_transaction=False,
            )
            self._record_payment_event_safely(
                booking_id=booking.id,
                event_type="negative_balance_applied",
                event_data={"dispute_id": dispute_id, "amount_cents": spent_cents},
            )

        user_repo = _stripe_service_module().RepositoryFactory.create_base_repository(self.db, User)
        user = user_repo.get_by_id(booking.student_id)
        if user:
            user.account_restricted = True
            user.account_restricted_at = datetime.now(timezone.utc)
            user.account_restricted_reason = f"dispute_lost:{dispute_id}"
        booking_payment.payment_status = PaymentStatus.SETTLED.value
        booking_payment.settlement_outcome = "student_wins_dispute_full_refund"

    def _record_dispute_closed_event(self, *, context: _DisputeContext) -> None:
        self._record_payment_event_safely(
            booking_id=context.booking.id,
            event_type="dispute_closed",
            event_data={
                "dispute_id": context.dispute_id,
                "payment_intent_id": context.payment_intent_id,
                "status": context.dispute.get("status"),
            },
        )

    def _handle_dispute_closed(self, event: dict[str, Any]) -> bool:
        """Handle charge.dispute.closed events."""
        context = self._load_closed_dispute_context(event)
        if not context:
            return False

        booking_lock_sync = _stripe_service_module().booking_lock_sync
        with booking_lock_sync(context.booking.id) as acquired:
            if not acquired:
                self.logger.warning(
                    "Dispute %s skipped due to lock for booking %s",
                    context.dispute_id,
                    context.booking.id,
                )
                return False

            with self.transaction():
                booking = self.booking_repository.get_by_id(context.booking.id)
                if not booking:
                    return False
                context.booking = booking
                booking_payment = self.booking_repository.ensure_payment(booking.id)
                dispute_record = self.booking_repository.ensure_dispute(booking.id)
                dispute_record.dispute_status = context.dispute.get("status")
                dispute_record.dispute_resolved_at = datetime.now(timezone.utc)

                status = context.dispute.get("status")
                if status in {"won", "warning_closed"}:
                    self._handle_won_dispute_outcome(
                        booking=booking,
                        booking_payment=booking_payment,
                        dispute_id=context.dispute_id,
                    )
                elif status == "lost":
                    self._handle_lost_dispute_outcome(
                        booking=booking,
                        booking_payment=booking_payment,
                        dispute_id=context.dispute_id,
                    )

                self._record_dispute_closed_event(context=context)
        return True
