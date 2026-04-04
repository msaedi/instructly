"""Payment analytics and reporting helpers."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking
from ...models.payment import PaymentIntent
from .mixin_base import PaymentRepositoryMixinBase


class PaymentAnalyticsMixin(PaymentRepositoryMixinBase):
    """Revenue, earnings, and history queries."""

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
            self.logger.error("Failed to get platform revenue stats: %s", str(e))
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
            self.logger.error("Failed to get instructor earnings: %s", str(e))
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
            self.logger.error("Failed to get user payment history: %s", str(e))
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
            self.logger.error("Failed to get instructor payment history: %s", str(e))
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
            self.logger.error("Failed to get instructor earnings export data: %s", str(e))
            raise RepositoryException(f"Failed to get instructor earnings export data: {str(e)}")
