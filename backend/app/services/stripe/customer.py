from __future__ import annotations

from importlib import import_module
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

import stripe

from ...core.exceptions import ServiceException
from ...models.payment import PaymentMethod, StripeCustomer
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.payment_repository import PaymentRepository
    from ...repositories.user_repository import UserRepository
    from ..stripe_service import StripeServiceModuleProtocol

logger = logging.getLogger(__name__)


def _stripe_service_module() -> StripeServiceModuleProtocol:
    return cast("StripeServiceModuleProtocol", import_module("app.services.stripe_service"))


class StripeCustomerMixin(BaseService):
    """Stripe customer management — creation, payment methods, setup intents."""

    payment_repository: PaymentRepository
    user_repository: UserRepository
    stripe_configured: bool

    if TYPE_CHECKING:

        def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
            ...

        def _check_stripe_configured(self) -> None:
            ...

    @BaseService.measure_operation("stripe_create_customer")
    def create_customer(self, user_id: str, email: str, name: str) -> StripeCustomer:
        """Create a Stripe customer for a user."""
        stripe_sdk = _stripe_service_module().stripe
        auth_error_cls = getattr(
            getattr(stripe_sdk, "error", None),
            "AuthenticationError",
            stripe.error.AuthenticationError,
        )
        try:
            with self.transaction():
                existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
                if existing_customer:
                    self.logger.info("Customer already exists for user %s", user_id)
                    return existing_customer

            try:
                stripe_customer = self._call_with_retry(
                    stripe_sdk.Customer.create,
                    email=email,
                    name=name,
                    metadata={"user_id": user_id},
                    idempotency_key=f"cust_{user_id}",
                )
                stripe_customer_id = stripe_customer.id
            except Exception as exc:
                if not self.stripe_configured:
                    if os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").lower() == "true":
                        raise ServiceException(
                            "Stripe not configured in production mode",
                            code="configuration_error",
                        )
                    message = str(exc)
                    auth_error = False
                    try:
                        auth_error = isinstance(exc, auth_error_cls)
                    except TypeError:
                        auth_error = False
                    if auth_error or "No API key" in message or "api key" in message.lower():
                        self.logger.warning(
                            "Stripe not configured (auth error); using mock customer for user %s",
                            user_id,
                        )
                        stripe_customer_id = f"mock_cust_{user_id}"
                    else:
                        self.logger.error("Stripe customer creation failed: %s", message)
                        raise ServiceException(f"Failed to create Stripe customer: {message}")
                else:
                    raise

            with self.transaction():
                customer_record = self.payment_repository.create_customer_record(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                )

            self.logger.info("Created Stripe customer %s for user %s", stripe_customer_id, user_id)
            return customer_record
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating customer: %s", exc)
            raise ServiceException(f"Failed to create Stripe customer: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error creating customer: %s", exc)
            raise ServiceException(f"Failed to create customer: {str(exc)}")

    @BaseService.measure_operation("stripe_get_or_create_customer")
    def get_or_create_customer(self, user_id: str) -> StripeCustomer:
        """Get an existing Stripe customer or create a new one."""
        try:
            existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
            if existing_customer:
                return existing_customer

            user = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException(f"User {user_id} not found")

            full_name = f"{user.first_name} {user.last_name}".strip()
            return self.create_customer(user_id, user.email, full_name)
        except Exception as exc:
            if isinstance(exc, ServiceException):
                raise
            self.logger.error("Error getting or creating customer: %s", exc)
            raise ServiceException(f"Failed to get or create customer: {str(exc)}")

    @BaseService.measure_operation("stripe_create_setup_intent_for_saving")
    def create_setup_intent_for_saving(self, user_id: str) -> Dict[str, str]:
        """Create a SetupIntent for saving a payment method via PaymentElement."""
        stripe_sdk = _stripe_service_module().stripe
        self._check_stripe_configured()
        customer = self.get_or_create_customer(user_id)
        setup_intent = self._call_with_retry(
            stripe_sdk.SetupIntent.create,
            customer=customer.stripe_customer_id,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            usage="off_session",
            metadata={"user_id": user_id, "platform": "instainstru"},
        )
        client_secret = setup_intent.client_secret
        if not client_secret:
            raise ServiceException("SetupIntent created without client_secret")
        return {"client_secret": client_secret}

    def _get_existing_saved_payment_method(
        self, *, user_id: str, payment_method_id: str, set_as_default: bool
    ) -> Optional[PaymentMethod]:
        existing = self.payment_repository.get_payment_method_by_stripe_id(
            payment_method_id,
            user_id,
        )
        if not existing:
            return None

        self.logger.info(
            "Payment method %s already exists for user %s",
            payment_method_id,
            user_id,
        )
        if set_as_default:
            self.payment_repository.set_default_payment_method(existing.id, user_id)
        return existing

    def _attach_stripe_payment_method(
        self, *, payment_method_id: str, stripe_customer_id: str
    ) -> Any:
        stripe_sdk = _stripe_service_module().stripe
        card_error_cls = getattr(
            getattr(stripe_sdk, "error", None),
            "CardError",
            stripe.error.CardError,
        )
        try:
            stripe_payment_method = stripe_sdk.PaymentMethod.retrieve(payment_method_id)
            if stripe_payment_method.customer:
                if stripe_payment_method.customer != stripe_customer_id:
                    self.logger.error(
                        "Payment method %s is attached to a different customer",
                        payment_method_id,
                    )
                    raise ServiceException(
                        "This payment method is already in use by another account"
                    )
                self.logger.info(
                    "Payment method %s already attached to customer",
                    payment_method_id,
                )
                return stripe_payment_method

            attached_payment_method = stripe_sdk.PaymentMethod.attach(
                payment_method_id,
                customer=stripe_customer_id,
            )
            self.logger.info("Attached payment method %s to customer", payment_method_id)
            return attached_payment_method
        except card_error_cls as exc:
            self.logger.error("Card error: %s", exc)
            error_message = str(exc.user_message) if hasattr(exc, "user_message") else str(exc)
            raise ServiceException(error_message)

    def _extract_saved_card_details(self, stripe_payment_method: Any) -> tuple[str, str]:
        card = stripe_payment_method.card
        last4 = cast(Optional[str], getattr(card, "last4", None) if card else None)
        brand = cast(Optional[str], getattr(card, "brand", None) if card else None)
        return last4 or "", brand or ""

    def _persist_saved_payment_method(
        self,
        *,
        user_id: str,
        payment_method_id: str,
        last4: str,
        brand: str,
        set_as_default: bool,
    ) -> PaymentMethod:
        return self.payment_repository.save_payment_method(
            user_id=user_id,
            stripe_payment_method_id=payment_method_id,
            last4=last4,
            brand=brand,
            is_default=set_as_default,
        )

    @BaseService.measure_operation("stripe_save_payment_method")
    def save_payment_method(
        self, user_id: str, payment_method_id: str, set_as_default: bool = False
    ) -> PaymentMethod:
        """Save a payment method for a user."""
        try:
            with self.transaction():
                existing = self._get_existing_saved_payment_method(
                    user_id=user_id,
                    payment_method_id=payment_method_id,
                    set_as_default=set_as_default,
                )
            if existing:
                return existing

            customer = self.get_or_create_customer(user_id)
            # Stripe PaymentMethod retrieve/attach stays outside DB transactions.
            stripe_payment_method = self._attach_stripe_payment_method(
                payment_method_id=payment_method_id,
                stripe_customer_id=customer.stripe_customer_id,
            )
            last4, brand = self._extract_saved_card_details(stripe_payment_method)
            with self.transaction():
                payment_method = self._persist_saved_payment_method(
                    user_id=user_id,
                    payment_method_id=payment_method_id,
                    last4=last4,
                    brand=brand,
                    set_as_default=set_as_default,
                )
            self.logger.info("Saved payment method %s for user %s", payment_method_id, user_id)
            return payment_method
        except ServiceException:
            raise
        except stripe.StripeError as exc:
            self.logger.error("Stripe error saving payment method: %s", exc)
            error_message = str(exc.user_message) if hasattr(exc, "user_message") else str(exc)
            raise ServiceException(f"Failed to save payment method: {error_message}")
        except Exception as exc:
            self.logger.error("Error saving payment method: %s", exc)
            raise ServiceException(f"Failed to save payment method: {str(exc)}")

    @BaseService.measure_operation("stripe_get_user_payment_methods")
    def get_user_payment_methods(self, user_id: str) -> List[PaymentMethod]:
        """Get all payment methods for a user."""
        try:
            return list(self.payment_repository.get_payment_methods_by_user(user_id))
        except Exception as exc:
            self.logger.error("Error getting payment methods: %s", exc)
            raise ServiceException(f"Failed to get payment methods: {str(exc)}")

    @BaseService.measure_operation("stripe_delete_payment_method")
    def delete_payment_method(self, payment_method_id: str, user_id: str) -> bool:
        """Delete a payment method."""
        stripe_sdk = _stripe_service_module().stripe
        try:
            if payment_method_id.startswith("pm_"):
                existing = self.payment_repository.get_payment_method_by_stripe_id(
                    payment_method_id,
                    user_id,
                )
                if not existing:
                    return False

            if payment_method_id.startswith("pm_"):
                try:
                    stripe_sdk.PaymentMethod.detach(payment_method_id)
                    self.logger.info("Detached payment method %s from Stripe", payment_method_id)
                except stripe.StripeError as exc:
                    self.logger.warning("Could not detach payment method from Stripe: %s", exc)

            with self.transaction():
                success = self.payment_repository.delete_payment_method(payment_method_id, user_id)

            if success:
                self.logger.info(
                    "Deleted payment method %s from database for user %s",
                    payment_method_id,
                    user_id,
                )
            return bool(success)
        except Exception as exc:
            self.logger.error("Error deleting payment method: %s", exc)
            raise ServiceException(f"Failed to delete payment method: {str(exc)}")
