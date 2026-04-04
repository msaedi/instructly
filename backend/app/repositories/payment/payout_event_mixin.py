"""Instructor payout-event persistence helpers."""

from datetime import datetime
from typing import List, Optional, cast

from ...core.exceptions import RepositoryException
from ...models.payment import InstructorPayoutEvent
from .mixin_base import PaymentRepositoryMixinBase


class PaymentPayoutEventMixin(PaymentRepositoryMixinBase):
    """Payout-event queries and mutations."""

    def record_payout_event(
        self,
        *,
        instructor_profile_id: str,
        stripe_account_id: str,
        payout_id: str,
        amount_cents: Optional[int],
        status: Optional[str],
        arrival_date: Optional[datetime],
        failure_code: Optional[str] = None,
        failure_message: Optional[str] = None,
    ) -> InstructorPayoutEvent:
        """Persist a payout event for instructor analytics."""
        try:
            evt = InstructorPayoutEvent(
                instructor_profile_id=instructor_profile_id,
                stripe_account_id=stripe_account_id,
                payout_id=payout_id,
                amount_cents=amount_cents,
                status=status,
                arrival_date=arrival_date,
                failure_code=failure_code,
                failure_message=failure_message,
            )
            self.db.add(evt)
            self.db.flush()
            return evt
        except Exception as e:
            self.logger.error("Failed to record payout event: %s", str(e))
            raise RepositoryException(f"Failed to record payout event: {str(e)}")

    def get_instructor_payout_history(
        self,
        instructor_profile_id: str,
        limit: int = 50,
    ) -> List[InstructorPayoutEvent]:
        """
        Get payout history for an instructor.

        Args:
            instructor_profile_id: Instructor profile ID
            limit: Maximum number of payouts to return

        Returns:
            List of InstructorPayoutEvent objects ordered by created_at DESC
        """
        try:
            return cast(
                List[InstructorPayoutEvent],
                (
                    self.db.query(InstructorPayoutEvent)
                    .filter(InstructorPayoutEvent.instructor_profile_id == instructor_profile_id)
                    .order_by(InstructorPayoutEvent.created_at.desc())
                    .limit(limit)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get instructor payout history: %s", str(e))
            raise RepositoryException(f"Failed to get instructor payout history: {str(e)}")
