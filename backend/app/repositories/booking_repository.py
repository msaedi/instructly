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

from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session, joinedload

from ..core.enums import RoleName
from ..core.exceptions import NotFoundException, RepositoryException
from ..core.timezone_utils import get_user_now_by_id, get_user_today_by_id
from ..models.booking import Booking, BookingStatus
from ..models.user import User
from .base_repository import BaseRepository
from .cached_repository_mixin import CachedRepositoryMixin, cached_method

logger = logging.getLogger(__name__)


class BookingRepository(BaseRepository[Booking], CachedRepositoryMixin):
    """
    Repository for booking data access with caching support.

    Implements all booking queries using self-contained booking data
    without any reference to availability slots.
    """

    def __init__(self, db: Session, cache_service: Optional[Any] = None):
        """Initialize with Booking model and optional cache service."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)
        self.init_cache(cache_service)

    def create(self, **kwargs: Any) -> Booking:
        """Create a booking, exposing integrity errors for conflict handling."""
        try:
            return super().create(**kwargs)
        except RepositoryException as exc:
            if isinstance(exc.__cause__, IntegrityError):
                raise exc.__cause__
            raise

    # Time-based Booking Queries (NEW)

    def get_bookings_by_time_range(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
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
                Booking.status.in_(
                    [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
                ),
                # Any overlap with the time range
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error getting bookings by time range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings by time: {str(e)}")

    def check_time_conflict(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
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
                Booking.status.in_(
                    [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
                ),
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
        student_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
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
                Booking.status.in_(
                    [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
                ),
                # Time overlap check: start_time < other_end_time AND end_time > other_start_time
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error checking student time conflict: {str(e)}")
            raise RepositoryException(f"Failed to check student conflict: {str(e)}")

    def get_instructor_bookings_for_date(
        self,
        instructor_id: str,
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

            return cast(List[Booking], query.order_by(Booking.start_time).all())

        except Exception as e:
            self.logger.error(f"Error getting bookings for date: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    def get_bookings_for_week(
        self,
        instructor_id: str,
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

            return cast(
                List[Booking], query.order_by(Booking.booking_date, Booking.start_time).all()
            )

        except Exception as e:
            self.logger.error(f"Error getting bookings for week: {str(e)}")
            raise RepositoryException(f"Failed to get weekly bookings: {str(e)}")

    def get_distinct_booking_dates(self, instructor_id: str) -> List[date]:
        """Return distinct booking dates for the instructor."""
        try:
            rows = (
                self.db.query(Booking.booking_date)
                .filter(Booking.instructor_id == instructor_id, Booking.booking_date.isnot(None))
                .distinct()
                .all()
            )
            return [cast(date, row[0]) for row in rows if row[0] is not None]
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "Error loading distinct booking dates for instructor %s: %s", instructor_id, exc
            )
            raise RepositoryException("Failed to load booking dates") from exc

    def count_instructor_completed_last_30d(self, instructor_id: str) -> int:
        """Return the number of completed bookings for an instructor in the last 30 days."""

        try:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(days=30)
            query = (
                self.db.query(func.count(Booking.id))
                .filter(Booking.instructor_id == instructor_id)
                .filter(Booking.status == BookingStatus.COMPLETED)
                .filter(Booking.completed_at.isnot(None))
                .filter(Booking.completed_at >= window_start)
            )
            result = query.scalar()
            return int(result or 0)
        except Exception as exc:
            self.logger.error("Error counting instructor completed bookings last 30d: %s", str(exc))
            raise RepositoryException("Failed to count instructor completions")

    def get_instructor_last_completed_at(self, instructor_id: str) -> Optional[datetime]:
        """Return the timestamp of the most recent completed booking for an instructor."""

        try:
            query = (
                self.db.query(func.max(Booking.completed_at))
                .filter(Booking.instructor_id == instructor_id)
                .filter(Booking.status == BookingStatus.COMPLETED)
            )
            result = cast(Optional[datetime], query.scalar())
            return result
        except Exception as exc:
            self.logger.error(
                "Error fetching instructor last completed booking timestamp: %s", str(exc)
            )
            raise RepositoryException("Failed to fetch last completion timestamp")

    def get_with_pricing_context(self, booking_id: str) -> Optional[Booking]:
        """Return booking hydrated with relationships required for pricing calculations."""

        try:
            return cast(
                Optional[Booking],
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor).joinedload(User.instructor_profile),
                    joinedload(Booking.instructor_service),
                )
                .filter(Booking.id == booking_id)
                .first(),
            )
        except Exception as exc:
            self.logger.error(
                "Error fetching booking %s with pricing context: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to load booking pricing context")

    # Opportunity Finding (MOVED from SlotManagerRepository)

    def find_booking_opportunities(
        self,
        available_slots: List[Dict[str, Any]],
        instructor_id: str,
        target_date: date,
        duration_minutes: int,
    ) -> List[Dict[str, Any]]:
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

            opportunities: List[Dict[str, Any]] = []

            # Process each available slot
            for slot in available_slots:
                slot_start = cast(time, slot["start_time"])  # time
                slot_end = cast(time, slot["end_time"])  # time

                # Find opportunities within this slot
                current_time = slot_start

                while current_time < slot_end:
                    # Calculate potential end time
                    from datetime import datetime, timedelta

                    start_dt = datetime.combine(target_date, current_time)
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

    @cached_method(tier="hot")
    def get_student_bookings(
        self,
        student_id: str,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a specific student with advanced filtering.

        CACHED: Results are cached for 5 minutes with proper serialization.

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
        try:
            query = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                )
                .filter(Booking.student_id == student_id)
            )

            # Handle status filter
            status_filter = status
            if include_past_confirmed and status == BookingStatus.COMPLETED:
                status_filter = None

            if status_filter:
                query = query.filter(Booking.status == status_filter)

            # Handle upcoming_only filter
            if upcoming_only:
                # Get user's current datetime in their timezone
                user_now = get_user_now_by_id(student_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                # Filter for truly upcoming bookings (considering both date and time)
                query = query.filter(
                    or_(
                        Booking.booking_date > today,  # Future dates
                        and_(
                            Booking.booking_date == today,  # Today
                            Booking.start_time > current_time.isoformat(),  # But after current time
                        ),
                    ),
                    Booking.status == BookingStatus.CONFIRMED,
                )

            # Handle exclude_future_confirmed (for History tab - past bookings + cancelled)
            elif exclude_future_confirmed:
                # Include: past bookings (any status) + future cancelled/no-show bookings
                # Exclude: future confirmed bookings
                # Get user's current datetime in their timezone
                user_now = get_user_now_by_id(student_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                query = query.filter(
                    or_(
                        # Past dates (any status)
                        Booking.booking_date < today,
                        # Today's past bookings (any status)
                        and_(
                            Booking.booking_date == today,
                            Booking.start_time <= current_time.isoformat(),
                        ),
                        # Future bookings that are NOT confirmed (cancelled/no-show)
                        and_(
                            or_(
                                Booking.booking_date > today,
                                and_(
                                    Booking.booking_date == today,
                                    Booking.start_time > current_time.isoformat(),
                                ),
                            ),
                            Booking.status.in_([BookingStatus.CANCELLED, BookingStatus.NO_SHOW]),
                            # Hide reschedule-driven cancellations from student History
                            Booking.cancellation_reason != "Rescheduled",
                        ),
                    )
                )

            # Handle include_past_confirmed (for BookAgain - only completed past bookings)
            elif include_past_confirmed:
                # Only past bookings with COMPLETED status
                # Get student's current datetime in their timezone
                user_now = get_user_now_by_id(student_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                query = query.filter(
                    or_(
                        Booking.booking_date < today,
                        and_(
                            Booking.booking_date == today,
                            Booking.start_time <= current_time.isoformat(),
                        ),
                    ),
                    Booking.status == BookingStatus.COMPLETED,
                )

            # For upcoming lessons, show nearest first (ASC). For history, show latest first (DESC)
            if upcoming_only:
                query = query.order_by(Booking.booking_date.asc(), Booking.start_time.asc())
            else:
                query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error getting student bookings: {str(e)}")
            raise RepositoryException(f"Failed to get student bookings: {str(e)}")

    def get_bookings_by_student_and_instructor(
        self,
        student_id: str,
        instructor_id: str,
    ) -> List[Booking]:
        """
        Get all bookings for a specific student-instructor pair.

        Used for SSE routing - when a conversation has multiple bookings,
        we need all booking IDs so the frontend can match any of them.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID

        Returns:
            List of bookings for this pair (may be empty)
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.student_id == student_id,
                    Booking.instructor_id == instructor_id,
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings by pair: {str(e)}")
            raise RepositoryException(f"Failed to get bookings by pair: {str(e)}")

    def get_instructor_bookings(
        self,
        instructor_id: str,
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
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                )
                .filter(Booking.instructor_id == instructor_id)
            )

            include_past_confirmed_mode = (
                include_past_confirmed and status == BookingStatus.COMPLETED
            )
            status_filter = None if include_past_confirmed_mode else status

            if include_past_confirmed_mode:
                self.logger.debug(
                    "Including chronologically past confirmed lessons for instructor",
                    extra={
                        "instructor_id": instructor_id,
                        "upcoming_only": upcoming_only,
                        "exclude_future_confirmed": exclude_future_confirmed,
                        "status": getattr(status, "value", status),
                    },
                )

            # Handle upcoming_only filter
            if upcoming_only:
                # Get instructor's current datetime in their timezone
                user_now = get_user_now_by_id(instructor_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                # Filter for truly upcoming bookings (considering both date and time)
                query = query.filter(
                    or_(
                        Booking.booking_date > today,  # Future dates
                        and_(
                            Booking.booking_date == today,  # Today
                            Booking.start_time > current_time.isoformat(),  # But after current time
                        ),
                    ),
                    Booking.status == BookingStatus.CONFIRMED,
                )

            # Handle exclude_future_confirmed (for History tab - past bookings + cancelled)
            elif exclude_future_confirmed:
                # Include: past bookings (any status) + future cancelled/no-show bookings
                # Exclude: future confirmed bookings
                # Get instructor's current datetime in their timezone
                user_now = get_user_now_by_id(instructor_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                query = query.filter(
                    or_(
                        # Past dates (any status)
                        Booking.booking_date < today,
                        # Today's past bookings (any status)
                        and_(
                            Booking.booking_date == today,
                            Booking.start_time <= current_time.isoformat(),
                        ),
                        # Future bookings that are NOT confirmed (cancelled/no-show)
                        and_(
                            or_(
                                Booking.booking_date > today,
                                and_(
                                    Booking.booking_date == today,
                                    Booking.start_time > current_time.isoformat(),
                                ),
                            ),
                            Booking.status.in_([BookingStatus.CANCELLED, BookingStatus.NO_SHOW]),
                        ),
                    )
                )

            # Handle include_past_confirmed (for BookAgain - only completed past bookings)
            elif include_past_confirmed_mode:
                # Include confirmed/completed lessons that have already finished
                user_now = get_user_now_by_id(instructor_id, self.db)
                today = user_now.date()
                current_time = user_now.time()

                query = query.filter(
                    or_(
                        Booking.booking_date < today,
                        and_(
                            Booking.booking_date == today,
                            Booking.end_time <= current_time.isoformat(),
                        ),
                    ),
                    Booking.status.in_(
                        [
                            BookingStatus.CONFIRMED,
                            BookingStatus.COMPLETED,
                            BookingStatus.NO_SHOW,
                        ]
                    ),
                )

            # Apply basic status filtering only when not using include_past_confirmed overrides
            if status_filter:
                query = query.filter(Booking.status == status_filter)

            # For upcoming lessons, show nearest first (ASC). For history, show latest first (DESC)
            if upcoming_only:
                query = query.order_by(Booking.booking_date.asc(), Booking.start_time.asc())
            else:
                query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error getting instructor bookings: {str(e)}")
            raise RepositoryException(f"Failed to get instructor bookings: {str(e)}")

    def get_instructor_future_bookings(
        self,
        instructor_id: str,
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
                from_date = get_user_today_by_id(instructor_id, self.db)

            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id, Booking.booking_date >= from_date
            )

            if exclude_cancelled:
                query = query.filter(Booking.status != BookingStatus.CANCELLED)

            return cast(
                List[Booking], query.order_by(Booking.booking_date, Booking.start_time).all()
            )

        except Exception as e:
            self.logger.error(f"Error getting instructor future bookings: {str(e)}")
            raise RepositoryException(f"Failed to get future bookings: {str(e)}")

    def get_bookings_for_service_catalog(
        self,
        service_catalog_id: str,
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
                .filter(
                    InstructorService.service_catalog_id == service_catalog_id,
                    Booking.booking_date >= from_date,
                )
            )

            if to_date:
                query = query.filter(Booking.booking_date <= to_date)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error getting bookings for service catalog: {str(e)}")
            raise RepositoryException(f"Failed to get service catalog bookings: {str(e)}")

    # Detailed Booking Queries (unchanged)

    def get_booking_with_details(self, booking_id: str) -> Optional[Booking]:
        """
        Get a booking with all relationships loaded.

        Loads all related objects for complete booking details.

        Args:
            booking_id: The booking ID

        Returns:
            The booking with all relationships, or None if not found
        """
        try:
            booking: Booking | None = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                    joinedload(Booking.rescheduled_from),
                    joinedload(Booking.cancelled_by),
                )
                .filter(Booking.id == booking_id)
                .first()
            )
            return booking
        except Exception as e:
            self.logger.error(f"Error getting booking details: {str(e)}")
            raise RepositoryException(f"Failed to get booking details: {str(e)}")

    # Statistics Queries (unchanged)

    def get_instructor_bookings_for_stats(self, instructor_id: str) -> List[Booking]:
        """
        Get all bookings for an instructor for statistics calculation.

        Returns minimal data needed for stats without heavy relationships.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of bookings for statistics
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking).filter(Booking.instructor_id == instructor_id).all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting instructor stats: {str(e)}")
            raise RepositoryException(f"Failed to get instructor statistics: {str(e)}")

    # Date-based Queries (simplified)

    def get_bookings_for_date(
        self,
        booking_date: date,
        status: Optional[BookingStatus] = None,
        with_relationships: bool = False,
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

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error(f"Error getting bookings for date: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for date: {str(e)}")

    # Counting Queries (unchanged)

    def count_bookings_by_status(self, user_id: str, user_role: str) -> Dict[str, int]:
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
            from sqlalchemy import func

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

    def complete_booking(self, booking_id: str) -> Booking:
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
            booking.completed_at = datetime.now(timezone.utc)

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

    def cancel_booking(
        self, booking_id: str, cancelled_by_id: str, reason: Optional[str] = None
    ) -> Booking:
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
            booking.cancelled_at = datetime.now(timezone.utc)
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

    def mark_no_show(self, booking_id: str) -> Booking:
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

    def _apply_eager_loading(self, query: Query) -> Query:
        """
        Override to include common relationships by default.

        For get_by_id and other single entity queries.
        """
        return query.options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.instructor_service),
        )

    def count_old_bookings(self, cutoff_date: datetime) -> int:
        """
        Count bookings created before a cutoff date.

        Used by: PrivacyService for retention statistics

        Args:
            cutoff_date: Count bookings created before this date

        Returns:
            Count of old bookings
        """
        from sqlalchemy import func

        return int(
            self.db.query(func.count(Booking.id)).filter(Booking.created_at < cutoff_date).scalar()
            or 0
        )

    def get_bookings_by_date_and_status(self, booking_date: date, status: str) -> List[Booking]:
        """
        Get all bookings for a specific date and status.

        Used by: NotificationService for sending reminders

        Args:
            booking_date: The date to check
            status: The booking status (e.g., "CONFIRMED")

        Returns:
            List of bookings matching the criteria
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(Booking.booking_date == booking_date, Booking.status == status)
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings by date and status: {str(e)}")
            return []

    def get_bookings_by_date_range_and_status(
        self, start_date: date, end_date: date, status: str
    ) -> List[Booking]:
        """
        Get all bookings within a date range for a specific status.

        Used by: NotificationService for efficient reminder queries

        Args:
            start_date: The start date (inclusive)
            end_date: The end date (inclusive)
            status: The booking status (e.g., "CONFIRMED")

        Returns:
            List of bookings matching the criteria
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                    Booking.status == status,
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings by date range and status: {str(e)}")
            return []

    def get_bookings_for_payment_authorization(self) -> List[Booking]:
        """
        Get bookings that need payment authorization.

        Returns bookings that are:
        - Status: CONFIRMED
        - Payment status: scheduled
        - Have payment method ID
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        Booking.payment_status == "scheduled",
                        Booking.payment_method_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings for payment authorization: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for payment authorization: {str(e)}")

    def get_bookings_for_payment_retry(self) -> List[Booking]:
        """
        Get bookings that need payment retry.

        Returns bookings that are:
        - Status: CONFIRMED
        - Payment status: auth_failed or auth_retry_failed
        - Have payment method ID
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        Booking.payment_status.in_(["auth_failed", "auth_retry_failed"]),
                        Booking.payment_method_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings for payment retry: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for payment retry: {str(e)}")

    def get_bookings_for_payment_capture(self) -> List[Booking]:
        """
        Get bookings that are ready for payment capture.

        Returns bookings that are:
        - Status: COMPLETED
        - Payment status: authorized
        - Have payment intent ID
        - Have completed_at timestamp
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.status == BookingStatus.COMPLETED,
                        Booking.payment_status == "authorized",
                        Booking.payment_intent_id.isnot(None),
                        Booking.completed_at.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings for payment capture: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for payment capture: {str(e)}")

    def get_bookings_for_auto_completion(self) -> List[Booking]:
        """
        Get bookings that need auto-completion.

        Returns bookings that are:
        - Status: CONFIRMED
        - Payment status: authorized
        - Have payment intent ID
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        Booking.payment_status == "authorized",
                        Booking.payment_intent_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings for auto completion: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for auto completion: {str(e)}")

    def get_bookings_with_expired_auth(self) -> List[Booking]:
        """
        Get bookings with potentially expired authorization.

        Returns bookings that are:
        - Payment status: authorized
        - Have payment intent ID
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.payment_status == "authorized",
                        Booking.payment_intent_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings with expired auth: {str(e)}")
            raise RepositoryException(f"Failed to get bookings with expired auth: {str(e)}")

    def count_overdue_authorizations(self, current_date: date) -> int:
        """
        Count bookings that are overdue for authorization.

        Args:
            current_date: Current date to compare against

        Returns:
            Count of overdue bookings
        """
        try:
            return int(
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        Booking.payment_status == "scheduled",
                        Booking.booking_date <= current_date,
                    )
                )
                .count()
            )
        except Exception as e:
            self.logger.error(f"Error counting overdue authorizations: {str(e)}")
            raise RepositoryException(f"Failed to count overdue authorizations: {str(e)}")

    def count_completed_lessons(
        self,
        *,
        instructor_user_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Count completed lessons for an instructor in a time window."""

        try:
            return int(
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.instructor_id == instructor_user_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                    Booking.completed_at >= window_start,
                    Booking.completed_at <= window_end,
                )
                .scalar()
                or 0
            )
        except Exception as exc:
            self.logger.error(
                "Error counting completed lessons for %s: %s", instructor_user_id, exc
            )
            raise RepositoryException(f"Failed to count completed lessons: {exc}")

    def count_student_completed_lifetime(self, student_id: str) -> int:
        """Return the lifetime completed session count for a student."""

        try:
            result = (
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.student_id == student_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                )
                .scalar()
            )
            return int(result or 0)
        except Exception as exc:
            self.logger.error(
                "Failed counting completed bookings for student %s: %s",
                student_id,
                str(exc),
            )
            raise RepositoryException("Failed to count student completed lessons")

    def get_student_most_recent_completed_at(self, student_id: str) -> Optional[datetime]:
        """Return the most recent completion timestamp for a student, if any."""

        try:
            record = (
                self.db.query(Booking.completed_at)
                .filter(
                    Booking.student_id == student_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                )
                .order_by(Booking.completed_at.desc())
                .first()
            )
            if not record:
                return None
            completed_at = record[0] if isinstance(record, tuple) else record
            return cast(Optional[datetime], completed_at)
        except Exception as exc:
            self.logger.error(
                "Failed getting latest completion for student %s: %s",
                student_id,
                str(exc),
            )
            raise RepositoryException("Failed to fetch student completion timestamp")

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

    # --------- Security helpers ---------
    def filter_owned_booking_ids(self, booking_ids: List[str], student_id: str) -> List[str]:
        """Return subset of booking_ids that are owned by the given student.

        Uses a single IN query for efficiency.
        """
        if not booking_ids:
            return []
        try:
            rows = (
                self.db.query(Booking.id)
                .filter(Booking.id.in_(booking_ids), Booking.student_id == student_id)
                .all()
            )
            return [r[0] if isinstance(r, tuple) else r.id for r in rows]
        except Exception as e:
            self.logger.error(f"Error filtering owned booking ids: {e}")
            return []

    # Per-user-pair conversation support
    def find_upcoming_for_pair(
        self,
        student_id: str,
        instructor_id: str,
        limit: int = 5,
    ) -> List[Booking]:
        """
        Find upcoming bookings for a student-instructor pair.

        Used for conversation context to show next/upcoming bookings.

        Args:
            student_id: The student's user ID
            instructor_id: The instructor's user ID
            limit: Maximum number of bookings to return

        Returns:
            List of upcoming bookings ordered by date/time ascending
        """
        try:
            # Use student's local time since bookings are stored in local time
            user_now = get_user_now_by_id(student_id, self.db)
            return cast(
                List[Booking],
                self.db.query(Booking)
                .options(joinedload(Booking.instructor_service))
                .filter(
                    Booking.student_id == student_id,
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    or_(
                        Booking.booking_date > user_now.date(),
                        and_(
                            Booking.booking_date == user_now.date(),
                            Booking.start_time > user_now.time(),
                        ),
                    ),
                )
                .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
                .limit(limit)
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error finding upcoming bookings for pair: {str(e)}")
            raise RepositoryException(f"Failed to find upcoming bookings for pair: {str(e)}")
