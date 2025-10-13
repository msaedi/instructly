"""Student wallet milestone and credit adjustment service."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment import PlatformCredit
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.repositories.payment_repository import PaymentRepository

from .base import BaseService

logger = logging.getLogger(__name__)

_MILESTONE_S5_AMOUNT = 1000
_MILESTONE_S11_AMOUNT = 2000
_MILESTONE_REASONS = {"milestone_s5", "milestone_s11"}


class StudentCreditService(BaseService):
    """Encapsulate milestone issuance, revocation, and credit reinstatement."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.payment_repository: PaymentRepository = RepositoryFactory.create_payment_repository(db)
        self.booking_repository: BookingRepository = RepositoryFactory.create_booking_repository(db)

    @BaseService.measure_operation("student_credit_maybe_issue")
    def maybe_issue_milestone_credit(
        self, *, student_id: str, booking_id: str
    ) -> Optional[PlatformCredit]:
        """Issue a milestone credit when the student's completion count hits S5/S11 cycle."""

        with self.transaction():
            lifetime_completed = self.booking_repository.count_student_completed_lifetime(
                student_id
            )

        if lifetime_completed <= 0:
            return None

        cycle_position = lifetime_completed % 11
        amount = 0
        reason: Optional[str] = None

        if cycle_position == 5:
            amount = _MILESTONE_S5_AMOUNT
            reason = "milestone_s5"
        elif cycle_position == 0:
            amount = _MILESTONE_S11_AMOUNT
            reason = "milestone_s11"

        if not amount or not reason:
            return None

        issued = self.issue_milestone_credit(
            student_id=student_id,
            booking_id=booking_id,
            amount_cents=amount,
            reason=reason,
        )

        if issued:
            logger.info(
                "student_milestone_credit_issued",
                extra={
                    "student_id": student_id,
                    "booking_id": booking_id,
                    "amount_cents": amount,
                    "reason": reason,
                    "lifetime_completed": lifetime_completed,
                },
            )
        return issued

    @BaseService.measure_operation("student_credit_issue")
    def issue_milestone_credit(
        self,
        *,
        student_id: str,
        booking_id: str,
        amount_cents: int,
        reason: str,
    ) -> Optional[PlatformCredit]:
        """Idempotently create a milestone credit for the student."""

        if amount_cents <= 0:
            return None

        with self.transaction():
            existing = self.payment_repository.get_credits_issued_for_source(booking_id)
            for credit in existing:
                if credit.reason == reason and credit.user_id == student_id:
                    return credit

            credit = self.payment_repository.create_platform_credit(
                user_id=student_id,
                amount_cents=amount_cents,
                reason=reason,
                source_booking_id=booking_id,
            )
            return credit

    @BaseService.measure_operation("student_credit_revoke")
    def revoke_milestone_credit(self, *, source_booking_id: str) -> int:
        """Revoke milestone credits derived from the booking and return total revoked cents."""

        total_revoked = 0
        with self.transaction():
            credits = self.payment_repository.get_credits_issued_for_source(source_booking_id)
            milestone_credits = [c for c in credits if c.reason in _MILESTONE_REASONS]
            if not milestone_credits:
                return 0

            revoke_already_recorded = any(c.reason == "milestone_revoke" for c in credits)

            for credit in milestone_credits:
                amount = max(0, credit.amount_cents)
                total_revoked += amount

                if credit.used_at is None:
                    self.payment_repository.delete_platform_credit(credit.id)
                else:
                    if not revoke_already_recorded:
                        correction = self.payment_repository.create_platform_credit(
                            user_id=credit.user_id,
                            amount_cents=amount,
                            reason="milestone_revoke",
                            source_booking_id=source_booking_id,
                        )
                        self.payment_repository.mark_credit_used(correction.id, source_booking_id)
                        revoke_already_recorded = True

        if total_revoked > 0:
            logger.info(
                "student_milestone_credit_revoked",
                extra={
                    "source_booking_id": source_booking_id,
                    "revoked_cents": total_revoked,
                },
            )
        return total_revoked

    @BaseService.measure_operation("student_credit_reinstate")
    def reinstate_used_credits(self, *, refunded_booking_id: str) -> int:
        """Reissue credits consumed by the refunded booking (idempotent)."""

        remaining: int = 0

        with self.transaction():
            used = self.payment_repository.get_credits_used_by_booking(refunded_booking_id)
            if not used:
                return 0

            booking = self.booking_repository.get_by_id(refunded_booking_id)
            if not booking:
                return 0

            student_id = booking.student_id
            total_used = sum(amount for _, amount in used)

            existing_refunds = [
                credit
                for credit in self.payment_repository.get_credits_issued_for_source(
                    refunded_booking_id
                )
                if credit.reason == "refund_reinstate"
            ]
            already_reinstated = sum(max(0, credit.amount_cents) for credit in existing_refunds)

            remaining = total_used - already_reinstated
            if remaining <= 0:
                return 0

            self.payment_repository.create_platform_credit(
                user_id=student_id,
                amount_cents=remaining,
                reason="refund_reinstate",
                source_booking_id=refunded_booking_id,
            )

        logger.info(
            "student_credits_reinstated",
            extra={
                "booking_id": refunded_booking_id,
                "reinstated_cents": remaining,
            },
        )
        return remaining

    @BaseService.measure_operation("student_credit_refund_hooks")
    def process_refund_hooks(self, *, booking: Booking) -> None:
        """Convenience wrapper to apply revoke and reinstate logic for a booking refund."""

        reinstated = self.reinstate_used_credits(refunded_booking_id=booking.id)
        revoked = self.revoke_milestone_credit(source_booking_id=booking.id)
        if reinstated or revoked:
            logger.info(
                "student_credit_refund_adjustments",
                extra={
                    "booking_id": booking.id,
                    "student_id": booking.student_id,
                    "reinstated_cents": reinstated,
                    "revoked_cents": revoked,
                },
            )


__all__ = ["StudentCreditService"]
