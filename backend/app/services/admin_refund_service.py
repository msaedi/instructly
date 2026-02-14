"""Service layer for admin-initiated booking refunds."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.booking import Booking, PaymentStatus
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_refunds import AdminRefundReason
from app.services.audit_redaction import redact
from app.services.audit_service import AuditService
from app.services.base import BaseService

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}

logger = logging.getLogger(__name__)

REASON_TO_BOOKING_STATUS = {
    AdminRefundReason.INSTRUCTOR_NO_SHOW: "NO_SHOW",
    AdminRefundReason.DISPUTE: "CANCELLED",
    AdminRefundReason.PLATFORM_ERROR: "CANCELLED",
    AdminRefundReason.OTHER: "CANCELLED",
}


class AdminRefundService(BaseService):
    """Admin refund workflow helpers."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.audit_repo = RepositoryFactory.create_audit_repository(db)

    @BaseService.measure_operation("admin_refund.get_booking")
    def get_booking(self, booking_id: str) -> Booking | None:
        return self.booking_repo.get_booking_with_details(booking_id)

    @BaseService.measure_operation("admin_refund.resolve_full_refund_cents")
    def resolve_full_refund_cents(self, booking: Booking) -> int:
        pd = booking.payment_detail
        payment_intent_id = pd.payment_intent_id if pd is not None else None
        if payment_intent_id:
            payment_record = self.payment_repo.get_payment_by_intent_id(payment_intent_id)
            if payment_record and payment_record.amount:
                return int(payment_record.amount)

        if booking.total_price is None:
            return 0

        total_price = Decimal(str(booking.total_price))
        return int(total_price * 100)

    @BaseService.measure_operation("admin_refund.apply_refund_updates")
    def apply_refund_updates(
        self,
        *,
        booking_id: str,
        reason: AdminRefundReason,
        note: Optional[str],
        amount_cents: int,
        stripe_reason: str,
        refund_id: Optional[str],
        actor: User,
    ) -> Booking | None:
        with self.transaction():
            booking = self.booking_repo.get_booking_with_details(booking_id)
            if not booking:
                return None

            bp = self.booking_repo.ensure_payment(booking.id)
            audit_before = redact(booking.to_dict()) or {}
            audit_before["payment_status"] = bp.payment_status

            bp.payment_status = PaymentStatus.SETTLED.value
            booking.status = REASON_TO_BOOKING_STATUS[reason]
            if not booking.cancelled_at:
                booking.cancelled_at = datetime.now(timezone.utc)
            if reason == AdminRefundReason.INSTRUCTOR_NO_SHOW:
                booking.cancelled_by_id = booking.instructor_id
                bp.settlement_outcome = "instructor_no_show_full_refund"
            elif reason == AdminRefundReason.DISPUTE:
                bp.settlement_outcome = "student_wins_dispute_full_refund"
            else:
                bp.settlement_outcome = "admin_refund"
            booking.refunded_to_card_amount = amount_cents
            booking.student_credit_amount = 0
            bp.instructor_payout_amount = 0

            try:
                from app.services.credit_service import CreditService

                credit_service = CreditService(self.db)
                credit_service.release_credits_for_booking(
                    booking_id=booking.id, use_transaction=False
                )
                bp.credits_reserved_cents = 0
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking.id,
                    exc,
                )

            refund_payload = {
                "reason": reason.value,
                "note": note,
                "amount_cents": amount_cents,
                "refund_id": refund_id,
                "stripe_reason": stripe_reason,
            }

            audit_after = redact(booking.to_dict()) or {}
            audit_after["payment_status"] = bp.payment_status
            audit_after["refund"] = refund_payload

            if AUDIT_ENABLED:
                audit_entry = AuditLog.from_change(
                    entity_type="booking",
                    entity_id=booking.id,
                    action="admin_refund",
                    actor={"id": actor.id, "role": "admin"},
                    before=audit_before,
                    after=audit_after,
                )
                self.audit_repo.write(audit_entry)
                try:
                    AuditService(self.db).log_changes(
                        action="payment.refund",
                        resource_type="payment",
                        resource_id=booking.id,
                        old_values=audit_before,
                        new_values=audit_after,
                        actor=actor,
                        actor_type="user",
                        description="Admin refund applied",
                        metadata={
                            "initiated_by": "admin",
                            "refund_amount_cents": amount_cents,
                            "stripe_reason": stripe_reason,
                            "refund_id": refund_id,
                        },
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)

            return booking
