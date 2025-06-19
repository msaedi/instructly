# backend/app/routes/bookings.py
"""
Booking routes for InstaInstru platform - Refactored with Service Layer.

This module now acts as a thin controller, delegating business logic
to the BookingService while handling HTTP-specific concerns.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..api.dependencies import get_booking_service, get_current_active_user
from ..core.exceptions import DomainException, NotFoundException, ValidationException
from ..database import get_db
from ..models.booking import BookingStatus
from ..models.user import User, UserRole
from ..schemas.booking import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingCancel,
    BookingCreate,
    BookingListResponse,
    BookingResponse,
    BookingStatsResponse,
    BookingUpdate,
    UpcomingBookingResponse,
)
from ..services.booking_service import BookingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def handle_domain_exception(exc: DomainException):
    """Convert domain exceptions to HTTP exceptions."""
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()

    # Default handling
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
    )


@router.get("/{booking_id}/preview")
async def get_booking_preview(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
    db: Session = Depends(get_db),
):
    """
    Get preview information for a booking.

    This endpoint provides quick preview data for the calendar view.
    """
    try:
        booking = booking_service.get_booking_for_user(booking_id, current_user)

        if not booking:
            raise NotFoundException("Booking not found")

        # Return preview data
        return {
            "booking_id": booking.id,
            "student_name": booking.student.full_name,
            "instructor_name": booking.instructor.full_name,
            "service_name": booking.service_name,
            "booking_date": booking.booking_date.isoformat(),
            "start_time": str(booking.start_time),
            "end_time": str(booking.end_time),
            "duration_minutes": booking.duration_minutes,
            "location_type": booking.location_type or "neutral",
            "location_type_display": booking.location_type_display
            if booking.location_type
            else "Neutral Location",
            "meeting_location": booking.meeting_location,
            "service_area": booking.service_area,
            "status": booking.status,
            "student_note": booking.student_note,
            "total_price": float(booking.total_price),
        }
    except DomainException as e:
        handle_domain_exception(e)


@router.get("/{booking_id}")
async def get_booking_details(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Get full booking details."""
    try:
        booking = booking_service.get_booking_for_user(booking_id, current_user)

        if not booking:
            raise NotFoundException("Booking not found")

        return BookingResponse.from_orm(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Create an instant booking.

    Students can book any available slot. The booking is immediately confirmed.
    """
    try:
        booking = await booking_service.create_booking(
            student=current_user, booking_data=booking_data
        )

        return BookingResponse.from_orm(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.get("/", response_model=BookingListResponse)
async def get_bookings(
    status: Optional[BookingStatus] = None,
    upcoming_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Get bookings for the current user."""
    try:
        # Get bookings from service
        bookings = booking_service.get_bookings_for_user(
            user=current_user, status=status, upcoming_only=upcoming_only
        )

        # Apply pagination
        total = len(bookings)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_bookings = bookings[start:end]

        return BookingListResponse(
            bookings=paginated_bookings, total=total, page=page, per_page=per_page
        )
    except DomainException as e:
        handle_domain_exception(e)


@router.get("/upcoming", response_model=List[UpcomingBookingResponse])
async def get_upcoming_bookings(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Get upcoming bookings for dashboard widget."""
    try:
        bookings = booking_service.get_bookings_for_user(
            user=current_user,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=limit,
        )

        # Transform to response format
        return [
            UpcomingBookingResponse(
                id=b.id,
                booking_date=b.booking_date,
                start_time=b.start_time,
                end_time=b.end_time,
                service_name=b.service_name,
                student_name=b.student.full_name,
                instructor_name=b.instructor.full_name,
                meeting_location=b.meeting_location,
            )
            for b in bookings
        ]
    except DomainException as e:
        handle_domain_exception(e)


@router.get("/stats", response_model=BookingStatsResponse)
async def get_booking_stats(
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Get booking statistics for instructors."""
    try:
        if current_user.role != UserRole.INSTRUCTOR:
            raise ValidationException("Only instructors can view booking stats")

        stats = booking_service.get_booking_stats_for_instructor(current_user.id)

        return BookingStatsResponse(**stats)
    except DomainException as e:
        handle_domain_exception(e)


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: int,
    update_data: BookingUpdate,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Update booking details (instructor only)."""
    try:
        booking = booking_service.update_booking(
            booking_id=booking_id, user=current_user, update_data=update_data
        )

        return BookingResponse.from_orm(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: int,
    cancel_data: BookingCancel,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Cancel a booking."""
    try:
        booking = await booking_service.cancel_booking(
            booking_id=booking_id, user=current_user, reason=cancel_data.reason
        )

        return BookingResponse.from_orm(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post("/{booking_id}/complete", response_model=BookingResponse)
async def complete_booking(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Mark a booking as completed (instructor only)."""
    try:
        booking = booking_service.complete_booking(
            booking_id=booking_id, instructor=current_user
        )

        return BookingResponse.from_orm(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post("/check-availability", response_model=AvailabilityCheckResponse)
async def check_availability(
    check_data: AvailabilityCheckRequest,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Check if a slot is available for booking."""
    try:
        result = await booking_service.check_availability(
            slot_id=check_data.availability_slot_id, service_id=check_data.service_id
        )

        return AvailabilityCheckResponse(**result)
    except DomainException as e:
        handle_domain_exception(e)


# Admin/system endpoints (keep for now, but should move to separate admin routes)
@router.post("/send-reminders", status_code=status.HTTP_200_OK)
async def send_reminder_emails(
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Send 24-hour reminder emails for tomorrow's bookings.

    This endpoint should be called by a scheduled job/cron.
    """
    # For now, restrict to a specific admin email
    if current_user.email != "admin@instainstru.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger reminder emails",
        )

    try:
        count = await booking_service.send_booking_reminders()

        return {
            "status": "success",
            "reminders_sent": count,
            "message": f"Successfully sent {count} reminder emails",
        }
    except Exception as e:
        logger.error(f"Failed to send reminder emails: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reminder emails",
        )
