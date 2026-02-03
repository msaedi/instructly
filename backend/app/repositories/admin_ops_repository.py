"""
Admin Operations Repository for MCP Admin Tools.

Provides data access methods for admin operations including:
- Booking summaries and listings
- Payment pipeline status
- Pending payouts
- User lookups and booking history
"""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Optional, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.booking import Booking, BookingStatus, PaymentStatus
from ..models.instructor import InstructorProfile
from ..models.payment import PaymentIntent
from ..models.service_catalog import InstructorService, ServiceCatalog
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AdminOpsRepository(BaseRepository[Booking]):
    """Repository for admin operations data access."""

    def __init__(self, db: Session) -> None:
        """Initialize with Booking model."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)

    # ==================== Booking Summary Queries ====================

    def get_bookings_in_date_range_with_service(
        self, start_date: date, end_date: date
    ) -> list[Booking]:
        """
        Get all bookings in a date range with instructor_service loaded.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of bookings with instructor_service relationship loaded
        """
        try:
            return cast(
                list[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                )
                .options(
                    joinedload(Booking.instructor_service)
                    .joinedload(InstructorService.catalog_entry)
                    .joinedload(ServiceCatalog.category)
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings in date range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings in date range: {str(e)}")

    def get_first_booking_date_for_student(self, student_id: str) -> Optional[date]:
        """
        Get the first booking date for a student.

        Args:
            student_id: The student's user ID

        Returns:
            The first booking date, or None if no bookings
        """
        try:
            result = (
                self.db.query(func.min(Booking.booking_date))
                .filter(Booking.student_id == student_id)
                .scalar()
            )
            return cast(Optional[date], result)
        except Exception as e:
            self.logger.error(f"Error getting first booking date: {str(e)}")
            raise RepositoryException(f"Failed to get first booking date: {str(e)}")

    def get_first_booking_dates_for_students(self, student_ids: list[str]) -> dict[str, date]:
        """
        Get the first booking date for multiple students in one query.

        Args:
            student_ids: List of student user IDs

        Returns:
            Mapping of student ID to their first booking date
        """
        if not student_ids:
            return {}

        try:
            results = (
                self.db.query(Booking.student_id, func.min(Booking.booking_date))
                .filter(Booking.student_id.in_(student_ids))
                .group_by(Booking.student_id)
                .all()
            )
            return {
                str(student_id): booking_date
                for student_id, booking_date in results
                if booking_date
            }
        except Exception as e:
            self.logger.error(f"Error getting first booking dates: {str(e)}")
            raise RepositoryException(f"Failed to get first booking dates: {str(e)}")

    # ==================== Recent Bookings Queries ====================

    def get_recent_bookings_with_details(
        self,
        cutoff: datetime,
        status: Optional[str],
        limit: int,
    ) -> list[Booking]:
        """
        Get recent bookings with student, instructor, and service loaded.

        Args:
            cutoff: Only include bookings created after this time
            status: Optional status filter (uppercase)
            limit: Maximum number of bookings to return

        Returns:
            List of bookings with relationships loaded
        """
        try:
            query = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                )
                .filter(Booking.created_at >= cutoff)
                .order_by(Booking.created_at.desc())
            )

            if status:
                query = query.filter(Booking.status == status.upper())

            return cast(list[Booking], query.limit(limit).all())
        except Exception as e:
            self.logger.error(f"Error getting recent bookings: {str(e)}")
            raise RepositoryException(f"Failed to get recent bookings: {str(e)}")

    # ==================== Payment Pipeline Queries ====================

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
                .filter(
                    Booking.payment_status == PaymentStatus.SCHEDULED.value,
                    Booking.booking_date >= from_date,
                    Booking.status == BookingStatus.CONFIRMED.value,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error(f"Error counting pending authorizations: {str(e)}")
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
            query = self.db.query(func.count(Booking.id)).filter(
                Booking.payment_status == payment_status
            )

            if booking_status:
                query = query.filter(Booking.status == booking_status)

            if updated_since:
                query = query.filter(Booking.updated_at >= updated_since)

            return cast(int, query.scalar() or 0)
        except Exception as e:
            self.logger.error(f"Error counting bookings by payment status: {str(e)}")
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
                .filter(
                    Booking.payment_status.in_(
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
            self.logger.error(f"Error counting failed payments: {str(e)}")
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
                .filter(
                    Booking.settlement_outcome.like("%refund%"),
                    Booking.updated_at >= updated_since,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error(f"Error counting refunded bookings: {str(e)}")
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
                .filter(
                    Booking.payment_status == PaymentStatus.SCHEDULED.value,
                    Booking.booking_start_utc <= cutoff_time,
                    Booking.status == BookingStatus.CONFIRMED.value,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error(f"Error counting overdue authorizations: {str(e)}")
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
                .filter(
                    Booking.payment_status == PaymentStatus.AUTHORIZED.value,
                    Booking.status == BookingStatus.COMPLETED.value,
                    Booking.completed_at < completed_before,
                )
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error(f"Error counting overdue captures: {str(e)}")
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
                .filter(
                    Booking.payment_status == PaymentStatus.SETTLED.value,
                    Booking.updated_at >= updated_since,
                )
                .scalar()
            )
            return float(result) if result else 0.0
        except Exception as e:
            self.logger.error(f"Error summing captured amounts: {str(e)}")
            raise RepositoryException(f"Failed to sum captured amounts: {str(e)}")

    # ==================== Pending Payouts Queries ====================

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
                .filter(
                    Booking.payment_status == PaymentStatus.AUTHORIZED.value,
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
            self.logger.error(f"Error getting instructors with pending payouts: {str(e)}")
            raise RepositoryException(f"Failed to get pending payouts: {str(e)}")

    # ==================== User Lookup Queries ====================

    def get_user_by_email_with_profile(self, email: str) -> Optional[User]:
        """
        Get user by email with instructor profile loaded.

        Args:
            email: User's email address

        Returns:
            User with instructor_profile loaded, or None
        """
        try:
            return cast(
                Optional[User],
                self.db.query(User)
                .filter(User.email == email)
                .options(
                    joinedload(User.instructor_profile).joinedload(
                        InstructorProfile.stripe_connected_account
                    )
                )
                .first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting user by email: {str(e)}")
            raise RepositoryException(f"Failed to get user by email: {str(e)}")

    def get_user_by_phone_with_profile(self, phone: str) -> Optional[User]:
        """
        Get user by phone with instructor profile loaded.

        Args:
            phone: User's phone number (various formats)

        Returns:
            User with instructor_profile loaded, or None
        """
        try:
            # Note: Takes last 10 digits for US phone matching.
            # Platform is NYC-only; adjust if expanding internationally.
            clean_phone = "".join(c for c in phone if c.isdigit())
            return cast(
                Optional[User],
                self.db.query(User)
                .filter(
                    or_(
                        User.phone == phone,
                        User.phone == clean_phone,
                        User.phone.like(f"%{clean_phone[-10:]}"),
                    )
                )
                .options(
                    joinedload(User.instructor_profile).joinedload(
                        InstructorProfile.stripe_connected_account
                    )
                )
                .first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting user by phone: {str(e)}")
            raise RepositoryException(f"Failed to get user by phone: {str(e)}")

    def sum_platform_fees(self, start_date: date, end_date: date) -> int:
        """Sum actual platform fees from captured bookings in date range."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(PaymentIntent.application_fee), 0))
                .join(Booking, Booking.id == PaymentIntent.booking_id)
                .filter(
                    Booking.payment_status == PaymentStatus.SETTLED.value,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                )
                .scalar()
            )
            return int(total or 0)
        except Exception as e:
            self.logger.error(f"Error summing platform fees: {str(e)}")
            raise RepositoryException(f"Failed to sum platform fees: {str(e)}")

    def get_user_by_id_with_profile(self, user_id: str) -> Optional[User]:
        """
        Get user by ID with instructor profile loaded.

        Args:
            user_id: User's ID

        Returns:
            User with instructor_profile loaded, or None
        """
        try:
            return cast(
                Optional[User],
                self.db.query(User)
                .filter(User.id == user_id)
                .options(
                    joinedload(User.instructor_profile).joinedload(
                        InstructorProfile.stripe_connected_account
                    )
                )
                .first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting user by ID: {str(e)}")
            raise RepositoryException(f"Failed to get user by ID: {str(e)}")

    def count_student_bookings(self, student_id: str) -> int:
        """
        Count total bookings for a student.

        Args:
            student_id: The student's user ID

        Returns:
            Count of bookings
        """
        try:
            return cast(
                int,
                self.db.query(func.count(Booking.id))
                .filter(Booking.student_id == student_id)
                .scalar()
                or 0,
            )
        except Exception as e:
            self.logger.error(f"Error counting student bookings: {str(e)}")
            raise RepositoryException(f"Failed to count student bookings: {str(e)}")

    def sum_student_spent(self, student_id: str) -> float:
        """
        Sum total amount spent by a student.

        Args:
            student_id: The student's user ID

        Returns:
            Total amount spent
        """
        try:
            result = (
                self.db.query(func.sum(Booking.total_price))
                .filter(
                    Booking.student_id == student_id,
                    Booking.status.in_(
                        [
                            BookingStatus.COMPLETED.value,
                            BookingStatus.CONFIRMED.value,
                        ]
                    ),
                )
                .scalar()
            )
            return float(result) if result else 0.0
        except Exception as e:
            self.logger.error(f"Error summing student spent: {str(e)}")
            raise RepositoryException(f"Failed to sum student spent: {str(e)}")

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
            self.logger.error(f"Error counting instructor completed lessons: {str(e)}")
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
            self.logger.error(f"Error summing instructor earned: {str(e)}")
            raise RepositoryException(f"Failed to sum instructor earned: {str(e)}")

    # ==================== User Booking History Queries ====================

    def get_user_with_instructor_profile(self, user_id: str) -> Optional[User]:
        """
        Get user with instructor profile for role determination.

        Args:
            user_id: The user's ID

        Returns:
            User with instructor_profile loaded, or None
        """
        try:
            return cast(
                Optional[User],
                self.db.query(User)
                .filter(User.id == user_id)
                .options(joinedload(User.instructor_profile))
                .first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting user with profile: {str(e)}")
            raise RepositoryException(f"Failed to get user with profile: {str(e)}")

    def get_user_booking_history(
        self, user_id: str, is_instructor: bool, limit: int
    ) -> list[Booking]:
        """
        Get booking history for a user.

        Args:
            user_id: The user's ID
            is_instructor: Whether the user is an instructor
            limit: Maximum number of bookings to return

        Returns:
            List of bookings with relationships loaded
        """
        try:
            query = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                )
                .order_by(Booking.booking_date.desc(), Booking.start_time.desc())
            )

            if is_instructor:
                query = query.filter(Booking.instructor_id == user_id)
            else:
                query = query.filter(Booking.student_id == user_id)

            return cast(list[Booking], query.limit(limit).all())
        except Exception as e:
            self.logger.error(f"Error getting user booking history: {str(e)}")
            raise RepositoryException(f"Failed to get booking history: {str(e)}")

    # ==================== Payment Timeline Queries ====================

    def get_booking_with_payment_intent(self, booking_id: str) -> Optional[Booking]:
        """Get a booking with payment intent loaded for payment timeline."""
        try:
            return cast(
                Optional[Booking],
                self.db.query(Booking)
                .options(joinedload(Booking.payment_intent))
                .filter(Booking.id == booking_id)
                .first(),
            )
        except Exception as e:
            self.logger.error(f"Error getting booking for payment timeline: {str(e)}")
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
                .options(joinedload(Booking.payment_intent))
                .filter(Booking.student_id == user_id)
                .filter(
                    or_(
                        Booking.booking_start_utc.between(start_time, end_time),
                        Booking.auth_scheduled_for.between(start_time, end_time),
                    )
                )
                .order_by(Booking.created_at.desc())
            )
            return cast(list[Booking], query.all())
        except Exception as e:
            self.logger.error(f"Error getting payment timeline bookings: {str(e)}")
            raise RepositoryException(f"Failed to get payment timeline bookings: {str(e)}")
