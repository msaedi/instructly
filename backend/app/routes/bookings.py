"""
Booking routes for InstaInstru platform.

This module handles all booking-related endpoints including:
- Creating instant bookings
- Viewing bookings (for students and instructors)
- Cancelling bookings
- Marking bookings as complete
- Checking availability
"""

import logging
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from ..database import get_db
from ..auth import get_current_user
from ..models.user import User, UserRole
from ..models.booking import Booking, BookingStatus
from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..schemas.booking import (
    BookingCreate,
    BookingUpdate,
    BookingCancel,
    BookingResponse,
    BookingListResponse,
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingStatsResponse,
    UpcomingBookingResponse,
    BookingResponse
)
from ..services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/bookings",
    tags=["bookings"]
)

notification_service = NotificationService()

async def get_current_active_user(
    current_user_email: str = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user."""
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.get("/{booking_id}/preview")
async def get_booking_preview(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get preview information for a booking.
    
    This endpoint provides quick preview data for the calendar view,
    including basic booking details without sensitive information.
    Only the instructor or student involved can view the preview.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        or_(
            Booking.student_id == current_user.id,
            Booking.instructor_id == current_user.id
        )
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
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
        "location_type_display": booking.location_type_display if booking.location_type else "Neutral Location",
        "meeting_location": booking.meeting_location,
        "service_area": booking.service_area,
        "status": booking.status,
        "student_note": booking.student_note,
        "total_price": float(booking.total_price)
    }

@router.get("/{booking_id}")
async def get_booking_details(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get full booking details.
    
    This endpoint provides complete booking information including
    all related data. Only accessible by the instructor or student
    involved in the booking.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        or_(
            Booking.student_id == current_user.id,
            Booking.instructor_id == current_user.id
        )
    ).options(
        joinedload(Booking.student),
        joinedload(Booking.instructor),
        joinedload(Booking.service)
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Return using the standardized response schema
    return BookingResponse.from_orm(booking)


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create an instant booking.
    
    Students can book any available slot. The booking is immediately confirmed.
    """
    # Only students can create bookings
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can create bookings"
        )
    
    # Get the availability slot with related data
    slot = db.query(AvailabilitySlot)\
        .options(joinedload(AvailabilitySlot.availability))\
        .filter(AvailabilitySlot.id == booking_data.availability_slot_id)\
        .first()
    
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability slot not found"
        )
    
    # Check if slot is already booked
    if slot.booking_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This slot is already booked"
        )
    
    # Get the service
    service = db.query(Service)\
        .filter(Service.id == booking_data.service_id)\
        .first()
    
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    
    # Verify the service belongs to the instructor
    if service.instructor_profile.user_id != slot.availability.instructor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service does not belong to this instructor"
        )
    
    # Get instructor profile for booking settings
    instructor_profile = service.instructor_profile
    
    # Check minimum advance booking time
    booking_datetime = datetime.combine(slot.availability.date, slot.start_time)
    min_booking_time = datetime.now() + timedelta(hours=instructor_profile.min_advance_booking_hours)
    
    if booking_datetime < min_booking_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bookings must be made at least {instructor_profile.min_advance_booking_hours} hours in advance"
        )
    
    # Calculate duration and price
    duration_minutes = service.duration or 60  # Default to 60 minutes
    hours = duration_minutes / 60
    total_price = float(service.hourly_rate) * hours
    
    # Create the booking
    booking = Booking(
        student_id=current_user.id,
        instructor_id=slot.availability.instructor_id,
        service_id=service.id,
        availability_slot_id=slot.id,
        booking_date=slot.availability.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        service_name=service.skill,
        hourly_rate=service.hourly_rate,
        total_price=total_price,
        duration_minutes=duration_minutes,
        status=BookingStatus.CONFIRMED,  # Instant booking!
        service_area=instructor_profile.areas_of_service,
        meeting_location=booking_data.meeting_location,
        student_note=booking_data.student_note
    )
    
    db.add(booking)
    db.flush()  # Get the booking ID
    
    # Update the slot to mark it as booked
    slot.booking_id = booking.id
    
    # Commit the transaction
    db.commit()
    db.refresh(booking)
    
    # Load relationships for response
    booking = db.query(Booking)\
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service)
        )\
        .filter(Booking.id == booking.id)\
        .first()
    
    logger.info(f"Booking {booking.id} created for student {current_user.id}")
    
    # UPDATED: Send confirmation emails
    try:
        # Initialize notification service with db session for loading additional data if needed
        notification_service_with_db = NotificationService(db)
        await notification_service_with_db.send_booking_confirmation(booking)
        logger.info(f"Confirmation emails sent for booking {booking.id}")
    except Exception as e:
        # Log the error but don't fail the booking
        logger.error(f"Failed to send confirmation emails for booking {booking.id}: {str(e)}")
        # In production, you might want to queue this for retry
    
    return booking


