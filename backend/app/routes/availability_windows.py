# app/routes/availability_windows.py

from datetime import timedelta, datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import date, time

from ..database import get_db
from ..models.user import User
from ..models.instructor import InstructorProfile 
from ..auth import get_current_user  
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
    DayOfWeekEnum,
    DateTimeSlot,
    WeekSpecificScheduleCreate,
    CopyWeekRequest,
    ApplyToDateRangeRequest
)

from .instructors import get_current_active_user

router = APIRouter(prefix="/instructors/availability-windows", tags=["availability-windows"])

def verify_instructor(current_user: User) -> User:
    """Verify the current user is an instructor"""
    if current_user.role != "instructor":
        raise HTTPException(status_code=403, detail="Only instructors can manage availability windows")
    return current_user

@router.get("/week")
async def get_week_availability(
    start_date: date = Query(..., description="Monday of the week"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get availability for a specific week, combining specific dates and recurring schedule"""
    
    # Ensure we have instructor profile
    instructor_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not instructor_profile:
        raise HTTPException(status_code=404, detail="Instructor profile not found")
    
    # Calculate week dates (Monday to Sunday)
    week_dates = []
    for i in range(7):
        week_dates.append(start_date + timedelta(days=i))
    
    # Get specific date availability for this week
    specific_availability = db.query(AvailabilityWindow).filter(
        and_(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.specific_date.in_(week_dates),
        )
    ).all()
    
    # Get recurring availability
    recurring_availability = db.query(AvailabilityWindow).filter(
        and_(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.day_of_week.isnot(None),
            AvailabilityWindow.is_recurring == True,
            AvailabilityWindow.is_available == True
        )
    ).all()
    
    # Build response combining both
    week_schedule = {}
    days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    for i, date_obj in enumerate(week_dates):
        date_str = date_obj.isoformat()
        day_name = days_of_week[i]
        
        # Check for specific date first
        specific_slots = [
            {
                "start_time": aw.start_time.strftime("%H:%M:%S"),
                "end_time": aw.end_time.strftime("%H:%M:%S"),
                "is_available": aw.is_available
            }
            for aw in specific_availability 
            if aw.specific_date == date_obj
        ]
        
        specific_entries = [
            aw for aw in specific_availability 
            if aw.specific_date == date_obj
        ]

        if specific_entries:
            # If there are specific entries, only show the available ones
            specific_slots = [
                {
                    "start_time": aw.start_time.strftime("%H:%M:%S"),
                    "end_time": aw.end_time.strftime("%H:%M:%S"),
                    "is_available": aw.is_available
                }
                for aw in specific_entries 
                if aw.is_available == True
            ]
            if specific_slots:
                week_schedule[date_str] = specific_slots
            # If no available slots, the day remains empty (cleared)
        else:
            # Fall back to recurring schedule only if NO specific date entry exists
            recurring_slots = [
                {
                    "start_time": aw.start_time.strftime("%H:%M:%S"),
                    "end_time": aw.end_time.strftime("%H:%M:%S"),
                    "is_available": aw.is_available
                }
                for aw in recurring_availability 
                if aw.day_of_week == day_name
            ]
            if recurring_slots:
                week_schedule[date_str] = recurring_slots
    
    return week_schedule

@router.post("/week")
async def save_week_availability(
    week_data: WeekSpecificScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Save availability for specific dates in a week"""
    
    # Ensure instructor profile exists
    instructor_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not instructor_profile:
        raise HTTPException(status_code=404, detail="Instructor profile not found")
    
    # Extract all dates from the schedule
    dates_in_schedule = [slot.date for slot in week_data.schedule]
    
    if week_data.clear_existing:
        # Get ALL dates for this week, not just the ones in the schedule
        if dates_in_schedule:
            # Calculate the Monday of the week
            first_date = min(dates_in_schedule)
            monday = first_date - timedelta(days=first_date.weekday())
            
            # Get all 7 days of the week
            week_dates = []
            for i in range(7):
                week_dates.append(monday + timedelta(days=i))
            
            # Clear ALL existing specific date availability for the entire week
            db.query(AvailabilityWindow).filter(
                and_(
                    AvailabilityWindow.instructor_id == current_user.id,
                    AvailabilityWindow.specific_date.in_(week_dates)
                )
            ).delete(synchronize_session=False)
    
    # Create new availability windows
    new_windows = []
    for slot in week_data.schedule:
        new_window = AvailabilityWindow(
            instructor_id=current_user.id,
            specific_date=slot.date,
            start_time=slot.start_time,  # Already a time object
            end_time=slot.end_time,      # Already a time object
            is_recurring=False,
            is_available=slot.is_available
        )
        new_windows.append(new_window)
        db.add(new_window)
    
    try:
        db.commit()
        # Return the saved week schedule
        # If no dates in schedule (cleared week), use the Monday of the current week
        if dates_in_schedule:
            monday = min(dates_in_schedule) - timedelta(days=min(dates_in_schedule).weekday())
        else:
            # Get current Monday from the request or use this week's Monday
            today = date.today()
            monday = today - timedelta(days=today.weekday())
        
        return await get_week_availability(
            start_date=monday,
            current_user=current_user,
            db=db
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/copy-week")
async def copy_week_availability(
    copy_data: CopyWeekRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Copy availability from one week to another"""
    
    # First, clear the target week completely
    target_week_dates = []
    for i in range(7):
        target_week_dates.append(copy_data.to_week_start + timedelta(days=i))
    
    # Delete ALL existing entries for the target week
    db.query(AvailabilityWindow).filter(
        and_(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.specific_date.in_(target_week_dates)
        )
    ).delete(synchronize_session=False)
    
    # Get source week availability
    source_week = await get_week_availability(
        start_date=copy_data.from_week_start,
        current_user=current_user,
        db=db
    )
    
    # Create schedule to copy
    schedule_to_create = []
    
    for i in range(7):
        source_date = copy_data.from_week_start + timedelta(days=i)
        target_date = copy_data.to_week_start + timedelta(days=i)
        
        source_date_str = source_date.isoformat()
        
        if source_date_str in source_week:
            # Copy each time slot
            for slot in source_week[source_date_str]:
                start_time = datetime.strptime(slot['start_time'], "%H:%M:%S").time()
                end_time = datetime.strptime(slot['end_time'], "%H:%M:%S").time()
                
                schedule_to_create.append(DateTimeSlot(
                    date=target_date,
                    start_time=start_time,
                    end_time=end_time,
                    is_available=slot['is_available']
                ))
        else:
            # IMPORTANT: Add unavailable marker for days with no slots
            schedule_to_create.append(DateTimeSlot(
                date=target_date,
                start_time=time(0, 0),  # midnight
                end_time=time(0, 1),    # 00:01
                is_available=False
            ))
    
    # Save the copied schedule
    week_data = WeekSpecificScheduleCreate(
        schedule=schedule_to_create,
        clear_existing=False  # We already cleared above
    )
    return await save_week_availability(week_data, current_user, db)

@router.post("/apply-to-date-range")
async def apply_to_date_range(
    apply_data: ApplyToDateRangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Apply a week's pattern to a date range"""
    
    # Get source week availability
    source_week = await get_week_availability(
        start_date=apply_data.from_week_start,
        current_user=current_user,
        db=db
    )
    
    # Create a pattern from the source week
    days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    week_pattern = {}
    
    for i in range(7):
        source_date = apply_data.from_week_start + timedelta(days=i)
        source_date_str = source_date.isoformat()
        day_name = days_of_week[i]
        
        if source_date_str in source_week:
            week_pattern[day_name] = source_week[source_date_str]
    
    # Apply pattern to date range
    current_date = apply_data.start_date
    all_slots = []
    
    while current_date <= apply_data.end_date:
        day_name = days_of_week[current_date.weekday()]
        
        if day_name in week_pattern:
            for slot in week_pattern[day_name]:
                start_time = datetime.strptime(slot['start_time'], "%H:%M:%S").time()
                end_time = datetime.strptime(slot['end_time'], "%H:%M:%S").time()
                
                all_slots.append(DateTimeSlot(
                    date=current_date,
                    start_time=start_time,
                    end_time=end_time,
                    is_available=slot['is_available']
                ))
        else:
            # Add unavailable marker for days with no pattern
            all_slots.append(DateTimeSlot(
                date=current_date,
                start_time=time(0, 0),
                end_time=time(0, 1),
                is_available=False
            ))
        
        current_date += timedelta(days=1)
    
    # Clear existing availability in the date range
    db.query(AvailabilityWindow).filter(
        and_(
            AvailabilityWindow.instructor_id == current_user.id,
            AvailabilityWindow.specific_date >= apply_data.start_date,
            AvailabilityWindow.specific_date <= apply_data.end_date
        )
    ).delete(synchronize_session=False)
    
    # Save all new slots
    for slot in all_slots:
        new_window = AvailabilityWindow(
            instructor_id=current_user.id,
            specific_date=slot.date,
            start_time=slot.start_time,  # Already a time object
            end_time=slot.end_time,      # Already a time object
            is_recurring=False,
            is_available=slot.is_available
        )
        db.add(new_window)
    
    try:
        db.commit()
        return {
            "message": f"Successfully applied schedule to {len(all_slots)} days",
            "start_date": apply_data.start_date.isoformat(),
            "end_date": apply_data.end_date.isoformat(),
            "slots_created": len(all_slots)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


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