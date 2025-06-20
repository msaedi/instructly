# backend/app/services/booking_service.py
"""
Booking Service for InstaInstru Platform

Handles all booking-related business logic including:
- Creating instant bookings
- Validating booking constraints
- Managing booking lifecycle
- Coordinating with other services
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User, UserRole
from ..schemas.booking import BookingCreate, BookingUpdate
from .base import BaseService
from .notification_service import NotificationService

# Import BookingConflictException if it exists, otherwise use ConflictException
try:
    from ..core.exceptions import BookingConflictException
except ImportError:
    BookingConflictException = ConflictException

logger = logging.getLogger(__name__)


class BookingService(BaseService):
    """
    Service layer for booking operations.

    Centralizes all booking business logic and coordinates
    with other services like availability and notifications.
    """

    def __init__(self, db: Session, notification_service: Optional[NotificationService] = None):
        """
        Initialize booking service.

        Args:
            db: Database session
            notification_service: Optional notification service instance
        """
        super().__init__(db)
        self.notification_service = notification_service or NotificationService(db)

    async def create_booking(self, student: User, booking_data: BookingCreate) -> Booking:
        """
        Create an instant booking.

        This is the main booking creation flow with all validations
        and business rules applied.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data

        Returns:
            Created booking instance

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
            BusinessRuleException: If business rules violated
            ConflictException: If slot already booked
        """
        # Log the operation
        self.log_operation(
            "create_booking",
            student_id=student.id,
            slot_id=booking_data.availability_slot_id,
            service_id=booking_data.service_id,
        )

        # Validate student role
        if student.role != UserRole.STUDENT:
            raise ValidationException("Only students can create bookings")

        with self.transaction():
            # 1. Validate and load all required data
            slot, service, instructor_profile = await self._validate_booking_data(booking_data)

            # 2. Check slot availability
            if slot.booking_id:
                raise ConflictException("This slot is already booked")

            # 3. Apply business rules
            await self._apply_booking_rules(slot, service, instructor_profile, booking_data)

            # 4. Calculate pricing
            pricing = self._calculate_pricing(service, slot)

            # 5. Create the booking
            booking = Booking(
                student_id=student.id,
                instructor_id=slot.availability.instructor_id,
                service_id=service.id,
                availability_slot_id=slot.id,
                booking_date=slot.availability.date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                service_name=service.skill,
                hourly_rate=service.hourly_rate,
                total_price=pricing["total_price"],
                duration_minutes=pricing["duration_minutes"],
                status=BookingStatus.CONFIRMED,  # Instant booking!
                service_area=instructor_profile.areas_of_service,
                meeting_location=booking_data.meeting_location,
                location_type=booking_data.location_type,
                student_note=booking_data.student_note,
            )

            self.db.add(booking)
            self.db.flush()  # Get the booking ID

            # 6. Mark slot as booked
            slot.booking_id = booking.id

            # 7. Commit transaction
            self.db.commit()

            # 8. Load relationships for response
            booking = self._load_booking_with_relationships(booking.id)

            # 9. Send notifications (async, don't fail booking if this fails)
            try:
                await self.notification_service.send_booking_confirmation(booking)
            except Exception as e:
                logger.error(f"Failed to send booking confirmation: {str(e)}")
                # Don't fail the booking, but log for retry

            # 10. Invalidate relevant caches
            self._invalidate_booking_caches(booking)

            logger.info(f"Booking {booking.id} created successfully")
            return booking

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
            booking = self._load_booking_with_relationships(booking_id)
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

            # Free up the availability slot
            if booking.availability_slot_id:
                slot = (
                    self.db.query(AvailabilitySlot).filter(AvailabilitySlot.id == booking.availability_slot_id).first()
                )
                if slot:
                    slot.booking_id = None

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
        query = self.db.query(Booking).options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service),
        )

        # Filter by user role
        if user.role == UserRole.STUDENT:
            query = query.filter(Booking.student_id == user.id)
        else:  # INSTRUCTOR
            query = query.filter(Booking.instructor_id == user.id)

        # Apply filters
        if status:
            query = query.filter(Booking.status == status)

        if upcoming_only:
            query = query.filter(
                Booking.booking_date >= date.today(),
                Booking.status == BookingStatus.CONFIRMED,
            )

        # Order and limit
        query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_booking_stats_for_instructor(self, instructor_id: int) -> Dict[str, Any]:
        """
        Get booking statistics for an instructor.

        Args:
            instructor_id: Instructor user ID

        Returns:
            Dictionary of statistics
        """
        bookings = self.db.query(Booking).filter(Booking.instructor_id == instructor_id).all()

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

    async def _validate_booking_data(
        self, booking_data: BookingCreate
    ) -> tuple[AvailabilitySlot, Service, InstructorProfile]:
        """Validate and load all required data for booking."""
        # Load availability slot
        slot = (
            self.db.query(AvailabilitySlot)
            .options(joinedload(AvailabilitySlot.availability))
            .filter(AvailabilitySlot.id == booking_data.availability_slot_id)
            .first()
        )

        if not slot:
            raise NotFoundException("Availability slot not found")

        # Load service - ONLY ACTIVE SERVICES
        service = (
            self.db.query(Service)
            .options(joinedload(Service.instructor_profile))
            .filter(
                Service.id == booking_data.service_id, Service.is_active == True  # Only allow booking active services
            )
            .first()
        )

        if not service:
            raise NotFoundException("Service not found or no longer available")

        # Verify service belongs to instructor
        if service.instructor_profile.user_id != slot.availability.instructor_id:
            raise ValidationException("Service does not belong to this instructor")

        return slot, service, service.instructor_profile

    async def _apply_booking_rules(
        self,
        slot: AvailabilitySlot,
        service: Service,
        instructor_profile: InstructorProfile,
        booking_data: BookingCreate,
    ) -> None:
        """Apply business rules for booking creation."""
        # Check minimum advance booking time
        booking_datetime = datetime.combine(slot.availability.date, slot.start_time)
        min_booking_time = datetime.now() + timedelta(hours=instructor_profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            raise BusinessRuleException(
                "Bookings must be made at least " f"{instructor_profile.min_advance_booking_hours} hours in advance"
            )

        # Additional business rules can be added here
        # - Check for blackout dates
        # - Check for maximum bookings per day
        # - Check for overlapping bookings
        # etc.

    async def _apply_cancellation_rules(self, booking: Booking, user: User) -> None:
        """Apply business rules for cancellation."""
        # Check cancellation deadline
        booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
        cancellation_deadline = booking_datetime - timedelta(hours=2)  # 2 hour policy

        if datetime.now() > cancellation_deadline:
            # Log late cancellation but allow it
            logger.warning(f"Late cancellation for booking {booking.id} by user {user.id}")

        # Additional rules based on who's cancelling
        if user.id == booking.instructor_id:
            # Instructor cancellation - might affect their rating
            logger.info(f"Instructor {user.id} cancelled booking {booking.id}")
        else:
            # Student cancellation
            logger.info(f"Student {user.id} cancelled booking {booking.id}")

    def _calculate_pricing(self, service: Service, slot: AvailabilitySlot) -> Dict[str, Any]:
        """Calculate booking pricing."""
        # Calculate duration
        start = datetime.combine(date.today(), slot.start_time)
        end = datetime.combine(date.today(), slot.end_time)
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

    def _load_booking_with_relationships(self, booking_id: int) -> Optional[Booking]:
        """Load booking with all relationships."""
        return (
            self.db.query(Booking)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.service),
                joinedload(Booking.availability_slot),
            )
            .filter(Booking.id == booking_id)
            .first()
        )

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
        booking = self._load_booking_with_relationships(booking_id)

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
        booking = self._load_booking_with_relationships(booking_id)

        if not booking:
            raise NotFoundException("Booking not found")

        # Only instructors can update bookings
        if user.id != booking.instructor_id:
            raise ValidationException("Only the instructor can update booking details")

        # Update allowed fields
        if update_data.instructor_note is not None:
            booking.instructor_note = update_data.instructor_note
        if update_data.meeting_location is not None:
            booking.meeting_location = update_data.meeting_location

        self.db.commit()
        self.db.refresh(booking)

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

        booking = self._load_booking_with_relationships(booking_id)

        if not booking:
            raise NotFoundException("Booking not found")

        if booking.instructor_id != instructor.id:
            raise ValidationException("You can only complete your own bookings")

        if booking.status != BookingStatus.CONFIRMED:
            raise BusinessRuleException(f"Only confirmed bookings can be completed - current status: {booking.status}")

        # Mark as complete
        booking.complete()
        self.db.commit()
        self.db.refresh(booking)

        self._invalidate_booking_caches(booking)

        logger.info(f"Booking {booking_id} marked as completed")
        return booking

    async def check_availability(self, slot_id: int, service_id: int) -> Dict[str, Any]:
        """
        Check if a slot is available for booking.

        Args:
            slot_id: Availability slot ID
            service_id: Service ID

        Returns:
            Dictionary with availability status and details
        """
        # Get the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .options(joinedload(AvailabilitySlot.availability))
            .filter(AvailabilitySlot.id == slot_id)
            .first()
        )

        if not slot:
            return {"available": False, "reason": "Slot not found"}

        # Check if already booked
        if slot.booking_id:
            return {"available": False, "reason": "Slot is already booked"}

        # Get service and instructor profile - ONLY ACTIVE SERVICES
        service = (
            self.db.query(Service)
            .options(joinedload(Service.instructor_profile))
            .filter(Service.id == service_id, Service.is_active == True)  # Only check active services
            .first()
        )

        if not service:
            return {"available": False, "reason": "Service not found or no longer available"}

        # Check minimum advance booking
        booking_datetime = datetime.combine(slot.availability.date, slot.start_time)
        min_booking_time = datetime.now() + timedelta(hours=service.instructor_profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            return {
                "available": False,
                "reason": f"Must book at least {service.instructor_profile.min_advance_booking_hours} hours in advance",
                "min_advance_hours": service.instructor_profile.min_advance_booking_hours,
            }

        return {
            "available": True,
            "slot_info": {
                "date": slot.availability.date.isoformat(),
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
                "instructor_id": slot.availability.instructor_id,
            },
        }

    async def send_booking_reminders(self) -> int:
        """
        Send 24-hour reminder emails for tomorrow's bookings.

        Returns:
            Number of reminders sent
        """
        tomorrow = date.today() + timedelta(days=1)

        bookings = (
            self.db.query(Booking)
            .filter(
                Booking.booking_date == tomorrow,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .options(joinedload(Booking.student), joinedload(Booking.instructor))
            .all()
        )

        logger.info(f"Found {len(bookings)} bookings for tomorrow")

        sent_count = 0
        for booking in bookings:
            try:
                await self.notification_service.send_reminder_emails()
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending reminder for booking {booking.id}: {str(e)}")

        return sent_count
