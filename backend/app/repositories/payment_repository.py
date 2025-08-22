"""
Payment Repository for InstaInstru Platform

Implements data access operations for Stripe payment integration,
including customer records, connected accounts, payment intents,
and payment methods.

This repository handles:
- Stripe customer record management
- Connected account management for instructors
- Payment intent tracking for bookings
- Payment method storage and management
- Platform revenue analytics
- Instructor earnings calculations
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import ulid
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.booking import Booking
from ..models.payment import (
    PaymentEvent,
    PaymentIntent,
    PaymentMethod,
    PlatformCredit,
    StripeConnectedAccount,
    StripeCustomer,
)
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class PaymentRepository(BaseRepository):
    """
    Repository for payment data access.

    Manages all payment-related database operations following
    the established repository pattern.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        # Use PaymentIntent as the primary model for BaseRepository
        super().__init__(db, PaymentIntent)
        self.logger = logging.getLogger(__name__)

    # ========== Customer Management ==========

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
            self.logger.error(f"Failed to create customer record: {str(e)}")
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
            return self.db.query(StripeCustomer).filter(StripeCustomer.user_id == user_id).first()
        except Exception as e:
            self.logger.error(f"Failed to get customer by user ID: {str(e)}")
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
            return self.db.query(StripeCustomer).filter(StripeCustomer.stripe_customer_id == stripe_customer_id).first()
        except Exception as e:
            self.logger.error(f"Failed to get customer by Stripe ID: {str(e)}")
            raise RepositoryException(f"Failed to get customer by Stripe ID: {str(e)}")

    # ========== Connected Account Management ==========

    def create_connected_account_record(
        self, instructor_profile_id: str, stripe_account_id: str, onboarding_completed: bool = False
    ) -> StripeConnectedAccount:
        """
        Create a new Stripe connected account record for an instructor.

        Args:
            instructor_profile_id: Instructor profile ID
            stripe_account_id: Stripe's connected account ID
            onboarding_completed: Whether onboarding is complete

        Returns:
            Created StripeConnectedAccount object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            account = StripeConnectedAccount(
                id=str(ulid.ULID()),
                instructor_profile_id=instructor_profile_id,
                stripe_account_id=stripe_account_id,
                onboarding_completed=onboarding_completed,
            )
            self.db.add(account)
            self.db.flush()
            return account
        except Exception as e:
            self.logger.error(f"Failed to create connected account: {str(e)}")
            raise RepositoryException(f"Failed to create connected account: {str(e)}")

    def get_connected_account_by_instructor_id(self, instructor_profile_id: str) -> Optional[StripeConnectedAccount]:
        """
        Get connected account by instructor profile ID.

        Args:
            instructor_profile_id: Instructor profile ID

        Returns:
            StripeConnectedAccount if found, None otherwise
        """
        try:
            return (
                self.db.query(StripeConnectedAccount)
                .filter(StripeConnectedAccount.instructor_profile_id == instructor_profile_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Failed to get connected account: {str(e)}")
            raise RepositoryException(f"Failed to get connected account: {str(e)}")

    def update_onboarding_status(self, stripe_account_id: str, completed: bool) -> Optional[StripeConnectedAccount]:
        """
        Update the onboarding status of a connected account.

        Args:
            stripe_account_id: Stripe's connected account ID
            completed: Whether onboarding is complete

        Returns:
            Updated StripeConnectedAccount if found, None otherwise
        """
        try:
            account = (
                self.db.query(StripeConnectedAccount)
                .filter(StripeConnectedAccount.stripe_account_id == stripe_account_id)
                .first()
            )
            if account:
                account.onboarding_completed = completed
                self.db.flush()
            return account
        except Exception as e:
            self.logger.error(f"Failed to update onboarding status: {str(e)}")
            raise RepositoryException(f"Failed to update onboarding status: {str(e)}")

    # ========== Payment Intent Management ==========

    def create_payment_record(
        self,
        booking_id: str,
        payment_intent_id: str,
        amount: int,
        application_fee: int,
        status: str = "requires_payment_method",
    ) -> PaymentIntent:
        """
        Create a new payment intent record for a booking.

        Args:
            booking_id: Booking ID
            payment_intent_id: Stripe's payment intent ID
            amount: Total amount in cents
            application_fee: Platform fee in cents
            status: Payment status (default: requires_payment_method)

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
            )
            self.db.add(payment)
            self.db.flush()
            return payment
        except Exception as e:
            self.logger.error(f"Failed to create payment record: {str(e)}")
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
                self.db.query(PaymentIntent).filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id).first()
            )
            if payment:
                payment.status = status
                self.db.flush()
            return payment
        except Exception as e:
            self.logger.error(f"Failed to update payment status: {str(e)}")
            raise RepositoryException(f"Failed to update payment status: {str(e)}")

    def get_payment_by_intent_id(self, payment_intent_id: str) -> Optional[PaymentIntent]:
        """
        Get payment record by Stripe payment intent ID.

        Args:
            payment_intent_id: Stripe's payment intent ID

        Returns:
            PaymentIntent if found, None otherwise
        """
        try:
            return (
                self.db.query(PaymentIntent).filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id).first()
            )
        except Exception as e:
            self.logger.error(f"Failed to get payment by intent ID: {str(e)}")
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
            return self.db.query(PaymentIntent).filter(PaymentIntent.booking_id == booking_id).first()
        except Exception as e:
            self.logger.error(f"Failed to get payment by booking ID: {str(e)}")
            raise RepositoryException(f"Failed to get payment by booking ID: {str(e)}")

    # ========== Payment Method Management ==========

    def save_payment_method(
        self, user_id: str, stripe_payment_method_id: str, last4: str, brand: str, is_default: bool = False
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
            # Check if payment method already exists
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
                # Update existing method
                if is_default:
                    # Unset other defaults first
                    self.db.query(PaymentMethod).filter(
                        and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                    ).update({"is_default": False})

                    # Set this one as default
                    existing_method.is_default = True
                    self.db.flush()

                return existing_method
            else:
                # Create new method
                # If setting as default, unset other defaults first
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
            self.logger.error(f"Failed to save payment method: {str(e)}")
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
            return (
                self.db.query(PaymentMethod)
                .filter(PaymentMethod.user_id == user_id)
                .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
                .all()
            )
        except Exception as e:
            self.logger.error(f"Failed to get payment methods: {str(e)}")
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
            return (
                self.db.query(PaymentMethod)
                .filter(and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True))
                .first()
            )
        except Exception as e:
            self.logger.error(f"Failed to get default payment method: {str(e)}")
            raise RepositoryException(f"Failed to get default payment method: {str(e)}")

    def get_payment_method_by_stripe_id(self, stripe_payment_method_id: str, user_id: str) -> Optional[PaymentMethod]:
        """
        Get a payment method by its Stripe ID.

        Args:
            stripe_payment_method_id: Stripe payment method ID
            user_id: User's ID

        Returns:
            PaymentMethod if found, None otherwise
        """
        try:
            return (
                self.db.query(PaymentMethod)
                .filter(
                    and_(
                        PaymentMethod.stripe_payment_method_id == stripe_payment_method_id,
                        PaymentMethod.user_id == user_id,
                    )
                )
                .first()
            )
        except Exception as e:
            self.logger.error(f"Failed to get payment method by Stripe ID: {str(e)}")
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
            # First unset any existing default
            self.db.query(PaymentMethod).filter(
                and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
            ).update({"is_default": False})

            # Set the new default
            result = (
                self.db.query(PaymentMethod)
                .filter(and_(PaymentMethod.id == payment_method_id, PaymentMethod.user_id == user_id))
                .update({"is_default": True})
            )
            self.db.flush()
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to set default payment method: {str(e)}")
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
            # First check if it's a Stripe payment method ID (starts with pm_)
            if payment_method_id.startswith("pm_"):
                result = (
                    self.db.query(PaymentMethod)
                    .filter(
                        and_(
                            PaymentMethod.stripe_payment_method_id == payment_method_id,
                            PaymentMethod.user_id == user_id,
                        )
                    )
                    .delete()
                )
            else:
                # Otherwise treat it as a database ID
                result = (
                    self.db.query(PaymentMethod)
                    .filter(and_(PaymentMethod.id == payment_method_id, PaymentMethod.user_id == user_id))
                    .delete()
                )
            self.db.flush()
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to delete payment method: {str(e)}")
            raise RepositoryException(f"Failed to delete payment method: {str(e)}")

    # ========== Analytics Methods ==========

    def get_platform_revenue_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get platform revenue statistics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with total_amount, total_fees, payment_count, average_transaction
        """
        try:
            query = self.db.query(
                func.sum(PaymentIntent.amount).label("total_amount"),
                func.sum(PaymentIntent.application_fee).label("total_fees"),
                func.count(PaymentIntent.id).label("payment_count"),
                func.avg(PaymentIntent.amount).label("average_transaction"),
            ).filter(PaymentIntent.status == "succeeded")

            if start_date:
                query = query.filter(PaymentIntent.created_at >= start_date)
            if end_date:
                query = query.filter(PaymentIntent.created_at <= end_date)

            result = query.first()

            return {
                "total_amount": result.total_amount or 0,
                "total_fees": result.total_fees or 0,
                "payment_count": result.payment_count or 0,
                "average_transaction": float(result.average_transaction or 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get platform revenue stats: {str(e)}")
            raise RepositoryException(f"Failed to get platform revenue stats: {str(e)}")

    def get_instructor_earnings(
        self, instructor_profile_id: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate instructor earnings after platform fees.

        Args:
            instructor_profile_id: Instructor profile ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with total_earned, total_fees, booking_count, average_earning
        """
        try:
            # Join PaymentIntent with Booking to filter by instructor
            query = (
                self.db.query(
                    func.sum(PaymentIntent.amount - PaymentIntent.application_fee).label("total_earned"),
                    func.sum(PaymentIntent.application_fee).label("total_fees"),
                    func.count(PaymentIntent.id).label("booking_count"),
                    func.avg(PaymentIntent.amount - PaymentIntent.application_fee).label("average_earning"),
                )
                .join(Booking, PaymentIntent.booking_id == Booking.id)
                .filter(
                    and_(
                        PaymentIntent.status == "succeeded",
                        Booking.instructor_id == instructor_profile_id,  # Assuming instructor_id maps to profile
                    )
                )
            )

            if start_date:
                query = query.filter(PaymentIntent.created_at >= start_date)
            if end_date:
                query = query.filter(PaymentIntent.created_at <= end_date)

            result = query.first()

            return {
                "total_earned": result.total_earned or 0,
                "total_fees": result.total_fees or 0,
                "booking_count": result.booking_count or 0,
                "average_earning": float(result.average_earning or 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get instructor earnings: {str(e)}")
            raise RepositoryException(f"Failed to get instructor earnings: {str(e)}")

    def get_user_payment_history(self, user_id: str, limit: int = 20, offset: int = 0) -> List[PaymentIntent]:
        """
        Get payment history for a user (as a student).

        Args:
            user_id: User ID to get payment history for
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of PaymentIntent objects with related booking data

        Raises:
            RepositoryException: If database operation fails
        """
        try:
            # Simple query - let the relationships load lazily within the session
            results = (
                self.db.query(PaymentIntent)
                .join(Booking, PaymentIntent.booking_id == Booking.id)
                .filter(and_(Booking.student_id == user_id, PaymentIntent.status.in_(["succeeded", "processing"])))
                .order_by(PaymentIntent.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            return results
        except Exception as e:
            self.logger.error(f"Failed to get user payment history: {str(e)}")
            raise RepositoryException(f"Failed to get user payment history: {str(e)}")

    # ========== Payment Events (Phase 1.1) ==========

    def create_payment_event(
        self, booking_id: str, event_type: str, event_data: Optional[Dict[str, Any]] = None
    ) -> PaymentEvent:
        """
        Create a payment event for tracking payment state changes.

        Args:
            booking_id: The booking this event relates to
            event_type: Type of event (e.g., 'auth_scheduled', 'auth_succeeded')
            event_data: Optional JSON data for the event

        Returns:
            Created PaymentEvent object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            event = PaymentEvent(
                id=str(ulid.ULID()),
                booking_id=booking_id,
                event_type=event_type,
                event_data=event_data or {},
            )
            self.db.add(event)
            self.db.flush()
            return event
        except Exception as e:
            self.logger.error(f"Failed to create payment event: {str(e)}")
            raise RepositoryException(f"Failed to create payment event: {str(e)}")

    def get_payment_events_for_booking(self, booking_id: str) -> List[PaymentEvent]:
        """
        Get all payment events for a booking.

        Args:
            booking_id: The booking ID

        Returns:
            List of PaymentEvent objects ordered by creation time

        Raises:
            RepositoryException: If query fails
        """
        try:
            return (
                self.db.query(PaymentEvent)
                .filter(PaymentEvent.booking_id == booking_id)
                .order_by(PaymentEvent.created_at.asc())
                .all()
            )
        except Exception as e:
            self.logger.error(f"Failed to get payment events: {str(e)}")
            raise RepositoryException(f"Failed to get payment events: {str(e)}")

    def get_latest_payment_event(self, booking_id: str, event_type: Optional[str] = None) -> Optional[PaymentEvent]:
        """
        Get the latest payment event for a booking.

        Args:
            booking_id: The booking ID
            event_type: Optional specific event type to filter

        Returns:
            Latest PaymentEvent or None

        Raises:
            RepositoryException: If query fails
        """
        try:
            query = self.db.query(PaymentEvent).filter(PaymentEvent.booking_id == booking_id)

            if event_type:
                query = query.filter(PaymentEvent.event_type == event_type)

            # Use ID for ordering since ULIDs are time-ordered and have better resolution
            return query.order_by(PaymentEvent.id.desc()).first()
        except Exception as e:
            self.logger.error(f"Failed to get latest payment event: {str(e)}")
            raise RepositoryException(f"Failed to get latest payment event: {str(e)}")

    # ========== Platform Credits (Phase 1.3) ==========

    def create_platform_credit(
        self,
        user_id: str,
        amount_cents: int,
        reason: str,
        source_booking_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> PlatformCredit:
        """
        Create a platform credit for a user.

        Args:
            user_id: User to credit
            amount_cents: Amount in cents
            reason: Reason for the credit
            source_booking_id: Optional booking that generated this credit
            expires_at: Optional expiration date

        Returns:
            Created PlatformCredit object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            credit = PlatformCredit(
                id=str(ulid.ULID()),
                user_id=user_id,
                amount_cents=amount_cents,
                reason=reason,
                source_booking_id=source_booking_id,
                expires_at=expires_at,
            )
            self.db.add(credit)
            self.db.flush()
            return credit
        except Exception as e:
            self.logger.error(f"Failed to create platform credit: {str(e)}")
            raise RepositoryException(f"Failed to create platform credit: {str(e)}")

    def get_available_credits(self, user_id: str) -> List[PlatformCredit]:
        """
        Get all available (unused, unexpired) credits for a user.

        Args:
            user_id: User ID

        Returns:
            List of available PlatformCredit objects

        Raises:
            RepositoryException: If query fails
        """
        try:
            now = datetime.now(timezone.utc)
            return (
                self.db.query(PlatformCredit)
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        PlatformCredit.used_at.is_(None),
                        # Either no expiration or not expired yet
                        (PlatformCredit.expires_at.is_(None) | (PlatformCredit.expires_at > now)),
                    )
                )
                .order_by(PlatformCredit.expires_at.asc().nullslast())  # Use expiring credits first
                .all()
            )
        except Exception as e:
            self.logger.error(f"Failed to get available credits: {str(e)}")
            raise RepositoryException(f"Failed to get available credits: {str(e)}")

    def get_total_available_credits(self, user_id: str) -> int:
        """
        Get total available credit amount for a user in cents.

        Args:
            user_id: User ID

        Returns:
            Total available credits in cents

        Raises:
            RepositoryException: If query fails
        """
        try:
            now = datetime.now(timezone.utc)
            result = (
                self.db.query(func.sum(PlatformCredit.amount_cents))
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        PlatformCredit.used_at.is_(None),
                        (PlatformCredit.expires_at.is_(None) | (PlatformCredit.expires_at > now)),
                    )
                )
                .scalar()
            )
            return result or 0
        except Exception as e:
            self.logger.error(f"Failed to get total available credits: {str(e)}")
            raise RepositoryException(f"Failed to get total available credits: {str(e)}")

    def mark_credit_used(self, credit_id: str, used_booking_id: str) -> PlatformCredit:
        """
        Mark a platform credit as used.

        Args:
            credit_id: Credit ID to mark as used
            used_booking_id: Booking where credit was used

        Returns:
            Updated PlatformCredit object

        Raises:
            RepositoryException: If update fails
        """
        try:
            credit = self.db.query(PlatformCredit).filter(PlatformCredit.id == credit_id).first()
            if not credit:
                raise RepositoryException(f"Platform credit {credit_id} not found")

            if credit.used_at:
                raise RepositoryException(f"Platform credit {credit_id} already used")

            credit.used_at = datetime.now(timezone.utc)
            credit.used_booking_id = used_booking_id
            self.db.flush()
            return credit
        except RepositoryException:
            raise
        except Exception as e:
            self.logger.error(f"Failed to mark credit as used: {str(e)}")
            raise RepositoryException(f"Failed to mark credit as used: {str(e)}")
