# backend/app/routes/availability_windows.py
"""
Availability management routes for InstaInstru.

This module provides API endpoints for instructors to manage their availability.
All business logic has been extracted to service layers for better separation
of concerns and testability.

Key Features:
    - Week-based availability viewing and editing
    - Copy availability from one week to another
    - Apply patterns to date ranges
    - Blackout date management for vacations
    
Router Endpoints:
    GET /week - Get availability for a specific week
    POST /week - Save availability for specific dates in a week
    POST /copy-week - Copy availability between weeks
    POST /apply-to-date-range - Apply a pattern to a date range
    POST /specific-date - Add availability for a single date
    GET / - Get all availability with optional date filtering
    PATCH /bulk-update - Bulk update availability slots
    PATCH /{window_id} - Update a specific time slot
    DELETE /{window_id} - Delete a specific time slot
    GET /week/booked-slots - Get booked slots for a week
    POST /week/validate-changes - Validate planned changes
    GET /blackout-dates - Get instructor's blackout dates
    POST /blackout-dates - Add a blackout date
    DELETE /blackout-dates/{id} - Remove a blackout date
"""

import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User, UserRole
from ..schemas.availability_window import (
    SpecificDateAvailabilityCreate,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    BlackoutDateCreate,
    BlackoutDateResponse,
    WeekSpecificScheduleCreate,
    CopyWeekRequest,
    ApplyToDateRangeRequest,
    BulkUpdateRequest,
    BulkUpdateResponse,
    WeekValidationResponse,
    ValidateWeekRequest,
)
from ..api.dependencies.auth import get_current_active_user
from ..core.constants import ERROR_INSTRUCTOR_ONLY
from ..core.exceptions import DomainException

# Service imports
from ..api.dependencies.services import (
    get_availability_service,
    get_week_operation_service,
    get_bulk_operation_service,
    get_conflict_checker,
    get_slot_manager,
    get_presentation_service
)
from ..services.availability_service import AvailabilityService
from ..services.week_operation_service import WeekOperationService
from ..services.bulk_operation_service import BulkOperationService
from ..services.conflict_checker import ConflictChecker
from ..services.slot_manager import SlotManager
from ..services.presentation_service import PresentationService

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
    if current_user.role != UserRole.INSTRUCTOR:
        logger.warning(f"Non-instructor user {current_user.email} attempted to access instructor-only endpoint")
        raise HTTPException(status_code=403, detail=ERROR_INSTRUCTOR_ONLY)
    return current_user


