"""Payment-oriented admin read queries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.booking_payment import BookingPayment
from ...models.payment import PaymentIntent
from .mixin_base import AdminOpsRepositoryMixinBase


class PaymentQueriesMixin(AdminOpsRepositoryMixinBase):
    """Payment-oriented admin read queries."""

    def count_pending_authorizations(self, from_date: date) -> int:
        """
        Count pending authorizations (scheduled payments for future bookings).

        Args:
            from_date: Only count bookings from this date onwards

        Returns:
            Count of pending authorizations
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.SCHEDULED.value,
                    Booking.booking_date >= from_date,
                    Booking.status == BookingStatus.CONFIRMED.value,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting pending authorizations: %s", str(e))
            raise RepositoryException(f"Failed to count pending authorizations: {str(e)}")

    def count_bookings_by_payment_and_status(
        self,
        payment_status: str,
        booking_status: Optional[str] = None,
        updated_since: Optional[datetime] = None,
    ) -> int:
        """
        Count bookings by payment status and optional booking status.

        Args:
            payment_status: The payment status to filter by
            booking_status: Optional booking status to filter by
            updated_since: Optional cutoff for updated_at

        Returns:
            Count of matching bookings
        """
        try:
            query = (
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(BookingPayment.payment_status == payment_status)
            )

            if booking_status:
                query = query.filter(Booking.status == booking_status)

            if updated_since:
                query = query.filter(Booking.updated_at >= updated_since)

            return cast(int, query.scalar() or 0)
        except Exception as e:
            self.logger.error("Error counting bookings by payment status: %s", str(e))
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    def count_failed_payments(self, updated_since: datetime) -> int:
        """
        Count bookings with failed payment status.

        Args:
            updated_since: Only count failures since this time

        Returns:
            Count of failed payments
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status.in_(
                        [
                            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
                            PaymentStatus.MANUAL_REVIEW.value,
                        ]
                    ),
                    Booking.updated_at >= updated_since,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting failed payments: %s", str(e))
            raise RepositoryException(f"Failed to count failed payments: {str(e)}")

    def count_refunded_bookings(self, updated_since: datetime) -> int:
        """
        Count bookings that were refunded.

        Args:
            updated_since: Only count refunds since this time

        Returns:
            Count of refunded bookings
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.settlement_outcome.like("%refund%"),
                    Booking.updated_at >= updated_since,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting refunded bookings: %s", str(e))
            raise RepositoryException(f"Failed to count refunded bookings: {str(e)}")

    def count_overdue_authorizations(self, cutoff_time: datetime) -> int:
        """
        Count bookings that are overdue for authorization.

        Args:
            cutoff_time: Booking start must be before this time

        Returns:
            Count of overdue authorizations
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.SCHEDULED.value,
                    Booking.booking_start_utc <= cutoff_time,
                    Booking.status == BookingStatus.CONFIRMED.value,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting overdue authorizations: %s", str(e))
            raise RepositoryException(f"Failed to count overdue authorizations: {str(e)}")

    def count_overdue_captures(self, completed_before: datetime) -> int:
        """
        Count bookings that are overdue for capture.

        Args:
            completed_before: Only count bookings completed before this time

        Returns:
            Count of overdue captures
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                    Booking.status == BookingStatus.COMPLETED.value,
                    Booking.completed_at < completed_before,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting overdue captures: %s", str(e))
            raise RepositoryException(f"Failed to count overdue captures: {str(e)}")

    def sum_captured_amount(self, updated_since: datetime) -> float:
        """
        Sum total price of captured bookings.

        Args:
            updated_since: Only sum captures since this time

        Returns:
            Sum of captured amounts
        """
        try:
            result = (
                self.db.query(func.sum(Booking.total_price))
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.SETTLED.value,
                    Booking.updated_at >= updated_since,
                )
                .scalar()
            )
            return float(result) if result else 0.0
        except Exception as e:
            self.logger.error("Error summing captured amounts: %s", str(e))
            raise RepositoryException(f"Failed to sum captured amounts: {str(e)}")

    def sum_platform_fees(self, start_date: date, end_date: date) -> int:
        """Sum actual platform fees from captured bookings in date range."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(PaymentIntent.application_fee), 0))
                .join(Booking, Booking.id == PaymentIntent.booking_id)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.SETTLED.value,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                )
                .scalar()
            )
            return int(total or 0)
        except Exception as e:
            self.logger.error("Error summing platform fees: %s", str(e))
            raise RepositoryException(f"Failed to sum platform fees: {str(e)}")

    def get_booking_with_payment_intent(self, booking_id: str) -> Optional[Booking]:
        """Get a booking with payment intent loaded for payment timeline."""
        try:
            return cast(
                Optional[Booking],
                self.db.query(Booking)
                .options(
                    joinedload(Booking.payment_intent),
                    joinedload(Booking.payment_detail),
                )
                .filter(Booking.id == booking_id)
                .first(),
            )
        except Exception as e:
            self.logger.error("Error getting booking for payment timeline: %s", str(e))
            raise RepositoryException(f"Failed to get booking for payment timeline: {str(e)}")

    def get_user_bookings_for_payment_timeline(
        self,
        *,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Booking]:
        """Get bookings for a user with payment intent loaded in a time window."""
        try:
            query = (
                self.db.query(Booking)
                .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(
                    joinedload(Booking.payment_intent),
                    joinedload(Booking.payment_detail),
                )
                .filter(Booking.student_id == user_id)
                .filter(
                    or_(
                        Booking.booking_start_utc.between(start_time, end_time),
                        BookingPayment.auth_scheduled_for.between(start_time, end_time),
                    )
                )
                .order_by(Booking.created_at.desc())
            )
            return cast(list[Booking], query.all())
        except Exception as e:
            self.logger.error("Error getting payment timeline bookings: %s", str(e))
            raise RepositoryException(f"Failed to get payment timeline bookings: {str(e)}")
