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

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
import ulid

from ..core.exceptions import RepositoryException
from ..models.booking import Booking
from ..models.booking_payment import BookingPayment
from ..models.payment import (
    InstructorPayoutEvent,
    PaymentEvent,
    PaymentIntent,
    PaymentMethod,
    PlatformCredit,
    StripeConnectedAccount,
    StripeCustomer,
)
from ..services.audit_service import AuditService, Status
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class PaymentRepository(BaseRepository[PaymentIntent]):
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
            customer = (
                self.db.query(StripeCustomer).filter(StripeCustomer.user_id == user_id).first()
            )
            return cast(Optional[StripeCustomer], customer)
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
            customer = (
                self.db.query(StripeCustomer)
                .filter(StripeCustomer.stripe_customer_id == stripe_customer_id)
                .first()
            )
            return cast(Optional[StripeCustomer], customer)
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
        except IntegrityError:
            # Let IntegrityError propagate for idempotency handling in service layer
            raise
        except Exception as e:
            self.logger.error(f"Failed to create connected account: {str(e)}")
            raise RepositoryException(f"Failed to create connected account: {str(e)}")

    def get_connected_account_by_instructor_id(
        self, instructor_profile_id: str
    ) -> Optional[StripeConnectedAccount]:
        """
        Get connected account by instructor profile ID.

        Args:
            instructor_profile_id: Instructor profile ID

        Returns:
            StripeConnectedAccount if found, None otherwise
        """
        try:
            account = (
                self.db.query(StripeConnectedAccount)
                .filter(StripeConnectedAccount.instructor_profile_id == instructor_profile_id)
                .first()
            )
            return cast(Optional[StripeConnectedAccount], account)
        except Exception as e:
            self.logger.error(f"Failed to get connected account: {str(e)}")
            raise RepositoryException(f"Failed to get connected account: {str(e)}")

    def update_onboarding_status(
        self, stripe_account_id: str, completed: bool
    ) -> Optional[StripeConnectedAccount]:
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
            return cast(Optional[StripeConnectedAccount], account)
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
                self.db.query(PaymentIntent)
                .filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id)
                .first()
            )
            if payment:
                payment.status = status
                self.db.flush()
            return cast(Optional[PaymentIntent], payment)
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
            payment = (
                self.db.query(PaymentIntent)
                .filter(PaymentIntent.stripe_payment_intent_id == payment_intent_id)
                .first()
            )
            return cast(Optional[PaymentIntent], payment)
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
            payment = (
                self.db.query(PaymentIntent).filter(PaymentIntent.booking_id == booking_id).first()
            )
            return cast(Optional[PaymentIntent], payment)
        except Exception as e:
            self.logger.error(f"Failed to get payment by booking ID: {str(e)}")
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
            self.logger.error(f"Failed to get payment intents for booking: {str(e)}")
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
            self.logger.error(f"Failed to get payment by booking prefix: {str(e)}")
            raise RepositoryException(f"Failed to get payment by booking prefix: {str(e)}")

    # ========== Payout Events (Analytics) ==========

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
            self.logger.error(f"Failed to record payout event: {str(e)}")
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
            self.logger.error(f"Failed to get instructor payout history: {str(e)}")
            raise RepositoryException(f"Failed to get instructor payout history: {str(e)}")

    # Helper to resolve Stripe account to instructor profile via connected account record
    def get_connected_account_by_stripe_id(
        self, stripe_account_id: str
    ) -> Optional[StripeConnectedAccount]:
        try:
            return cast(
                Optional[StripeConnectedAccount],
                (
                    self.db.query(StripeConnectedAccount)
                    .filter(StripeConnectedAccount.stripe_account_id == stripe_account_id)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error(f"Failed to get connected account by stripe id: {str(e)}")
            raise RepositoryException(f"Failed to get connected account by stripe id: {str(e)}")

    # ========== Payment Method Management ==========

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

                return cast(PaymentMethod, existing_method)
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
            method = (
                self.db.query(PaymentMethod)
                .filter(and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True))
                .first()
            )
            return cast(Optional[PaymentMethod], method)
        except Exception as e:
            self.logger.error(f"Failed to get default payment method: {str(e)}")
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
                # Otherwise treat it as a database ID
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
            if result is None:
                return {
                    "total_amount": 0,
                    "total_fees": 0,
                    "payment_count": 0,
                    "average_transaction": 0.0,
                }

            return {
                "total_amount": getattr(result, "total_amount", 0) or 0,
                "total_fees": getattr(result, "total_fees", 0) or 0,
                "payment_count": getattr(result, "payment_count", 0) or 0,
                "average_transaction": float(getattr(result, "average_transaction", 0) or 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get platform revenue stats: {str(e)}")
            raise RepositoryException(f"Failed to get platform revenue stats: {str(e)}")

    def get_instructor_earnings(
        self,
        instructor_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculate instructor earnings after platform fees.

        Args:
            instructor_id: Instructor user ID (Booking.instructor_id FK)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with total_earned, total_fees, booking_count, average_earning
        """
        try:
            # Join PaymentIntent with Booking to filter by instructor
            query = (
                self.db.query(
                    func.sum(PaymentIntent.amount - PaymentIntent.application_fee).label(
                        "total_earned"
                    ),
                    func.sum(PaymentIntent.application_fee).label("total_fees"),
                    func.count(PaymentIntent.id).label("booking_count"),
                    func.avg(PaymentIntent.amount - PaymentIntent.application_fee).label(
                        "average_earning"
                    ),
                )
                .join(Booking, PaymentIntent.booking_id == Booking.id)
                .filter(
                    and_(
                        PaymentIntent.status == "succeeded",
                        # Booking.instructor_id references users.id (the instructor's user_id)
                        Booking.instructor_id == instructor_id,
                    )
                )
            )

            if start_date:
                query = query.filter(PaymentIntent.created_at >= start_date)
            if end_date:
                query = query.filter(PaymentIntent.created_at <= end_date)

            result = query.first()
            if result is None:
                return {
                    "total_earned": 0,
                    "total_fees": 0,
                    "booking_count": 0,
                    "average_earning": 0.0,
                }

            return {
                "total_earned": getattr(result, "total_earned", 0) or 0,
                "total_fees": getattr(result, "total_fees", 0) or 0,
                "booking_count": getattr(result, "booking_count", 0) or 0,
                "average_earning": float(getattr(result, "average_earning", 0) or 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get instructor earnings: {str(e)}")
            raise RepositoryException(f"Failed to get instructor earnings: {str(e)}")

    def get_user_payment_history(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> List[PaymentIntent]:
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
            results = cast(
                List[PaymentIntent],
                (
                    self.db.query(PaymentIntent)
                    .join(Booking, PaymentIntent.booking_id == Booking.id)
                    .filter(
                        and_(
                            Booking.student_id == user_id,
                            PaymentIntent.status.in_(["succeeded", "processing"]),
                        )
                    )
                    .order_by(PaymentIntent.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                ),
            )

            return results
        except Exception as e:
            self.logger.error(f"Failed to get user payment history: {str(e)}")
            raise RepositoryException(f"Failed to get user payment history: {str(e)}")

    def get_instructor_payment_history(
        self,
        instructor_id: str,
        limit: int = 50,
    ) -> List[PaymentIntent]:
        """
        Get successful payments associated with a specific instructor's bookings.

        Args:
            instructor_id: Instructor's user ID
            limit: Maximum number of payment intents to return
        """
        try:
            query = (
                self.db.query(PaymentIntent)
                .join(Booking, PaymentIntent.booking_id == Booking.id)
                .options(
                    joinedload(PaymentIntent.booking).joinedload(Booking.student),
                    joinedload(PaymentIntent.booking).joinedload(Booking.instructor_service),
                )
                .filter(
                    PaymentIntent.status == "succeeded",
                    Booking.instructor_id == instructor_id,
                )
                .order_by(PaymentIntent.created_at.desc())
            )

            if limit:
                query = query.limit(limit)

            return cast(List[PaymentIntent], query.all())
        except Exception as e:
            self.logger.error(f"Failed to get instructor payment history: {str(e)}")
            raise RepositoryException(f"Failed to get instructor payment history: {str(e)}")

    def get_instructor_earnings_for_export(
        self,
        instructor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get earnings data for CSV export.

        Args:
            instructor_id: Instructor user ID
            start_date: Optional booking start date filter
            end_date: Optional booking end date filter
        """
        try:
            query = (
                self.db.query(PaymentIntent)
                .join(Booking, PaymentIntent.booking_id == Booking.id)
                .options(
                    joinedload(PaymentIntent.booking).joinedload(Booking.student),
                    joinedload(PaymentIntent.booking).joinedload(Booking.instructor_service),
                )
                .filter(
                    PaymentIntent.status == "succeeded",
                    Booking.instructor_id == instructor_id,
                )
                .order_by(Booking.booking_date.desc(), PaymentIntent.created_at.desc())
            )

            if start_date:
                query = query.filter(Booking.booking_date >= start_date)
            if end_date:
                query = query.filter(Booking.booking_date <= end_date)

            results: List[Dict[str, Any]] = []
            for payment in query.all():
                booking = payment.booking
                if not booking:
                    continue

                student = getattr(booking, "student", None)
                student_name = None
                if student:
                    last_initial = (student.last_name or "").strip()[:1]
                    student_name = (
                        f"{student.first_name} {last_initial}."
                        if last_initial
                        else student.first_name
                    )

                results.append(
                    {
                        "lesson_date": booking.booking_date,
                        "student_name": student_name,
                        "service_name": booking.service_name,
                        "duration_minutes": booking.duration_minutes,
                        "hourly_rate": booking.hourly_rate,
                        "payment_amount_cents": payment.amount,
                        "application_fee_cents": payment.application_fee,
                        "status": payment.status,
                        "payment_id": payment.stripe_payment_intent_id,
                    }
                )

            return results
        except Exception as e:
            self.logger.error(f"Failed to get instructor earnings export data: {str(e)}")
            raise RepositoryException(f"Failed to get instructor earnings export data: {str(e)}")

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
            # Ensure high-resolution timestamp to make ordering deterministic in tight loops
            try:
                event.created_at = datetime.now(timezone.utc)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.db.add(event)
            self.db.flush()
            try:
                audit_action = _payment_event_to_audit_action(event_type)
                if audit_action:
                    status: Status = "failed" if _event_indicates_failure(event_type) else "success"
                    AuditService(self.db).log(
                        action=audit_action,
                        resource_type="payment",
                        resource_id=booking_id,
                        actor_type="system",
                        actor_id="payment_tasks",
                        description=f"Payment event: {event_type}",
                        metadata={
                            "event_type": event_type,
                            "event_data": event_data or {},
                            "booking_id": booking_id,
                        },
                        status=status,
                    )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return event
        except Exception as e:
            self.logger.error(f"Failed to create payment event: {str(e)}")
            raise RepositoryException(f"Failed to create payment event: {str(e)}")

    def bulk_create_payment_events(self, events: List[Dict[str, Any]]) -> List[PaymentEvent]:
        """
        Bulk insert payment events for a booking.

        Args:
            events: List of dicts containing booking_id, event_type, and optional event_data

        Returns:
            List of PaymentEvent objects (IDs populated)
        """
        if not events:
            return []
        try:
            now = datetime.now(timezone.utc)
            payment_events = [
                PaymentEvent(
                    id=str(ulid.ULID()),
                    booking_id=event["booking_id"],
                    event_type=event["event_type"],
                    event_data=event.get("event_data", {}),
                    created_at=event.get("created_at", now),
                )
                for event in events
            ]
            self.db.bulk_save_objects(payment_events)
            self.db.flush()
            return payment_events
        except Exception as e:
            self.logger.error(f"Failed to bulk create payment events: {str(e)}")
            raise RepositoryException(f"Failed to bulk create payment events: {str(e)}")

    def get_payment_events_for_booking(
        self,
        booking_id: str,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[PaymentEvent]:
        """
        Get all payment events for a booking.

        Args:
            booking_id: The booking ID
            start_time: Optional start datetime (inclusive).
            end_time: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).

        Returns:
            List of PaymentEvent objects ordered by creation time

        Raises:
            RepositoryException: If query fails
        """
        try:
            query = (
                self.db.query(PaymentEvent)
                .options(joinedload(PaymentEvent.booking).joinedload(Booking.payment_intent))
                .filter(PaymentEvent.booking_id == booking_id)
            )
            if start_time:
                query = query.filter(PaymentEvent.created_at >= start_time)
            if end_time:
                query = query.filter(PaymentEvent.created_at <= end_time)
            query = query.order_by(PaymentEvent.created_at.asc())
            if limit is not None:
                query = query.limit(limit)
            return cast(
                List[PaymentEvent],
                query.all(),
            )
        except Exception as e:
            self.logger.error(f"Failed to get payment events: {str(e)}")
            raise RepositoryException(f"Failed to get payment events: {str(e)}")

    def get_payment_events_for_user(
        self,
        user_id: str,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[PaymentEvent]:
        """
        Get all payment events for a user (as a student).

        Args:
            user_id: The user's ID (student).
            start_time: Optional start datetime (inclusive).
            end_time: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).

        Returns:
            List of PaymentEvent objects ordered by creation time.

        Raises:
            RepositoryException: If query fails.
        """
        try:
            query = (
                self.db.query(PaymentEvent)
                .join(Booking, PaymentEvent.booking_id == Booking.id)
                .options(joinedload(PaymentEvent.booking).joinedload(Booking.payment_intent))
                .filter(Booking.student_id == user_id)
            )
            if start_time:
                query = query.filter(PaymentEvent.created_at >= start_time)
            if end_time:
                query = query.filter(PaymentEvent.created_at <= end_time)
            query = query.order_by(PaymentEvent.created_at.asc())
            if limit is not None:
                query = query.limit(limit)
            return cast(List[PaymentEvent], query.all())
        except Exception as e:
            self.logger.error(f"Failed to get payment events for user: {str(e)}")
            raise RepositoryException(f"Failed to get payment events for user: {str(e)}")

    def list_payment_events_by_types(
        self,
        event_types: Sequence[str],
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
        desc: bool = True,
    ) -> List[PaymentEvent]:
        """
        List payment events by event types with optional date filtering.

        Args:
            event_types: Event types to include.
            start: Optional start datetime (inclusive).
            end: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).
            offset: Rows to skip before returning results.
            desc: Order descending by created_at when True.

        Returns:
            List of PaymentEvent objects.
        """
        try:
            query = self.db.query(PaymentEvent).filter(PaymentEvent.event_type.in_(event_types))
            if start:
                query = query.filter(PaymentEvent.created_at >= start)
            if end:
                query = query.filter(PaymentEvent.created_at <= end)

            order_by = PaymentEvent.created_at.desc() if desc else PaymentEvent.created_at.asc()
            query = query.order_by(order_by)

            offset = max(0, offset)
            if offset:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(max(0, limit))

            return cast(List[PaymentEvent], query.all())
        except Exception as e:
            self.logger.error(f"Failed to list payment events by type: {str(e)}")
            raise RepositoryException(f"Failed to list payment events: {str(e)}")

    def count_payment_events_by_types(
        self,
        event_types: Sequence[str],
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """Count payment events by event types with optional date filtering."""
        try:
            query = (
                self.db.query(func.count())
                .select_from(PaymentEvent)
                .filter(PaymentEvent.event_type.in_(event_types))
            )
            if start:
                query = query.filter(PaymentEvent.created_at >= start)
            if end:
                query = query.filter(PaymentEvent.created_at <= end)
            return int(query.scalar() or 0)
        except Exception as e:
            self.logger.error(f"Failed to count payment events by type: {str(e)}")
            raise RepositoryException(f"Failed to count payment events: {str(e)}")

    def sum_application_fee_for_booking_date_range(self, start: date, end: date) -> int:
        """Sum application fees for bookings in the given date range."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(PaymentIntent.application_fee), 0))
                .join(Booking, Booking.id == PaymentIntent.booking_id)
                .filter(Booking.booking_date >= start, Booking.booking_date <= end)
                .scalar()
            )
            return int(total or 0)
        except Exception as e:
            self.logger.error(f"Failed to sum application fee: {str(e)}")
            raise RepositoryException(f"Failed to sum application fee: {str(e)}")

    def get_latest_payment_event(
        self, booking_id: str, event_type: Optional[str] = None
    ) -> Optional[PaymentEvent]:
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

            # Order by timestamp primarily; tie-breaker by ULID to ensure stability
            return cast(
                Optional[PaymentEvent],
                (query.order_by(PaymentEvent.created_at.desc(), PaymentEvent.id.desc())).first(),
            )
        except Exception as e:
            self.logger.error(f"Failed to get latest payment event: {str(e)}")
            raise RepositoryException(f"Failed to get latest payment event: {str(e)}")

    # ========== Platform Credits (Phase 1.3) ==========

    def get_applied_credit_cents_for_booking(self, booking_id: str) -> int:
        """Return total cents of credits applied to the booking so far."""

        try:
            try:
                bp = (
                    self.db.query(BookingPayment)
                    .filter(BookingPayment.booking_id == booking_id)
                    .first()
                )
                if bp and bp.credits_reserved_cents:
                    return max(0, int(bp.credits_reserved_cents or 0))
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            credit_use_events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credit_used",
                )
                .all()
            )

            total_used = 0
            for event in credit_use_events:
                data = event.event_data or {}
                try:
                    total_used += max(0, int(data.get("used_cents") or 0))
                except (TypeError, ValueError):
                    continue

            if total_used > 0:
                return total_used

            # Legacy fallback: aggregated credits_applied events (pre "credit_used" granularity)
            legacy_events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credits_applied",
                )
                .all()
            )

            legacy_total = 0
            for event in legacy_events:
                data = event.event_data or {}
                try:
                    legacy_total += max(0, int(data.get("applied_cents") or 0))
                except (TypeError, ValueError):
                    continue

            return legacy_total
        except Exception as exc:
            self.logger.error(
                "Failed to load applied credits for booking %s: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to compute applied credits")

    def create_platform_credit(
        self,
        user_id: str,
        amount_cents: int,
        reason: str,
        source_type: Optional[str] = None,
        source_booking_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        original_expires_at: Optional[datetime] = None,
        status: Optional[str] = None,
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
            # Default expiry: 1 year if not provided
            if expires_at is None:
                expires_at = datetime.now(timezone.utc) + timedelta(days=365)
            if original_expires_at is None:
                original_expires_at = expires_at
            credit = PlatformCredit(
                id=str(ulid.ULID()),
                user_id=user_id,
                amount_cents=amount_cents,
                reason=reason,
                source_type=source_type or reason or "legacy",
                source_booking_id=source_booking_id,
                expires_at=expires_at,
                original_expires_at=original_expires_at,
                status=status or "available",
                reserved_amount_cents=0,
            )
            self.db.add(credit)
            self.db.flush()
            return credit
        except Exception as e:
            self.logger.error(f"Failed to create platform credit: {str(e)}")
            raise RepositoryException(f"Failed to create platform credit: {str(e)}")

    def apply_credits_for_booking(
        self, *, user_id: str, booking_id: str, amount_cents: int
    ) -> Dict[str, Any]:
        """
        Reserve available platform credits to offset an amount for a booking.

        - Uses FIFO ordering (oldest credits first)
        - Reserves credits; if a credit exceeds remaining amount, creates a remainder credit
        - Emits per-credit and summary payment events

        Returns a dict with applied amount and credit IDs used.
        """
        try:
            if amount_cents <= 0:
                return {"applied_cents": 0, "used_credit_ids": [], "remainder_credit_id": None}

            available = self.get_available_credits(user_id)
            remaining = amount_cents
            applied_total = 0
            used_ids: List[str] = []
            remainder_credit_id: Optional[str] = None
            now = datetime.now(timezone.utc)

            for credit in available:
                if remaining <= 0:
                    break

                original_credit_cents = int(credit.amount_cents or 0)
                reserve_amount = min(original_credit_cents, remaining)
                if reserve_amount <= 0:
                    continue

                # Create remainder credit if needed
                local_remainder_id: Optional[str] = None
                if original_credit_cents > reserve_amount:
                    remainder = PlatformCredit(
                        id=str(ulid.ULID()),
                        user_id=user_id,
                        amount_cents=original_credit_cents - reserve_amount,
                        reason=f"Remainder of {credit.id}",
                        source_type=getattr(credit, "source_type", "legacy"),
                        source_booking_id=credit.source_booking_id,
                        expires_at=credit.expires_at,
                        status="available",
                        reserved_amount_cents=0,
                    )
                    self.db.add(remainder)
                    self.db.flush()
                    remainder_credit_id = remainder.id
                    local_remainder_id = remainder.id
                    credit.amount_cents = reserve_amount
                else:
                    local_remainder_id = None

                credit.reserved_amount_cents = reserve_amount
                credit.reserved_for_booking_id = booking_id
                credit.reserved_at = now
                credit.status = "reserved"
                self.db.flush()
                used_ids.append(credit.id)

                # Per-credit reservation event
                self.create_payment_event(
                    booking_id=booking_id,
                    event_type="credit_reserved",
                    event_data={
                        "credit_id": credit.id,
                        "reserved_cents": reserve_amount,
                        "original_credit_cents": original_credit_cents,
                        "remainder_credit_id": local_remainder_id,
                    },
                )

                applied_total += reserve_amount
                remaining -= reserve_amount

            if applied_total > 0:
                self.create_payment_event(
                    booking_id=booking_id,
                    event_type="credits_applied",
                    event_data={
                        "applied_cents": applied_total,
                        "requested_cents": amount_cents,
                        "used_credit_ids": used_ids,
                        "remaining_to_charge_cents": max(amount_cents - applied_total, 0),
                    },
                )

            return {
                "applied_cents": applied_total,
                "used_credit_ids": used_ids,
                "remainder_credit_id": remainder_credit_id,
            }
        except Exception as e:
            self.logger.error(f"Failed to apply credits for booking {booking_id}: {str(e)}")
            raise RepositoryException(f"Failed to apply credits: {str(e)}")

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
            return cast(
                List[PlatformCredit],
                (
                    self.db.query(PlatformCredit)
                    .filter(
                        and_(
                            PlatformCredit.user_id == user_id,
                            (
                                PlatformCredit.status.is_(None)
                                | (PlatformCredit.status == "available")
                            ),
                            # Either no expiration or not expired yet
                            (
                                PlatformCredit.expires_at.is_(None)
                                | (PlatformCredit.expires_at > now)
                            ),
                        )
                    )
                    .order_by(
                        PlatformCredit.expires_at.asc().nullslast(),
                        PlatformCredit.created_at.asc(),
                        PlatformCredit.id.asc(),
                    )
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Failed to get available credits: {str(e)}")
            raise RepositoryException(f"Failed to get available credits: {str(e)}")

    def delete_platform_credit(self, credit_id: str) -> None:
        """Delete a platform credit by id."""

        try:
            credit = (
                self.db.query(PlatformCredit).filter(PlatformCredit.id == credit_id).one_or_none()
            )
            if not credit:
                return
            self.db.delete(credit)
            self.db.flush()
        except Exception as exc:
            self.logger.error("Failed to delete platform credit %s: %s", credit_id, str(exc))
            raise RepositoryException("Failed to delete platform credit")

    def get_credits_issued_for_source(self, booking_id: str) -> List[PlatformCredit]:
        """Return credits generated from the given booking (source)."""

        try:
            credits = (
                self.db.query(PlatformCredit)
                .filter(PlatformCredit.source_booking_id == booking_id)
                .order_by(PlatformCredit.created_at.asc())
                .all()
            )
            return cast(List[PlatformCredit], credits)
        except Exception as exc:
            self.logger.error(
                "Failed to load credits for source booking %s: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to load source credits")

    def get_credits_used_by_booking(self, booking_id: str) -> List[Tuple[str, int]]:
        """Return list of (credit_id, used_amount_cents) for credits applied to a booking."""

        try:
            used: List[Tuple[str, int]] = []
            credits = (
                self.db.query(PlatformCredit)
                .filter(PlatformCredit.used_booking_id == booking_id)
                .all()
            )

            for credit in credits:
                try:
                    amount_int = int(credit.amount_cents or 0)
                except (TypeError, ValueError):
                    continue
                if amount_int <= 0:
                    continue
                used.append((str(credit.id), amount_int))

            if used:
                return used

            events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credit_used",
                )
                .all()
            )

            for event in events:
                data = event.event_data or {}
                credit_id = data.get("credit_id")
                used_amount = data.get("used_cents")
                if not credit_id:
                    continue
                if used_amount is None:
                    continue
                try:
                    amount_int = int(used_amount)
                except (TypeError, ValueError):
                    continue
                if amount_int <= 0:
                    continue
                used.append((str(credit_id), amount_int))
            return used
        except Exception as exc:
            self.logger.error("Failed to load credits used by booking %s: %s", booking_id, str(exc))
            raise RepositoryException("Failed to load used credits for booking")

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
                        (PlatformCredit.status.is_(None) | (PlatformCredit.status == "available")),
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
            credit_opt = cast(
                Optional[PlatformCredit],
                self.db.query(PlatformCredit).filter(PlatformCredit.id == credit_id).first(),
            )
            if credit_opt is None:
                raise RepositoryException(f"Platform credit {credit_id} not found")

            if credit_opt.used_at:
                raise RepositoryException(f"Platform credit {credit_id} already used")

            credit = credit_opt
            now = datetime.now(timezone.utc)
            credit.used_at = now
            credit.used_booking_id = used_booking_id
            credit.forfeited_at = now
            credit.status = "forfeited"
            credit.reserved_amount_cents = 0
            self.db.flush()
            return credit
        except RepositoryException:
            raise
        except Exception as e:
            self.logger.error(f"Failed to mark credit as used: {str(e)}")
            raise RepositoryException(f"Failed to mark credit as used: {str(e)}")


def _payment_event_to_audit_action(event_type: str) -> str | None:
    normalized = (event_type or "").lower()
    if "refund" in normalized:
        return "payment.refund"
    if "capture" in normalized:
        return "payment.capture"
    if "auth" in normalized or "authorize" in normalized:
        return "payment.authorize"
    return None


def _event_indicates_failure(event_type: str) -> bool:
    normalized = (event_type or "").lower()
    return any(token in normalized for token in ("failed", "failure", "error", "denied"))
