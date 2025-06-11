# app/routes/availability_windows.py

import logging
from datetime import timedelta, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict
from datetime import date, time

from ..database import get_db
from ..models.user import User
from ..models.instructor import InstructorProfile 
from ..models.availability import (
    RecurringAvailability, 
    SpecificDateAvailability, 
    DateTimeSlot as DateTimeSlotModel,
    BlackoutDate, 
)
from ..schemas.availability_window import (
    SpecificDateAvailabilityCreate,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    WeeklyScheduleCreate,
    WeeklyScheduleResponse,
    BlackoutDateCreate,
    BlackoutDateResponse,
    ApplyPresetRequest,
    AvailabilityPreset,
    WeekSpecificScheduleCreate,
    CopyWeekRequest,
    ApplyToDateRangeRequest
)
from ..utils.time_helpers import time_to_string, string_to_time
from .instructors import get_current_active_user
from ..core.constants import (
    ERROR_INSTRUCTOR_ONLY,
    ERROR_INSTRUCTOR_NOT_FOUND,
    ERROR_INVALID_TIME_RANGE,
    ERROR_OVERLAPPING_SLOT,
    DAYS_OF_WEEK
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instructors/availability-windows", tags=["availability-windows"])

def verify_instructor(current_user: User) -> User:
    """
    Verify the current user is an instructor.
    
    Args:
        current_user: The authenticated user
        
    Returns:
        User: The verified instructor user
        
    Raises:
        HTTPException: If user is not an instructor
    """
    if current_user.role != "instructor":
        logger.warning(f"Non-instructor user {current_user.email} attempted to access instructor-only endpoint")
        raise HTTPException(status_code=403, detail=ERROR_INSTRUCTOR_ONLY)
    return current_user

@router.get("/week")
async def get_week_availability(
    start_date: date = Query(..., description="Monday of the week"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get availability for a specific week, combining specific dates and recurring schedule.
    
    This endpoint returns a week view of availability, showing time slots for each day.
    It combines recurring weekly patterns with date-specific overrides.
    
    Args:
        start_date: The Monday of the week to retrieve
        current_user: The authenticated user
        db: Database session
        
    Returns:
        Dict[str, List]: Dictionary mapping date strings to lists of time slots
        
    Raises:
        HTTPException: If instructor profile not found
    """
    logger.info(f"Getting week availability for instructor {current_user.id} starting {start_date}")
    
    # Ensure we have instructor profile
    instructor_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not instructor_profile:
        logger.error(f"Instructor profile not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail=ERROR_INSTRUCTOR_NOT_FOUND)
    
    # Calculate week dates (Monday to Sunday)
    week_dates = []
    for i in range(7):
        week_dates.append(start_date + timedelta(days=i))
    
    logger.debug(f"Week dates: {[d.isoformat() for d in week_dates]}")
    
    # Get specific date availability for this week
    specific_dates = db.query(SpecificDateAvailability).filter(
        and_(
            SpecificDateAvailability.instructor_id == current_user.id,
            SpecificDateAvailability.date.in_(week_dates)
        )
    ).options(joinedload(SpecificDateAvailability.time_slots)).all()
    
    logger.debug(f"Found {len(specific_dates)} specific date entries for the week")
    
    # Create a map of date to specific availability
    specific_date_map = {sd.date: sd for sd in specific_dates}
    
    # Get recurring availability
    recurring_availability = db.query(RecurringAvailability).filter(
        RecurringAvailability.instructor_id == current_user.id
    ).all()
    
    logger.debug(f"Found {len(recurring_availability)} recurring availability entries")
    
    # Create a map of day_of_week to recurring slots
    recurring_map = {}
    for ra in recurring_availability:
        if ra.day_of_week not in recurring_map:
            recurring_map[ra.day_of_week] = []
        recurring_map[ra.day_of_week].append(ra)
    
    # Build response combining both
    week_schedule = {}
    
    for i, date_obj in enumerate(week_dates):
        date_str = date_obj.isoformat()
        day_name = DAYS_OF_WEEK[i]
        
        # Check for specific date override
        if date_obj in specific_date_map:
            specific_entry = specific_date_map[date_obj]
            
            # Check if day is explicitly cleared
            if specific_entry.is_cleared:
                logger.debug(f"Day {date_str} is explicitly cleared")
                continue
            
            # Use specific date time slots
            if specific_entry.time_slots:
                week_schedule[date_str] = [
                    {
                        "start_time": time_to_string(slot.start_time),
                        "end_time": time_to_string(slot.end_time),
                        "is_available": True
                    }
                    for slot in specific_entry.time_slots
                ]
                logger.debug(f"Using {len(specific_entry.time_slots)} specific slots for {date_str}")
        else:
            # Fall back to recurring schedule
            if day_name in recurring_map:
                week_schedule[date_str] = [
                    {
                        "start_time": time_to_string(ra.start_time),
                        "end_time": time_to_string(ra.end_time),
                        "is_available": True
                    }
                    for ra in recurring_map[day_name]
                ]
                logger.debug(f"Using {len(recurring_map[day_name])} recurring slots for {date_str}")
    
    logger.info(f"Returning week schedule with {len(week_schedule)} days having availability")
    return week_schedule

@router.post("/week")
async def save_week_availability(
    week_data: WeekSpecificScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Save availability for specific dates in a week.
    
    This endpoint allows instructors to set their availability for specific dates,
    overriding any recurring patterns. Days without slots will be marked as cleared
    if clear_existing is True.
    
    Args:
        week_data: The week schedule data to save
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict[str, List]: The updated week availability
        
    Raises:
        HTTPException: If instructor profile not found or database error
    """
    logger.info(f"Saving week availability for instructor {current_user.id}")
    logger.debug(f"Schedule has {len(week_data.schedule)} entries, clear_existing={week_data.clear_existing}")
    
    # Ensure instructor profile exists
    instructor_profile = db.query(InstructorProfile).filter(
        InstructorProfile.user_id == current_user.id
    ).first()
    
    if not instructor_profile:
        logger.error(f"Instructor profile not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail=ERROR_INSTRUCTOR_NOT_FOUND)
    
    # Determine which week we're working with
    if week_data.week_start:
        monday = week_data.week_start
    elif week_data.schedule:
        # Get Monday from the first date in schedule
        first_date = min(slot.date for slot in week_data.schedule)
        monday = first_date - timedelta(days=first_date.weekday())
    else:
        # Fallback to current week
        today = date.today()
        monday = today - timedelta(days=today.weekday())
    
    logger.debug(f"Working with week starting {monday}")
    
    # Calculate all week dates
    week_dates = [monday + timedelta(days=i) for i in range(7)]
    
    if week_data.clear_existing:
        # Delete existing specific date entries for this week
        deleted_count = db.query(SpecificDateAvailability).filter(
            and_(
                SpecificDateAvailability.instructor_id == current_user.id,
                SpecificDateAvailability.date.in_(week_dates)
            )
        ).delete(synchronize_session=False)
        logger.info(f"Deleted {deleted_count} existing entries for the week")
    
    # Group schedule by date
    schedule_by_date = {}
    for slot in week_data.schedule:
        if slot.date not in schedule_by_date:
            schedule_by_date[slot.date] = []
        schedule_by_date[slot.date].append(slot)
    
    # Process each day of the week
    dates_created = 0
    slots_created = 0
    
    for week_date in week_dates:
        if week_date in schedule_by_date:
            # Day has time slots
            specific_date = SpecificDateAvailability(
                instructor_id=current_user.id,
                date=week_date,
                is_cleared=False
            )
            db.add(specific_date)
            db.flush()  # Get the ID
            dates_created += 1
            
            # Add time slots
            for slot in schedule_by_date[week_date]:
                time_slot = DateTimeSlotModel(
                    date_override_id=specific_date.id,
                    start_time=slot.start_time,
                    end_time=slot.end_time
                )
                db.add(time_slot)
                slots_created += 1
        else:
            # Day has no slots - check if we should mark it as cleared
            if week_data.clear_existing:
                # Mark as cleared to override recurring schedule
                logger.debug(f"Creating cleared entry for {week_date}")
                specific_date = SpecificDateAvailability(
                    instructor_id=current_user.id,
                    date=week_date,
                    is_cleared=True
                )
                db.add(specific_date)
                dates_created += 1
    
    try:
        db.commit()
        logger.info(f"Successfully saved week availability: {dates_created} dates, {slots_created} slots")
        return await get_week_availability(
            start_date=monday,
            current_user=current_user,
            db=db
        )
    except Exception as e:
        logger.error(f"Error saving week availability: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/copy-week")
async def copy_week_availability(
    copy_data: CopyWeekRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Copy availability from one week to another.
    
    This endpoint copies all availability patterns from a source week to a target week,
    including both time slots and cleared days.
    
    Args:
        copy_data: Source and target week information
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict[str, List]: The updated target week availability
        
    Raises:
        HTTPException: If database error occurs
    """
    logger.info(f"Copying week availability for instructor {current_user.id} from {copy_data.from_week_start} to {copy_data.to_week_start}")
    
    # Calculate target week dates
    target_week_dates = [copy_data.to_week_start + timedelta(days=i) for i in range(7)]
    
    # Delete ALL existing entries for the target week
    deleted_count = db.query(SpecificDateAvailability).filter(
        and_(
            SpecificDateAvailability.instructor_id == current_user.id,
            SpecificDateAvailability.date.in_(target_week_dates)
        )
    ).delete(synchronize_session=False)
    
    logger.debug(f"Deleted {deleted_count} existing entries in target week")
    
    # Get source week availability
    source_week = await get_week_availability(
        start_date=copy_data.from_week_start,
        current_user=current_user,
        db=db
    )
    
    # Copy each day
    dates_created = 0
    slots_created = 0
    
    for i in range(7):
        source_date = copy_data.from_week_start + timedelta(days=i)
        target_date = copy_data.to_week_start + timedelta(days=i)
        source_date_str = source_date.isoformat()
        
        if source_date_str in source_week and source_week[source_date_str]:
            # Copy time slots
            specific_date = SpecificDateAvailability(
                instructor_id=current_user.id,
                date=target_date,
                is_cleared=False
            )
            db.add(specific_date)
            db.flush()
            dates_created += 1
            
            for slot in source_week[source_date_str]:
                time_slot = DateTimeSlotModel(
                    date_override_id=specific_date.id,
                    start_time=string_to_time(slot['start_time']),
                    end_time=string_to_time(slot['end_time'])
                )
                db.add(time_slot)
                slots_created += 1
        else:
            # Source day has no slots - mark target as cleared
            specific_date = SpecificDateAvailability(
                instructor_id=current_user.id,
                date=target_date,
                is_cleared=True
            )
            db.add(specific_date)
            dates_created += 1
    
    try:
        db.commit()
        logger.info(f"Successfully copied week: {dates_created} dates, {slots_created} slots")
        return await get_week_availability(
            start_date=copy_data.to_week_start,
            current_user=current_user,
            db=db
        )
    except Exception as e:
        logger.error(f"Error copying week availability: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/apply-to-date-range")
async def apply_to_date_range(
    apply_data: ApplyToDateRangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Apply a week's pattern to a date range.
    
    This endpoint takes a source week's availability pattern and applies it
    repeatedly to all weeks within the specified date range.
    
    Args:
        apply_data: Source week and date range information
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict: Summary of the operation including dates affected
        
    Raises:
        HTTPException: If database error occurs
    """
    logger.info(f"Applying week pattern for instructor {current_user.id} from {apply_data.from_week_start} to range {apply_data.start_date} - {apply_data.end_date}")
    
    # Get source week availability
    source_week = await get_week_availability(
        start_date=apply_data.from_week_start,
        current_user=current_user,
        db=db
    )
    
    # Create a pattern from the source week
    week_pattern = {}
    
    for i in range(7):
        source_date = apply_data.from_week_start + timedelta(days=i)
        source_date_str = source_date.isoformat()
        day_name = DAYS_OF_WEEK[i]
        
        if source_date_str in source_week:
            week_pattern[day_name] = source_week[source_date_str]
    
    logger.debug(f"Created pattern with availability for days: {list(week_pattern.keys())}")
    
    # Clear existing specific date availability in the date range
    deleted_count = db.query(SpecificDateAvailability).filter(
        and_(
            SpecificDateAvailability.instructor_id == current_user.id,
            SpecificDateAvailability.date >= apply_data.start_date,
            SpecificDateAvailability.date <= apply_data.end_date
        )
    ).delete(synchronize_session=False)
    
    logger.info(f"Deleted {deleted_count} existing entries in date range")
    
    # Apply pattern to date range
    current_date = apply_data.start_date
    dates_created = 0
    slots_created = 0
    
    while current_date <= apply_data.end_date:
        day_name = DAYS_OF_WEEK[current_date.weekday()]
        
        if day_name in week_pattern and week_pattern[day_name]:
            # Day has time slots
            specific_date = SpecificDateAvailability(
                instructor_id=current_user.id,
                date=current_date,
                is_cleared=False
            )
            db.add(specific_date)
            db.flush()
            
            # Add time slots
            for slot in week_pattern[day_name]:
                time_slot = DateTimeSlotModel(
                    date_override_id=specific_date.id,
                    start_time=string_to_time(slot['start_time']),
                    end_time=string_to_time(slot['end_time'])
                )
                db.add(time_slot)
                slots_created += 1
        else:
            # Day has no pattern - create cleared entry
            specific_date = SpecificDateAvailability(
                instructor_id=current_user.id,
                date=current_date,
                is_cleared=True
            )
            db.add(specific_date)
        
        dates_created += 1
        current_date += timedelta(days=1)
    
    try:
        db.commit()
        logger.info(f"Successfully applied pattern to {dates_created} days with {slots_created} total slots")
        return {
            "message": f"Successfully applied schedule to {dates_created} days",
            "start_date": apply_data.start_date.isoformat(),
            "end_date": apply_data.end_date.isoformat(),
            "dates_created": dates_created,
            "slots_created": slots_created
        }
    except Exception as e:
        logger.error(f"Error applying pattern to date range: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/weekly", response_model=WeeklyScheduleResponse)
def get_weekly_schedule(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get instructor's weekly recurring availability.
    
    This endpoint returns the instructor's default weekly schedule pattern
    that applies when no specific date overrides exist.
    
    Args:
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        WeeklyScheduleResponse: Organized by day of week
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Getting weekly recurring schedule for instructor {instructor.id}")
    
    # Get all recurring availability
    recurring_slots = db.query(RecurringAvailability).filter(
        RecurringAvailability.instructor_id == current_user.id
    ).all()
    
    logger.debug(f"Found {len(recurring_slots)} recurring availability slots")
    
    # Organize by day of week
    schedule = WeeklyScheduleResponse()
    
    for slot in recurring_slots:
        # Convert day_of_week to the attribute name on the response object
        day_name = slot.day_of_week  # This is already a string like 'monday'
        
        # Create availability window response format
        window_data = {
            "id": slot.id,
            "instructor_id": slot.instructor_id,
            "start_time": time_to_string(slot.start_time),
            "end_time": time_to_string(slot.end_time),
            "is_available": True,
            "is_recurring": True,
            "day_of_week": day_name
        }
        
        # Add to the appropriate day list
        getattr(schedule, day_name).append(window_data)
    
    return schedule

@router.post("/weekly", response_model=WeeklyScheduleResponse)
def set_weekly_schedule(
    schedule_data: WeeklyScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Set instructor's weekly recurring availability.
    
    This endpoint sets the default weekly pattern. If clear_existing is True,
    it replaces all existing recurring availability.
    
    Args:
        schedule_data: The weekly schedule to set
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        WeeklyScheduleResponse: The updated weekly schedule
        
    Raises:
        HTTPException: If database error occurs
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Setting weekly schedule for instructor {instructor.id} with {len(schedule_data.schedule)} slots")
    
    # Clear existing recurring availability if requested
    if schedule_data.clear_existing:
        deleted_count = db.query(RecurringAvailability).filter(
            RecurringAvailability.instructor_id == current_user.id
        ).delete()
        logger.info(f"Cleared {deleted_count} existing recurring slots")
    
    # Create new recurring availability entries
    for window_data in schedule_data.schedule:
        # Ensure we're using lowercase day values
        day_value = window_data.day_of_week
        if hasattr(day_value, 'value'):
            day_value = day_value.value
        else:
            day_value = str(day_value).lower()
        
        logger.debug(f"Creating recurring slot for {day_value}: {window_data.start_time} - {window_data.end_time}")
        
        recurring_slot = RecurringAvailability(
            instructor_id=current_user.id,
            day_of_week=day_value,
            start_time=window_data.start_time,
            end_time=window_data.end_time
        )
        db.add(recurring_slot)
    
    try:
        db.commit()
        logger.info(f"Successfully set weekly schedule with {len(schedule_data.schedule)} slots")
        # Return the updated schedule
        return get_weekly_schedule(current_user, db)
    except Exception as e:
        logger.error(f"Error setting weekly schedule: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/preset", response_model=WeeklyScheduleResponse)
def apply_preset_schedule(
    preset_data: ApplyPresetRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Apply a preset schedule template.
    
    Available presets:
    - weekday_9_to_5: Monday-Friday 9:00-17:00
    - mornings_only: All days 8:00-12:00
    - evenings_only: All days 17:00-21:00
    - weekends_only: Saturday-Sunday 9:00-17:00
    
    Args:
        preset_data: The preset to apply
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        WeeklyScheduleResponse: The updated weekly schedule
        
    Raises:
        HTTPException: If invalid preset or database error
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Applying preset {preset_data.preset} for instructor {instructor.id}")
    
    # Clear existing if requested
    if preset_data.clear_existing:
        deleted_count = db.query(RecurringAvailability).filter(
            RecurringAvailability.instructor_id == current_user.id
        ).delete()
        logger.info(f"Cleared {deleted_count} existing recurring slots")
    
    # Define preset schedules with day strings
    presets = {
        AvailabilityPreset.WEEKDAY_9_TO_5: [
            ('monday', time(9, 0), time(17, 0)),
            ('tuesday', time(9, 0), time(17, 0)),
            ('wednesday', time(9, 0), time(17, 0)),
            ('thursday', time(9, 0), time(17, 0)),
            ('friday', time(9, 0), time(17, 0)),
        ],
        AvailabilityPreset.MORNINGS_ONLY: [
            ('monday', time(8, 0), time(12, 0)),
            ('tuesday', time(8, 0), time(12, 0)),
            ('wednesday', time(8, 0), time(12, 0)),
            ('thursday', time(8, 0), time(12, 0)),
            ('friday', time(8, 0), time(12, 0)),
            ('saturday', time(8, 0), time(12, 0)),
            ('sunday', time(8, 0), time(12, 0)),
        ],
        AvailabilityPreset.EVENINGS_ONLY: [
            ('monday', time(17, 0), time(21, 0)),
            ('tuesday', time(17, 0), time(21, 0)),
            ('wednesday', time(17, 0), time(21, 0)),
            ('thursday', time(17, 0), time(21, 0)),
            ('friday', time(17, 0), time(21, 0)),
            ('saturday', time(17, 0), time(21, 0)),
            ('sunday', time(17, 0), time(21, 0)),
        ],
        AvailabilityPreset.WEEKENDS_ONLY: [
            ('saturday', time(9, 0), time(17, 0)),
            ('sunday', time(9, 0), time(17, 0)),
        ],
    }
    
    # Apply the selected preset
    preset_schedule = presets.get(preset_data.preset)
    if not preset_schedule:
        logger.error(f"Invalid preset requested: {preset_data.preset}")
        raise HTTPException(status_code=400, detail="Invalid preset")
    
    slots_created = 0
    for day_str, start, end in preset_schedule:
        logger.debug(f"Creating preset slot for {day_str}: {start} - {end}")
        
        recurring_slot = RecurringAvailability(
            instructor_id=current_user.id,
            day_of_week=day_str,
            start_time=start,
            end_time=end
        )
        db.add(recurring_slot)
        slots_created += 1
    
    try:
        db.commit()
        logger.info(f"Successfully applied preset {preset_data.preset} with {slots_created} slots")
        return get_weekly_schedule(current_user, db)
    except Exception as e:
        logger.error(f"Error applying preset schedule: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/specific-date", response_model=AvailabilityWindowResponse)
def add_specific_date_availability(
    availability_data: SpecificDateAvailabilityCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Add availability for a specific date (one-time).
    
    This creates a date-specific override that takes precedence over
    recurring availability for that date.
    
    Args:
        availability_data: The specific date and time slot
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        AvailabilityWindowResponse: The created availability slot
        
    Raises:
        HTTPException: If slot already exists or database error
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Adding specific date availability for instructor {instructor.id} on {availability_data.specific_date}")
    
    # Check if there's already a specific date entry for this date
    existing = db.query(SpecificDateAvailability).filter(
        SpecificDateAvailability.instructor_id == current_user.id,
        SpecificDateAvailability.date == availability_data.specific_date
    ).first()
    
    if existing and not existing.is_cleared:
        # Check if this exact time slot already exists
        existing_slot = db.query(DateTimeSlotModel).filter(
            DateTimeSlotModel.date_override_id == existing.id,
            DateTimeSlotModel.start_time == availability_data.start_time,
            DateTimeSlotModel.end_time == availability_data.end_time
        ).first()
        
        if existing_slot:
            logger.warning(f"Time slot already exists for {availability_data.specific_date}")
            raise HTTPException(status_code=400, detail=ERROR_OVERLAPPING_SLOT)
    
    # Create or get the specific date entry
    if not existing:
        specific_date = SpecificDateAvailability(
            instructor_id=current_user.id,
            date=availability_data.specific_date,
            is_cleared=False
        )
        db.add(specific_date)
        db.flush()
        logger.debug(f"Created new specific date entry for {availability_data.specific_date}")
    else:
        specific_date = existing
        # If it was cleared, unclear it
        if specific_date.is_cleared:
            specific_date.is_cleared = False
            logger.debug(f"Uncleared previously cleared date {availability_data.specific_date}")
    
    # Add the time slot
    time_slot = DateTimeSlotModel(
        date_override_id=specific_date.id,
        start_time=availability_data.start_time,
        end_time=availability_data.end_time
    )
    db.add(time_slot)
    
    try:
        db.commit()
        db.refresh(specific_date)
        logger.info(f"Successfully added specific date availability for {availability_data.specific_date}")
        
        # Return in the expected format
        return {
            "id": specific_date.id,
            "instructor_id": specific_date.instructor_id,
            "specific_date": specific_date.date,
            "start_time": time_to_string(availability_data.start_time),
            "end_time": time_to_string(availability_data.end_time),
            "is_available": availability_data.is_available,
            "is_recurring": False,
            "is_cleared": False
        }
    except Exception as e:
        logger.error(f"Error adding specific date availability: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[AvailabilityWindowResponse])
def get_all_availability(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all availability windows (both recurring and specific dates).
    
    This endpoint returns a flat list of all availability slots, combining
    recurring patterns and specific date overrides. Optionally filter by date range.
    
    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        List[AvailabilityWindowResponse]: All availability slots
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Getting all availability for instructor {instructor.id}")
    
    if start_date and end_date:
        logger.debug(f"Filtering by date range: {start_date} to {end_date}")
    
    result = []
    
    # Get recurring availability
    recurring_slots = db.query(RecurringAvailability).filter(
        RecurringAvailability.instructor_id == current_user.id
    ).all()
    
    logger.debug(f"Found {len(recurring_slots)} recurring slots")
    
    # Add recurring slots to result
    for slot in recurring_slots:
        result.append({
            "id": slot.id,
            "instructor_id": slot.instructor_id,
            "day_of_week": slot.day_of_week,
            "start_time": time_to_string(slot.start_time),
            "end_time": time_to_string(slot.end_time),
            "is_available": True,
            "is_recurring": True,
            "specific_date": None,
            "is_cleared": False
        })
    
    # Get specific date availability
    query = db.query(SpecificDateAvailability).filter(
        SpecificDateAvailability.instructor_id == current_user.id
    ).options(joinedload(SpecificDateAvailability.time_slots))
    
    if start_date and end_date:
        query = query.filter(
            SpecificDateAvailability.date >= start_date,
            SpecificDateAvailability.date <= end_date
        )
    
    specific_dates = query.all()
    logger.debug(f"Found {len(specific_dates)} specific date entries")
    
    # Add specific date slots to result
    for specific in specific_dates:
        if specific.is_cleared:
            # Skip cleared days in this list view
            continue
        else:
            # Add each time slot
            for slot in specific.time_slots:
                result.append({
                    "id": slot.id,
                    "instructor_id": specific.instructor_id,
                    "specific_date": specific.date,
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True,
                    "is_recurring": False,
                    "day_of_week": None,
                    "is_cleared": False
                })
    
    logger.info(f"Returning {len(result)} total availability slots")
    return result

@router.patch("/{window_id}", response_model=AvailabilityWindowResponse)
def update_availability_window(
    window_id: int,
    update_data: AvailabilityWindowUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an availability window (either recurring or specific date time slot).
    
    Args:
        window_id: The ID of the window to update
        update_data: The fields to update
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        AvailabilityWindowResponse: The updated availability window
        
    Raises:
        HTTPException: If window not found or not owned by instructor
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Updating availability window {window_id} for instructor {instructor.id}")
    
    # First, try to find in recurring availability
    recurring_slot = db.query(RecurringAvailability).filter(
        RecurringAvailability.id == window_id,
        RecurringAvailability.instructor_id == current_user.id
    ).first()
    
    if recurring_slot:
        # Update recurring slot
        if update_data.start_time is not None:
            recurring_slot.start_time = update_data.start_time
        if update_data.end_time is not None:
            recurring_slot.end_time = update_data.end_time
        
        try:
            db.commit()
            db.refresh(recurring_slot)
            logger.info(f"Successfully updated recurring slot {window_id}")
            
            return {
                "id": recurring_slot.id,
                "instructor_id": recurring_slot.instructor_id,
                "day_of_week": recurring_slot.day_of_week,
                "start_time": time_to_string(recurring_slot.start_time),
                "end_time": time_to_string(recurring_slot.end_time),
                "is_available": True,
                "is_recurring": True,
                "specific_date": None,
                "is_cleared": False
            }
        except Exception as e:
            logger.error(f"Error updating recurring slot: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    
    # If not found in recurring, try time slots
    time_slot = db.query(DateTimeSlotModel).filter(
        DateTimeSlotModel.id == window_id
    ).options(joinedload(DateTimeSlotModel.date_override)).first()
    
    if time_slot and time_slot.date_override.instructor_id == current_user.id:
        # Update time slot
        if update_data.start_time is not None:
            time_slot.start_time = update_data.start_time
        if update_data.end_time is not None:
            time_slot.end_time = update_data.end_time
        
        try:
            db.commit()
            db.refresh(time_slot)
            logger.info(f"Successfully updated time slot {window_id}")
            
            return {
                "id": time_slot.id,
                "instructor_id": time_slot.date_override.instructor_id,
                "specific_date": time_slot.date_override.date,
                "start_time": time_to_string(time_slot.start_time),
                "end_time": time_to_string(time_slot.end_time),
                "is_available": update_data.is_available if update_data.is_available is not None else True,
                "is_recurring": False,
                "day_of_week": None,
                "is_cleared": False
            }
        except Exception as e:
            logger.error(f"Error updating time slot: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    
    logger.error(f"Availability window {window_id} not found for instructor {instructor.id}")
    raise HTTPException(status_code=404, detail="Availability window not found")

@router.delete("/{window_id}")
def delete_availability_window(
    window_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete an availability window (either recurring or specific date time slot).
    
    Args:
        window_id: The ID of the window to delete
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict: Success message
        
    Raises:
        HTTPException: If window not found or not owned by instructor
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Deleting availability window {window_id} for instructor {instructor.id}")
    
    # First, try to find in recurring availability
    recurring_slot = db.query(RecurringAvailability).filter(
        RecurringAvailability.id == window_id,
        RecurringAvailability.instructor_id == current_user.id
    ).first()
    
    if recurring_slot:
        db.delete(recurring_slot)
        try:
            db.commit()
            logger.info(f"Successfully deleted recurring slot {window_id}")
            return {"message": "Recurring availability window deleted"}
        except Exception as e:
            logger.error(f"Error deleting recurring slot: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    
    # If not found in recurring, try time slots
    time_slot = db.query(DateTimeSlotModel).filter(
        DateTimeSlotModel.id == window_id
    ).options(joinedload(DateTimeSlotModel.date_override)).first()
    
    if time_slot and time_slot.date_override.instructor_id == current_user.id:
        # Delete the time slot
        db.delete(time_slot)
        
        # Check if this was the last time slot for this date
        remaining_slots = db.query(DateTimeSlotModel).filter(
            DateTimeSlotModel.date_override_id == time_slot.date_override_id
        ).count()
        
        # If no more time slots remain, delete the specific date entry too
        if remaining_slots == 0:
            logger.debug(f"Deleting specific date entry as no slots remain")
            db.delete(time_slot.date_override)
        
        try:
            db.commit()
            logger.info(f"Successfully deleted time slot {window_id}")
            return {"message": "Specific date time slot deleted"}
        except Exception as e:
            logger.error(f"Error deleting time slot: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    
    logger.error(f"Availability window {window_id} not found for instructor {instructor.id}")
    raise HTTPException(status_code=404, detail="Availability window not found")

# Blackout dates endpoints
@router.get("/blackout-dates", response_model=List[BlackoutDateResponse])
def get_blackout_dates(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get instructor's blackout dates.
    
    Returns all future blackout dates (vacation/unavailable days) for the instructor.
    
    Args:
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        List[BlackoutDateResponse]: List of blackout dates
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Getting blackout dates for instructor {instructor.id}")
    
    blackout_dates = db.query(BlackoutDate).filter(
        BlackoutDate.instructor_id == current_user.id,
        BlackoutDate.date >= date.today()
    ).order_by(BlackoutDate.date).all()
    
    logger.debug(f"Found {len(blackout_dates)} future blackout dates")
    return blackout_dates

@router.post("/blackout-dates", response_model=BlackoutDateResponse)
def add_blackout_date(
    blackout_data: BlackoutDateCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Add a blackout date (vacation/unavailable).
    
    Blackout dates prevent any bookings on that date regardless of
    availability settings.
    
    Args:
        blackout_data: The blackout date information
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        BlackoutDateResponse: The created blackout date
        
    Raises:
        HTTPException: If date already exists or database error
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Adding blackout date {blackout_data.date} for instructor {instructor.id}")
    
    # Check if already exists
    existing = db.query(BlackoutDate).filter(
        BlackoutDate.instructor_id == current_user.id,
        BlackoutDate.date == blackout_data.date
    ).first()
    
    if existing:
        logger.warning(f"Blackout date {blackout_data.date} already exists")
        raise HTTPException(status_code=400, detail="Blackout date already exists")
    
    blackout = BlackoutDate(
        instructor_id=current_user.id,
        date=blackout_data.date,
        reason=blackout_data.reason
    )
    
    db.add(blackout)
    
    try:
        db.commit()
        db.refresh(blackout)
        logger.info(f"Successfully added blackout date {blackout_data.date}")
        return blackout
    except Exception as e:
        logger.error(f"Error adding blackout date: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/blackout-dates/{blackout_id}")
def delete_blackout_date(
    blackout_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a blackout date.
    
    Args:
        blackout_id: The ID of the blackout date to delete
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict: Success message
        
    Raises:
        HTTPException: If blackout date not found or not owned by instructor
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Deleting blackout date {blackout_id} for instructor {instructor.id}")
    
    blackout = db.query(BlackoutDate).filter(
        BlackoutDate.id == blackout_id,
        BlackoutDate.instructor_id == current_user.id
    ).first()
    
    if not blackout:
        logger.error(f"Blackout date {blackout_id} not found")
        raise HTTPException(status_code=404, detail="Blackout date not found")
    
    db.delete(blackout)
    
    try:
        db.commit()
        logger.info(f"Successfully deleted blackout date {blackout_id}")
        return {"message": "Blackout date deleted"}
    except Exception as e:
        logger.error(f"Error deleting blackout date: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))