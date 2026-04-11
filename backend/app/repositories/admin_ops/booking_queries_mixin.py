"""Booking-oriented admin read queries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, cast

from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking
from ...models.service_catalog import InstructorService, ServiceCatalog
from ...models.subcategory import ServiceSubcategory
from .mixin_base import AdminOpsRepositoryMixinBase


class BookingQueriesMixin(AdminOpsRepositoryMixinBase):
    """Booking-oriented admin read queries."""

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
                    .joinedload(ServiceCatalog.subcategory)
                    .joinedload(ServiceSubcategory.category)
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings in date range: %s", str(e))
            raise RepositoryException(f"Failed to get bookings in date range: {str(e)}")

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
            self.logger.error("Error getting recent bookings: %s", str(e))
            raise RepositoryException(f"Failed to get recent bookings: {str(e)}")

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
            self.logger.error("Error getting user booking history: %s", str(e))
            raise RepositoryException(f"Failed to get booking history: {str(e)}")
