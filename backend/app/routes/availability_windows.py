# app/routes/availability_windows.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, time

from ..database import get_db
from ..models.user import User
from ..models.availability import AvailabilityWindow, BlackoutDate, DayOfWeek
from ..schemas.availability_window import (
    RecurringAvailabilityCreate,
    SpecificDateAvailabilityCreate,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    WeeklyScheduleCreate,
    WeeklyScheduleResponse,
    BlackoutDateCreate,
    BlackoutDateResponse,
    ApplyPresetRequest,
    AvailabilityPreset,
    DayOfWeekEnum
)
from .instructors import get_current_active_user

router = APIRouter(prefix="/instructors/availability-windows", tags=["availability-windows"])

def verify_instructor(current_user: User) -> User:
    """Verify the current user is an instructor"""
    if current_user.role != "instructor":
        raise HTTPException(status_code=403, detail="Only instructors can manage availability windows")
    return current_user

@router.get("/weekly", response_model=WeeklyScheduleResponse)
def get_weekly_schedule(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get instructor's weekly recurring availability"""
    instructor = verify_instructor(current_user)
    
    # Get all recurring availability windows
    windows = db.query(AvailabilityWindow).filter(
        AvailabilityWindow.instructor_id == current_user.id,
        AvailabilityWindow.is_recurring == True,
        AvailabilityWindow.day_of_week.isnot(None)
    ).all()
    
    # Organize by day of week
    schedule = WeeklyScheduleResponse()
    for window in windows:
        # When reading, window.day_of_week might be string or enum
        if hasattr(window.day_of_week, 'value'):
            day_name = window.day_of_week.value
        else:
            day_name = window.day_of_week
        getattr(schedule, day_name).append(AvailabilityWindowResponse.from_orm(window))
    
    return schedule

@router.post("/weekly", response_model=WeeklyScheduleResponse)
def set_weekly_schedule(
    schedule_data: WeeklyScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Set instructor's weekly recurring availability (replaces existing if specified)"""
    instructor = verify_instructor(current_user)
    
    # Clear existing recurring availability if requested
    if schedule_data.clear_existing:
        db.query(AvailabilityWindow).filter(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.is_recurring == True
        ).delete()
    
    # Create new availability windows
    for window_data in schedule_data.schedule:
        # Ensure we're using lowercase day values
        day_value = window_data.day_of_week
        if hasattr(day_value, 'value'):
            day_value = day_value.value
        else:
            day_value = str(day_value).lower()
        
        window = AvailabilityWindow(
            instructor_id=current_user.id,
            day_of_week=day_value,  # This should be a lowercase string
            start_time=window_data.start_time,
            end_time=window_data.end_time,
            is_available=window_data.is_available,
            is_recurring=True
        )
        db.add(window)
    
    db.commit()
    
    # Return the updated schedule
    return get_weekly_schedule(current_user, db)

@router.post("/preset", response_model=WeeklyScheduleResponse)
def apply_preset_schedule(
    preset_data: ApplyPresetRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Apply a preset schedule template"""
    instructor = verify_instructor(current_user)
    
    # Clear existing if requested
    if preset_data.clear_existing:
        db.query(AvailabilityWindow).filter(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.is_recurring == True
        ).delete()
    
    # Define preset schedules with DayOfWeek enum values
    presets = {
        AvailabilityPreset.WEEKDAY_9_TO_5: [
            (DayOfWeek.MONDAY, time(9, 0), time(17, 0)),
            (DayOfWeek.TUESDAY, time(9, 0), time(17, 0)),
            (DayOfWeek.WEDNESDAY, time(9, 0), time(17, 0)),
            (DayOfWeek.THURSDAY, time(9, 0), time(17, 0)),
            (DayOfWeek.FRIDAY, time(9, 0), time(17, 0)),
        ],
        AvailabilityPreset.MORNINGS_ONLY: [
            (DayOfWeek.MONDAY, time(8, 0), time(12, 0)),
            (DayOfWeek.TUESDAY, time(8, 0), time(12, 0)),
            (DayOfWeek.WEDNESDAY, time(8, 0), time(12, 0)),
            (DayOfWeek.THURSDAY, time(8, 0), time(12, 0)),
            (DayOfWeek.FRIDAY, time(8, 0), time(12, 0)),
            (DayOfWeek.SATURDAY, time(8, 0), time(12, 0)),
        ],
        AvailabilityPreset.EVENINGS_ONLY: [
            (DayOfWeek.MONDAY, time(17, 0), time(21, 0)),
            (DayOfWeek.TUESDAY, time(17, 0), time(21, 0)),
            (DayOfWeek.WEDNESDAY, time(17, 0), time(21, 0)),
            (DayOfWeek.THURSDAY, time(17, 0), time(21, 0)),
            (DayOfWeek.FRIDAY, time(17, 0), time(21, 0)),
        ],
        AvailabilityPreset.WEEKENDS_ONLY: [
            (DayOfWeek.SATURDAY, time(9, 0), time(17, 0)),
            (DayOfWeek.SUNDAY, time(9, 0), time(17, 0)),
        ],
    }
    
    # Apply the selected preset
    preset_schedule = presets.get(preset_data.preset)
    if not preset_schedule:
        raise HTTPException(status_code=400, detail="Invalid preset")
    
    # Debug logging
    print(f"Applying preset: {preset_data.preset}")
    
    for day_enum, start, end in preset_schedule:
        # IMPORTANT: Use .value to get the lowercase string
        print(f"Creating window for day: {day_enum} (value: {day_enum.value})")
        
        window = AvailabilityWindow(
            instructor_id=current_user.id,
            day_of_week=day_enum.value,  # USE .value HERE!
            start_time=start,
            end_time=end,
            is_available=True,
            is_recurring=True
        )
        db.add(window)
    
    db.commit()
    return get_weekly_schedule(current_user, db)

@router.post("/specific-date", response_model=AvailabilityWindowResponse)
def add_specific_date_availability(
    availability_data: SpecificDateAvailabilityCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Add availability for a specific date (one-time)"""
    instructor = verify_instructor(current_user)
    
    # Check if there's already a specific date entry
    existing = db.query(AvailabilityWindow).filter(
        AvailabilityWindow.instructor_id == current_user.id,
        AvailabilityWindow.specific_date == availability_data.specific_date,
        AvailabilityWindow.start_time == availability_data.start_time
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Availability already exists for this date and time")
    
    window = AvailabilityWindow(
        instructor_id=current_user.id,
        specific_date=availability_data.specific_date,
        start_time=availability_data.start_time,
        end_time=availability_data.end_time,
        is_available=availability_data.is_available,
        is_recurring=False
    )
    
    db.add(window)
    db.commit()
    db.refresh(window)
    
    return window

@router.get("/", response_model=List[AvailabilityWindowResponse])
def get_all_availability(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all availability windows (both recurring and specific dates)"""
    instructor = verify_instructor(current_user)
    
    query = db.query(AvailabilityWindow).filter(
        AvailabilityWindow.instructor_id == current_user.id
    )
    
    if start_date and end_date:
        # For specific date windows in range
        query = query.filter(
            (AvailabilityWindow.specific_date >= start_date) & 
            (AvailabilityWindow.specific_date <= end_date) |
            (AvailabilityWindow.is_recurring == True)
        )
    
    return query.all()

@router.patch("/{window_id}", response_model=AvailabilityWindowResponse)
def update_availability_window(
    window_id: int,
    update_data: AvailabilityWindowUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update an availability window"""
    instructor = verify_instructor(current_user)
    
    window = db.query(AvailabilityWindow).filter(
        AvailabilityWindow.id == window_id,
        AvailabilityWindow.instructor_id == current_user.id
    ).first()
    
    if not window:
        raise HTTPException(status_code=404, detail="Availability window not found")
    
    # Update fields if provided
    if update_data.start_time is not None:
        window.start_time = update_data.start_time
    if update_data.end_time is not None:
        window.end_time = update_data.end_time
    if update_data.is_available is not None:
        window.is_available = update_data.is_available
    
    db.commit()
    db.refresh(window)
    
    return window

@router.delete("/{window_id}")
def delete_availability_window(
    window_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an availability window"""
    instructor = verify_instructor(current_user)
    
    window = db.query(AvailabilityWindow).filter(
        AvailabilityWindow.id == window_id,
        AvailabilityWindow.instructor_id == current_user.id
    ).first()
    
    if not window:
        raise HTTPException(status_code=404, detail="Availability window not found")
    
    db.delete(window)
    db.commit()
    
    return {"message": "Availability window deleted"}

# Blackout dates endpoints
@router.get("/blackout-dates", response_model=List[BlackoutDateResponse])
def get_blackout_dates(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get instructor's blackout dates"""
    instructor = verify_instructor(current_user)
    
    return db.query(BlackoutDate).filter(
        BlackoutDate.instructor_id == current_user.id,
        BlackoutDate.date >= date.today()
    ).order_by(BlackoutDate.date).all()

@router.post("/blackout-dates", response_model=BlackoutDateResponse)
def add_blackout_date(
    blackout_data: BlackoutDateCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Add a blackout date (vacation/unavailable)"""
    instructor = verify_instructor(current_user)
    
    # Check if already exists
    existing = db.query(BlackoutDate).filter(
        BlackoutDate.instructor_id == current_user.id,
        BlackoutDate.date == blackout_data.date
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Blackout date already exists")
    
    blackout = BlackoutDate(
        instructor_id=current_user.id,
        date=blackout_data.date,
        reason=blackout_data.reason
    )
    
    db.add(blackout)
    db.commit()
    db.refresh(blackout)
    
    return blackout

@router.delete("/blackout-dates/{blackout_id}")
def delete_blackout_date(
    blackout_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a blackout date"""
    instructor = verify_instructor(current_user)
    
    blackout = db.query(BlackoutDate).filter(
        BlackoutDate.id == blackout_id,
        BlackoutDate.instructor_id == current_user.id
    ).first()
    
    if not blackout:
        raise HTTPException(status_code=404, detail="Blackout date not found")
    
    db.delete(blackout)
    db.commit()
    
    return {"message": "Blackout date deleted"}