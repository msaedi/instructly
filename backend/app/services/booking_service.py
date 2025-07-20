# backend/app/services/booking_service.py
"""
Booking Service for InstaInstru Platform

Handles all booking-related business logic including:
- Creating instant bookings using time ranges
- Finding booking opportunities
- Validating booking constraints
- Managing booking lifecycle
- Coordinating with other services

UPDATED IN v65: Added performance metrics and refactored long methods.
All methods now under 50 lines with comprehensive observability! ⚡
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User, UserRole
from ..repositories.factory import RepositoryFactory
from ..schemas.booking import BookingCreate, BookingUpdate
from .base import BaseService
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


class BookingService(BaseService):
    """
    Service layer for booking operations.

    Centralizes all booking business logic and coordinates
    with other services.
    """

    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
        repository=None,
        conflict_checker_repository=None,
        cache_service=None,
    ):
        """
        Initialize booking service.

        Args:
            db: Database session
            notification_service: Optional notification service instance
            repository: Optional BookingRepository instance
            conflict_checker_repository: Optional ConflictCheckerRepository instance
            cache_service: Optional cache service for invalidation
        """
        super().__init__(db, cache=cache_service)
        self.notification_service = notification_service or NotificationService(db)
        self.repository = repository or RepositoryFactory.create_booking_repository(db)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.conflict_checker_repository = (
            conflict_checker_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )
        self.cache_service = cache_service

    @BaseService.measure_operation("create_booking")
    async def create_booking(self, student: User, booking_data: BookingCreate, selected_duration: int) -> Booking:
        """
        Create an instant booking using selected duration.

        REFACTORED: Split into helper methods to stay under 50 lines.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data with date/time range
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
            BusinessRuleException: If business rules violated
            ConflictException: If time slot already booked
        """
        self.log_operation(
            "create_booking",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            selected_duration=selected_duration,
        )

        # 1. Validate and load required data
        service, instructor_profile = await self._validate_booking_prerequisites(student, booking_data)

        # 2. Validate selected duration
        if selected_duration not in service.duration_options:
            raise ValidationException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        # 3. Calculate end time for conflict checking
        start_datetime = datetime.combine(booking_data.booking_date, booking_data.start_time)
        end_datetime = start_datetime + timedelta(minutes=selected_duration)
        calculated_end_time = end_datetime.time()

        # Update booking_data end_time for conflict checking
        booking_data.end_time = calculated_end_time

        # 4. Check conflicts and apply business rules
        await self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)

        # 5. Create the booking with transaction
        with self.transaction():
            booking = await self._create_booking_record(
                student, booking_data, service, instructor_profile, selected_duration
            )
            self.db.commit()

        # 5. Handle post-creation tasks
        await self._handle_post_booking_tasks(booking)

        return booking

    @BaseService.measure_operation("find_booking_opportunities")
    async def find_booking_opportunities(
        self,
        instructor_id: int,
        target_date: date,
        target_duration_minutes: int = 60,
        earliest_time: Optional[time] = None,
        latest_time: Optional[time] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find available time slots for booking based on instructor availability.

        REFACTORED: Split into helper methods to stay under 50 lines.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            target_duration_minutes: Desired booking duration
            earliest_time: Earliest acceptable time (default 9 AM)
            latest_time: Latest acceptable time (default 9 PM)

        Returns:
            List of available time slots for booking
        """
        # Set defaults
        if not earliest_time:
            earliest_time = time(9, 0)
        if not latest_time:
            latest_time = time(21, 0)

        # Get availability data
        availability_slots = await self._get_instructor_availability_windows(
            instructor_id, target_date, earliest_time, latest_time
        )

        existing_bookings = await self._get_existing_bookings_for_date(
            instructor_id, target_date, earliest_time, latest_time
        )

        # Find opportunities
        opportunities = self._calculate_booking_opportunities(
            availability_slots,
            existing_bookings,
            target_duration_minutes,
            earliest_time,
            latest_time,
            instructor_id,
            target_date,
        )

        return opportunities

    @BaseService.measure_operation("cancel_booking")
    async def cancel_booking(self, booking_id: int, user: User, reason: Optional[str] = None) -> Booking:
        """
        Cancel a booking.

        Args:
            booking_id: ID of booking to cancel
            user: User performing cancellation
            reason: Optional cancellation reason

        Returns:
            Cancelled booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot cancel
            BusinessRuleException: If booking not cancellable
        """
        with self.transaction():
            # Load booking with relationships
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            # Validate user can cancel
            if user.id not in [booking.student_id, booking.instructor_id]:
                raise ValidationException("You don't have permission to cancel this booking")

            # Check if cancellable
            if not booking.is_cancellable:
                raise BusinessRuleException(f"Booking cannot be cancelled - current status: {booking.status}")

            # Apply cancellation rules
            await self._apply_cancellation_rules(booking, user)

            # Cancel the booking
            booking.cancel(user.id, reason)

            self.db.commit()

            # Send notifications
            try:
                await self.notification_service.send_cancellation_notification(
                    booking=booking, cancelled_by=user, reason=reason
                )
            except Exception as e:
                logger.error(f"Failed to send cancellation notification: {str(e)}")

            # Invalidate caches
            self._invalidate_booking_caches(booking)

            return booking

    @BaseService.measure_operation("get_bookings_for_user")
    def get_bookings_for_user(
        self,
        user: User,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a user (student or instructor).

        Args:
            user: User to get bookings for
            status: Optional status filter
            upcoming_only: Only return future bookings
            limit: Optional result limit

        Returns:
            List of bookings
        """
        if user.role == UserRole.STUDENT:
            return self.repository.get_student_bookings(
                student_id=user.id, status=status, upcoming_only=upcoming_only, limit=limit
            )
        else:  # INSTRUCTOR
            return self.repository.get_instructor_bookings(
                instructor_id=user.id, status=status, upcoming_only=upcoming_only, limit=limit
            )

    @BaseService.measure_operation("get_booking_stats_for_instructor")
    def get_booking_stats_for_instructor(self, instructor_id: int) -> Dict[str, Any]:
        """
        Get booking statistics for an instructor.

        Args:
            instructor_id: Instructor user ID

        Returns:
            Dictionary of statistics
        """
        bookings = self.repository.get_instructor_bookings_for_stats(instructor_id)

        # Calculate stats
        total_bookings = len(bookings)
        upcoming_bookings = sum(1 for b in bookings if b.is_upcoming)
        completed_bookings = sum(1 for b in bookings if b.status == BookingStatus.COMPLETED)
        cancelled_bookings = sum(1 for b in bookings if b.status == BookingStatus.CANCELLED)

        # Calculate earnings (only completed bookings)
        total_earnings = sum(float(b.total_price) for b in bookings if b.status == BookingStatus.COMPLETED)

        # This month's earnings
        first_day_of_month = date.today().replace(day=1)
        this_month_earnings = sum(
            float(b.total_price)
            for b in bookings
            if b.status == BookingStatus.COMPLETED and b.booking_date >= first_day_of_month
        )

        return {
            "total_bookings": total_bookings,
            "upcoming_bookings": upcoming_bookings,
            "completed_bookings": completed_bookings,
            "cancelled_bookings": cancelled_bookings,
            "total_earnings": total_earnings,
            "this_month_earnings": this_month_earnings,
            "completion_rate": completed_bookings / total_bookings if total_bookings > 0 else 0,
            "cancellation_rate": cancelled_bookings / total_bookings if total_bookings > 0 else 0,
        }

    @BaseService.measure_operation("get_booking_for_user")
    def get_booking_for_user(self, booking_id: int, user: User) -> Optional[Booking]:
        """
        Get a booking if the user has access to it.

        Args:
            booking_id: ID of the booking
            user: User requesting the booking

        Returns:
            Booking if user has access, None otherwise
        """
        booking = self.repository.get_booking_with_details(booking_id)

        if booking and user.id in [booking.student_id, booking.instructor_id]:
            return booking

        return None

    @BaseService.measure_operation("update_booking")
    def update_booking(self, booking_id: int, user: User, update_data: BookingUpdate) -> Booking:
        """
        Update booking details (instructor only).

        Args:
            booking_id: ID of booking to update
            user: User performing update
            update_data: Fields to update

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot update
        """
        booking = self.repository.get_booking_with_details(booking_id)

        if not booking:
            raise NotFoundException("Booking not found")

        # Only instructors can update bookings
        if user.id != booking.instructor_id:
            raise ValidationException("Only the instructor can update booking details")

        # Update allowed fields using repository
        update_dict = {}
        if update_data.instructor_note is not None:
            update_dict["instructor_note"] = update_data.instructor_note
        if update_data.meeting_location is not None:
            update_dict["meeting_location"] = update_data.meeting_location

        if update_dict:
            booking = self.repository.update(booking_id, **update_dict)

        self.db.commit()

        # Reload with relationships
        booking = self.repository.get_booking_with_details(booking_id)

        self._invalidate_booking_caches(booking)

        return booking

    @BaseService.measure_operation("complete_booking")
    def complete_booking(self, booking_id: int, instructor: User) -> Booking:
        """
        Mark a booking as completed (instructor only).

        Args:
            booking_id: ID of booking to complete
            instructor: Instructor marking as complete

        Returns:
            Completed booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be completed
        """
        if instructor.role != UserRole.INSTRUCTOR:
            raise ValidationException("Only instructors can mark bookings as complete")

        booking = self.repository.get_booking_with_details(booking_id)

        if not booking:
            raise NotFoundException("Booking not found")

        if booking.instructor_id != instructor.id:
            raise ValidationException("You can only complete your own bookings")

        if booking.status != BookingStatus.CONFIRMED:
            raise BusinessRuleException(f"Only confirmed bookings can be completed - current status: {booking.status}")

        # Mark as complete
        booking.complete()
        self.db.commit()

        # Reload booking
        booking = self.repository.get_booking_with_details(booking_id)

        self._invalidate_booking_caches(booking)

        return booking

    @BaseService.measure_operation("check_availability")
    async def check_availability(
        self, instructor_id: int, booking_date: date, start_time: time, end_time: time, service_id: int
    ) -> Dict[str, Any]:
        """
        Check if a time range is available for booking.

        Args:
            instructor_id: The instructor ID
            booking_date: The date to check
            start_time: Start time
            end_time: End time
            service_id: Service ID

        Returns:
            Dictionary with availability status and details
        """
        # Check for conflicts
        has_conflict = self.repository.check_time_conflict(
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
        )

        if has_conflict:
            return {"available": False, "reason": "Time slot has conflicts with existing bookings"}

        # Get service and instructor profile using repositories
        service = self.conflict_checker_repository.get_active_service(service_id)
        if not service:
            return {"available": False, "reason": "Service not found or no longer available"}

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(instructor_id)

        # Check minimum advance booking
        booking_datetime = datetime.combine(booking_date, start_time)
        min_booking_time = datetime.now() + timedelta(hours=instructor_profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            return {
                "available": False,
                "reason": f"Must book at least {instructor_profile.min_advance_booking_hours} hours in advance",
                "min_advance_hours": instructor_profile.min_advance_booking_hours,
            }

        return {
            "available": True,
            "time_info": {
                "date": booking_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "instructor_id": instructor_id,
            },
        }

    @BaseService.measure_operation("send_booking_reminders")
    async def send_booking_reminders(self) -> int:
        """
        Send 24-hour reminder emails for tomorrow's bookings.

        Returns:
            Number of reminders sent
        """
        tomorrow = date.today() + timedelta(days=1)

        bookings = self.repository.get_bookings_for_date(
            booking_date=tomorrow, status=BookingStatus.CONFIRMED, with_relationships=True
        )

        sent_count = 0
        for booking in bookings:
            try:
                await self.notification_service.send_reminder_emails()
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending reminder for booking {booking.id}: {str(e)}")

        return sent_count

    # Private helper methods for create_booking refactoring

    async def _validate_booking_prerequisites(
        self, student: User, booking_data: BookingCreate
    ) -> Tuple[Service, InstructorProfile]:
        """
        Validate student role and load required data.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data

        Returns:
            Tuple of (service, instructor_profile)

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
        """
        # Validate student role
        if student.role != UserRole.STUDENT:
            raise ValidationException("Only students can create bookings")

        # Use repositories instead of direct queries
        service = self.conflict_checker_repository.get_active_service(booking_data.service_id)
        if not service:
            raise NotFoundException("Service not found or no longer available")

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(booking_data.instructor_id)
        if not instructor_profile:
            raise NotFoundException("Instructor profile not found")

        # Verify service belongs to instructor
        if service.instructor_profile_id != instructor_profile.id:
            raise ValidationException("Service does not belong to this instructor")

        return service, instructor_profile

    async def _check_conflicts_and_rules(
        self,
        booking_data: BookingCreate,
        service: Service,
        instructor_profile: InstructorProfile,
        student: Optional[User] = None,
        exclude_booking_id: Optional[int] = None,
    ) -> None:
        """
        Check for time conflicts and apply business rules.

        Args:
            booking_data: Booking creation data
            service: The service being booked
            instructor_profile: Instructor's profile
            student: The student making the booking (for student conflict checks)
            exclude_booking_id: Optional booking ID to exclude (for updates)

        Raises:
            ConflictException: If time slot conflicts
            BusinessRuleException: If business rules violated
        """
        # Check for instructor time conflicts
        existing_conflicts = self.repository.check_time_conflict(
            instructor_id=booking_data.instructor_id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            exclude_booking_id=exclude_booking_id,
        )

        if existing_conflicts:
            raise ConflictException("This time slot conflicts with an existing booking")

        # Check for student time conflicts
        if student:
            student_conflicts = self.repository.check_student_time_conflict(
                student_id=student.id,
                booking_date=booking_data.booking_date,
                start_time=booking_data.start_time,
                end_time=booking_data.end_time,
                exclude_booking_id=exclude_booking_id,
            )

            if student_conflicts:
                raise ConflictException("You already have a booking scheduled at this time")

        # Check minimum advance booking time
        booking_datetime = datetime.combine(booking_data.booking_date, booking_data.start_time)
        min_booking_time = datetime.now() + timedelta(hours=instructor_profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            raise BusinessRuleException(
                f"Bookings must be made at least {instructor_profile.min_advance_booking_hours} hours in advance"
            )

    async def _create_booking_record(
        self,
        student: User,
        booking_data: BookingCreate,
        service: Service,
        instructor_profile: InstructorProfile,
        selected_duration: int,
    ) -> Booking:
        """
        Create the booking record with pricing calculation.

        Args:
            student: Student creating the booking
            booking_data: Booking data
            service: Service being booked
            instructor_profile: Instructor's profile
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance
        """
        # Calculate end time based on selected duration
        start_datetime = datetime.combine(booking_data.booking_date, booking_data.start_time)
        end_datetime = start_datetime + timedelta(minutes=selected_duration)
        calculated_end_time = end_datetime.time()

        # Calculate pricing based on selected duration
        total_price = service.session_price(selected_duration)

        # Create the booking
        booking = self.repository.create(
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            service_id=service.id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=calculated_end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=total_price,
            duration_minutes=selected_duration,
            status=BookingStatus.CONFIRMED,
            service_area=instructor_profile.areas_of_service,
            meeting_location=booking_data.meeting_location,
            location_type=booking_data.location_type,
            student_note=booking_data.student_note,
        )

        # Load relationships for response
        booking = self.repository.get_booking_with_details(booking.id)

        return booking

    async def _handle_post_booking_tasks(self, booking: Booking) -> None:
        """
        Handle notifications and cache invalidation after booking creation.

        Args:
            booking: The created booking
        """
        # Send notifications
        try:
            await self.notification_service.send_booking_confirmation(booking)
        except Exception as e:
            logger.error(f"Failed to send booking confirmation: {str(e)}")

        # Invalidate relevant caches
        self._invalidate_booking_caches(booking)

    # Private helper methods for find_booking_opportunities refactoring

    async def _get_instructor_availability_windows(
        self,
        instructor_id: int,
        target_date: date,
        earliest_time: time,
        latest_time: time,
    ) -> List[Any]:
        """
        Get instructor's availability slots for the date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            earliest_time: Earliest time boundary
            latest_time: Latest time boundary

        Returns:
            List of availability slots
        """
        availability_slots = self.availability_repository.get_slots_by_date(instructor_id, target_date)

        # Filter slots within time range
        return [
            slot
            for slot in availability_slots
            if not (slot.end_time <= earliest_time or slot.start_time >= latest_time)
        ]

    async def _get_existing_bookings_for_date(
        self,
        instructor_id: int,
        target_date: date,
        earliest_time: time,
        latest_time: time,
    ) -> List[Booking]:
        """
        Get existing bookings for the instructor on the date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            earliest_time: Earliest time boundary
            latest_time: Latest time boundary

        Returns:
            List of existing bookings
        """
        return self.repository.get_bookings_by_time_range(
            instructor_id=instructor_id,
            booking_date=target_date,
            start_time=earliest_time,
            end_time=latest_time,
        )

    def _calculate_booking_opportunities(
        self,
        availability_slots: List[Any],
        existing_bookings: List[Booking],
        target_duration_minutes: int,
        earliest_time: time,
        latest_time: time,
        instructor_id: int,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Calculate available booking opportunities from slots and bookings.

        Args:
            availability_slots: Available time slots
            existing_bookings: Existing bookings
            target_duration_minutes: Desired duration
            earliest_time: Earliest boundary
            latest_time: Latest boundary
            instructor_id: Instructor ID
            target_date: Target date

        Returns:
            List of booking opportunities
        """
        opportunities = []

        for slot in availability_slots:
            # Adjust slot boundaries to requested time range
            slot_start = max(slot.start_time, earliest_time)
            slot_end = min(slot.end_time, latest_time)

            # Find opportunities within this slot
            opportunities.extend(
                self._find_opportunities_in_slot(
                    slot_start,
                    slot_end,
                    existing_bookings,
                    target_duration_minutes,
                    instructor_id,
                    target_date,
                )
            )

        return opportunities

    def _find_opportunities_in_slot(
        self,
        slot_start: time,
        slot_end: time,
        existing_bookings: List[Booking],
        target_duration_minutes: int,
        instructor_id: int,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Find booking opportunities within a single availability slot.

        Args:
            slot_start: Start of availability slot
            slot_end: End of availability slot
            existing_bookings: List of existing bookings
            target_duration_minutes: Desired booking duration
            instructor_id: Instructor ID
            target_date: Target date

        Returns:
            List of opportunities in this slot
        """
        opportunities = []
        current_time = slot_start

        while current_time < slot_end:
            # Calculate potential end time
            start_dt = datetime.combine(date.today(), current_time)
            end_dt = start_dt + timedelta(minutes=target_duration_minutes)
            potential_end = end_dt.time()

            # Check if this exceeds slot boundary
            if potential_end > slot_end:
                break

            # Check for conflicts with existing bookings
            has_conflict = False
            for booking in existing_bookings:
                if current_time < booking.end_time and potential_end > booking.start_time:
                    # Conflict found, skip to after this booking
                    current_time = booking.end_time
                    has_conflict = True
                    break

            if not has_conflict:
                # This is a valid opportunity
                opportunities.append(
                    {
                        "start_time": current_time.isoformat(),
                        "end_time": potential_end.isoformat(),
                        "duration_minutes": target_duration_minutes,
                        "available": True,
                        "instructor_id": instructor_id,
                        "date": target_date.isoformat(),
                    }
                )

                # Move to next potential slot
                current_time = potential_end

        return opportunities

    # Existing private helper methods

    async def _apply_cancellation_rules(self, booking: Booking, user: User) -> None:
        """Apply business rules for cancellation."""
        # Check cancellation deadline
        booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
        cancellation_deadline = booking_datetime - timedelta(hours=2)

        if datetime.now() > cancellation_deadline:
            # Log late cancellation but allow it
            logger.warning(f"Late cancellation for booking {booking.id} by user {user.id}")

    def _calculate_pricing(self, service: Service, start_time: time, end_time: time) -> Dict[str, Any]:
        """Calculate booking pricing based on time range."""
        # Calculate duration
        start = datetime.combine(date.today(), start_time)
        end = datetime.combine(date.today(), end_time)
        duration = end - start
        duration_minutes = int(duration.total_seconds() / 60)

        # Calculate price based on actual booking duration
        hours = duration_minutes / 60
        total_price = float(service.hourly_rate) * hours

        return {
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "hourly_rate": service.hourly_rate,
        }

    def _invalidate_booking_caches(self, booking: Booking) -> None:
        """Invalidate caches affected by booking changes using enhanced cache service."""
        # Use enhanced cache service to invalidate availability caches
        if self.cache_service:
            try:
                # Invalidate all availability caches for the instructor and specific date
                self.cache_service.invalidate_instructor_availability(booking.instructor_id, [booking.booking_date])
                logger.debug(f"Invalidated availability caches for instructor {booking.instructor_id}")
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate availability caches: {cache_error}")

        # Legacy cache invalidation for other booking-related caches
        self.invalidate_cache(f"user_bookings:{booking.student_id}")
        self.invalidate_cache(f"user_bookings:{booking.instructor_id}")

        # Invalidate date-specific caches
        self.invalidate_cache(f"bookings:date:{booking.booking_date}")

        # Invalidate instructor availability caches (fallback)
        self.invalidate_cache(f"instructor_availability:{booking.instructor_id}:{booking.booking_date}")

        # Invalidate stats caches
        self.invalidate_cache(f"instructor_stats:{booking.instructor_id}")
