"""Payment-intent persistence helpers."""

from decimal import Decimal
from typing import List, Optional, cast

import ulid

from ...core.exceptions import RepositoryException
from ...models.payment import PaymentIntent
from .mixin_base import PaymentRepositoryMixinBase


class PaymentPaymentIntentMixin(PaymentRepositoryMixinBase):
    """Payment-intent queries and mutations."""

    def create_payment_record(
        self,
        booking_id: str,
        payment_intent_id: str,
        amount: int,
        application_fee: int,
        status: str = "requires_payment_method",
        *,
        base_price_cents: Optional[int] = None,
        instructor_tier_pct: Optional[Decimal] = None,
        instructor_payout_cents: Optional[int] = None,
    ) -> PaymentIntent:
        """
        Create a new payment intent record for a booking.

        Args:
            booking_id: Booking ID
            payment_intent_id: Stripe's payment intent ID
            amount: Total amount in cents
            application_fee: Platform fee in cents
            status: Payment status (default: requires_payment_method)
            base_price_cents: Lesson price in cents (optional, for earnings display)
            instructor_tier_pct: Instructor's platform fee rate (optional, for earnings display)
            instructor_payout_cents: Amount transferred to instructor in cents (optional)

        Returns:
            Created PaymentIntent object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            payment = PaymentIntent(
                id=str(ulid.ULID()),
                booking_id=booking_id,
                stripe_payment_intent_id=payment_intent_id,
                amount=amount,
                application_fee=application_fee,
                status=status,
                base_price_cents=base_price_cents,
                instructor_tier_pct=instructor_tier_pct,
                instructor_payout_cents=instructor_payout_cents,
            )
            self.db.add(payment)
            self.db.flush()
            return payment
        except Exception as e:
            self.logger.error("Failed to create payment record: %s", str(e))
            raise RepositoryException(f"Failed to create payment record: {str(e)}")

    def update_payment_status(self, payment_intent_id: str, status: str) -> Optional[PaymentIntent]:
        """
        Update the status of a payment intent.

        Args:
            payment_intent_id: Stripe's payment intent ID
            status: New payment status

        Returns:
            Updated PaymentIntent if found, None otherwise
        """
        try:
            payment = (
                self.db.query(PaymentIntent)
                .filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id)
                .first()
            )
            if payment:
                payment.status = status
                self.db.flush()
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error("Failed to update payment status: %s", str(e))
            raise RepositoryException(f"Failed to update payment status: {str(e)}")

    def update_payment_status_for_update(
        self, payment_intent_id: str, status: str
    ) -> Optional[PaymentIntent]:
        """Variant of :meth:`update_payment_status` that takes a row-level lock.

        H4: used by the ``charge.refunded`` webhook handler to serialize
        concurrent writers (webhook vs. local refund flow) so the final
        ``payment_status`` is not subject to last-write-wins.
        """
        try:
            payment = (
                self.db.query(PaymentIntent)
                .filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id)
                .with_for_update()
                .first()
            )
            if payment:
                payment.status = status
                self.db.flush()
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error("Failed to update payment status (locked): %s", str(e))
            raise RepositoryException(f"Failed to update payment status (locked): {str(e)}")

    def get_payment_by_intent_id(self, payment_intent_id: str) -> Optional[PaymentIntent]:
        """
        Get payment record by Stripe payment intent ID.

        Args:
            payment_intent_id: Stripe's payment intent ID

        Returns:
            PaymentIntent if found, None otherwise
        """
        try:
            payment = (
                self.db.query(PaymentIntent)
                .filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id)
                .first()
            )
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error("Failed to get payment by intent ID: %s", str(e))
            raise RepositoryException(f"Failed to get payment by intent ID: {str(e)}")

    def get_payment_by_booking_id(self, booking_id: str) -> Optional[PaymentIntent]:
        """
        Get payment record by booking ID.

        Args:
            booking_id: Booking ID

        Returns:
            PaymentIntent if found, None otherwise
        """
        try:
            payment = (
                self.db.query(PaymentIntent).filter(PaymentIntent.booking_id == booking_id).first()
            )
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error("Failed to get payment by booking ID: %s", str(e))
            raise RepositoryException(f"Failed to get payment by booking ID: {str(e)}")

    def get_payment_intents_for_booking(self, booking_id: str) -> List[PaymentIntent]:
        """Return all payment intent records for a booking ordered newest first."""

        try:
            return cast(
                List[PaymentIntent],
                (
                    self.db.query(PaymentIntent)
                    .filter(PaymentIntent.booking_id == booking_id)
                    .order_by(PaymentIntent.created_at.desc())
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get payment intents for booking: %s", str(e))
            raise RepositoryException(f"Failed to get payment intents for booking: {str(e)}")

    def find_payment_by_booking_and_amount(
        self, booking_id: str, amount_cents: int
    ) -> Optional[PaymentIntent]:
        """Return the most recent payment intent for a booking that matches amount."""

        try:
            payment = (
                self.db.query(PaymentIntent)
                .filter(
                    PaymentIntent.booking_id == booking_id,
                    PaymentIntent.amount == amount_cents,
                )
                .order_by(PaymentIntent.created_at.desc())
                .first()
            )
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error(
                "Failed to find payment intent for booking %s amount %s: %s",
                booking_id,
                amount_cents,
                e,
            )
            raise RepositoryException("Failed to find payment intent by amount")

    def get_payment_by_booking_prefix(self, booking_prefix: str) -> Optional[PaymentIntent]:
        """Get payment record by booking ID prefix (used for truncated references)."""

        try:
            return cast(
                Optional[PaymentIntent],
                (
                    self.db.query(PaymentIntent)
                    .filter(PaymentIntent.booking_id.like(f"{booking_prefix}%"))
                    .order_by(PaymentIntent.created_at.desc())
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get payment by booking prefix: %s", str(e))
            raise RepositoryException(f"Failed to get payment by booking prefix: {str(e)}")
