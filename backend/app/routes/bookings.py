# backend/app/routes/bookings.py
"""
Booking routes for InstaInstru platform - Clean Architecture Implementation.

COMPLETELY REWRITTEN for time-based bookings without slot references.
All legacy patterns removed. No backward compatibility.

Key Changes:
- Bookings created with instructor_id, date, and time range
- No availability_slot_id references
- Proper schema serialization (no manual response building)
- Removed dead code and unused endpoints

Key Features:
    - Instant booking with time-based creation
    - Self-contained bookings (no slot dependencies)
    - Booking lifecycle management (create, cancel, complete)
    - Availability checking using time ranges
    - Booking statistics for instructors
    - Preview and full details endpoints
    - Pagination support for listing bookings

Router Endpoints:
    GET /{booking_id}/preview - Quick preview for calendar display
    GET /{booking_id} - Full booking details
    POST / - Create instant booking with time range
    GET / - List bookings with filters and pagination
    GET /upcoming - Dashboard widget for upcoming bookings
    GET /stats - Instructor booking statistics
    PATCH /{booking_id} - Update booking (instructor notes/location)
    POST /{booking_id}/cancel - Cancel a booking
    POST /{booking_id}/complete - Mark booking as completed
    POST /check-availability - Check if time range is available
    POST /send-reminders - Admin endpoint for reminder emails
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..api.dependencies import get_booking_service, get_current_active_user
from ..core.config import settings
from ..core.exceptions import DomainException, NotFoundException, ValidationException
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
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
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# 1. First: all specific routes


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

        # Use schema for clean response
        return [UpcomingBookingResponse.model_validate(b) for b in bookings]
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


@router.post("/check-availability", response_model=AvailabilityCheckResponse)
@rate_limit(
    "30/minute", key_type=RateLimitKeyType.USER, error_message="Too many availability checks. Please slow down."
)
async def check_availability(
    request: Request,  # ADD THIS for rate limiting
    check_data: AvailabilityCheckRequest,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Check if a time range is available for booking.

    CLEAN ARCHITECTURE: Uses time-based checking.
    No slot references. Direct time conflict checking.

    Rate limited to prevent abuse of expensive availability checks.
    """
    try:
        # AvailabilityCheckRequest now has: instructor_id, booking_date, start_time, end_time, service_id
        result = await booking_service.check_availability(
            instructor_id=check_data.instructor_id,
            booking_date=check_data.booking_date,
            start_time=check_data.start_time,
            end_time=check_data.end_time,
            service_id=check_data.service_id,
        )

        return AvailabilityCheckResponse(**result)
    except DomainException as e:
        handle_domain_exception(e)


# Admin endpoint - consider moving to separate admin routes in future
@router.post("/send-reminders", status_code=status.HTTP_200_OK)
@rate_limit(
    "1/hour", key_type=RateLimitKeyType.IP, error_message="Reminder emails can only be triggered once per hour."
)
async def send_reminder_emails(
    request: Request,  # ADD THIS for rate limiting
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Send 24-hour reminder emails for tomorrow's bookings.

    Should be called by scheduled job/cron.
    Rate limited to prevent email spam.
    """
    # Simple admin check - improve in future
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


# 2. Then: routes without path params


@router.get("/", response_model=BookingListResponse)
async def get_bookings(
    status: Optional[BookingStatus] = None,
    upcoming_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """Get bookings for the current user with pagination."""
    try:
        bookings = booking_service.get_bookings_for_user(user=current_user, status=status, upcoming_only=upcoming_only)

        # Apply pagination
        total = len(bookings)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_bookings = bookings[start:end]

        return BookingListResponse(bookings=paginated_bookings, total=total, page=page, per_page=per_page)
    except DomainException as e:
        handle_domain_exception(e)


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(
    f"{settings.rate_limit_booking_per_minute}/minute",
    key_type=RateLimitKeyType.USER,
    error_message="Too many booking attempts. Please wait a moment and try again.",
)
async def create_booking(
    request: Request,  # ADD THIS for rate limiting
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Create an instant booking with time-based information.

    CLEAN ARCHITECTURE: Uses instructor_id, date, and time range.
    No slot references. Bookings are self-contained.

    Rate limited per user to prevent booking spam.
    """
    try:
        # The schema now enforces the correct format with extra='forbid'
        # BookingCreate has: instructor_id, service_id, booking_date, start_time, selected_duration, etc.
        # Extract selected_duration from booking_data
        selected_duration = booking_data.selected_duration

        booking = await booking_service.create_booking(
            student=current_user, booking_data=booking_data, selected_duration=selected_duration
        )

        return BookingResponse.model_validate(booking)
    except DomainException as e:
        handle_domain_exception(e)


# 3. Finally: routes with path parameters


@router.get("/{booking_id}/preview")
async def get_booking_preview(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Get preview information for a booking.

    Clean implementation - returns only meaningful data.
    """
    try:
        booking = booking_service.get_booking_for_user(booking_id, current_user)
        if not booking:
            raise NotFoundException("Booking not found")

        # Return clean preview data
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
            "location_type_display": booking.location_type_display if booking.location_type else "Neutral Location",
            "meeting_location": booking.meeting_location,
            "service_area": booking.service_area,
            "status": booking.status,
            "student_note": booking.student_note,
            "total_price": float(booking.total_price),
        }
    except DomainException as e:
        handle_domain_exception(e)


@router.get("/{booking_id}", response_model=BookingResponse)
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

        return BookingResponse.model_validate(booking)
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
        booking = booking_service.update_booking(booking_id=booking_id, user=current_user, update_data=update_data)
        return BookingResponse.model_validate(booking)
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
        return BookingResponse.model_validate(booking)
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
        booking = booking_service.complete_booking(booking_id=booking_id, instructor=current_user)
        return BookingResponse.model_validate(booking)
    except DomainException as e:
        handle_domain_exception(e)
