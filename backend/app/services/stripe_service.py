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

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
import stripe

from ..core.config import settings
from ..core.exceptions import ServiceException
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

        # Configure Stripe API key with defensive error handling
        self.stripe_configured = False
        try:
            if settings.stripe_secret_key:
                stripe.api_key = settings.stripe_secret_key.get_secret_value()
                # Set sane network timeouts/retries to avoid blocking the server on Stripe calls
                try:
                    # 8s overall timeout; 1 retry for transient failures
                    stripe.default_http_client = stripe.http_client.RequestsClient(timeout=8)
                    stripe.max_network_retries = 1
                    stripe.verify_ssl_certs = True
                except Exception:
                    # Non-fatal if client customization isn't available
                    pass
                self.stripe_configured = True
                self.logger.info("Stripe service configured successfully")
            else:
                self.logger.warning(
                    "Stripe secret key not configured - service will operate in mock mode"
                )
        except Exception as e:
            self.logger.error(
                f"Failed to configure Stripe service: {e} - service will operate in mock mode"
            )

        # Platform fee percentage (15 means 15%, not 0.15)
        self.platform_fee_percentage = (
            getattr(settings, "stripe_platform_fee_percentage", 15) / 100.0
        )

        self.logger = logging.getLogger(__name__)

    def _check_stripe_configured(self) -> None:
        """Check if Stripe is properly configured before making API calls."""
        if not self.stripe_configured:
            raise ServiceException(
                "Stripe service not configured. Please check STRIPE_SECRET_KEY environment variable."
            )

    # ========== Identity Verification ==========
    @BaseService.measure_operation("stripe_create_identity_session")
    def create_identity_verification_session(
        self,
        *,
        user_id: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe Identity verification session for the given user.

        Returns dict with `client_secret` and `verification_session_id`.
        """
        try:
            self._check_stripe_configured()

            user: Optional[User] = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException("User not found for identity verification")

            # Build verification session parameters
            params: Dict[str, Any] = {
                "type": "document",
                "metadata": {"user_id": user_id},
                "options": {
                    "document": {"require_live_capture": True, "require_matching_selfie": True}
                },
                "return_url": return_url,
            }

            session = stripe.identity.VerificationSession.create(**params)  # type: ignore[attr-defined]

            client_secret = getattr(session, "client_secret", None)
            if not client_secret:
                raise ServiceException("Failed to create identity verification session")

            return {
                "verification_session_id": getattr(session, "id", None),
                "client_secret": client_secret,
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating identity session: {str(e)}")
            raise ServiceException(f"Failed to start identity verification: {str(e)}")
        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error creating identity session: {str(e)}")
            raise ServiceException("Failed to start identity verification")

    @BaseService.measure_operation("stripe_get_latest_identity_status")
    def get_latest_identity_status(self, user_id: str) -> Dict[str, Any]:
        """Return latest Stripe Identity verification status for a user.

        Uses session metadata.user_id to find the most recent session.
        """
        try:
            self._check_stripe_configured()
            # Fetch recent sessions and filter by our metadata
            # Run list call with bounded timeout via stripe client defaults
            sessions = stripe.identity.VerificationSession.list(limit=20)  # type: ignore[attr-defined]
            latest = None
            for s in sessions.get("data", []):
                try:
                    meta = getattr(s, "metadata", {}) or {}
                    if str(meta.get("user_id")) == str(user_id):
                        if latest is None or getattr(s, "created", 0) > getattr(
                            latest, "created", 0
                        ):
                            latest = s
                except Exception:
                    continue

            if not latest:
                return {"status": "not_found"}

            return {
                "status": getattr(latest, "status", "unknown"),
                "id": getattr(latest, "id", None),
                "created": getattr(latest, "created", None),
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error getting identity status: {str(e)}")
            raise ServiceException(f"Failed to get identity status: {str(e)}")
        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error getting identity status: {str(e)}")
            raise ServiceException("Failed to get identity status")

    def _mock_payment_response(self, booking_id: str, amount_cents: int) -> Dict[str, Any]:
        """Return a mock payment response for testing/CI when Stripe is not configured."""
        return {
            "success": True,
            "payment_intent_id": f"mock_pi_{booking_id}",
            "status": "succeeded",
            "amount": amount_cents / 100.0,
            "application_fee": 0,
            "client_secret": None,
        }

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

                # Try real Stripe path first (allows tests to @patch)
                try:
                    stripe_customer = stripe.Customer.create(
                        email=email, name=name, metadata={"user_id": user_id}
                    )
                    customer_record = self.payment_repository.create_customer_record(
                        user_id=user_id, stripe_customer_id=stripe_customer.id
                    )
                    self.logger.info(
                        f"Created Stripe customer {stripe_customer.id} for user {user_id}"
                    )
                    return customer_record
                except Exception as e:
                    # If Stripe isn't configured, decide between mock fallback and raising
                    if not self.stripe_configured:
                        msg = str(e)
                        auth_error = False
                        try:
                            # AuthenticationError indicates missing/invalid API key
                            auth_error = isinstance(e, stripe.error.AuthenticationError)  # type: ignore[attr-defined]
                        except Exception:
                            auth_error = False

                        if auth_error or "No API key" in msg or "api key" in msg.lower():
                            self.logger.warning(
                                f"Stripe not configured (auth error); using mock customer for user {user_id}"
                            )
                            return self.payment_repository.create_customer_record(
                                user_id=user_id, stripe_customer_id=f"mock_cust_{user_id}"
                            )

                        # For other errors (e.g., tests patching to raise API Error), surface as ServiceException
                        self.logger.error(f"Stripe customer creation failed: {msg}")
                        raise ServiceException(f"Failed to create Stripe customer: {msg}")

                    # If configured, bubble up as a service error
                    raise

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
    def create_connected_account(
        self, instructor_profile_id: str, email: str
    ) -> StripeConnectedAccount:
        """
        Create a Stripe Connect Express account for an instructor.

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
                try:
                    # Try real Stripe path first (allows tests to @patch)
                    stripe_account = stripe.Account.create(
                        type="express",
                        email=email,
                        capabilities={"transfers": {"requested": True}},
                        metadata={"instructor_profile_id": instructor_profile_id},
                    )

                    account_record = self.payment_repository.create_connected_account_record(
                        instructor_profile_id=instructor_profile_id,
                        stripe_account_id=stripe_account.id,
                        onboarding_completed=False,
                    )

                    # Set default payout schedule (best-effort)
                    try:
                        stripe.Account.modify(
                            stripe_account.id,
                            settings={
                                "payouts": {
                                    "schedule": {
                                        "interval": "weekly",
                                        "weekly_anchor": "tuesday",
                                    }
                                }
                            },
                        )
                    except Exception:
                        pass

                    self.logger.info(
                        f"Created Stripe Express account {stripe_account.id} for instructor {instructor_profile_id}"
                    )
                    return account_record
                except Exception as e:
                    if not self.stripe_configured:
                        self.logger.warning(
                            f"Stripe not configured or call failed ({e}); using mock connected account for instructor {instructor_profile_id}"
                        )
                        return self.payment_repository.create_connected_account_record(
                            instructor_profile_id=instructor_profile_id,
                            stripe_account_id=f"mock_acct_{instructor_profile_id}",
                            onboarding_completed=False,
                        )
                    raise

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")

    @BaseService.measure_operation("stripe_create_account_link")
    def create_account_link(
        self, instructor_profile_id: str, refresh_url: str, return_url: str
    ) -> str:
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
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                raise ServiceException(
                    f"No connected account found for instructor {instructor_profile_id}"
                )

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

    @BaseService.measure_operation("stripe_set_payout_schedule")
    def set_payout_schedule_for_account(
        self,
        *,
        instructor_profile_id: str,
        interval: str = "weekly",
        weekly_anchor: str = "tuesday",
    ) -> Dict[str, Any]:
        """
        Set the payout schedule for a connected account (Express).

        Recommended to run right after onboarding completes and via a periodic audit.
        """
        try:
            account = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account:
                raise ServiceException("Connected account not found for instructor")

            updated = stripe.Account.modify(
                account.stripe_account_id,
                settings={
                    "payouts": {
                        "schedule": {
                            "interval": interval,
                            "weekly_anchor": weekly_anchor,
                        }
                    }
                },
            )
            self.logger.info(
                f"Updated payout schedule for {account.stripe_account_id}: interval={interval}, anchor={weekly_anchor}"
            )
            # Return minimal details to caller
            try:
                settings_obj = getattr(updated, "settings", {})
            except Exception:
                settings_obj = {}
            return {"account_id": account.stripe_account_id, "settings": settings_obj}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error setting payout schedule: {str(e)}")
            raise ServiceException(f"Failed to set payout schedule: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error setting payout schedule: {str(e)}")
            raise ServiceException(f"Failed to set payout schedule: {str(e)}")

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
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                return {
                    "has_account": False,
                    "onboarding_completed": False,
                    "can_accept_payments": False,
                }

            # Get account details from Stripe
            stripe_account = stripe.Account.retrieve(account_record.stripe_account_id)

            charges_enabled = bool(getattr(stripe_account, "charges_enabled", False))
            payouts_enabled = bool(getattr(stripe_account, "payouts_enabled", False))
            details_submitted = bool(getattr(stripe_account, "details_submitted", False))

            # Compute actual onboarding completion from live Stripe fields
            computed_completed = bool(charges_enabled and details_submitted)

            # Keep DB flag in sync (do not force true when not actually completed)
            if account_record.onboarding_completed != computed_completed:
                try:
                    self.payment_repository.update_onboarding_status(
                        account_record.stripe_account_id, computed_completed
                    )
                    account_record.onboarding_completed = computed_completed
                except Exception:
                    # Non-fatal if persistence fails; return live-computed status
                    pass

            return {
                "has_account": True,
                "onboarding_completed": computed_completed,
                "can_accept_payments": charges_enabled,
                "payouts_enabled": payouts_enabled,
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
        self,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        amount_cents: int,
        currency: str = "usd",
    ) -> PaymentIntent:
        """
        Create a Stripe PaymentIntent for a booking.

        Args:
            booking_id: Booking ID
            customer_id: Stripe customer ID
            destination_account_id: Stripe connected account ID
            amount_cents: Amount in cents

        Returns:
            PaymentIntent record

        Raises:
            ServiceException: If PaymentIntent creation fails
        """
        try:
            with self.transaction():
                application_fee_cents = int(amount_cents * self.platform_fee_percentage)

                try:
                    # Try real Stripe path first (allows tests to @patch)
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

                    payment_record = self.payment_repository.create_payment_record(
                        booking_id=booking_id,
                        payment_intent_id=stripe_intent.id,
                        amount=amount_cents,
                        application_fee=application_fee_cents,
                        status=stripe_intent.status,
                    )
                    self.logger.info(
                        f"Created payment intent {stripe_intent.id} for booking {booking_id}"
                    )
                    return payment_record
                except Exception as e:
                    if not self.stripe_configured:
                        self.logger.warning(
                            f"Stripe not configured or call failed ({e}); using mock payment intent for booking {booking_id}"
                        )
                        return self.payment_repository.create_payment_record(
                            booking_id=booking_id,
                            payment_intent_id=f"mock_pi_{booking_id}",
                            amount=amount_cents,
                            application_fee=application_fee_cents,
                            status="requires_payment_method",
                        )
                    raise

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating payment intent: {str(e)}")
            raise ServiceException(f"Failed to create payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating payment intent: {str(e)}")
            raise ServiceException(f"Failed to create payment intent: {str(e)}")

    @BaseService.measure_operation("stripe_create_and_confirm_manual_authorization")
    def create_and_confirm_manual_authorization(
        self,
        *,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str = "usd",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a manual-capture PaymentIntent for immediate authorization (<24h bookings) and confirm off-session.

        Returns a dict with keys: payment_intent (Stripe object), status, requires_action, client_secret.
        """
        try:
            application_fee_cents = int(amount_cents * self.platform_fee_percentage)

            pi = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                capture_method="manual",
                confirm=True,
                off_session=True,
                transfer_data={"destination": destination_account_id},
                application_fee_amount=application_fee_cents,
                metadata={"booking_id": booking_id, "platform": "instainstru"},
                idempotency_key=idempotency_key,
            )

            result: Dict[str, Any] = {"payment_intent": pi, "status": pi.status}
            if getattr(pi, "status", "") == "requires_action":
                result.update(
                    {
                        "requires_action": True,
                        "client_secret": getattr(pi, "client_secret", None),
                    }
                )
            else:
                result.update({"requires_action": False, "client_secret": None})

            # Persist/Upsert payment record if present in DB
            try:
                self.payment_repository.upsert_payment_record(
                    booking_id=booking_id,
                    payment_intent_id=pi.id,
                    amount=amount_cents,
                    application_fee=application_fee_cents,
                    status=pi.status,
                )
            except Exception:
                # Repository might not have upsert; ignore non-critical
                pass

            return result
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating manual authorization: {str(e)}")
            raise ServiceException(f"Failed to authorize payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating manual authorization: {str(e)}")
            raise ServiceException(f"Failed to authorize payment: {str(e)}")

    @BaseService.measure_operation("stripe_confirm_payment_intent")
    def confirm_payment_intent(
        self, payment_intent_id: str, payment_method_id: str
    ) -> PaymentIntent:
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
                # Confirm payment intent with return_url for redirect-based payment methods
                stripe_intent = stripe.PaymentIntent.confirm(
                    payment_intent_id,
                    payment_method=payment_method_id,
                    return_url=f"{settings.frontend_url}/student/payment/complete",
                )

                # Update payment status
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id, stripe_intent.status
                )

                if not payment_record:
                    raise ServiceException(
                        f"Payment record not found for intent {payment_intent_id}"
                    )

                self.logger.info(f"Confirmed payment intent {payment_intent_id}")
                return payment_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")

    @BaseService.measure_operation("stripe_capture_payment_intent")
    def capture_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Capture a manual-capture PaymentIntent and return charge and transfer info.

        Returns dict: {"payment_intent": pi, "charge_id": str|None, "transfer_id": str|None, "amount_received": int|None}
        """
        try:
            pi = stripe.PaymentIntent.capture(payment_intent_id, idempotency_key=idempotency_key)

            charge_id = None
            transfer_id = None
            amount_received = None

            try:
                if pi.get("charges") and pi["charges"]["data"]:
                    charge = pi["charges"]["data"][0]
                    charge_id = charge.get("id")
                    amount_received = charge.get("amount") or pi.get("amount_received")
                    # For destination charges, charge.transfer holds the transfer id
                    transfer_id = charge.get("transfer")
            except Exception:
                pass

            # Update stored payment status if present
            try:
                self.payment_repository.update_payment_status(payment_intent_id, pi.status)
            except Exception:
                pass

            return {
                "payment_intent": pi,
                "charge_id": charge_id,
                "transfer_id": transfer_id,
                "amount_received": amount_received,
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error capturing payment intent: {str(e)}")
            raise ServiceException(f"Failed to capture payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error capturing payment intent: {str(e)}")
            raise ServiceException(f"Failed to capture payment: {str(e)}")

    @BaseService.measure_operation("stripe_reverse_transfer")
    def reverse_transfer(
        self,
        *,
        transfer_id: str,
        amount_cents: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Reverse a transfer (full or partial) back to platform balance.
        """
        try:
            params: Dict[str, Any] = {"transfer": transfer_id}
            if amount_cents is not None:
                params["amount"] = amount_cents
            if reason:
                params["metadata"] = {"reason": reason}
            # stripe.Transfer.create_reversal expects transfer id as positional arg
            kwargs: Dict[str, Any] = {}
            if amount_cents is not None:
                kwargs["amount"] = amount_cents
            if reason:
                kwargs["metadata"] = {"reason": reason}
            reversal = stripe.Transfer.create_reversal(
                transfer_id, idempotency_key=idempotency_key, **kwargs
            )

            # Alert/metrics for insufficient funds or negative balance scenarios
            try:
                # Stripe returns balance_transaction on reversal; if missing or amount < requested, log alert
                reversed_amount = getattr(reversal, "amount_reversed", None) or getattr(
                    reversal, "amount", None
                )
                if (
                    amount_cents is not None
                    and reversed_amount is not None
                    and reversed_amount < amount_cents
                ):
                    self.logger.warning(
                        f"Partial reversal for transfer {transfer_id}: requested={amount_cents} reversed={reversed_amount}"
                    )
                # If failure_code present in reversal (rare), log as error
                failure_code = (
                    getattr(reversal, "failure_code", None) or reversal.get("failure_code")
                    if isinstance(reversal, dict)
                    else None
                )
                if failure_code:
                    self.logger.error(
                        f"Transfer reversal reported failure_code={failure_code} for transfer {transfer_id}"
                    )
            except Exception:
                # Do not fail the main flow for metrics issues
                pass

            return {"reversal": reversal}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error reversing transfer: {str(e)}")
            raise ServiceException(f"Failed to reverse transfer: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error reversing transfer: {str(e)}")
            raise ServiceException(f"Failed to reverse transfer: {str(e)}")

    @BaseService.measure_operation("stripe_cancel_payment_intent")
    def cancel_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a PaymentIntent to release authorization.
        """
        try:
            pi = stripe.PaymentIntent.cancel(payment_intent_id, idempotency_key=idempotency_key)
            try:
                self.payment_repository.update_payment_status(payment_intent_id, pi.status)
            except Exception:
                pass
            return {"payment_intent": pi}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error canceling payment intent: {str(e)}")
            raise ServiceException(f"Failed to cancel payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error canceling payment intent: {str(e)}")
            raise ServiceException(f"Failed to cancel payment intent: {str(e)}")

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
                instructor_profile = self.instructor_repository.get_by_user_id(
                    booking.instructor_id
                )
                if not instructor_profile:
                    raise ServiceException(
                        f"Instructor profile not found for user {booking.instructor_id}"
                    )

                connected_account = self.payment_repository.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )
                if not connected_account or not connected_account.onboarding_completed:
                    raise ServiceException("Instructor payment account not set up")

                # Calculate amount in cents and apply any available platform credits up-front
                original_amount_cents = int(booking.total_price * 100)
                credits_applied = 0
                try:
                    if hasattr(self.payment_repository, "apply_credits_for_booking"):
                        credit_result = self.payment_repository.apply_credits_for_booking(
                            user_id=booking.student_id,
                            booking_id=booking.id,
                            amount_cents=original_amount_cents,
                        )
                        if isinstance(credit_result, dict):
                            credits_applied = int(credit_result.get("applied_cents", 0) or 0)
                except Exception as credit_err:
                    self.logger.warning(
                        f"Failed to apply credits for booking {booking.id}: {credit_err}. Proceeding without credits."
                    )

                amount_cents = max(original_amount_cents - credits_applied, 0)

                # If credits fully cover the cost, record success and return without creating a PI
                if amount_cents <= 0:
                    try:
                        self.payment_repository.create_payment_event(
                            booking_id=booking.id,
                            event_type="auth_succeeded_credits_only",
                            event_data={
                                "original_amount_cents": original_amount_cents,
                                "credits_applied_cents": credits_applied,
                                "authorized_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    except Exception:
                        pass

                    # Mark booking as authorized for payment purposes
                    booking.payment_status = "authorized"

                    return {
                        "success": True,
                        "payment_intent_id": "credit_only",
                        "status": "succeeded",
                        "amount": 0,
                        "application_fee": 0,
                        "client_secret": None,
                    }

                # Create payment intent
                payment_record = self.create_payment_intent(
                    booking_id=booking_id,
                    customer_id=customer.stripe_customer_id,
                    destination_account_id=connected_account.stripe_account_id,
                    amount_cents=amount_cents,
                )

                # Confirm payment
                # Confirm payment and handle 3DS requirements
                try:
                    stripe_intent = stripe.PaymentIntent.confirm(
                        payment_record.stripe_payment_intent_id,
                        payment_method=payment_method_id,
                        return_url=f"{settings.frontend_url}/student/payment/complete",
                    )
                except stripe.error.CardError as e:
                    raise ServiceException(f"Card error: {str(e)}")

                # Persist updated status
                try:
                    self.payment_repository.update_payment_status(
                        payment_record.stripe_payment_intent_id, stripe_intent.status
                    )
                except Exception:
                    pass

                requires_action = stripe_intent.status in [
                    "requires_action",
                    "requires_confirmation",
                ]
                client_secret = (
                    getattr(stripe_intent, "client_secret", None) if requires_action else None
                )

                return {
                    "success": True,
                    "payment_intent_id": payment_record.stripe_payment_intent_id,
                    "status": stripe_intent.status,
                    "amount": amount_cents,
                    "application_fee": payment_record.application_fee,
                    "client_secret": client_secret,
                }

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error processing booking payment: {str(e)}")
            raise ServiceException(f"Failed to process payment: {str(e)}")

    # ========== Payment Method Management ==========

    @BaseService.measure_operation("stripe_save_payment_method")
    def save_payment_method(
        self, user_id: str, payment_method_id: str, set_as_default: bool = False
    ) -> PaymentMethod:
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
                # Check if payment method already exists in our database
                existing = self.payment_repository.get_payment_method_by_stripe_id(
                    payment_method_id, user_id
                )
                if existing:
                    self.logger.info(
                        f"Payment method {payment_method_id} already exists for user {user_id}"
                    )
                    # If setting as default, update the existing one
                    if set_as_default:
                        self.payment_repository.set_default_payment_method(existing.id, user_id)
                    return existing

                # Ensure user has a Stripe customer
                customer = self.get_or_create_customer(user_id)

                # First retrieve the payment method to check its status
                try:
                    stripe_pm = stripe.PaymentMethod.retrieve(payment_method_id)

                    # Check if already attached to a customer
                    if stripe_pm.customer:
                        if stripe_pm.customer != customer.stripe_customer_id:
                            # Payment method is attached to a different customer
                            self.logger.error(
                                f"Payment method {payment_method_id} is attached to a different customer"
                            )
                            raise ServiceException(
                                "This payment method is already in use by another account"
                            )
                        # Already attached to this customer, just retrieve it
                        self.logger.info(
                            f"Payment method {payment_method_id} already attached to customer"
                        )
                    else:
                        # Not attached, so attach it
                        stripe_pm = stripe.PaymentMethod.attach(
                            payment_method_id, customer=customer.stripe_customer_id
                        )
                        self.logger.info(f"Attached payment method {payment_method_id} to customer")

                except stripe.error.CardError as e:
                    # Handle specific card errors
                    self.logger.error(f"Card error: {str(e)}")
                    error_message = str(e.user_message) if hasattr(e, "user_message") else str(e)
                    raise ServiceException(error_message)

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

        except ServiceException:
            # Re-raise service exceptions
            raise
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error saving payment method: {str(e)}")
            # Extract user-friendly message from Stripe error
            error_message = str(e.user_message) if hasattr(e, "user_message") else str(e)
            raise ServiceException(f"Failed to save payment method: {error_message}")
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
            payment_method_id: Payment method ID (can be database ID or Stripe ID)
            user_id: User's ID (for ownership verification)

        Returns:
            True if deleted successfully

        Raises:
            ServiceException: If deletion fails
        """
        try:
            with self.transaction():
                # Try to detach from Stripe if it's a Stripe payment method ID
                if payment_method_id.startswith("pm_"):
                    try:
                        stripe.PaymentMethod.detach(payment_method_id)
                        self.logger.info(f"Detached payment method {payment_method_id} from Stripe")
                    except stripe.StripeError as e:
                        # Log but don't fail - payment method might already be detached
                        self.logger.warning(
                            f"Could not detach payment method from Stripe: {str(e)}"
                        )

                # Delete from database (handles both database ID and Stripe ID)
                success = self.payment_repository.delete_payment_method(payment_method_id, user_id)

                if success:
                    self.logger.info(
                        f"Deleted payment method {payment_method_id} from database for user {user_id}"
                    )

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

            elif event_type.startswith("payout."):
                success = self._handle_payout_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("identity.verification_session."):
                success = self._handle_identity_webhook(event)
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
                settings.stripe_webhook_secret.get_secret_value()
                if settings.stripe_webhook_secret
                else None
            )
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            try:
                event = stripe.Webhook.construct_event(
                    payload.encode("utf-8") if isinstance(payload, str) else payload,
                    signature,
                    webhook_secret,
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
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id, new_status
                )

                if payment_record:
                    self.logger.info(f"Updated payment {payment_intent_id} status to {new_status}")

                    # Handle successful payments
                    if new_status == "succeeded":
                        self._handle_successful_payment(payment_record)

                    return True
                else:
                    self.logger.warning(
                        f"Payment record not found for webhook event {payment_intent_id}"
                    )
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

            self.logger.info(
                f"Processed successful payment for booking {payment_record.booking_id}"
            )

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

            elif event_type == "transfer.reversed":
                # Funds moved back to platform balance; record event for the related booking if possible
                try:
                    amount = transfer_data.get("amount")
                    # If we had stored mapping transfer->booking, we would look it up. Fallback: log only.
                    self.logger.info(f"Transfer {transfer_id} reversed (amount={amount})")
                except Exception:
                    pass
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
                try:
                    # Update payment record if possible
                    payment_intent_id = charge_data.get("payment_intent")
                    if payment_intent_id:
                        self.payment_repository.update_payment_status(payment_intent_id, "refunded")
                        booking_payment = self.payment_repository.get_payment_by_intent_id(
                            payment_intent_id
                        )
                        if booking_payment:
                            booking = self.booking_repository.get_by_id(booking_payment.booking_id)
                            if booking:
                                # Emit a domain-level log; event stream is handled by tasks/routes
                                self.logger.info(
                                    f"Marked booking {booking.id} payment as refunded for PI {payment_intent_id}"
                                )
                except Exception as e:
                    self.logger.error(f"Failed to process charge.refunded: {e}")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error handling charge webhook: {str(e)}")
            return False

    def _handle_payout_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe payout events for connected accounts."""
        try:
            event_type = event.get("type", "")
            payout = event.get("data", {}).get("object", {})
            payout_id = payout.get("id")
            amount = payout.get("amount")
            status = payout.get("status")
            arrival_date = payout.get("arrival_date")
            account_id = payout.get("destination") or payout.get("stripe_account")

            if event_type == "payout.created":
                self.logger.info(
                    f"Payout created: {payout_id} amount={amount} status={status} arrival={arrival_date}"
                )
                try:
                    # Resolve instructor_profile_id via connected account
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )  # type: ignore[attr-defined]
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status=status,
                                arrival_date=None,
                            )
                except Exception as e:  # best-effort analytics only
                    self.logger.warning(f"Failed to persist payout.created analytics: {e}")
                return True

            if event_type == "payout.paid":
                self.logger.info(
                    f"Payout paid: {payout_id} amount={amount} status={status} arrival={arrival_date}"
                )
                try:
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )  # type: ignore[attr-defined]
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status=status,
                                arrival_date=None,
                            )
                except Exception as e:
                    self.logger.warning(f"Failed to persist payout.paid analytics: {e}")
                return True

            if event_type == "payout.failed":
                failure_code = payout.get("failure_code")
                failure_message = payout.get("failure_message")
                self.logger.error(
                    f"Payout failed: {payout_id} amount={amount} code={failure_code} message={failure_message}"
                )
                # TODO: optionally notify instructor and disable instant payout UI until resolved
                try:
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )  # type: ignore[attr-defined]
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status="failed",
                                arrival_date=None,
                                failure_code=failure_code,
                                failure_message=failure_message,
                            )
                except Exception as e:
                    self.logger.warning(f"Failed to persist payout.failed analytics: {e}")
                return True

            # Unhandled payout event
            return False
        except Exception as e:
            self.logger.error(f"Error handling payout webhook: {str(e)}")
            return False

    def _handle_identity_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe Identity verification session events to persist verification status."""
        try:
            _evt_type = event.get("type", "")
            obj = event.get("data", {}).get("object", {})
            verification_status = obj.get("status")

            # Locate our user via metadata.user_id
            meta = obj.get("metadata") or {}
            user_id = meta.get("user_id")
            if not user_id:
                # Not our session; ignore
                return True

            # Find instructor profile by user_id
            profile = self.instructor_repository.get_by_user_id(user_id)
            if not profile:
                # User exists but no profile yet; ignore graciously
                return True

            # On verified, mark identity_verified_at and store session id
            if verification_status == "verified":
                try:
                    from datetime import datetime, timezone as _tz

                    self.instructor_repository.update(
                        profile.id,
                        identity_verified_at=datetime.now(_tz.utc),
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed updating identity verification on profile {profile.id}: {e}"
                    )
                    return False
                return True

            # For other terminal statuses, we can store the session id for audit
            if verification_status in {"requires_input", "canceled", "processing"}:
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    pass
                return True

            return True
        except Exception as e:
            self.logger.error(f"Error handling identity webhook: {str(e)}")
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
    def get_instructor_earnings(
        self, instructor_profile_id: str, start_date=None, end_date=None
    ) -> Dict[str, Any]:
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
            return self.payment_repository.get_instructor_earnings(
                instructor_profile_id, start_date, end_date
            )
        except Exception as e:
            self.logger.error(f"Error getting instructor earnings: {str(e)}")
            raise ServiceException(f"Failed to get instructor earnings: {str(e)}")
