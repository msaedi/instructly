"""
Availability management routes for InstaInstru.

This module provides API endpoints for instructors to manage their availability.
The system uses a week-based UI where instructors can set their available time
slots for specific dates, copy schedules between weeks, and apply patterns to
date ranges.

Key Features:
    - Week-based availability viewing and editing
    - Copy availability from one week to another
    - Apply patterns to date ranges
    - Blackout date management for vacations
    
The availability system has been refactored to remove recurring patterns and
now uses only date-specific availability for better flexibility and clarity.

Router Endpoints:
    GET /week - Get availability for a specific week
    POST /week - Save availability for specific dates in a week
    POST /copy-week - Copy availability between weeks
    POST /apply-to-date-range - Apply a pattern to a date range
    POST /specific-date - Add availability for a single date
    GET / - Get all availability with optional date filtering
    PATCH /{window_id} - Update a specific time slot
    DELETE /{window_id} - Delete a specific time slot
    GET /blackout-dates - Get instructor's blackout dates
    POST /blackout-dates - Add a blackout date
    DELETE /blackout-dates/{id} - Remove a blackout date
"""

import logging
from datetime import timedelta, date, time
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models.user import User
from ..models.instructor import InstructorProfile 
from ..models.booking import Booking
from ..models.service import Service
from ..models.availability import (
    InstructorAvailability,
    AvailabilitySlot as AvailabilitySlotModel,
    BlackoutDate, 
)
from ..schemas.availability_window import (
    SpecificDateAvailabilityCreate,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    BlackoutDateCreate,
    BlackoutDateResponse,
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
    Get availability for a specific week.
    
    This endpoint returns a week view of availability, showing time slots for each day
    based on the instructor's saved availability. The response is organized as a
    dictionary mapping ISO date strings to lists of time slots.
    
    Args:
        start_date: The Monday of the week to retrieve
        current_user: The authenticated user (must be an instructor)
        db: Database session
        
    Returns:
        Dict[str, List[Dict]]: Dictionary mapping date strings to time slot lists.
        Example:
            {
                "2024-06-10": [
                    {"start_time": "09:00:00", "end_time": "12:00:00", "is_available": true},
                    {"start_time": "14:00:00", "end_time": "17:00:00", "is_available": true}
                ],
                "2024-06-11": []  # No availability this day
            }
        
    Raises:
        HTTPException: 404 if instructor profile not found
        
    Note:
        Days marked as "cleared" will not appear in the response.
        Days without any entry will also not appear in the response.
    """
    logger.info(f"Getting week availability for instructor {current_user.id} starting {start_date}")
    
    # Validate that start_date is a Monday
    if start_date.weekday() != 0:
        logger.warning(f"Start date {start_date} is not a Monday (weekday={start_date.weekday()})")
    
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
    
    # Get instructor availability for this week
    instructor_availability = db.query(InstructorAvailability).filter(
        and_(
            InstructorAvailability.instructor_id == current_user.id,
            InstructorAvailability.date.in_(week_dates)
        )
    ).options(joinedload(InstructorAvailability.time_slots)).all()
    
    logger.debug(f"Found {len(instructor_availability)} instructor availability entries for the week")
    
    # Build response
    week_schedule = {}
    
    for availability_entry in instructor_availability:
        date_str = availability_entry.date.isoformat()
        
        # Skip cleared days
        if availability_entry.is_cleared:
            logger.debug(f"Day {date_str} is explicitly cleared")
            continue
            
        # Add time slots
        if availability_entry.time_slots:
            week_schedule[date_str] = [
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                    "is_available": True
                }
                for slot in availability_entry.time_slots
            ]
            logger.debug(f"Added {len(availability_entry.time_slots)} slots for {date_str}")
    
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
    completely replacing any existing availability for those dates. The operation
    is atomic - either all changes succeed or all are rolled back.
    
    Behavior:
        - If clear_existing=True: Deletes ALL existing entries for the week first
        - Days with time slots: Creates availability entries with those slots
        - Days without slots + clear_existing=True: Creates "cleared" entries
        - Days without slots + clear_existing=False: Leaves unchanged
    
    Args:
        week_data: The week schedule data containing:
            - schedule: List of date/time slot entries
            - clear_existing: Whether to clear all existing entries first
            - week_start: Optional Monday date (inferred if not provided)
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict[str, List]: The updated week availability (same format as GET /week)
        
    Raises:
        HTTPException: 
            - 404 if instructor profile not found
            - 400 if database operation fails
            
    Example Request:
        {
            "clear_existing": true,
            "schedule": [
                {
                    "date": "2024-06-10",
                    "start_time": "09:00:00",
                    "end_time": "12:00:00"
                }
            ]
        }
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
    
    # Import Booking model if not already imported
    from app.models.booking import Booking
    
    # Group schedule by date first
    schedule_by_date = {}
    for slot in week_data.schedule:
        # Skip past dates with a warning
        if slot.date < date.today():
            logger.warning(f"Skipping past date: {slot.date}")
            continue
            
        if slot.date not in schedule_by_date:
            schedule_by_date[slot.date] = []
        schedule_by_date[slot.date].append(slot)
    
    # Process each day of the week individually
    dates_created = 0
    slots_created = 0
    dates_with_bookings = []
    
    for week_date in week_dates:
        # Skip past dates
        if week_date < date.today():
            logger.debug(f"Skipping past date: {week_date}")
            continue
        
        # Process the date based on whether we have new slots for it
        if week_date in schedule_by_date:
            # We have new slots for this date
            logger.info(f"Processing {len(schedule_by_date[week_date])} new slots for {week_date}")
            
            # Get existing availability entry or create new one
            existing_availability = db.query(InstructorAvailability).filter(
                and_(
                    InstructorAvailability.instructor_id == current_user.id,
                    InstructorAvailability.date == week_date
                )
            ).first()
            
            if existing_availability:
                # Check which existing slots have bookings
                booked_slots = (
                    db.query(AvailabilitySlotModel)
                    .join(Booking, AvailabilitySlotModel.id == Booking.availability_slot_id)
                    .filter(
                        AvailabilitySlotModel.availability_id == existing_availability.id,
                        Booking.status.in_(['CONFIRMED', 'COMPLETED'])
                    )
                    .all()
                )
                
                booked_time_ranges = [(slot.start_time, slot.end_time) for slot in booked_slots]
                if booked_time_ranges:
                    logger.info(f"Found {len(booked_time_ranges)} booked slots for {week_date}: {booked_time_ranges}")
                
                # Delete only non-booked slots
                if week_data.clear_existing:
                    # Get IDs of booked slots
                    booked_slot_ids = [slot.id for slot in booked_slots]
                    
                    # Delete slots that are NOT in the booked list
                    query = db.query(AvailabilitySlotModel).filter(
                        AvailabilitySlotModel.availability_id == existing_availability.id
                    )
                    
                    if booked_slot_ids:
                        query = query.filter(~AvailabilitySlotModel.id.in_(booked_slot_ids))
                    
                    deleted = query.delete(synchronize_session=False)
                    logger.debug(f"Deleted {deleted} unbooked slots for {week_date}")
                
                # Use existing availability entry
                availability_entry = existing_availability
                availability_entry.is_cleared = False
            else:
                # Create new availability entry
                availability_entry = InstructorAvailability(
                    instructor_id=current_user.id,
                    date=week_date,
                    is_cleared=False
                )
                db.add(availability_entry)
                db.flush()
                dates_created += 1
                booked_time_ranges = []  # No existing bookings for new entry
            
            # Add new time slots (skip if they conflict with booked slots)
            for slot in schedule_by_date[week_date]:
                # Check if this slot would conflict with a booked slot
                conflicts_with_booking = False
                for booked_start, booked_end in booked_time_ranges:
                    if (slot.start_time < booked_end and slot.end_time > booked_start):
                        logger.warning(f"Skipping slot {slot.start_time}-{slot.end_time} as it conflicts with booking")
                        conflicts_with_booking = True
                        break
                
                if not conflicts_with_booking:
                    time_slot = AvailabilitySlotModel(
                        availability_id=availability_entry.id,
                        start_time=slot.start_time,
                        end_time=slot.end_time
                    )
                    db.add(time_slot)
                    slots_created += 1
                    logger.debug(f"Added time slot {slot.start_time}-{slot.end_time} for {week_date}")
                    
        else:
            # No new slots for this date
            if week_data.clear_existing:
                # Check if any slots for this date have bookings
                existing_bookings = (
                    db.query(Booking)
                    .join(AvailabilitySlotModel, Booking.availability_slot_id == AvailabilitySlotModel.id)
                    .join(InstructorAvailability, AvailabilitySlotModel.availability_id == InstructorAvailability.id)
                    .filter(
                        InstructorAvailability.instructor_id == current_user.id,
                        InstructorAvailability.date == week_date,
                        Booking.status.in_(['CONFIRMED', 'COMPLETED'])
                    )
                    .count()
                )
                
                if existing_bookings > 0:
                    dates_with_bookings.append(week_date.strftime("%Y-%m-%d"))
                    logger.warning(f"Date {week_date} has {existing_bookings} bookings - cannot clear")
                    continue
                
                # Safe to delete - no bookings
                deleted = db.query(InstructorAvailability).filter(
                    and_(
                        InstructorAvailability.instructor_id == current_user.id,
                        InstructorAvailability.date == week_date
                    )
                ).delete(synchronize_session=False)
                
                # Create a cleared entry (but not for today)
                if deleted > 0 and week_date != date.today():
                    logger.debug(f"Creating cleared entry for {week_date}")
                    availability_entry = InstructorAvailability(
                        instructor_id=current_user.id,
                        date=week_date,
                        is_cleared=True
                    )
                    db.add(availability_entry)
                    dates_created += 1
    
    # If we skipped any dates due to bookings, include that in the response
    if dates_with_bookings:
        logger.info(f"Skipped {len(dates_with_bookings)} dates with bookings: {dates_with_bookings}")
    
    try:
        db.commit()
        logger.info(f"Successfully saved week availability: {dates_created} dates, {slots_created} slots")
        
        # Add a note about skipped dates in the response if any
        result = await get_week_availability(
            start_date=monday,
            current_user=current_user,
            db=db
        )
        
        logger.info(f"Returning availability for week starting {monday}")
        logger.info(f"Result keys: {list(result.keys())}")

        # Optionally add metadata about skipped dates
        if dates_with_bookings:
            result["_metadata"] = {
                "skipped_dates_with_bookings": dates_with_bookings,
                "message": f"Changes saved successfully. {len(dates_with_bookings)} date(s) with existing bookings were not modified."
            }
            
        return result
        
    except IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        db.rollback()
        if "foreign key constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Cannot modify availability due to existing bookings. Please cancel bookings first."
            )
        raise HTTPException(status_code=400, detail="Database error occurred")
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
    
    This endpoint provides a quick way to duplicate an entire week's availability
    pattern to another week. It's particularly useful for instructors with
    consistent schedules who want to set up multiple weeks at once.
    
    The copy operation:
        1. Deletes ALL existing entries in the target week
        2. Copies all time slots from source week to target week
        3. Preserves "cleared" days (days explicitly marked unavailable)
        4. Creates cleared entries for days with no availability in source
    
    Args:
        copy_data: Contains:
            - from_week_start: Monday of the source week
            - to_week_start: Monday of the target week
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict[str, List]: The updated target week availability
        
    Raises:
        HTTPException: 400 if database operation fails
        
    Example:
        Copy this week to next week:
        {
            "from_week_start": "2024-06-10",
            "to_week_start": "2024-06-17"
        }
    """
    logger.info(f"Copying week availability for instructor {current_user.id} from {copy_data.from_week_start} to {copy_data.to_week_start}")
    
    # Validate dates are Mondays
    if copy_data.from_week_start.weekday() != 0:
        logger.warning(f"Source week start {copy_data.from_week_start} is not a Monday")
    if copy_data.to_week_start.weekday() != 0:
        logger.warning(f"Target week start {copy_data.to_week_start} is not a Monday")
    
    # Calculate target week dates
    target_week_dates = [copy_data.to_week_start + timedelta(days=i) for i in range(7)]
    
    # Delete ALL existing entries for the target week
    deleted_count = db.query(InstructorAvailability).filter(
        and_(
            InstructorAvailability.instructor_id == current_user.id,
            InstructorAvailability.date.in_(target_week_dates)
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
            availability_entry = InstructorAvailability(
                instructor_id=current_user.id,
                date=target_date,
                is_cleared=False
            )
            db.add(availability_entry)
            db.flush()
            dates_created += 1
            
            for slot in source_week[source_date_str]:
                time_slot = AvailabilitySlotModel(
                    availability_id=availability_entry.id,  # Changed from date_override_id
                    start_time=string_to_time(slot['start_time']),
                    end_time=string_to_time(slot['end_time'])
                )
                db.add(time_slot)
                slots_created += 1
        else:
            # Source day has no slots - mark target as cleared
            availability_entry = InstructorAvailability(
                instructor_id=current_user.id,
                date=target_date,
                is_cleared=True
            )
            db.add(availability_entry)
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
    
    # Clear existing availability in the date range
    deleted_count = db.query(InstructorAvailability).filter(
        and_(
            InstructorAvailability.instructor_id == current_user.id,
            InstructorAvailability.date >= apply_data.start_date,
            InstructorAvailability.date <= apply_data.end_date
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
            availability_entry = InstructorAvailability(
                instructor_id=current_user.id,
                date=current_date,
                is_cleared=False
            )
            db.add(availability_entry)
            db.flush()
            
            # Add time slots
            for slot in week_pattern[day_name]:
                time_slot = AvailabilitySlotModel(
                    availability_id=availability_entry.id,  # Changed from date_override_id
                    start_time=string_to_time(slot['start_time']),
                    end_time=string_to_time(slot['end_time'])
                )
                db.add(time_slot)
                slots_created += 1
        else:
            # Day has no pattern - create cleared entry
            availability_entry = InstructorAvailability(
                instructor_id=current_user.id,
                date=current_date,
                is_cleared=True
            )
            db.add(availability_entry)
        
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

# NOTE: All recurring availability endpoints have been removed since we're dropping that table

@router.post("/specific-date", response_model=AvailabilityWindowResponse)
def add_specific_date_availability(
    availability_data: SpecificDateAvailabilityCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Add availability for a specific date (one-time).
    
    This creates a date-specific availability entry.
    
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
    
    # Check if there's already an entry for this date
    existing = db.query(InstructorAvailability).filter(
        InstructorAvailability.instructor_id == current_user.id,
        InstructorAvailability.date == availability_data.specific_date
    ).first()
    
    if existing and not existing.is_cleared:
        # Check if this exact time slot already exists
        existing_slot = db.query(AvailabilitySlotModel).filter(
            AvailabilitySlotModel.availability_id == existing.id,
            AvailabilitySlotModel.start_time == availability_data.start_time,
            AvailabilitySlotModel.end_time == availability_data.end_time
        ).first()
        
        if existing_slot:
            logger.warning(f"Time slot already exists for {availability_data.specific_date}")
            raise HTTPException(status_code=400, detail=ERROR_OVERLAPPING_SLOT)
    
    # Create or get the availability entry
    if not existing:
        availability_entry = InstructorAvailability(
            instructor_id=current_user.id,
            date=availability_data.specific_date,
            is_cleared=False
        )
        db.add(availability_entry)
        db.flush()
        logger.debug(f"Created new availability entry for {availability_data.specific_date}")
    else:
        availability_entry = existing
        # If it was cleared, unclear it
        if availability_entry.is_cleared:
            availability_entry.is_cleared = False
            logger.debug(f"Uncleared previously cleared date {availability_data.specific_date}")
    
    # Add the time slot
    time_slot = AvailabilitySlotModel(
        availability_id=availability_entry.id,  # Changed from date_override_id
        start_time=availability_data.start_time,
        end_time=availability_data.end_time
    )
    db.add(time_slot)
    
    try:
        db.commit()
        db.refresh(availability_entry)
        logger.info(f"Successfully added specific date availability for {availability_data.specific_date}")
        
        # Return in the expected format
        return {
            "id": availability_entry.id,
            "instructor_id": availability_entry.instructor_id,
            "specific_date": availability_entry.date,
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
    Get all availability windows.
    
    This endpoint returns a flat list of all availability slots.
    Optionally filter by date range.
    
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
    
    # Get instructor availability
    query = db.query(InstructorAvailability).filter(
        InstructorAvailability.instructor_id == current_user.id
    ).options(joinedload(InstructorAvailability.time_slots))
    
    if start_date and end_date:
        query = query.filter(
            InstructorAvailability.date >= start_date,
            InstructorAvailability.date <= end_date
        )
    
    availability_entries = query.all()
    logger.debug(f"Found {len(availability_entries)} availability entries")
    
    # Add slots to result
    for entry in availability_entries:
        if entry.is_cleared:
            # Skip cleared days in this list view
            continue
        else:
            # Add each time slot
            for slot in entry.time_slots:
                result.append({
                    "id": slot.id,
                    "instructor_id": entry.instructor_id,
                    "specific_date": entry.date,
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
    Update an availability time slot.
    
    Args:
        window_id: The ID of the slot to update
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
    
    # Find the time slot
    time_slot = db.query(AvailabilitySlotModel).filter(
        AvailabilitySlotModel.id == window_id
    ).options(joinedload(AvailabilitySlotModel.availability)).first()
    
    if time_slot and time_slot.availability.instructor_id == current_user.id:
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
                "instructor_id": time_slot.availability.instructor_id,
                "specific_date": time_slot.availability.date,
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
    Delete an availability time slot.
    
    Args:
        window_id: The ID of the slot to delete
        current_user: The authenticated instructor
        db: Database session
        
    Returns:
        Dict: Success message
        
    Raises:
        HTTPException: If window not found or not owned by instructor
    """
    instructor = verify_instructor(current_user)
    logger.info(f"Deleting availability window {window_id} for instructor {instructor.id}")
    
    # Find the time slot
    time_slot = db.query(AvailabilitySlotModel).filter(
        AvailabilitySlotModel.id == window_id
    ).options(joinedload(AvailabilitySlotModel.availability)).first()
    
    if time_slot and time_slot.availability.instructor_id == current_user.id:
        # Delete the time slot
        db.delete(time_slot)
        
        # Check if this was the last time slot for this date
        remaining_slots = db.query(AvailabilitySlotModel).filter(
            AvailabilitySlotModel.availability_id == time_slot.availability_id
        ).count()
        
        # If no more time slots remain, delete the availability entry too
        if remaining_slots == 0:
            logger.debug(f"Deleting availability entry as no slots remain")
            db.delete(time_slot.availability)
        
        try:
            db.commit()
            logger.info(f"Successfully deleted time slot {window_id}")
            return {"message": "Availability time slot deleted"}
        except Exception as e:
            logger.error(f"Error deleting time slot: {str(e)}")
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    
    logger.error(f"Availability window {window_id} not found for instructor {instructor.id}")
    raise HTTPException(status_code=404, detail="Availability window not found")

# Get all booked slots for a week
@router.get("/week/booked-slots")
async def get_week_booked_slots(
    start_date: date = Query(..., description="Start date (Monday) of the week"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all booked slots for a week."""
    week_dates = [start_date + timedelta(days=i) for i in range(7)]
    
    booked_slots = (
        db.query(
            Booking.booking_date.label("date"),
            AvailabilitySlotModel.start_time,
            AvailabilitySlotModel.end_time,
            User.full_name.label("student_name"),
            Service.skill.label("service_name")
        )
        .join(AvailabilitySlotModel, Booking.availability_slot_id == AvailabilitySlotModel.id)
        .join(InstructorAvailability, AvailabilitySlotModel.availability_id == InstructorAvailability.id)
        .join(User, Booking.student_id == User.id)
        .join(Service, Booking.service_id == Service.id)
        .filter(
            InstructorAvailability.instructor_id == current_user.id,
            Booking.booking_date.in_(week_dates),
            Booking.status.in_(['CONFIRMED', 'COMPLETED'])
        )
        .all()
    )
    
    return {
        "booked_slots": [
            {
                "date": slot.date.isoformat(),
                "start_time": str(slot.start_time),
                "end_time": str(slot.end_time),
                "student_name": slot.student_name,
                "service_name": slot.service_name
            }
            for slot in booked_slots
        ]
    }


# Blackout dates endpoints remain unchanged
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