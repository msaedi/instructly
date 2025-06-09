from datetime import timedelta
from pytz import timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta

from .instructors import get_current_active_user
from ..database import get_db
from ..auth import get_current_user
from ..models.user import User
from ..models.instructor import InstructorProfile
from ..models.booking import Booking, BookingStatus, TimeSlot
from ..models.service import Service
from ..schemas.booking import (
    BookingCreateOld,
    BookingCreate, 
    BookingResponse, 
    BookingListResponse,
    BookingCancel,
    AvailableSlotResponse
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

@router.post("/create", response_model=BookingResponse)
def create_booking(
    booking: BookingCreateOld,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new booking as a student"""
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can create bookings")
    
    # Verify time slot exists and is available
    time_slot = db.query(TimeSlot).filter(
        TimeSlot.id == booking.timeslot_id,
        TimeSlot.instructor_id == booking.instructor_id,
        TimeSlot.is_available == True
    ).first()
    
    if not time_slot:
        raise HTTPException(status_code=404, detail="Time slot not found or unavailable")
    
    # Verify service exists and belongs to instructor
    service = db.query(Service).join(Service.instructor_profile).filter(
        Service.id == booking.service_id,
        Service.instructor_profile.has(user_id=booking.instructor_id)
    ).first()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this instructor")
    
    # Calculate total price (assuming 1 hour sessions for now)
    total_price = service.hourly_rate
    
    # Set cancellation deadline (24 hours before session)
    cancellation_deadline = time_slot.start_time - timedelta(hours=24)
    
    # Create booking
    new_booking = Booking(
        student_id=current_user.id,
        instructor_id=booking.instructor_id,
        timeslot_id=booking.timeslot_id,
        service_id=booking.service_id,
        total_price=total_price,
        cancellation_deadline=cancellation_deadline,
        status=BookingStatus.PENDING
    )
    
    # Mark time slot as unavailable
    time_slot.is_available = False
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    # Load relationships for response
    new_booking = db.query(Booking).options(
        joinedload(Booking.time_slot),
        joinedload(Booking.service),
        joinedload(Booking.instructor)
    ).filter(Booking.id == new_booking.id).first()
    
    return new_booking

@router.post("/create-new", response_model=BookingResponse)
async def create_booking_new(
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new booking using the direct time-based system.
    This replaces the old timeslot-based booking creation.
    """
    
    # Verify the user is a student
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can create bookings")
    
    # Get the service and verify it exists
    service = db.query(Service).filter(Service.id == booking_data.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Get instructor profile for buffer time and minimum advance booking
    instructor_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == booking_data.instructor_id
    ).first()
    if not instructor_profile:
        raise HTTPException(status_code=404, detail="Instructor profile not found")
    
    # Check minimum advance booking time
    tz = timezone('America/New_York')
    now = datetime.now(tz).astimezone(timezone('UTC'))
    min_booking_time = now + timedelta(hours=instructor_profile.minimum_advance_hours)
    
    if booking_data.start_time < min_booking_time:
        raise HTTPException(
            status_code=400, 
            detail=f"Bookings must be made at least {instructor_profile.minimum_advance_hours} hours in advance"
        )
    
    # Calculate end time based on duration
    end_time = booking_data.start_time + timedelta(minutes=booking_data.duration_minutes)
    
    # Check if the instructor is available during this time
    # First, check if there's an availability window that covers this time
    availability_windows = db.query(TimeSlot).filter(
        TimeSlot.instructor_id == booking_data.instructor_id,
        TimeSlot.is_available == True,
        TimeSlot.start_time <= booking_data.start_time,
        TimeSlot.end_time >= end_time
    ).first()
    
    if not availability_windows:
        raise HTTPException(
            status_code=400,
            detail="Instructor is not available during the requested time"
        )
    
    # Check for conflicts with existing bookings (including buffer time)
    buffer_minutes = instructor_profile.buffer_time
    buffered_start = booking_data.start_time - timedelta(minutes=buffer_minutes)
    buffered_end = end_time + timedelta(minutes=buffer_minutes)
    
    conflicting_booking = db.query(Booking).filter(
        Booking.instructor_id == booking_data.instructor_id,
        Booking.status != BookingStatus.CANCELLED,
        # Check for any overlap with the buffered time range
        ~((Booking.end_time <= buffered_start) | (Booking.start_time >= buffered_end))
    ).first()
    
    if conflicting_booking:
        raise HTTPException(
            status_code=400,
            detail="This time slot conflicts with another booking"
        )
    
    # Calculate total price
    hourly_rate = service.hourly_rate
    total_price = (hourly_rate / 60) * booking_data.duration_minutes
    
    # Set cancellation deadline (24 hours before start time)
    cancellation_deadline = booking_data.start_time - timedelta(hours=24)
    
    # Create the booking
    new_booking = Booking(
        student_id=current_user.id,
        instructor_id=booking_data.instructor_id,
        service_id=booking_data.service_id,
        start_time=booking_data.start_time,
        end_time=end_time,
        duration_minutes=booking_data.duration_minutes,
        original_duration=booking_data.duration_minutes,
        status=BookingStatus.CONFIRMED,
        total_price=total_price,
        cancellation_deadline=cancellation_deadline,
        # Keep timeslot_id for now - we'll remove it in a future migration
        timeslot_id=availability_windows.id if availability_windows else None
    )
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    # Prepare response with related data
    new_booking = db.query(Booking).options(
        joinedload(Booking.service),
        joinedload(Booking.instructor),
        joinedload(Booking.student)
    ).filter(Booking.id == new_booking.id).first()

    return new_booking

@router.get("/my-bookings", response_model=BookingListResponse)
def get_my_bookings(
    role: Optional[str] = Query(None, description="Filter by role: 'student' or 'instructor'"),
    status: Optional[BookingStatus] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all bookings for the current user (as student or instructor)"""
    query = db.query(Booking).options(
        joinedload(Booking.time_slot),
        joinedload(Booking.service),
        joinedload(Booking.instructor),
        joinedload(Booking.student)
    )
    
    # Filter by role
    if role == "student" or (not role and current_user.role == "student"):
        query = query.filter(Booking.student_id == current_user.id)
    elif role == "instructor" or (not role and current_user.role == "instructor"):
        query = query.filter(Booking.instructor_id == current_user.id)
    else:
        # Show all bookings for the user (both as student and instructor)
        query = query.filter(
            (Booking.student_id == current_user.id) | 
            (Booking.instructor_id == current_user.id)
        )
    
    # Filter by status
    if status:
        query = query.filter(Booking.status == status)
    
    # Order by session time
    query = query.join(TimeSlot).order_by(TimeSlot.start_time.desc())
    
    bookings = query.all()
    
    return BookingListResponse(
        bookings=bookings,
        total=len(bookings)
    )

@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific booking"""
    booking = db.query(Booking).options(
        joinedload(Booking.time_slot),
        joinedload(Booking.service),
        joinedload(Booking.instructor),
        joinedload(Booking.student)
    ).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Verify user has access to this booking
    if booking.student_id != current_user.id and booking.instructor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return booking

@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(
    booking_id: int,
    cancel_data: BookingCancel,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancel a booking"""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Verify user has access to cancel
    if booking.student_id != current_user.id and booking.instructor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if already cancelled
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    
    # Check cancellation deadline for students
    if current_user.id == booking.student_id:
        if datetime.utcnow() > booking.cancellation_deadline:
            raise HTTPException(
                status_code=400, 
                detail="Cancellation deadline has passed. Contact instructor directly."
            )
    
    # Update booking
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    booking.cancellation_reason = cancel_data.cancellation_reason
    
    # Make time slot available again
    time_slot = db.query(TimeSlot).filter(TimeSlot.id == booking.timeslot_id).first()
    if time_slot:
        time_slot.is_available = True
    
    db.commit()
    db.refresh(booking)
    
    # Load relationships for response
    booking = db.query(Booking).options(
        joinedload(Booking.time_slot),
        joinedload(Booking.service),
        joinedload(Booking.instructor)
    ).filter(Booking.id == booking.id).first()
    
    return booking

@router.get("/instructors/{instructor_id}/available-slots", response_model=List[AvailableSlotResponse])
def get_instructor_available_slots(
    instructor_id: int,
    start_date: Optional[datetime] = Query(None, description="Filter slots after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter slots before this date"),
    service_id: Optional[int] = Query(None, description="Include pricing for specific service"),
    db: Session = Depends(get_db)
):
    """Get available time slots for an instructor"""
    query = db.query(TimeSlot).filter(
        TimeSlot.instructor_id == instructor_id,
        TimeSlot.is_available == True
    )
    
    if start_date:
        query = query.filter(TimeSlot.start_time >= start_date)
    if end_date:
        query = query.filter(TimeSlot.end_time <= end_date)
    
    # Order by start time
    query = query.order_by(TimeSlot.start_time)
    
    slots = query.all()
    
    # If service_id provided, include pricing
    if service_id:
        service = db.query(Service).filter(Service.id == service_id).first()
        if service:
            return [
                AvailableSlotResponse(
                    id=slot.id,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    service_id=service_id,
                    hourly_rate=service.hourly_rate
                )
                for slot in slots
            ]
    
    return slots