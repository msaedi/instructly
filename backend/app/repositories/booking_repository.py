# backend/app/repositories/booking_repository.py
"""
Booking Repository for InstaInstru Platform

UPDATED FOR CLEAN ARCHITECTURE: Complete separation from availability slots.
ENHANCED WITH CACHING: Repository-level caching for frequently accessed data.

Implements all data access operations for booking management,
with new methods for time-based queries without slot references.

This repository handles:
- Booking CRUD operations
- User-specific booking queries (student/instructor)
- Time-based conflict checking
- Booking statistics and counting
- Date-based queries
- Booking relationships eager loading
- Caching for performance optimization
"""

import logging
from datetime import date, datetime, time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from ..core.enums import RoleName
from ..core.exceptions import NotFoundException, RepositoryException
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository
from .cached_repository_mixin import CachedRepositoryMixin

logger = logging.getLogger(__name__)


class BookingRepository(BaseRepository[Booking], CachedRepositoryMixin):
    """
    Repository for booking data access with caching support.

    Implements all booking queries using self-contained booking data
    without any reference to availability slots.
    """

    def __init__(self, db: Session, cache_service=None):
        """Initialize with Booking model and optional cache service."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)
        self.init_cache(cache_service)

    # Time-based Booking Queries (NEW)

    def get_bookings_by_time_range(
        self,
        instructor_id: int,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings within a time range for conflict checking.

        Uses booking's own time fields for filtering.

        Args:
            instructor_id: The instructor ID
            booking_date: The date to check
            start_time: Range start time
            end_time: Range end time
            exclude_booking_id: Optional booking to exclude

        Returns:
            List of bookings in the time range
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                # Any overlap with the time range
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting bookings by time range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings by time: {str(e)}")

    def check_time_conflict(
        self,
        instructor_id: int,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> bool:
        """
        Check if a time range has any booking conflicts.

        Efficient boolean check for quick validation.

        Args:
            instructor_id: The instructor ID
            booking_date: The date to check
            start_time: Start time to check
            end_time: End time to check
            exclude_booking_id: Optional booking to exclude

        Returns:
            True if there are conflicts, False otherwise
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                # Time overlap check
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return query.first() is not None

        except Exception as e:
            self.logger.error(f"Error checking time conflict: {str(e)}")
            raise RepositoryException(f"Failed to check conflict: {str(e)}")

    def check_student_time_conflict(
        self,
        student_id: int,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> List[Booking]:
        """
        Check if a student has any conflicting bookings at the given time.

        Args:
            student_id: The student ID
            booking_date: The date to check
            start_time: Start time to check
            end_time: End time to check
            exclude_booking_id: Optional booking to exclude (for updates)

        Returns:
            List of conflicting bookings (empty if no conflicts)
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.student_id == student_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                # Time overlap check: start_time < other_end_time AND end_time > other_start_time
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error checking student time conflict: {str(e)}")
            raise RepositoryException(f"Failed to check student conflict: {str(e)}")

    def get_instructor_bookings_for_date(
        self,
        instructor_id: int,
        target_date: date,
        status_filter: Optional[List[BookingStatus]] = None,
    ) -> List[Booking]:
        """
        Get all bookings for an instructor on a specific date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to query
            status_filter: Optional list of statuses to filter

        Returns:
            List of bookings for the date
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
            )

            if status_filter:
                query = query.filter(Booking.status.in_(status_filter))

            return query.order_by(Booking.start_time).all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for date: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    def get_bookings_for_week(
        self,
        instructor_id: int,
        week_dates: List[date],
        status_filter: Optional[List[BookingStatus]] = None,
    ) -> List[Booking]:
        """
        Get all bookings for an instructor for a week.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            status_filter: Optional status filter

        Returns:
            List of bookings for the week
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date.in_(week_dates),
            )

            if status_filter:
                query = query.filter(Booking.status.in_(status_filter))

            return query.order_by(Booking.booking_date, Booking.start_time).all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for week: {str(e)}")
            raise RepositoryException(f"Failed to get weekly bookings: {str(e)}")

    # Opportunity Finding (MOVED from SlotManagerRepository)

    def find_booking_opportunities(
        self,
        available_slots: List[Dict[str, any]],
        instructor_id: int,
        target_date: date,
        duration_minutes: int,
    ) -> List[Dict[str, any]]:
        """
        Find booking opportunities within available time slots.

        This method analyzes available slots and existing bookings
        to find free time periods suitable for new bookings.

        Args:
            available_slots: List of available time slots
            instructor_id: The instructor ID
            target_date: The date to check
            duration_minutes: Required duration for booking

        Returns:
            List of booking opportunities
        """
        try:
            # Get all bookings for the date
            existing_bookings = self.get_bookings_by_time_range(
                instructor_id=instructor_id,
                booking_date=target_date,
                start_time=time(0, 0),  # Start of day
                end_time=time(23, 59),  # End of day
            )

            opportunities = []

            # Process each available slot
            for slot in available_slots:
                slot_start = slot["start_time"]
                slot_end = slot["end_time"]

                # Find opportunities within this slot
                current_time = slot_start

                while current_time < slot_end:
                    # Calculate potential end time
                    from datetime import datetime, timedelta

                    start_dt = datetime.combine(date.today(), current_time)
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    potential_end = end_dt.time()

                    # Check if this exceeds slot boundary
                    if potential_end > slot_end:
                        break

                    # Check for conflicts
                    has_conflict = False
                    for booking in existing_bookings:
                        if current_time < booking.end_time and potential_end > booking.start_time:
                            # Conflict found, skip to after this booking
                            current_time = booking.end_time
                            has_conflict = True
                            break

                    if not has_conflict:
                        opportunities.append(
                            {
                                "start_time": current_time.isoformat(),
                                "end_time": potential_end.isoformat(),
                                "duration_minutes": duration_minutes,
                                "available": True,
                            }
                        )
                        current_time = potential_end

            return opportunities

        except Exception as e:
            self.logger.error(f"Error finding opportunities: {str(e)}")
            raise RepositoryException(f"Failed to find opportunities: {str(e)}")

    # User Booking Queries (unchanged)

    def get_student_bookings(
        self,
        student_id: int,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a specific student with advanced filtering.

        CACHED: Results are cached for 5 minutes to reduce database load.

        Args:
            student_id: The student's user ID
            status: Optional status filter
            upcoming_only: Only return future bookings
            exclude_future_confirmed: Exclude future confirmed bookings (for History tab)
            include_past_confirmed: Include past confirmed bookings (for BookAgain)
            limit: Optional result limit

        Returns:
            List of student's bookings
        """
        # Try to get from cache first
        if self.cache_service and self._cache_enabled:
            cache_key = self._generate_cache_key(
                "get_student_bookings",
                student_id,
                status,
                upcoming_only,
                exclude_future_confirmed,
                include_past_confirmed,
                limit,
            )
            cached_result = self.cache_service.get(cache_key)
            if cached_result is not None:
                self.logger.debug(f"Cache hit for get_student_bookings: {cache_key}")
                return cached_result

        try:
            query = (
                self.db.query(Booking)
                .options(joinedload(Booking.instructor), joinedload(Booking.instructor_service))
                .filter(Booking.student_id == student_id)
            )

            # Handle status filter
            if status:
                query = query.filter(Booking.status == status)

            # Handle upcoming_only filter
            if upcoming_only:
                query = query.filter(Booking.booking_date >= date.today(), Booking.status == BookingStatus.CONFIRMED)

            # Handle exclude_future_confirmed (for History tab - past bookings + cancelled)
            elif exclude_future_confirmed:
                # Include: past bookings (any status) + future cancelled/no-show bookings
                # Exclude: future confirmed bookings
                from sqlalchemy import and_, or_

                query = query.filter(
                    or_(
                        # Past bookings (any status)
                        Booking.booking_date < date.today(),
                        # Future bookings that are NOT confirmed
                        and_(
                            Booking.booking_date >= date.today(),
                            Booking.status.in_([BookingStatus.CANCELLED, BookingStatus.NO_SHOW]),
                        ),
                    )
                )

            # Handle include_past_confirmed (for BookAgain - only completed past bookings)
            elif include_past_confirmed:
                # Only past bookings with COMPLETED status
                query = query.filter(Booking.booking_date < date.today(), Booking.status == BookingStatus.COMPLETED)

            query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            result = query.all()

            # Cache the result
            if self.cache_service and self._cache_enabled:
                cache_key = self._generate_cache_key(
                    "get_student_bookings",
                    student_id,
                    status,
                    upcoming_only,
                    exclude_future_confirmed,
                    include_past_confirmed,
                    limit,
                )
                self.cache_service.set(cache_key, result, tier="hot")
                self.logger.debug(f"Cached result for get_student_bookings: {cache_key}")

            return result

        except Exception as e:
            self.logger.error(f"Error getting student bookings: {str(e)}")
            raise RepositoryException(f"Failed to get student bookings: {str(e)}")

    def get_instructor_bookings(
        self,
        instructor_id: int,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a specific instructor with advanced filtering.

        Args:
            instructor_id: The instructor's user ID
            status: Optional status filter
            upcoming_only: Only return future bookings
            exclude_future_confirmed: Exclude future confirmed bookings (for History tab)
            include_past_confirmed: Include past confirmed bookings (for BookAgain)
            limit: Optional result limit

        Returns:
            List of instructor's bookings
        """
        try:
            query = (
                self.db.query(Booking)
                .options(joinedload(Booking.student), joinedload(Booking.instructor_service))
                .filter(Booking.instructor_id == instructor_id)
            )

            # Handle status filter
            if status:
                query = query.filter(Booking.status == status)

            # Handle upcoming_only filter
            if upcoming_only:
                query = query.filter(Booking.booking_date >= date.today(), Booking.status == BookingStatus.CONFIRMED)

            # Handle exclude_future_confirmed (for History tab - past bookings + cancelled)
            elif exclude_future_confirmed:
                # Include: past bookings (any status) + future cancelled/no-show bookings
                # Exclude: future confirmed bookings
                from sqlalchemy import and_, or_

                query = query.filter(
                    or_(
                        # Past bookings (any status)
                        Booking.booking_date < date.today(),
                        # Future bookings that are NOT confirmed
                        and_(
                            Booking.booking_date >= date.today(),
                            Booking.status.in_([BookingStatus.CANCELLED, BookingStatus.NO_SHOW]),
                        ),
                    )
                )

            # Handle include_past_confirmed (for BookAgain - only completed past bookings)
            elif include_past_confirmed:
                # Only past bookings with COMPLETED status
                query = query.filter(Booking.booking_date < date.today(), Booking.status == BookingStatus.COMPLETED)

            # For upcoming lessons, show nearest first (ASC). For history, show latest first (DESC)
            if upcoming_only:
                query = query.order_by(Booking.booking_date.asc(), Booking.start_time.asc())
            else:
                query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting instructor bookings: {str(e)}")
            raise RepositoryException(f"Failed to get instructor bookings: {str(e)}")

    def get_instructor_future_bookings(
        self,
        instructor_id: int,
        from_date: Optional[date] = None,
        exclude_cancelled: bool = True,
    ) -> List[Booking]:
        """
        Get all future bookings for an instructor, excluding cancelled ones by default.

        Used for checking if an instructor can change their account status.

        Args:
            instructor_id: The instructor's user ID
            from_date: The date to start from (defaults to today)
            exclude_cancelled: Whether to exclude cancelled bookings (default True)

        Returns:
            List of future bookings for the instructor
        """
        try:
            if from_date is None:
                from_date = date.today()

            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id, Booking.booking_date >= from_date
            )

            if exclude_cancelled:
                query = query.filter(Booking.status != BookingStatus.CANCELLED)

            return query.order_by(Booking.booking_date, Booking.start_time).all()

        except Exception as e:
            self.logger.error(f"Error getting instructor future bookings: {str(e)}")
            raise RepositoryException(f"Failed to get future bookings: {str(e)}")

    def get_bookings_for_service_catalog(
        self,
        service_catalog_id: int,
        from_date: date,
        to_date: Optional[date] = None,
    ) -> List[Booking]:
        """
        Get all bookings for a specific service catalog type within a date range.

        This is used for analytics calculations to aggregate bookings across
        all instructors offering the same service type.

        Args:
            service_catalog_id: The service catalog ID
            from_date: Start date for the query
            to_date: Optional end date (defaults to today)

        Returns:
            List of bookings for this service type
        """
        try:
            from ..models.service_catalog import InstructorService

            query = (
                self.db.query(Booking)
                .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
                .filter(InstructorService.service_catalog_id == service_catalog_id, Booking.booking_date >= from_date)
            )

            if to_date:
                query = query.filter(Booking.booking_date <= to_date)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for service catalog: {str(e)}")
            raise RepositoryException(f"Failed to get service catalog bookings: {str(e)}")

    # Detailed Booking Queries (unchanged)

    def get_booking_with_details(self, booking_id: int) -> Optional[Booking]:
        """
        Get a booking with all relationships loaded.

        Loads all related objects for complete booking details.

        Args:
            booking_id: The booking ID

        Returns:
            The booking with all relationships, or None if not found
        """
        try:
            return (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                    joinedload(Booking.cancelled_by),
                )
                .filter(Booking.id == booking_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting booking details: {str(e)}")
            raise RepositoryException(f"Failed to get booking details: {str(e)}")

    # Statistics Queries (unchanged)

    def get_instructor_bookings_for_stats(self, instructor_id: int) -> List[Booking]:
        """
        Get all bookings for an instructor for statistics calculation.

        Returns minimal data needed for stats without heavy relationships.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of bookings for statistics
        """
        try:
            return self.db.query(Booking).filter(Booking.instructor_id == instructor_id).all()
        except Exception as e:
            self.logger.error(f"Error getting instructor stats: {str(e)}")
            raise RepositoryException(f"Failed to get instructor statistics: {str(e)}")

    # Date-based Queries (simplified)

    def get_bookings_for_date(
        self, booking_date: date, status: Optional[BookingStatus] = None, with_relationships: bool = False
    ) -> List[Booking]:
        """
        Get bookings for a specific date (system-wide).

        Used for reminder emails and daily views.

        Args:
            booking_date: The date to query
            status: Optional status filter
            with_relationships: Whether to eager load relationships

        Returns:
            List of bookings for the date
        """
        try:
            query = self.db.query(Booking).filter(Booking.booking_date == booking_date)

            if status:
                query = query.filter(Booking.status == status)

            if with_relationships:
                query = query.options(joinedload(Booking.student), joinedload(Booking.instructor))

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for date: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for date: {str(e)}")

    # Counting Queries (unchanged)

    def count_bookings_by_status(self, user_id: int, user_role: str) -> Dict[str, int]:
        """
        Count bookings grouped by status for a user.

        OPTIMIZED: Uses SQL aggregation instead of Python-side counting.

        Args:
            user_id: The user's ID
            user_role: The user's role (student/instructor)

        Returns:
            Dictionary with status as key and count as value
        """
        try:
            from sqlalchemy import case, func

            # Build the filter based on role
            if user_role == RoleName.STUDENT:
                filter_condition = Booking.student_id == user_id
            elif user_role == RoleName.INSTRUCTOR:
                filter_condition = Booking.instructor_id == user_id
            else:
                return {status.value: 0 for status in BookingStatus}

            # Use SQL aggregation to count by status in a single query
            status_counts_query = (
                self.db.query(Booking.status, func.count(Booking.id).label("count"))
                .filter(filter_condition)
                .group_by(Booking.status)
                .all()
            )

            # Convert to dictionary with all statuses (even those with 0 count)
            status_counts = {status.value: 0 for status in BookingStatus}
            for row in status_counts_query:
                if row.status:  # Handle potential None values
                    # row.status is already a string from the database
                    status_counts[row.status] = row.count

            return status_counts

        except Exception as e:
            self.logger.error(f"Error counting bookings by status: {str(e)}")
            raise RepositoryException(f"Failed to count bookings by status: {str(e)}")

    # Status Management Methods

    def complete_booking(self, booking_id: int) -> Booking:
        """
        Mark booking as completed with timestamp.

        Args:
            booking_id: ID of the booking to complete

        Returns:
            Updated booking instance

        Raises:
            NotFoundException: If booking not found
            RepositoryException: If update fails
        """
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.status = BookingStatus.COMPLETED
            booking.completed_at = datetime.utcnow()

            self.db.flush()
            self.logger.info(f"Marked booking {booking_id} as completed")

            # Invalidate caches for this booking and related entities
            self.invalidate_entity_cache(booking_id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error(f"Error completing booking {booking_id}: {str(e)}")
            raise RepositoryException(f"Failed to complete booking: {str(e)}")

    def cancel_booking(self, booking_id: int, cancelled_by_id: int, reason: Optional[str] = None) -> Booking:
        """
        Cancel booking with audit trail.

        Args:
            booking_id: ID of the booking to cancel
            cancelled_by_id: ID of the user cancelling the booking
            reason: Optional cancellation reason

        Returns:
            Updated booking instance

        Raises:
            NotFoundException: If booking not found
            RepositoryException: If update fails
        """
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.utcnow()
            booking.cancelled_by_id = cancelled_by_id
            booking.cancellation_reason = reason

            self.db.flush()
            self.logger.info(f"Cancelled booking {booking_id} by user {cancelled_by_id}")

            # Invalidate caches for this booking and related entities
            self.invalidate_entity_cache(booking_id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error(f"Error cancelling booking {booking_id}: {str(e)}")
            raise RepositoryException(f"Failed to cancel booking: {str(e)}")

    def mark_no_show(self, booking_id: int) -> Booking:
        """
        Mark booking as no-show.

        Args:
            booking_id: ID of the booking to mark as no-show

        Returns:
            Updated booking instance

        Raises:
            NotFoundException: If booking not found
            RepositoryException: If update fails
        """
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.status = BookingStatus.NO_SHOW

            self.db.flush()
            self.logger.info(f"Marked booking {booking_id} as no-show")

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error(f"Error marking booking {booking_id} as no-show: {str(e)}")
            raise RepositoryException(f"Failed to mark booking as no-show: {str(e)}")

    # Helper method overrides

    def _apply_eager_loading(self, query):
        """
        Override to include common relationships by default.

        For get_by_id and other single entity queries.
        """
        return query.options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.instructor_service),
        )

    # Additional Repository Methods (from BaseRepository)
    # The following are inherited from BaseRepository:
    # - create(**kwargs) -> Booking
    # - update(id: int, **kwargs) -> Optional[Booking]
    # - delete(id: int) -> bool
    # - get_by_id(id: int, load_relationships: bool = True) -> Optional[Booking]
    # - exists(**kwargs) -> bool
    # - count(**kwargs) -> int
    # - find_by(**kwargs) -> List[Booking]
    # - find_one_by(**kwargs) -> Optional[Booking]
    # - bulk_create(entities: List[Dict]) -> List[Booking]
    # - bulk_update(updates: List[Dict]) -> int
