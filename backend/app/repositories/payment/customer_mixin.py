"""Stripe customer persistence helpers."""

from typing import Optional, cast

import ulid

from ...core.exceptions import RepositoryException
from ...models.payment import StripeCustomer
from .mixin_base import PaymentRepositoryMixinBase


class PaymentCustomerMixin(PaymentRepositoryMixinBase):
    """Customer management queries and mutations."""

    def create_customer_record(self, user_id: str, stripe_customer_id: str) -> StripeCustomer:
        """
        Create a new Stripe customer record.

        Args:
            user_id: User's ID (ULID string)
            stripe_customer_id: Stripe's customer ID

        Returns:
            Created StripeCustomer object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            customer = StripeCustomer(
                id=str(ulid.ULID()),
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
            )
            self.db.add(customer)
            self.db.flush()
            return customer
        except Exception as e:
            self.logger.error("Failed to create customer record: %s", str(e))
            raise RepositoryException(f"Failed to create customer record: {str(e)}")

    def get_customer_by_user_id(self, user_id: str) -> Optional[StripeCustomer]:
        """
        Get Stripe customer record by user ID.

        Args:
            user_id: User's ID

        Returns:
            StripeCustomer if found, None otherwise
        """
        try:
            customer = (
                self.db.query(StripeCustomer).filter(StripeCustomer.user_id == user_id).first()
            )
            return cast(Optional[StripeCustomer], customer)
        except Exception as e:
            self.logger.error("Failed to get customer by user ID: %s", str(e))
            raise RepositoryException(f"Failed to get customer by user ID: {str(e)}")

    def get_customer_by_stripe_id(self, stripe_customer_id: str) -> Optional[StripeCustomer]:
        """
        Get customer record by Stripe customer ID.

        Args:
            stripe_customer_id: Stripe's customer ID

        Returns:
            StripeCustomer if found, None otherwise
        """
        try:
            customer = (
                self.db.query(StripeCustomer)
                .filter(StripeCustomer.stripe_customer_id == stripe_customer_id)
                .first()
            )
            return cast(Optional[StripeCustomer], customer)
        except Exception as e:
            self.logger.error("Failed to get customer by Stripe ID: %s", str(e))
            raise RepositoryException(f"Failed to get customer by Stripe ID: {str(e)}")
