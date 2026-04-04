"""Stored payment-method persistence helpers."""

from typing import List, Optional, cast

from sqlalchemy import and_
import ulid

from ...core.exceptions import RepositoryException
from ...models.payment import PaymentMethod
from .mixin_base import PaymentRepositoryMixinBase


class PaymentPaymentMethodMixin(PaymentRepositoryMixinBase):
    """Payment-method queries and mutations."""

    def save_payment_method(
        self,
        user_id: str,
        stripe_payment_method_id: str,
        last4: str,
        brand: str,
        is_default: bool = False,
    ) -> PaymentMethod:
        """
        Save a payment method for a user.

        If is_default=True, unsets other defaults for this user first.

        Args:
            user_id: User's ID
            stripe_payment_method_id: Stripe's payment method ID
            last4: Last 4 digits of card
            brand: Card brand (visa, mastercard, etc.)
            is_default: Whether this is the default payment method

        Returns:
            Created PaymentMethod object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            existing_method = (
                self.db.query(PaymentMethod)
                .filter(
                    and_(
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.stripe_payment_method_id == stripe_payment_method_id,
                    )
                )
                .first()
            )

            if existing_method:
                if is_default:
                    self.db.query(PaymentMethod).filter(
                        and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                    ).update({"is_default": False})

                    existing_method.is_default = True
                    self.db.flush()

                return cast(PaymentMethod, existing_method)
            else:
                if is_default:
                    self.db.query(PaymentMethod).filter(
                        and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                    ).update({"is_default": False})

                method = PaymentMethod(
                    id=str(ulid.ULID()),
                    user_id=user_id,
                    stripe_payment_method_id=stripe_payment_method_id,
                    last4=last4,
                    brand=brand,
                    is_default=is_default,
                )
                self.db.add(method)
                self.db.flush()
                return method
        except Exception as e:
            self.logger.error("Failed to save payment method: %s", str(e))
            raise RepositoryException(f"Failed to save payment method: {str(e)}")

    def get_payment_methods_by_user(self, user_id: str) -> List[PaymentMethod]:
        """
        Get all payment methods for a user.

        Args:
            user_id: User's ID

        Returns:
            List of PaymentMethod objects, ordered by is_default DESC, created_at DESC
        """
        try:
            return cast(
                List[PaymentMethod],
                (
                    self.db.query(PaymentMethod)
                    .filter(PaymentMethod.user_id == user_id)
                    .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get payment methods: %s", str(e))
            raise RepositoryException(f"Failed to get payment methods: {str(e)}")

    def get_default_payment_method(self, user_id: str) -> Optional[PaymentMethod]:
        """
        Get the default payment method for a user.

        Args:
            user_id: User's ID

        Returns:
            Default PaymentMethod if found, None otherwise
        """
        try:
            method = (
                self.db.query(PaymentMethod)
                .filter(and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True))
                .first()
            )
            return cast(Optional[PaymentMethod], method)
        except Exception as e:
            self.logger.error("Failed to get default payment method: %s", str(e))
            raise RepositoryException(f"Failed to get default payment method: {str(e)}")

    def get_payment_method_by_stripe_id(
        self, stripe_payment_method_id: str, user_id: str
    ) -> Optional[PaymentMethod]:
        """
        Get a payment method by its Stripe ID.

        Args:
            stripe_payment_method_id: Stripe payment method ID
            user_id: User's ID

        Returns:
            PaymentMethod if found, None otherwise
        """
        try:
            method = (
                self.db.query(PaymentMethod)
                .filter(
                    and_(
                        PaymentMethod.stripe_payment_method_id == stripe_payment_method_id,
                        PaymentMethod.user_id == user_id,
                    )
                )
                .first()
            )
            return cast(Optional[PaymentMethod], method)
        except Exception as e:
            self.logger.error("Failed to get payment method by Stripe ID: %s", str(e))
            raise RepositoryException(f"Failed to get payment method by Stripe ID: {str(e)}")

    def set_default_payment_method(self, payment_method_id: str, user_id: str) -> bool:
        """
        Set a payment method as default.

        Args:
            payment_method_id: Payment method ID (database ID)
            user_id: User's ID

        Returns:
            True if updated, False if not found
        """
        try:
            self.db.query(PaymentMethod).filter(
                and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
            ).update({"is_default": False})

            result = cast(
                int,
                (
                    self.db.query(PaymentMethod)
                    .filter(
                        and_(
                            PaymentMethod.id == payment_method_id,
                            PaymentMethod.user_id == user_id,
                        )
                    )
                    .update({"is_default": True})
                ),
            )
            self.db.flush()
            return result > 0
        except Exception as e:
            self.logger.error("Failed to set default payment method: %s", str(e))
            raise RepositoryException(f"Failed to set default payment method: {str(e)}")

    def delete_payment_method(self, payment_method_id: str, user_id: str) -> bool:
        """
        Delete a payment method.

        Args:
            payment_method_id: Payment method ID (can be either database ID or Stripe ID)
            user_id: User's ID (for ownership verification)

        Returns:
            True if deleted, False if not found
        """
        try:
            if payment_method_id.startswith("pm_"):
                result = cast(
                    int,
                    (
                        self.db.query(PaymentMethod)
                        .filter(
                            and_(
                                PaymentMethod.stripe_payment_method_id == payment_method_id,
                                PaymentMethod.user_id == user_id,
                            )
                        )
                        .delete()
                    ),
                )
            else:
                result = cast(
                    int,
                    (
                        self.db.query(PaymentMethod)
                        .filter(
                            and_(
                                PaymentMethod.id == payment_method_id,
                                PaymentMethod.user_id == user_id,
                            )
                        )
                        .delete()
                    ),
                )
            self.db.flush()
            return result > 0
        except Exception as e:
            self.logger.error("Failed to delete payment method: %s", str(e))
            raise RepositoryException(f"Failed to delete payment method: {str(e)}")
