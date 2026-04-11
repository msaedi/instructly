"""Payout-oriented admin read queries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.booking_payment import BookingPayment
from ...models.instructor import InstructorProfile
from ...models.user import User
from .mixin_base import AdminOpsRepositoryMixinBase


class PayoutQueriesMixin(AdminOpsRepositoryMixinBase):
    """Payout-oriented admin read queries."""

    def get_instructors_with_pending_payouts(
        self, limit: int
    ) -> list[tuple[User, float, int, Optional[datetime]]]:
        """
        Get instructors with pending payouts.

        Args:
            limit: Maximum number of instructors to return

        Returns:
            List of tuples: (User, pending_amount, lesson_count, oldest_date)
        """
        try:
            subquery = (
                self.db.query(
                    Booking.instructor_id,
                    func.sum(Booking.total_price).label("pending_amount"),
                    func.count(Booking.id).label("lesson_count"),
                    func.min(Booking.completed_at).label("oldest_date"),
                )
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                    Booking.status == BookingStatus.COMPLETED.value,
                )
                .group_by(Booking.instructor_id)
                .order_by(func.sum(Booking.total_price).desc())
                .limit(limit)
                .subquery()
            )

            results = (
                self.db.query(
                    User,
                    subquery.c.pending_amount,
                    subquery.c.lesson_count,
                    subquery.c.oldest_date,
                )
                .join(subquery, User.id == subquery.c.instructor_id)
                .options(
                    joinedload(User.instructor_profile).joinedload(
                        InstructorProfile.stripe_connected_account
                    )
                )
                .all()
            )

            return cast(
                list[tuple[User, float, int, Optional[datetime]]],
                results,
            )
        except Exception as e:
            self.logger.error("Error getting instructors with pending payouts: %s", str(e))
            raise RepositoryException(f"Failed to get pending payouts: {str(e)}")

    def count_instructor_completed_lessons(self, instructor_id: str) -> int:
        """
        Count completed lessons for an instructor.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            Count of completed lessons
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.COMPLETED.value,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error("Error counting instructor completed lessons: %s", str(e))
            raise RepositoryException(f"Failed to count completed lessons: {str(e)}")

    def sum_instructor_earned(self, instructor_id: str) -> float:
        """
        Sum total earned by an instructor.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            Total amount earned (before platform fee deduction)
        """
        try:
            result = (
                self.db.query(func.sum(Booking.total_price))
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.COMPLETED.value,
                )
                .scalar()
            )
            return float(result) if result else 0.0
        except Exception as e:
            self.logger.error("Error summing instructor earned: %s", str(e))
            raise RepositoryException(f"Failed to sum instructor earned: {str(e)}")