@router.get("/", response_model=BookingListResponse)
async def get_bookings(
    status: Optional[BookingStatus] = None,
    upcoming_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get bookings for the current user.
    
    Students see their bookings, instructors see bookings for their services.
    """
    # Base query
    query = db.query(Booking).options(
        joinedload(Booking.student),
        joinedload(Booking.instructor),
        joinedload(Booking.service)
    )
    
    # Filter by user role
    if current_user.role == UserRole.STUDENT:
        query = query.filter(Booking.student_id == current_user.id)
    else:  # INSTRUCTOR
        query = query.filter(Booking.instructor_id == current_user.id)
    
    # Filter by status if provided
    if status:
        query = query.filter(Booking.status == status)
    
    # Filter for upcoming only
    if upcoming_only:
        query = query.filter(
            Booking.booking_date >= date.today(),
            Booking.status == BookingStatus.CONFIRMED
        )
    
    # Order by booking date and time
    query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())
    
    # Pagination
    total = query.count()
    bookings = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return BookingListResponse(
        bookings=bookings,
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/upcoming", response_model=List[UpcomingBookingResponse])
async def get_upcoming_bookings(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get upcoming bookings for dashboard widget."""
    query = db.query(Booking).options(
        joinedload(Booking.student),
        joinedload(Booking.instructor)
    )
    
    # Filter by user role
    if current_user.role == UserRole.STUDENT:
        query = query.filter(Booking.student_id == current_user.id)
    else:  # INSTRUCTOR
        query = query.filter(Booking.instructor_id == current_user.id)
    
    # Get upcoming confirmed bookings
    bookings = query.filter(
        Booking.booking_date >= date.today(),
        Booking.status == BookingStatus.CONFIRMED
    ).order_by(
        Booking.booking_date,
        Booking.start_time
    ).limit(limit).all()
    
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
            meeting_location=b.meeting_location
        )
        for b in bookings
    ]


