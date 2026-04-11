"""User-oriented admin read queries."""

from __future__ import annotations

from datetime import date
from typing import Optional, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from ...models.instructor import InstructorProfile
from ...models.user import User
from .mixin_base import AdminOpsRepositoryMixinBase


class UserQueriesMixin(AdminOpsRepositoryMixinBase):
    """User-oriented admin read queries."""

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
            self.logger.error("Error getting first booking date: %s", str(e))
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
            self.logger.error("Error getting first booking dates: %s", str(e))
            raise RepositoryException(f"Failed to get first booking dates: {str(e)}")

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
            self.logger.error("Error getting user by email: %s", str(e))
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
            self.logger.error("Error getting user by phone: %s", str(e))
            raise RepositoryException(f"Failed to get user by phone: {str(e)}")

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
            self.logger.error("Error getting user by ID: %s", str(e))
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
            self.logger.error("Error counting student bookings: %s", str(e))
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
            self.logger.error("Error summing student spent: %s", str(e))
            raise RepositoryException(f"Failed to sum student spent: {str(e)}")

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
            self.logger.error("Error getting user with profile: %s", str(e))
            raise RepositoryException(f"Failed to get user with profile: {str(e)}")
