# backend/app/services/booking_service.py
"""
Booking Service for InstaInstru Platform

Handles all booking-related business logic including:
- Creating instant bookings using time ranges
- Finding booking opportunities
- Validating booking constraints
- Managing booking lifecycle
- Coordinating with other services
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

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
    ):
        """
        Initialize booking service.

        Args:
            db: Database session
            notification_service: Optional notification service instance
            repository: Optional BookingRepository instance
            conflict_checker_repository: Optional ConflictCheckerRepository instance
        """
        super().__init__(db)
        self.notification_service = notification_service or NotificationService(db)
        self.repository = repository or RepositoryFactory.create_booking_repository(db)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.conflict_checker_repository = (
            conflict_checker_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )

    async def create_booking(self, student: User, booking_data: BookingCreate) -> Booking:
        """
        Create an instant booking using time range.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data with date/time range

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
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            service_id=booking_data.service_id,
        )

        # Validate student role
        if student.role != UserRole.STUDENT:
            raise ValidationException("Only students can create bookings")

        with self.transaction():
            # 1. Validate and load required data
            service, instructor_profile = await self._validate_booking_data(booking_data)

            # 2. Check for time conflicts
            existing_conflicts = self.repository.check_time_conflict(
                instructor_id=booking_data.instructor_id,
                booking_date=booking_data.booking_date,
                start_time=booking_data.start_time,
                end_time=booking_data.end_time,
            )

            if existing_conflicts:
                raise ConflictException("This time slot conflicts with an existing booking")

            # 3. Apply business rules
            await self._apply_booking_rules(booking_data, service, instructor_profile)

            # 4. Calculate pricing
            pricing = self._calculate_pricing(service, booking_data.start_time, booking_data.end_time)

            # 5. Create the booking
            booking = self.repository.create(
                student_id=student.id,
                instructor_id=booking_data.instructor_id,
                service_id=service.id,
                booking_date=booking_data.booking_date,
                start_time=booking_data.start_time,
                end_time=booking_data.end_time,
                service_name=service.skill,
                hourly_rate=service.hourly_rate,
                total_price=pricing["total_price"],
                duration_minutes=pricing["duration_minutes"],
                status=BookingStatus.CONFIRMED,
                service_area=instructor_profile.areas_of_service,
                meeting_location=booking_data.meeting_location,
                location_type=booking_data.location_type,
                student_note=booking_data.student_note,
            )

            # 6. Commit transaction
            self.db.commit()

            # 7. Load relationships for response
            booking = self.repository.get_booking_with_details(booking.id)

            # 8. Send notifications
            try:
                await self.notification_service.send_booking_confirmation(booking)
            except Exception as e:
                logger.error(f"Failed to send booking confirmation: {str(e)}")

            # 9. Invalidate relevant caches
            self._invalidate_booking_caches(booking)

            return booking

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

        # Get instructor's availability slots for the date
        availability_slots = self.availability_repository.get_slots_by_date(instructor_id, target_date)

        # Get existing bookings for the date
        existing_bookings = self.repository.get_bookings_by_time_range(
            instructor_id=instructor_id,
            booking_date=target_date,
            start_time=earliest_time,
            end_time=latest_time,
        )

        opportunities = []

        # For each availability slot, find booking opportunities
        for slot in availability_slots:
            # Skip if slot is outside requested time range
            if slot.end_time <= earliest_time or slot.start_time >= latest_time:
                continue

            # Adjust slot boundaries to requested time range
            slot_start = max(slot.start_time, earliest_time)
            slot_end = min(slot.end_time, latest_time)

            # Find opportunities within this slot
            current_time = slot_start

            while current_time < slot_end:
                # Calculate potential booking end time
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

    # Private helper methods

    async def _validate_booking_data(self, booking_data: BookingCreate) -> tuple[Service, InstructorProfile]:
        """Validate and load all required data for booking."""
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

    async def _apply_booking_rules(
        self,
        booking_data: BookingCreate,
        service: Service,
        instructor_profile: InstructorProfile,
    ) -> None:
        """Apply business rules for booking creation."""
        # Check minimum advance booking time
        booking_datetime = datetime.combine(booking_data.booking_date, booking_data.start_time)
        min_booking_time = datetime.now() + timedelta(hours=instructor_profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            raise BusinessRuleException(
                f"Bookings must be made at least {instructor_profile.min_advance_booking_hours} hours in advance"
            )

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

        # Use service duration if specified
        if service.duration_override:
            duration_minutes = service.duration_override

        # Calculate price
        hours = duration_minutes / 60
        total_price = float(service.hourly_rate) * hours

        return {
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "hourly_rate": service.hourly_rate,
        }

    def _invalidate_booking_caches(self, booking: Booking) -> None:
        """Invalidate caches affected by booking changes."""
        # Invalidate user-specific caches
        self.invalidate_cache(f"user_bookings:{booking.student_id}")
        self.invalidate_cache(f"user_bookings:{booking.instructor_id}")

        # Invalidate date-specific caches
        self.invalidate_cache(f"bookings:date:{booking.booking_date}")

        # Invalidate instructor availability caches
        self.invalidate_cache(f"instructor_availability:{booking.instructor_id}:{booking.booking_date}")

        # Invalidate stats caches
        self.invalidate_cache(f"instructor_stats:{booking.instructor_id}")

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