@router.get("/stats", response_model=BookingStatsResponse)
async def get_booking_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get booking statistics for instructors."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can view booking stats"
        )
    
    # Get all bookings for this instructor
    bookings = db.query(Booking).filter(
        Booking.instructor_id == current_user.id
    ).all()
    
    # Calculate stats
    total_bookings = len(bookings)
    upcoming_bookings = sum(1 for b in bookings if b.is_upcoming)
    completed_bookings = sum(1 for b in bookings if b.status == BookingStatus.COMPLETED)
    cancelled_bookings = sum(1 for b in bookings if b.status == BookingStatus.CANCELLED)
    
    # Calculate earnings (only completed bookings)
    total_earnings = sum(
        float(b.total_price) for b in bookings 
        if b.status == BookingStatus.COMPLETED
    )
    
    # This month's earnings
    first_day_of_month = date.today().replace(day=1)
    this_month_earnings = sum(
        float(b.total_price) for b in bookings 
        if b.status == BookingStatus.COMPLETED and b.booking_date >= first_day_of_month
    )
    
    return BookingStatsResponse(
        total_bookings=total_bookings,
        upcoming_bookings=upcoming_bookings,
        completed_bookings=completed_bookings,
        cancelled_bookings=cancelled_bookings,
        total_earnings=total_earnings,
        this_month_earnings=this_month_earnings
    )


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific booking."""
    booking = db.query(Booking)\
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service)
        )\
        .filter(Booking.id == booking_id)\
        .first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Check access rights
    if current_user.id not in [booking.student_id, booking.instructor_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this booking"
        )
    
    return booking


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: int,
    update_data: BookingUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update booking details.
    
    Only instructors can update booking notes and meeting location.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Only instructors can update bookings
    if current_user.id != booking.instructor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the instructor can update booking details"
        )
    
    # Update allowed fields
    if update_data.instructor_note is not None:
        booking.instructor_note = update_data.instructor_note
    if update_data.meeting_location is not None:
        booking.meeting_location = update_data.meeting_location
    
    db.commit()
    db.refresh(booking)
    
    # Load relationships
    booking = db.query(Booking)\
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service)
        )\
        .filter(Booking.id == booking_id)\
        .first()
    
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: int,
    cancel_data: BookingCancel,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancel a booking."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Check if user can cancel this booking
    if current_user.id not in [booking.student_id, booking.instructor_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to cancel this booking"
        )
    
    # Check if booking can be cancelled
    if not booking.is_cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking cannot be cancelled - current status: {booking.status}"
        )
    
    # Cancel the booking
    booking.cancel(current_user.id, cancel_data.reason)
    
    # Free up the availability slot
    if booking.availability_slot_id:
        slot = db.query(AvailabilitySlot).filter(
            AvailabilitySlot.id == booking.availability_slot_id
        ).first()
        if slot:
            slot.booking_id = None
    
    db.commit()
    db.refresh(booking)
    
    # Load relationships
    booking = db.query(Booking)\
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service)
        )\
        .filter(Booking.id == booking_id)\
        .first()
    
    logger.info(f"Booking {booking_id} cancelled by user {current_user.id}")
    
    # UPDATED: Send cancellation emails
    try:
        notification_service_with_db = NotificationService(db)
        await notification_service_with_db.send_cancellation_notification(
            booking=booking,
            cancelled_by=current_user,
            reason=cancel_data.reason
        )
        logger.info(f"Cancellation emails sent for booking {booking_id}")
    except Exception as e:
        # Log the error but don't fail the cancellation
        logger.error(f"Failed to send cancellation emails for booking {booking_id}: {str(e)}")
        # In production, you might want to queue this for retry
    
    return booking


@router.post("/{booking_id}/complete", response_model=BookingResponse)
async def complete_booking(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mark a booking as completed (instructor only)."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can mark bookings as complete"
        )
    
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Check if this is the instructor's booking
    if booking.instructor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only complete your own bookings"
        )
    
    # Check if booking can be completed
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only confirmed bookings can be completed - current status: {booking.status}"
        )
    
    # Mark as complete
    booking.complete()
    db.commit()
    db.refresh(booking)
    
    # Load relationships
    booking = db.query(Booking)\
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service)
        )\
        .filter(Booking.id == booking_id)\
        .first()
    
    logger.info(f"Booking {booking_id} marked as completed")
    
    return booking


@router.post("/check-availability", response_model=AvailabilityCheckResponse)
async def check_availability(
    check_data: AvailabilityCheckRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Check if a slot is available for booking."""
    # Get the slot
    slot = db.query(AvailabilitySlot)\
        .options(joinedload(AvailabilitySlot.availability))\
        .filter(AvailabilitySlot.id == check_data.availability_slot_id)\
        .first()
    
    if not slot:
        return AvailabilityCheckResponse(
            available=False,
            reason="Slot not found"
        )
    
    # Check if already booked
    if slot.booking_id:
        return AvailabilityCheckResponse(
            available=False,
            reason="Slot is already booked"
        )
    
    # Get service and instructor profile
    service = db.query(Service)\
        .options(joinedload(Service.instructor_profile))\
        .filter(Service.id == check_data.service_id)\
        .first()
    
    if not service:
        return AvailabilityCheckResponse(
            available=False,
            reason="Service not found"
        )
    
    # Check minimum advance booking
    booking_datetime = datetime.combine(slot.availability.date, slot.start_time)
    min_booking_time = datetime.now() + timedelta(hours=service.instructor_profile.min_advance_booking_hours)
    
    if booking_datetime < min_booking_time:
        return AvailabilityCheckResponse(
            available=False,
            reason=f"Must book at least {service.instructor_profile.min_advance_booking_hours} hours in advance",
            min_advance_hours=service.instructor_profile.min_advance_booking_hours
        )
    
    return AvailabilityCheckResponse(
        available=True,
        slot_info={
            "date": slot.availability.date.isoformat(),
            "start_time": slot.start_time.isoformat(),
            "end_time": slot.end_time.isoformat(),
            "instructor_id": slot.availability.instructor_id
        }
    )

# ENDPOINT for sending reminder emails (can be called by a cron job)
@router.post("/send-reminders", status_code=status.HTTP_200_OK)
async def send_reminder_emails(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Send 24-hour reminder emails for tomorrow's bookings.
    
    This endpoint should be called by a scheduled job/cron.
    In production, this would be restricted to admin users or internal services.
    """
    # For now, restrict to a specific admin email or role
    # In production, use proper admin authentication
    if current_user.email != "admin@instainstru.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger reminder emails"
        )
    
    try:
        notification_service_with_db = NotificationService(db)
        count = await notification_service_with_db.send_reminder_emails()
        
        return {
            "status": "success",
            "reminders_sent": count,
            "message": f"Successfully sent {count} reminder emails"
        }
    except Exception as e:
        logger.error(f"Failed to send reminder emails: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reminder emails"
        )