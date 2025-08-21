"""
Stripe Service for InstaInstru Platform

Implements all Stripe API interactions for marketplace payment processing
using Stripe Connect. This service handles customer management, connected
accounts for instructors, payment processing, and webhook handling.

Key Features:
- Marketplace payments with destination charges
- Express accounts for instructor onboarding
- Application fees (15% default) for platform revenue
- Webhook signature validation
- Comprehensive error handling and logging

Architecture:
- Uses repository pattern for all database operations
- Performance monitoring on all public methods
- Transaction management for data consistency
- Follows established service patterns
"""

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import stripe
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import ServiceException
from ..models.booking import Booking
from ..models.instructor import InstructorProfile
from ..models.payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from .base import BaseService

logger = logging.getLogger(__name__)


class StripeService(BaseService):
    """
    Service for all Stripe API interactions and payment business logic.

    Handles marketplace payment processing using Stripe Connect with
    destination charges, express accounts, and application fees.
    """

    def __init__(self, db: Session):
        """Initialize with database session and configure Stripe."""
        super().__init__(db)
        self.payment_repository = RepositoryFactory.create_payment_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)

        # Configure Stripe API key
        stripe.api_key = settings.stripe_secret_key.get_secret_value() if settings.stripe_secret_key else None

        # Platform fee percentage (15 means 15%, not 0.15)
        self.platform_fee_percentage = getattr(settings, "stripe_platform_fee_percentage", 15) / 100.0

        self.logger = logging.getLogger(__name__)

    # ========== Customer Management ==========

    @BaseService.measure_operation("stripe_create_customer")
    def create_customer(self, user_id: str, email: str, name: str) -> StripeCustomer:
        """
        Create a Stripe customer for a user.

        Args:
            user_id: User's ID (ULID string)
            email: User's email address
            name: User's full name

        Returns:
            StripeCustomer record

        Raises:
            ServiceException: If customer creation fails
        """
        try:
            with self.transaction():
                # Check if customer already exists
                existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
                if existing_customer:
                    self.logger.info(f"Customer already exists for user {user_id}")
                    return existing_customer

                # Create Stripe customer
                stripe_customer = stripe.Customer.create(email=email, name=name, metadata={"user_id": user_id})

                # Save to database
                customer_record = self.payment_repository.create_customer_record(
                    user_id=user_id, stripe_customer_id=stripe_customer.id
                )

                self.logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
                return customer_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating customer: {str(e)}")
            raise ServiceException(f"Failed to create Stripe customer: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating customer: {str(e)}")
            raise ServiceException(f"Failed to create customer: {str(e)}")

    @BaseService.measure_operation("stripe_get_or_create_customer")
    def get_or_create_customer(self, user_id: str) -> StripeCustomer:
        """
        Get existing customer or create a new one.

        Args:
            user_id: User's ID

        Returns:
            StripeCustomer record

        Raises:
            ServiceException: If user not found or customer creation fails
        """
        try:
            # Check if customer already exists
            existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
            if existing_customer:
                return existing_customer

            # Get user details
            user = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException(f"User {user_id} not found")

            # Create new customer
            full_name = f"{user.first_name} {user.last_name}".strip()
            return self.create_customer(user_id, user.email, full_name)

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error getting or creating customer: {str(e)}")
            raise ServiceException(f"Failed to get or create customer: {str(e)}")

    # ========== Connected Account Management ==========

    @BaseService.measure_operation("stripe_create_connected_account")
    def create_connected_account(self, instructor_profile_id: str, email: str) -> StripeConnectedAccount:
        """
        Create a Stripe Express account for an instructor.

        Args:
            instructor_profile_id: Instructor profile ID
            email: Instructor's email address

        Returns:
            StripeConnectedAccount record

        Raises:
            ServiceException: If account creation fails
        """
        try:
            with self.transaction():
                # Check if account already exists
                existing_account = self.payment_repository.get_connected_account_by_instructor_id(instructor_profile_id)
                if existing_account:
                    self.logger.info(f"Connected account already exists for instructor {instructor_profile_id}")
                    return existing_account

                # Create Stripe Express account
                stripe_account = stripe.Account.create(
                    type="express",
                    email=email,
                    capabilities={
                        "transfers": {"requested": True},
                    },
                    metadata={"instructor_profile_id": instructor_profile_id},
                )

                # Save to database
                account_record = self.payment_repository.create_connected_account_record(
                    instructor_profile_id=instructor_profile_id,
                    stripe_account_id=stripe_account.id,
                    onboarding_completed=False,
                )

                self.logger.info(
                    f"Created Stripe Express account {stripe_account.id} for instructor {instructor_profile_id}"
                )
                return account_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")

    @BaseService.measure_operation("stripe_create_account_link")
    def create_account_link(self, instructor_profile_id: str, refresh_url: str, return_url: str) -> str:
        """
        Create an account link for Express account onboarding.

        Args:
            instructor_profile_id: Instructor profile ID
            refresh_url: URL to redirect if link expires
            return_url: URL to redirect after onboarding

        Returns:
            Account link URL

        Raises:
            ServiceException: If account link creation fails
        """
        try:
            # Get connected account
            account_record = self.payment_repository.get_connected_account_by_instructor_id(instructor_profile_id)
            if not account_record:
                raise ServiceException(f"No connected account found for instructor {instructor_profile_id}")

            # Create account link
            account_link = stripe.AccountLink.create(
                account=account_record.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
            )

            self.logger.info(f"Created account link for instructor {instructor_profile_id}")
            return account_link.url

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating account link: {str(e)}")
            raise ServiceException(f"Failed to create account link: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating account link: {str(e)}")
            raise ServiceException(f"Failed to create account link: {str(e)}")

    @BaseService.measure_operation("stripe_check_account_status")
    def check_account_status(self, instructor_profile_id: str) -> Dict[str, Any]:
        """
        Check the onboarding status of a connected account.

        Args:
            instructor_profile_id: Instructor profile ID

        Returns:
            Dictionary with account status information

        Raises:
            ServiceException: If status check fails
        """
        try:
            # Get connected account
            account_record = self.payment_repository.get_connected_account_by_instructor_id(instructor_profile_id)
            if not account_record:
                return {"has_account": False, "onboarding_completed": False, "can_accept_payments": False}

            # Get account details from Stripe
            stripe_account = stripe.Account.retrieve(account_record.stripe_account_id)

            charges_enabled = stripe_account.charges_enabled
            details_submitted = stripe_account.details_submitted

            # Update onboarding status if completed
            if charges_enabled and details_submitted and not account_record.onboarding_completed:
                self.payment_repository.update_onboarding_status(account_record.stripe_account_id, True)
                account_record.onboarding_completed = True

            return {
                "has_account": True,
                "onboarding_completed": account_record.onboarding_completed,
                "can_accept_payments": charges_enabled,
                "details_submitted": details_submitted,
                "stripe_account_id": account_record.stripe_account_id,
            }

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error checking account status: {str(e)}")
            raise ServiceException(f"Failed to check account status: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error checking account status: {str(e)}")
            raise ServiceException(f"Failed to check account status: {str(e)}")

    # ========== Payment Processing ==========

    @BaseService.measure_operation("stripe_create_payment_intent")
    def create_payment_intent(
        self, booking_id: str, customer_id: str, destination_account_id: str, amount_cents: int, currency: str = "usd"
    ) -> PaymentIntent:
        """
        Create a payment intent for a booking with destination charge.

        Args:
            booking_id: Booking ID
            customer_id: Stripe customer ID
            destination_account_id: Instructor's Stripe account ID
            amount_cents: Total amount in cents
            currency: Currency code (default: usd)

        Returns:
            PaymentIntent record

        Raises:
            ServiceException: If payment intent creation fails
        """
        try:
            with self.transaction():
                # Calculate application fee (platform commission)
                application_fee_cents = int(amount_cents * self.platform_fee_percentage)

                # Create Stripe payment intent with destination charge
                stripe_intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency=currency,
                    customer=customer_id,
                    transfer_data={
                        "destination": destination_account_id,
                    },
                    application_fee_amount=application_fee_cents,
                    metadata={"booking_id": booking_id, "platform": "instainstru"},
                )

                # Save payment record
                payment_record = self.payment_repository.create_payment_record(
                    booking_id=booking_id,
                    payment_intent_id=stripe_intent.id,
                    amount=amount_cents,
                    application_fee=application_fee_cents,
                    status=stripe_intent.status,
                )

                self.logger.info(f"Created payment intent {stripe_intent.id} for booking {booking_id}")
                return payment_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating payment intent: {str(e)}")
            raise ServiceException(f"Failed to create payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating payment intent: {str(e)}")
            raise ServiceException(f"Failed to create payment intent: {str(e)}")

    @BaseService.measure_operation("stripe_confirm_payment_intent")
    def confirm_payment_intent(self, payment_intent_id: str, payment_method_id: str) -> PaymentIntent:
        """
        Confirm a payment intent with a payment method.

        Args:
            payment_intent_id: Stripe payment intent ID
            payment_method_id: Stripe payment method ID

        Returns:
            Updated PaymentIntent record

        Raises:
            ServiceException: If confirmation fails
        """
        try:
            with self.transaction():
                # Confirm payment intent
                stripe_intent = stripe.PaymentIntent.confirm(payment_intent_id, payment_method=payment_method_id)

                # Update payment status
                payment_record = self.payment_repository.update_payment_status(payment_intent_id, stripe_intent.status)

                if not payment_record:
                    raise ServiceException(f"Payment record not found for intent {payment_intent_id}")

                self.logger.info(f"Confirmed payment intent {payment_intent_id}")
                return payment_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")

    @BaseService.measure_operation("stripe_process_booking_payment")
    def process_booking_payment(self, booking_id: str, payment_method_id: str) -> Dict[str, Any]:
        """
        Process payment for a booking end-to-end.

        Args:
            booking_id: Booking ID
            payment_method_id: Stripe payment method ID

        Returns:
            Dictionary with payment result

        Raises:
            ServiceException: If payment processing fails
        """
        try:
            with self.transaction():
                # Get booking details
                booking = self.booking_repository.get_by_id(booking_id)
                if not booking:
                    raise ServiceException(f"Booking {booking_id} not found")

                # Get or create customer
                customer = self.get_or_create_customer(booking.student_id)

                # Get instructor's connected account
                instructor_profile = self.instructor_repository.get_by_user_id(booking.instructor_id)
                if not instructor_profile:
                    raise ServiceException(f"Instructor profile not found for user {booking.instructor_id}")

                connected_account = self.payment_repository.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )
                if not connected_account or not connected_account.onboarding_completed:
                    raise ServiceException("Instructor payment account not set up")

                # Calculate amount in cents
                amount_cents = int(booking.total_price * 100)

                # Create payment intent
                payment_record = self.create_payment_intent(
                    booking_id=booking_id,
                    customer_id=customer.stripe_customer_id,
                    destination_account_id=connected_account.stripe_account_id,
                    amount_cents=amount_cents,
                )

                # Confirm payment
                confirmed_payment = self.confirm_payment_intent(
                    payment_record.stripe_payment_intent_id, payment_method_id
                )

                return {
                    "success": True,
                    "payment_intent_id": confirmed_payment.stripe_payment_intent_id,
                    "status": confirmed_payment.status,
                    "amount": amount_cents,
                    "application_fee": confirmed_payment.application_fee,
                }

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error processing booking payment: {str(e)}")
            raise ServiceException(f"Failed to process payment: {str(e)}")

    # ========== Payment Method Management ==========

    @BaseService.measure_operation("stripe_save_payment_method")
    def save_payment_method(self, user_id: str, payment_method_id: str, set_as_default: bool = False) -> PaymentMethod:
        """
        Save a payment method for a user.

        Args:
            user_id: User's ID
            payment_method_id: Stripe payment method ID
            set_as_default: Whether to set as default payment method

        Returns:
            PaymentMethod record

        Raises:
            ServiceException: If saving fails
        """
        try:
            with self.transaction():
                # Get payment method details from Stripe
                stripe_pm = stripe.PaymentMethod.retrieve(payment_method_id)

                # Extract card details
                card = stripe_pm.card
                last4 = card.last4 if card else None
                brand = card.brand if card else None

                # Save to database
                payment_method = self.payment_repository.save_payment_method(
                    user_id=user_id,
                    stripe_payment_method_id=payment_method_id,
                    last4=last4,
                    brand=brand,
                    is_default=set_as_default,
                )

                self.logger.info(f"Saved payment method {payment_method_id} for user {user_id}")
                return payment_method

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error saving payment method: {str(e)}")
            raise ServiceException(f"Failed to save payment method: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error saving payment method: {str(e)}")
            raise ServiceException(f"Failed to save payment method: {str(e)}")

    @BaseService.measure_operation("stripe_get_user_payment_methods")
    def get_user_payment_methods(self, user_id: str) -> List[PaymentMethod]:
        """
        Get all payment methods for a user.

        Args:
            user_id: User's ID

        Returns:
            List of PaymentMethod records

        Raises:
            ServiceException: If retrieval fails
        """
        try:
            return self.payment_repository.get_payment_methods_by_user(user_id)
        except Exception as e:
            self.logger.error(f"Error getting payment methods: {str(e)}")
            raise ServiceException(f"Failed to get payment methods: {str(e)}")

    @BaseService.measure_operation("stripe_delete_payment_method")
    def delete_payment_method(self, payment_method_id: str, user_id: str) -> bool:
        """
        Delete a payment method.

        Args:
            payment_method_id: Payment method ID
            user_id: User's ID (for ownership verification)

        Returns:
            True if deleted successfully

        Raises:
            ServiceException: If deletion fails
        """
        try:
            with self.transaction():
                # Delete from database
                success = self.payment_repository.delete_payment_method(payment_method_id, user_id)

                if success:
                    self.logger.info(f"Deleted payment method {payment_method_id} for user {user_id}")

                return success

        except Exception as e:
            self.logger.error(f"Error deleting payment method: {str(e)}")
            raise ServiceException(f"Failed to delete payment method: {str(e)}")

    # ========== Webhook Handling ==========

    @BaseService.measure_operation("stripe_verify_webhook_signature")
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw webhook payload
            signature: Stripe signature header

        Returns:
            True if signature is valid

        Raises:
            ServiceException: If verification fails
        """
        try:
            webhook_secret = settings.stripe_webhook_secret
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            # Verify signature
            try:
                stripe.Webhook.construct_event(payload, signature, webhook_secret)
                return True
            except stripe.SignatureVerificationError:
                self.logger.warning("Invalid webhook signature")
                return False

        except Exception as e:
            self.logger.error(f"Error verifying webhook signature: {str(e)}")
            raise ServiceException(f"Failed to verify webhook signature: {str(e)}")

    @BaseService.measure_operation("stripe_handle_webhook")
    def handle_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an already-verified webhook event.

        This method is called after signature verification has been performed,
        typically when multiple webhook secrets need to be tried.

        Args:
            event: Already-parsed and verified Stripe event dictionary

        Returns:
            Dictionary with processing result

        Raises:
            ServiceException: If event processing fails
        """
        try:
            event_type = event.get("type", "")
            self.logger.info(f"Processing webhook event: {event_type}")

            # Route to appropriate handler based on event type
            if event_type.startswith("payment_intent."):
                success = self.handle_payment_intent_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("account."):
                success = self._handle_account_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("transfer."):
                success = self._handle_transfer_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("charge."):
                success = self._handle_charge_webhook(event)
                return {"success": success, "event_type": event_type}

            else:
                self.logger.info(f"Unhandled webhook event type: {event_type}")
                return {"success": True, "event_type": event_type, "handled": False}

        except Exception as e:
            self.logger.error(f"Error processing webhook event: {str(e)}")
            raise ServiceException(f"Failed to process webhook event: {str(e)}")

    @BaseService.measure_operation("stripe_handle_webhook_legacy")
    def handle_webhook(self, payload: str, signature: str) -> Dict[str, Any]:
        """
        Legacy webhook handler that verifies signature and processes events.

        This method is kept for backward compatibility. New code should use
        handle_webhook_event() with pre-verified events.

        Args:
            payload: Raw webhook payload as string
            signature: Stripe signature header

        Returns:
            Dictionary with processing result

        Raises:
            ServiceException: If webhook processing fails
        """
        try:
            # Verify webhook signature and construct event
            webhook_secret = (
                settings.stripe_webhook_secret.get_secret_value() if settings.stripe_webhook_secret else None
            )
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            try:
                event = stripe.Webhook.construct_event(
                    payload.encode("utf-8") if isinstance(payload, str) else payload, signature, webhook_secret
                )
            except stripe.SignatureVerificationError as e:
                self.logger.warning(f"Invalid webhook signature: {str(e)}")
                raise ServiceException("Invalid webhook signature")
            except Exception as e:
                self.logger.error(f"Error constructing webhook event: {str(e)}")
                raise ServiceException(f"Invalid webhook payload: {str(e)}")

            # Use the new method to process the event
            return self.handle_webhook_event(event)

        except ServiceException:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error handling webhook: {str(e)}")
            raise ServiceException(f"Failed to process webhook: {str(e)}")

    @BaseService.measure_operation("stripe_handle_payment_intent_webhook")
    def handle_payment_intent_webhook(self, event: Dict[str, Any]) -> bool:
        """
        Handle payment intent webhook events.

        Args:
            event: Stripe webhook event

        Returns:
            True if handled successfully

        Raises:
            ServiceException: If handling fails
        """
        try:
            with self.transaction():
                payment_intent = event["data"]["object"]
                payment_intent_id = payment_intent["id"]
                new_status = payment_intent["status"]

                # Update payment status
                payment_record = self.payment_repository.update_payment_status(payment_intent_id, new_status)

                if payment_record:
                    self.logger.info(f"Updated payment {payment_intent_id} status to {new_status}")

                    # Handle successful payments
                    if new_status == "succeeded":
                        self._handle_successful_payment(payment_record)

                    return True
                else:
                    self.logger.warning(f"Payment record not found for webhook event {payment_intent_id}")
                    return False

        except Exception as e:
            self.logger.error(f"Error handling payment intent webhook: {str(e)}")
            raise ServiceException(f"Failed to handle payment webhook: {str(e)}")

    def _handle_successful_payment(self, payment_record: PaymentIntent) -> None:
        """
        Handle successful payment processing.

        Args:
            payment_record: PaymentIntent record
        """
        try:
            # Update booking status if needed
            booking = self.booking_repository.get_by_id(payment_record.booking_id)
            if booking and booking.status == "PENDING":
                booking.status = "CONFIRMED"
                # repo-pattern-ignore: Transaction management requires direct DB flush
                self.db.flush()

            self.logger.info(f"Processed successful payment for booking {payment_record.booking_id}")

        except Exception as e:
            self.logger.error(f"Error handling successful payment: {str(e)}")
            # Don't raise exception to avoid webhook retry loops

    def _handle_account_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe Connect account events."""
        try:
            event_type = event.get("type", "")
            account_data = event.get("data", {}).get("object", {})
            account_id = account_data.get("id")

            if event_type == "account.updated":
                # Check if onboarding completed
                charges_enabled = account_data.get("charges_enabled", False)
                details_submitted = account_data.get("details_submitted", False)

                if charges_enabled and details_submitted:
                    self.payment_repository.update_onboarding_status(account_id, True)
                    self.logger.info(f"Account {account_id} onboarding completed")

                return True

            elif event_type == "account.application.deauthorized":
                self.logger.warning(f"Account {account_id} was deauthorized")
                # Could implement logic to notify instructor or disable their services
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error handling account webhook: {str(e)}")
            return False

    def _handle_transfer_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe transfer events."""
        try:
            event_type = event.get("type", "")
            transfer_data = event.get("data", {}).get("object", {})
            transfer_id = transfer_data.get("id")

            if event_type == "transfer.created":
                self.logger.info(f"Transfer {transfer_id} created")
                return True

            elif event_type == "transfer.paid":
                self.logger.info(f"Transfer {transfer_id} paid successfully")
                return True

            elif event_type == "transfer.failed":
                self.logger.error(f"Transfer {transfer_id} failed")
                # Could implement logic to notify instructor or retry
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error handling transfer webhook: {str(e)}")
            return False

    def _handle_charge_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe charge events."""
        try:
            event_type = event.get("type", "")
            charge_data = event.get("data", {}).get("object", {})
            charge_id = charge_data.get("id")

            if event_type == "charge.succeeded":
                self.logger.info(f"Charge {charge_id} succeeded")
                return True

            elif event_type == "charge.failed":
                self.logger.error(f"Charge {charge_id} failed")
                # Could implement logic to notify student
                return True

            elif event_type == "charge.refunded":
                self.logger.info(f"Charge {charge_id} refunded")
                # Could implement logic to update booking status
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error handling charge webhook: {str(e)}")
            return False

    # ========== Analytics and Reporting ==========

    @BaseService.measure_operation("stripe_get_platform_revenue_stats")
    def get_platform_revenue_stats(self, start_date=None, end_date=None) -> Dict[str, Any]:
        """
        Get platform revenue statistics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with revenue statistics
        """
        try:
            return self.payment_repository.get_platform_revenue_stats(start_date, end_date)
        except Exception as e:
            self.logger.error(f"Error getting platform revenue stats: {str(e)}")
            raise ServiceException(f"Failed to get revenue stats: {str(e)}")

    @BaseService.measure_operation("stripe_get_instructor_earnings")
    def get_instructor_earnings(self, instructor_profile_id: str, start_date=None, end_date=None) -> Dict[str, Any]:
        """
        Get instructor earnings statistics.

        Args:
            instructor_profile_id: Instructor profile ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with earnings statistics
        """
        try:
            return self.payment_repository.get_instructor_earnings(instructor_profile_id, start_date, end_date)
        except Exception as e:
            self.logger.error(f"Error getting instructor earnings: {str(e)}")
            raise ServiceException(f"Failed to get instructor earnings: {str(e)}")