@router.get("/week")
async def get_week_availability(
    start_date: date = Query(..., description="Monday of the week"),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service)
):
    """
    Get availability for a specific week.
    
    This endpoint returns a week view of availability, showing time slots for each day
    based on the instructor's saved availability.
    
    Args:
        start_date: The Monday of the week to retrieve
        current_user: The authenticated user (must be an instructor)
        availability_service: The availability service instance
        
    Returns:
        Dict mapping date strings to time slot lists
    """
    verify_instructor(current_user)
    
    try:
        return availability_service.get_week_availability(
            instructor_id=current_user.id,
            start_date=start_date
        )
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting week availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/week")
async def save_week_availability(
    week_data: WeekSpecificScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    db: Session = Depends(get_db)
):
    """
    Save availability for specific dates in a week.
    
    This endpoint allows instructors to set their availability for specific dates,
    completely replacing any existing availability for those dates while preserving
    booked slots.
    """
    verify_instructor(current_user)
    
    try:
        result = await availability_service.save_week_availability(
            instructor_id=current_user.id,
            week_data=week_data
        )
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error saving week availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/copy-week")
async def copy_week_availability(
    copy_data: CopyWeekRequest,
    current_user: User = Depends(get_current_active_user),
    week_operation_service: WeekOperationService = Depends(get_week_operation_service),
    db: Session = Depends(get_db)
):
    """
    Copy availability from one week to another while preserving existing bookings.
    
    This endpoint provides a quick way to duplicate an entire week's availability
    pattern to another week. Booked slots from the source week become available
    slots in the target week.
    """
    verify_instructor(current_user)
    
    try:
        result = await week_operation_service.copy_week_availability(
            instructor_id=current_user.id,
            from_week_start=copy_data.from_week_start,
            to_week_start=copy_data.to_week_start
        )
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error copying week: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/apply-to-date-range")
async def apply_to_date_range(
    apply_data: ApplyToDateRangeRequest,
    current_user: User = Depends(get_current_active_user),
    week_operation_service: WeekOperationService = Depends(get_week_operation_service),
    db: Session = Depends(get_db)
):
    """
    Apply a week's pattern to a date range while preserving all existing bookings.
    
    This endpoint takes a source week's availability pattern and applies it
    repeatedly to all weeks within the specified date range.
    """
    verify_instructor(current_user)
    
    try:
        result = await week_operation_service.apply_pattern_to_date_range(
            instructor_id=current_user.id,
            from_week_start=apply_data.from_week_start,
            start_date=apply_data.start_date,
            end_date=apply_data.end_date
        )
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error applying pattern: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/specific-date", response_model=AvailabilityWindowResponse)
def add_specific_date_availability(
    availability_data: SpecificDateAvailabilityCreate,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    db: Session = Depends(get_db)
):
    """
    Add availability for a specific date (one-time).
    
    This creates a date-specific availability entry.
    """
    verify_instructor(current_user)
    
    try:
        result = availability_service.add_specific_date_availability(
            instructor_id=current_user.id,
            availability_data=availability_data
        )
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error adding specific date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=List[AvailabilityWindowResponse])
def get_all_availability(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service)
):
    """
    Get all availability windows.
    
    This endpoint returns a flat list of all availability slots.
    Optionally filter by date range.
    """
    verify_instructor(current_user)
    
    try:
        # Get availability entries
        availability_entries = availability_service.get_all_availability(
            instructor_id=current_user.id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Convert to response format
        result = []
        for entry in availability_entries:
            if not entry.is_cleared and entry.time_slots:
                for slot in entry.time_slots:
                    result.append({
                        "id": slot.id,
                        "instructor_id": entry.instructor_id,
                        "specific_date": entry.date,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                        "is_available": True,
                        "is_recurring": False,
                        "day_of_week": None,
                        "is_cleared": False
                    })
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting all availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/bulk-update", response_model=BulkUpdateResponse)
async def bulk_update_availability(
    update_data: BulkUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    bulk_operation_service: BulkOperationService = Depends(get_bulk_operation_service),
    db: Session = Depends(get_db)
):
    """
    Bulk update availability slots.
    
    This endpoint allows multiple operations in a single transaction:
    - Add new slots (with automatic overlap merging)
    - Remove specific slots (only if not booked)
    - Update existing slots (respecting bookings)
    """
    verify_instructor(current_user)
    
    try:
        result = await bulk_operation_service.process_bulk_update(
            instructor_id=current_user.id,
            update_data=update_data
        )
        
        return BulkUpdateResponse(**result)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error in bulk update: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{window_id}", response_model=AvailabilityWindowResponse)
def update_availability_window(
    window_id: int,
    update_data: AvailabilityWindowUpdate,
    current_user: User = Depends(get_current_active_user),
    slot_manager: SlotManager = Depends(get_slot_manager),
    db: Session = Depends(get_db)
):
    """
    Update an availability time slot.
    
    Args:
        window_id: The ID of the slot to update
        update_data: The fields to update
        current_user: The authenticated instructor
        slot_manager: The slot manager service
    """
    verify_instructor(current_user)
    
    try:
        # Update the slot
        updated_slot = slot_manager.update_slot(
            slot_id=window_id,
            start_time=update_data.start_time,
            end_time=update_data.end_time,
            validate_conflicts=True
        )
        
        # Return in expected format
        return {
            "id": updated_slot.id,
            "instructor_id": updated_slot.availability.instructor_id,
            "specific_date": updated_slot.availability.date,
            "start_time": updated_slot.start_time.isoformat(),
            "end_time": updated_slot.end_time.isoformat(),
            "is_available": update_data.is_available if update_data.is_available is not None else True,
            "is_recurring": False,
            "day_of_week": None,
            "is_cleared": False
        }
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error updating slot: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{window_id}")
def delete_availability_window(
    window_id: int,
    current_user: User = Depends(get_current_active_user),
    slot_manager: SlotManager = Depends(get_slot_manager),
    db: Session = Depends(get_db)
):
    """
    Delete an availability time slot.
    
    Args:
        window_id: The ID of the slot to delete
        current_user: The authenticated instructor
        slot_manager: The slot manager service
    """
    verify_instructor(current_user)
    
    try:
        slot_manager.delete_slot(slot_id=window_id, force=False)
        
        return {"message": "Availability time slot deleted"}
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error deleting slot: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/week/booked-slots")
async def get_week_booked_slots(
    start_date: date = Query(..., description="Start date (Monday) of the week"),
    current_user: User = Depends(get_current_active_user),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    presentation_service: PresentationService = Depends(get_presentation_service)
):
    """
    Get all booked slots for a week with enhanced preview information.
    
    Returns booking details formatted for calendar preview display.
    """
    verify_instructor(current_user)
    
    try:
        # Get booked slots from service
        booked_slots_by_date = conflict_checker.get_booked_slots_for_week(
            instructor_id=current_user.id,
            week_start=start_date
        )
        
        # Format for frontend display using presentation service
        formatted_slots = presentation_service.format_booked_slots_from_service_data(
            booked_slots_by_date
        )
        
        return {"booked_slots": formatted_slots}
        
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting booked slots: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/week/validate-changes", response_model=WeekValidationResponse)
async def validate_week_changes(
    validation_data: ValidateWeekRequest,
    current_user: User = Depends(get_current_active_user),
    bulk_operation_service: BulkOperationService = Depends(get_bulk_operation_service)
):
    """
    Validate planned changes to week availability without applying them.
    
    This endpoint allows the frontend to preview what would happen if changes
    were saved, including identifying any conflicts with existing bookings.
    """
    verify_instructor(current_user)
    
    try:
        result = await bulk_operation_service.validate_week_changes(
            instructor_id=current_user.id,
            validation_data=validation_data
        )
        return WeekValidationResponse(**result)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error validating changes: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Blackout dates endpoints
@router.get("/blackout-dates", response_model=List[BlackoutDateResponse])
def get_blackout_dates(
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service)
):
    """
    Get instructor's blackout dates.
    
    Returns all future blackout dates (vacation/unavailable days) for the instructor.
    """
    verify_instructor(current_user)
    
    try:
        return availability_service.get_blackout_dates(instructor_id=current_user.id)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting blackout dates: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/blackout-dates", response_model=BlackoutDateResponse)
def add_blackout_date(
    blackout_data: BlackoutDateCreate,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    db: Session = Depends(get_db)
):
    """
    Add a blackout date (vacation/unavailable).
    
    Blackout dates prevent any bookings on that date regardless of
    availability settings.
    """
    verify_instructor(current_user)
    
    try:
        result = availability_service.add_blackout_date(
            instructor_id=current_user.id,
            blackout_data=blackout_data
        )
        
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error adding blackout date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/blackout-dates/{blackout_id}")
def delete_blackout_date(
    blackout_id: int,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    db: Session = Depends(get_db)
):
    """
    Delete a blackout date.
    
    Args:
        blackout_id: The ID of the blackout date to delete
        current_user: The authenticated instructor
        availability_service: The availability service
    """
    verify_instructor(current_user)
    
    try:
        availability_service.delete_blackout_date(
            instructor_id=current_user.id,
            blackout_id=blackout_id
        )
        
        return {"message": "Blackout date deleted"}
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error deleting blackout date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")