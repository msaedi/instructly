from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from ..database import get_db
from ..auth import get_current_user
from ..models.user import User, UserRole
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..schemas.instructor import (
    InstructorProfileCreate,
    InstructorProfileUpdate,
    InstructorProfileResponse
)
from ..schemas.availability import TimeSlotCreate, TimeSlotUpdate, TimeSlotResponse
from ..models.booking import TimeSlot, Booking, BookingStatus

async def get_current_active_user(
    current_user_email: str = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

router = APIRouter(
    prefix="/instructors",
    tags=["instructors"]
)

@router.get("/", response_model=List[InstructorProfileResponse])
async def get_all_instructors(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    instructors = db.query(InstructorProfile)\
        .options(joinedload(InstructorProfile.user))\
        .offset(skip).limit(limit).all()
    return instructors

@router.post("/profile", response_model=InstructorProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_instructor_profile(
    profile: InstructorProfileCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Check if profile already exists
    existing_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists"
        )
    
    # Create the instructor profile (without services)
    profile_data = profile.model_dump(exclude={'services'})
    db_profile = InstructorProfile(
        user_id=current_user.id,
        **profile_data
    )
    
    db.add(db_profile)
    db.flush()  # Flush to get the profile ID
    
    # Create services
    for service_data in profile.services:
        db_service = Service(
            instructor_profile_id=db_profile.id,
            **service_data.model_dump()
        )
        db.add(db_service)
    
    # Update user role to instructor
    current_user.role = UserRole.INSTRUCTOR
    
    db.commit()
    db.refresh(db_profile)
    db_profile = db.query(InstructorProfile)\
        .options(joinedload(InstructorProfile.user))\
        .options(joinedload(InstructorProfile.services))\
        .filter(InstructorProfile.id == db_profile.id)\
        .first()
    return db_profile

@router.get("/profile", response_model=InstructorProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles"
        )
    
    profile = db.query(InstructorProfile)\
        .options(joinedload(InstructorProfile.user))\
        .options(joinedload(InstructorProfile.services))\
        .filter(InstructorProfile.user_id == current_user.id)\
        .first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    return profile

@router.put("/profile", response_model=InstructorProfileResponse)
async def update_profile(
    profile_update: InstructorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update profiles"
        )
    
    db_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Update basic profile fields
    update_data = profile_update.model_dump(exclude={'services'}, exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_profile, field, value)
    
    # Handle services update if provided
    if profile_update.services is not None:
        # Delete existing services
        db.query(Service).filter(Service.instructor_profile_id == db_profile.id).delete()
        
        # Create new services
        for service_data in profile_update.services:
            db_service = Service(
                instructor_profile_id=db_profile.id,
                **service_data.model_dump()
            )
            db.add(db_service)
    
    db.commit()
    db.refresh(db_profile)
    db_profile = db.query(InstructorProfile)\
        .options(joinedload(InstructorProfile.user))\
        .options(joinedload(InstructorProfile.services))\
        .filter(InstructorProfile.id == db_profile.id)\
        .first()
    return db_profile

@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instructor_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete instructor profile and revert user to student role.
    This will also handle cascading deletes for related data.
    """
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can delete their profiles"
        )
    
    # Get the instructor profile
    db_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Check for active bookings
    active_bookings = db.query(Booking).filter(
        Booking.instructor_id == current_user.id,
        Booking.status != BookingStatus.CANCELLED
    ).count()
    
    if active_bookings > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete profile with {active_bookings} active bookings. Please cancel all bookings first."
        )
    
    # Delete related time slots
    db.query(TimeSlot).filter(TimeSlot.instructor_id == current_user.id).delete()
    
    # Delete the profile (services will be cascade deleted due to relationship)
    db.delete(db_profile)
    
    # Change user role back to student
    current_user.role = UserRole.STUDENT
    
    db.commit()
    
    return {"message": "Instructor profile deleted successfully"}

@router.get("/availability", response_model=List[TimeSlotResponse])
async def get_availability(
    date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get instructor's availability for a specific date or all future slots."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can manage availability"
        )
    
    query = db.query(TimeSlot).filter(TimeSlot.instructor_id == current_user.id)
    
    if date:
        # Get slots for specific date
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())
        query = query.filter(
            TimeSlot.start_time >= start_of_day,
            TimeSlot.start_time <= end_of_day
        )
    else:
        # Get all future slots
        query = query.filter(TimeSlot.start_time >= datetime.now())
    
    slots = query.order_by(TimeSlot.start_time).all()
    return slots

@router.post("/availability", response_model=TimeSlotResponse, status_code=status.HTTP_201_CREATED)
async def create_availability_slot(
    slot_data: TimeSlotCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new availability slot."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can manage availability"
        )
    
    # Validate time slot
    if slot_data.end_time <= slot_data.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time"
        )
    
    # Check for overlapping slots
    overlapping = db.query(TimeSlot).filter(
        TimeSlot.instructor_id == current_user.id,
        TimeSlot.start_time < slot_data.end_time,
        TimeSlot.end_time > slot_data.start_time
    ).first()
    
    if overlapping:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Time slot overlaps with existing slot"
        )
    
    # Create the slot
    db_slot = TimeSlot(
        instructor_id=current_user.id,
        **slot_data.model_dump()
    )
    
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    
    return db_slot

@router.patch("/availability/{slot_id}", response_model=TimeSlotResponse)
async def update_availability_slot(
    slot_id: int,
    slot_update: TimeSlotUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update availability status of a time slot."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can manage availability"
        )
    
    db_slot = db.query(TimeSlot).filter(
        TimeSlot.id == slot_id,
        TimeSlot.instructor_id == current_user.id
    ).first()
    
    if not db_slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time slot not found"
        )
    
    # Check if slot has a booking
    existing_booking = db.query(Booking).filter(
        Booking.timeslot_id == slot_id,
        Booking.status != BookingStatus.CANCELLED
    ).first()
    
    if existing_booking and slot_update.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark slot as available - it has an active booking"
        )
    
    # Update the slot
    update_data = slot_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_slot, field, value)
    
    db.commit()
    db.refresh(db_slot)
    
    return db_slot

@router.delete("/availability/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_availability_slot(
    slot_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an availability slot."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can manage availability"
        )
    
    db_slot = db.query(TimeSlot).filter(
        TimeSlot.id == slot_id,
        TimeSlot.instructor_id == current_user.id
    ).first()
    
    if not db_slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time slot not found"
        )
    
    # Check if slot has a booking
    existing_booking = db.query(Booking).filter(
        Booking.timeslot_id == slot_id,
        Booking.status != BookingStatus.CANCELLED
    ).first()
    
    if existing_booking:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete slot with active booking"
        )
    
    db.delete(db_slot)
    db.commit()
    
    return {"message": "Time slot deleted successfully"}

@router.get("/{instructor_id}", response_model=InstructorProfileResponse)
async def get_instructor_profile(
    instructor_id: int,
    db: Session = Depends(get_db)
):
    profile = db.query(InstructorProfile)\
        .options(joinedload(InstructorProfile.user))\
        .options(joinedload(InstructorProfile.services))\
        .filter(InstructorProfile.id == instructor_id)\
        .first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor profile not found"
        )
    
    return profile