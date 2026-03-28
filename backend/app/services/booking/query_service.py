from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from ...core.enums import RoleName
from ...models.booking import Booking, BookingStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ...schemas.booking import PaymentSummary
    from ..cache_service import CacheServiceSyncAdapter
    from ..config_service import ConfigService

logger = logging.getLogger(__name__)


class BookingQueryMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        cache_service: Optional[CacheServiceSyncAdapter]
        config_service: ConfigService

    @BaseService.measure_operation("get_bookings_for_user")
    def get_bookings_for_user(
        self,
        user: User,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a user (student or instructor) with advanced filtering.

        Args:
            user: User to get bookings for
            status: Optional status filter
            upcoming_only: Only return future bookings
            exclude_future_confirmed: Exclude future confirmed bookings (for History tab)
            include_past_confirmed: Include past confirmed bookings (for BookAgain)
            limit: Optional result limit

        Returns:
            List of bookings
        """
        roles = cast(list[Any], getattr(user, "roles", []) or [])
        is_student = any(cast(str, getattr(role, "name", "")) == RoleName.STUDENT for role in roles)
        if is_student:
            student_bookings: List[Booking] = self.repository.get_student_bookings(
                student_id=user.id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                limit=limit,
            )
            return student_bookings
        else:  # INSTRUCTOR
            bookings: List[Booking] = self.repository.get_instructor_bookings(
                instructor_id=user.id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                limit=limit,
            )
            return bookings

    @BaseService.measure_operation("get_paginated_bookings_for_user")
    def get_paginated_bookings_for_user(
        self,
        *,
        user: User,
        page: int,
        per_page: int,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
    ) -> tuple[List[Booking], int]:
        """Get one page of bookings for a user along with the filtered total count."""
        roles = cast(list[Any], getattr(user, "roles", []) or [])
        is_student = any(cast(str, getattr(role, "name", "")) == RoleName.STUDENT for role in roles)
        if is_student:
            return self.repository.get_student_bookings_page(
                student_id=user.id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                page=page,
                per_page=per_page,
            )

        return self.repository.get_instructor_bookings_page(
            instructor_id=user.id,
            status=status,
            upcoming_only=upcoming_only,
            exclude_future_confirmed=exclude_future_confirmed,
            include_past_confirmed=include_past_confirmed,
            page=page,
            per_page=per_page,
        )

    @BaseService.measure_operation("get_booking_stats_for_instructor")
    def get_booking_stats_for_instructor(self, instructor_id: str) -> Dict[str, Any]:
        """
        Get booking statistics for an instructor with caching.

        CACHED: Results are cached for 5 minutes at the service level to reduce
        computation overhead for frequently accessed statistics.

        Args:
            instructor_id: Instructor user ID

        Returns:
            Dictionary of statistics
        """
        # Try to get from cache first if available
        if self.cache_service:
            cache_key = f"booking_stats:instructor:{instructor_id}"
            cached_stats = self.cache_service.get(cache_key)
            if cached_stats is not None:
                logger.debug("Cache hit for instructor %s booking stats", instructor_id)
                return cast(Dict[str, Any], cached_stats)

        # Calculate stats if not cached
        bookings = self.repository.get_instructor_bookings_for_stats(instructor_id)

        # Use UTC for date-based calculations
        instructor_today = datetime.now(timezone.utc).date()

        # Calculate stats
        total_bookings = len(bookings)
        upcoming_bookings = sum(1 for b in bookings if b.is_upcoming(instructor_today))
        completed_bookings = sum(1 for b in bookings if b.status == BookingStatus.COMPLETED)
        cancelled_bookings = sum(1 for b in bookings if b.status == BookingStatus.CANCELLED)

        # Calculate earnings (only completed bookings)
        total_earnings = sum(
            float(b.total_price) for b in bookings if b.status == BookingStatus.COMPLETED
        )

        # This month's earnings (in instructor's timezone)
        first_day_of_month = instructor_today.replace(day=1)
        this_month_earnings = sum(
            float(b.total_price)
            for b in bookings
            if b.status == BookingStatus.COMPLETED and b.booking_date >= first_day_of_month
        )

        stats = {
            "total_bookings": total_bookings,
            "upcoming_bookings": upcoming_bookings,
            "completed_bookings": completed_bookings,
            "cancelled_bookings": cancelled_bookings,
            "total_earnings": total_earnings,
            "this_month_earnings": this_month_earnings,
            "completion_rate": completed_bookings / total_bookings if total_bookings > 0 else 0,
            "cancellation_rate": cancelled_bookings / total_bookings if total_bookings > 0 else 0,
        }

        # Cache the results for 5 minutes
        if self.cache_service:
            self.cache_service.set(cache_key, stats, tier="hot")
            logger.debug("Cached stats for instructor %s", instructor_id)

        return stats

    @BaseService.measure_operation("get_booking_for_user")
    def get_booking_for_user(self, booking_id: str, user: User) -> Optional[Booking]:
        """
        Get a booking if the user has access to it.

        Defense-in-depth: filters by participant at the DB query level
        rather than fetching first and checking ownership afterward.

        Args:
            booking_id: ID of the booking
            user: User requesting the booking

        Returns:
            Booking if user has access, None otherwise
        """
        return self.repository.get_booking_for_participant(booking_id, user.id)

    @BaseService.measure_operation("get_booking_pricing_preview")
    def get_booking_pricing_preview(
        self,
        booking_id: str,
        current_user_id: str,
        applied_credit_cents: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Get pricing preview for a booking.

        Args:
            booking_id: Booking ULID
            current_user_id: Current user's ID (for access control)
            applied_credit_cents: Credits to apply

        Returns:
            Dict with pricing data or None if booking not found/access denied
        """
        from ...schemas.pricing_preview import PricingPreviewData
        from ..pricing_service import PricingService

        # Defense-in-depth: filter by participant at DB level (AUTHZ-VULN-01)
        booking = self.repository.get_booking_for_participant(booking_id, current_user_id)
        if not booking:
            return None

        pricing_service = PricingService(self.db)
        pricing_data: PricingPreviewData = pricing_service.compute_booking_pricing(
            booking_id,
            applied_credit_cents,
        )
        return dict(pricing_data)

    @BaseService.measure_operation("get_booking_with_payment_summary")
    def get_booking_with_payment_summary(
        self,
        booking_id: str,
        user: "User",
    ) -> Optional[tuple["Booking", Optional["PaymentSummary"]]]:
        """
        Get booking with payment summary for student.

        Args:
            booking_id: Booking ULID
            user: Current user (for access control and payment summary)

        Returns:
            Tuple of (booking, payment_summary) or None if not found
        """
        from ...repositories.factory import RepositoryFactory
        from ...repositories.review_repository import ReviewTipRepository
        from ..payment_summary_service import build_student_payment_summary

        booking = self.get_booking_for_user(booking_id, user)
        if not booking:
            return None

        payment_summary: Optional[PaymentSummary] = None
        if booking.student_id == user.id:
            pricing_config, _ = self.config_service.get_pricing_config()
            payment_repo = RepositoryFactory.create_payment_repository(self.db)
            tip_repo = ReviewTipRepository(self.db)
            payment_summary = build_student_payment_summary(
                booking=booking,
                pricing_config=pricing_config,
                payment_repo=payment_repo,
                review_tip_repo=tip_repo,
            )

        return (booking, payment_summary)
