"""Instructor referral payout persistence helpers."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, cast

from sqlalchemy.exc import IntegrityError

from ...core.exceptions import RepositoryException
from ...models.referrals import InstructorReferralPayout
from .mixin_base import ReferralRewardRepositoryMixinBase


class InstructorPayoutMixin(ReferralRewardRepositoryMixinBase):
    """Instructor payout queries and mutations."""

    def create_instructor_referral_payout(
        self,
        *,
        referrer_user_id: str,
        referred_instructor_id: str,
        triggering_booking_id: str,
        amount_cents: int,
        was_founding_bonus: bool,
        idempotency_key: str,
    ) -> Optional[InstructorReferralPayout]:
        """
        Create instructor referral payout record.

        Returns None if a payout already exists for the idempotency key or referred instructor.
        """
        existing = (
            self.db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return None

        existing_for_instructor = (
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.referred_instructor_id == referred_instructor_id,
            )
            .first()
        )
        if existing_for_instructor:
            return None

        try:
            with self.db.begin_nested():
                payout = InstructorReferralPayout(
                    referrer_user_id=referrer_user_id,
                    referred_instructor_id=referred_instructor_id,
                    triggering_booking_id=triggering_booking_id,
                    amount_cents=amount_cents,
                    was_founding_bonus=was_founding_bonus,
                    idempotency_key=idempotency_key,
                    stripe_transfer_status="pending",
                )
                self.db.add(payout)
                self.db.flush()
                return payout
        except IntegrityError as exc:
            existing = (
                self.db.query(InstructorReferralPayout)
                .filter(InstructorReferralPayout.idempotency_key == idempotency_key)
                .first()
            )
            if existing is not None:
                self.logger.info(
                    "Payout already exists for idempotency key %s "
                    "(concurrent creation handled by DB constraint)",
                    idempotency_key,
                )
                return None

            existing_for_instructor = (
                self.db.query(InstructorReferralPayout)
                .filter(
                    InstructorReferralPayout.referred_instructor_id == referred_instructor_id,
                )
                .first()
            )
            if existing_for_instructor is not None:
                self.logger.info(
                    "Payout already exists for referred instructor %s "
                    "(concurrent creation handled by DB constraint)",
                    referred_instructor_id,
                )
                return None

            raise RepositoryException("Unable to create instructor referral payout") from exc

    def get_instructor_referral_payout_by_id(
        self, payout_id: str
    ) -> Optional[InstructorReferralPayout]:
        """Get a payout record by ID."""
        result = (
            self.db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.id == payout_id)
            .first()
        )
        return cast(Optional[InstructorReferralPayout], result)

    def get_instructor_referral_payout_by_referred(
        self, referred_instructor_id: str
    ) -> Optional[InstructorReferralPayout]:
        """Get payout record for a specific referred instructor."""
        result = (
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.referred_instructor_id == referred_instructor_id,
            )
            .first()
        )
        return cast(Optional[InstructorReferralPayout], result)

    def get_payout_for_update(self, payout_id: str) -> Optional[InstructorReferralPayout]:
        """Get a payout record with a SELECT FOR UPDATE lock."""
        result = (
            self.db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.id == payout_id)
            .with_for_update()
            .first()
        )
        return cast(Optional[InstructorReferralPayout], result)

    def get_failed_payouts_since(self, since: datetime) -> List[InstructorReferralPayout]:
        """Get all failed payouts since the given time."""
        return list(
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.stripe_transfer_status == "failed",
                InstructorReferralPayout.failed_at >= since,
            )
            .all()
        )

    def get_pending_payouts_older_than(self, cutoff: datetime) -> List[InstructorReferralPayout]:
        """Get pending payouts older than the cutoff time."""
        return list(
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.stripe_transfer_status == "pending",
                InstructorReferralPayout.created_at <= cutoff,
            )
            .all()
        )

    def get_referrer_payouts(
        self,
        referrer_user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[InstructorReferralPayout]:
        """Get payouts for a referrer, optionally filtered by status."""
        query = self.db.query(InstructorReferralPayout).filter(
            InstructorReferralPayout.referrer_user_id == referrer_user_id
        )
        if status:
            query = query.filter(InstructorReferralPayout.stripe_transfer_status == status)
        return cast(
            List[InstructorReferralPayout],
            query.order_by(InstructorReferralPayout.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all(),
        )
