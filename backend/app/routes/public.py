# backend/app/routes/public.py
"""
Public routes for InstaInstru platform.

These routes do not require authentication and are designed for
student-facing features like viewing instructor availability.

Key Design Decisions:
1. No authentication required - these are public endpoints
2. No internal IDs exposed except instructor_id
3. Heavy caching for performance
4. Only shows actually bookable slots (accounts for existing bookings)
5. Respects blackout dates
"""

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import get_db
from ..models.instructor import InstructorProfile
from ..models.user import User
from ..schemas.public_availability import (
    PublicAvailabilityMinimal,
    PublicAvailabilitySummary,
    PublicDayAvailability,
    PublicInstructorAvailability,
    PublicTimeSlot,
)
from ..services.availability_service import AvailabilityService
from ..services.cache_service import CacheService
from ..services.conflict_checker import ConflictChecker
from ..services.instructor_service import InstructorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public", tags=["public"])


def get_availability_service(db: Session = Depends(get_db)) -> AvailabilityService:
    """Get availability service instance."""
    return AvailabilityService(db)


def get_conflict_checker(db: Session = Depends(get_db)) -> ConflictChecker:
    """Get conflict checker instance."""
    return ConflictChecker(db)


def get_instructor_service(db: Session = Depends(get_db)) -> InstructorService:
    """Get instructor service instance."""
    return InstructorService(db)


def get_cache_service_dep() -> Optional[CacheService]:
    """Get cache service instance."""
    try:
        return CacheService()
    except Exception:
        return None


@router.get(
    "/instructors/{instructor_id}/availability",
    response_model=Union[PublicInstructorAvailability, PublicAvailabilitySummary, PublicAvailabilityMinimal],
    summary="Get instructor availability for students",
    description="Public endpoint to view instructor's available time slots for booking. No authentication required.",
)
async def get_instructor_public_availability(
    instructor_id: int,
    request: Request,
    response_obj: Response,
    start_date: date = Query(..., description="Start date for availability search"),
    end_date: Optional[date] = Query(None, description="End date (defaults to configured days from start)"),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    instructor_service: InstructorService = Depends(get_instructor_service),
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
    db: Session = Depends(get_db),
):
    """
    Get public availability for an instructor.

    This endpoint:
    1. Returns available time slots that can actually be booked
    2. Excludes slots that already have bookings
    3. Respects blackout dates
    4. Uses caching for performance
    5. Provides a student-friendly response format

    Args:
        instructor_id: The instructor's user ID
        start_date: Start of date range to check
        end_date: End of date range (max configured days)

    Returns:
        PublicInstructorAvailability with bookable time slots

    Raises:
        404: If instructor not found
        400: If date range is invalid
    """
    # Validate instructor exists and is active
    instructor_user = db.query(User).filter(User.id == instructor_id).first()
    if not instructor_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    # Verify they have an instructor profile
    instructor_profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
    if not instructor_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    # Validate dates FIRST before setting defaults
    if start_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start date cannot be in the past")

    # If end_date is provided, validate it
    if end_date:
        if end_date < start_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be after start date")

        # Check if range is too large
        if (end_date - start_date).days > 90:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date range cannot exceed 90 days")

    # NOW set default end_date if not provided
    if not end_date:
        end_date = start_date + timedelta(days=settings.public_availability_days - 1)  # -1 because range is inclusive

    # Enforce configured maximum even if user requests more
    max_end_date = start_date + timedelta(days=settings.public_availability_days - 1)
    if end_date > max_end_date:
        end_date = max_end_date

    # Generate ETag for conditional requests
    etag_data = f"{instructor_id}:{start_date}:{end_date}:{settings.public_availability_detail_level}"
    etag = hashlib.md5(etag_data.encode()).hexdigest()

    # Check if client has current version using ETag
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip('"') == etag:
        response_obj.status_code = status.HTTP_304_NOT_MODIFIED
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    # Check cache first - include detail level in cache key
    cache_key = (
        f"public_availability:{instructor_id}:{start_date}:{end_date}:{settings.public_availability_detail_level}"
    )
    cached_result = None
    if cache_service:
        try:
            cached_data = cache_service.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for public availability: {cache_key}")
                cached_result = cached_data
        except Exception as e:
            logger.warning(f"Cache error: {e}")

    # If we have cached data, set headers and return
    if cached_result:
        # Set cache control headers (5 minutes)
        response_obj.headers["Cache-Control"] = "public, max-age=300"
        response_obj.headers["ETag"] = f'"{etag}"'
        return cached_result

    # Build response based on detail level
    if settings.public_availability_detail_level == "minimal":
        # Minimal: Just check if any availability exists
        all_slots = availability_service.repository.get_week_availability(instructor_id, start_date, end_date)

        response_data = PublicAvailabilityMinimal(
            instructor_id=instructor_id,
            instructor_name=instructor_user.full_name
            if settings.public_availability_show_instructor_name
            else "Instructor",
            has_availability=len(all_slots) > 0,
            earliest_available_date=all_slots[0].specific_date.isoformat() if all_slots else None,
            timezone="America/New_York",
        )

    elif settings.public_availability_detail_level == "summary":
        # Summary: Show counts and time ranges, not specific slots
        all_slots = availability_service.repository.get_week_availability(instructor_id, start_date, end_date)

        # Group by morning/afternoon/evening
        availability_summary = {}
        for slot in all_slots:
            date_str = slot.specific_date.isoformat()
            if date_str not in availability_summary:
                availability_summary[date_str] = {
                    "date": date_str,
                    "morning_available": False,  # Before noon
                    "afternoon_available": False,  # Noon to 5pm
                    "evening_available": False,  # After 5pm
                    "total_hours": 0,
                }

            # Categorize time slots
            if slot.start_time.hour < 12:
                availability_summary[date_str]["morning_available"] = True
            elif slot.start_time.hour < 17:
                availability_summary[date_str]["afternoon_available"] = True
            else:
                availability_summary[date_str]["evening_available"] = True

            # Add hours
            duration = (
                datetime.combine(date.min, slot.end_time) - datetime.combine(date.min, slot.start_time)
            ).seconds / 3600
            availability_summary[date_str]["total_hours"] += duration

        response_data = PublicAvailabilitySummary(
            instructor_id=instructor_id,
            instructor_name=instructor_user.full_name
            if settings.public_availability_show_instructor_name
            else "Instructor",
            availability_summary=availability_summary,
            timezone="America/New_York",
            total_available_days=len(availability_summary),
            detail_level="summary",
        )

    else:  # "full" detail level
        # Build availability data
        availability_by_date = {}
        total_available_slots = 0
        earliest_available_date = None

        # Get all availability slots in the date range
        all_slots = availability_service.repository.get_week_availability(instructor_id, start_date, end_date)

        # Get blackout dates
        blackout_dates = availability_service.get_blackout_dates(instructor_id)
        blackout_date_set = {b.date for b in blackout_dates}

        # Process each date in the range
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()

            # Check if this is a blackout date
            if current_date in blackout_date_set:
                availability_by_date[date_str] = PublicDayAvailability(
                    date=date_str, available_slots=[], is_blackout=True
                )
                current_date += timedelta(days=1)
                continue

            # Get slots for this date
            date_slots = [s for s in all_slots if s.specific_date == current_date]

            if date_slots:
                # Get booked times for this date
                booked_bookings = conflict_checker.repository.get_bookings_for_date(instructor_id, current_date)

                # Convert to time format
                booked_times = []
                for booking in booked_bookings:
                    booked_times.append({"start_time": booking.start_time, "end_time": booking.end_time})

                # Filter out booked slots
                available_slots = []
                for slot in date_slots:
                    # Check if this slot overlaps with any booking
                    is_booked = False
                    for booked in booked_times:
                        # Check for overlap using the times directly
                        if slot.start_time < booked["end_time"] and slot.end_time > booked["start_time"]:
                            is_booked = True
                            break

                    if not is_booked:
                        available_slots.append(
                            PublicTimeSlot(
                                start_time=slot.start_time.strftime("%H:%M"), end_time=slot.end_time.strftime("%H:%M")
                            )
                        )
                        total_available_slots += 1

                        if not earliest_available_date:
                            earliest_available_date = date_str

                availability_by_date[date_str] = PublicDayAvailability(
                    date=date_str, available_slots=available_slots, is_blackout=False
                )
            else:
                # No slots for this date
                availability_by_date[date_str] = PublicDayAvailability(
                    date=date_str, available_slots=[], is_blackout=False
                )

            current_date += timedelta(days=1)

        # Build response - use instructor's user full_name, not profile
        response_data = PublicInstructorAvailability(
            instructor_id=instructor_id,
            instructor_name=instructor_user.full_name
            if settings.public_availability_show_instructor_name
            else "Instructor",
            availability_by_date=availability_by_date,
            timezone="America/New_York",  # NYC-based platform
            total_available_slots=total_available_slots,
            earliest_available_date=earliest_available_date,
        )

    # Cache the response
    if cache_service:
        try:
            cache_service.set(cache_key, response_data.model_dump(), ttl=settings.public_availability_cache_ttl)
        except Exception as e:
            logger.warning(f"Failed to cache public availability: {e}")

    # Set cache control headers (5 minutes) and ETag on FastAPI Response object
    response_obj.headers["Cache-Control"] = "public, max-age=300"
    response_obj.headers["ETag"] = f'"{etag}"'
    response_obj.headers["Vary"] = "Accept-Encoding"

    return response_data


@router.get(
    "/instructors/{instructor_id}/next-available",
    summary="Get next available slot for an instructor",
    description="Quick endpoint to find the next available booking slot",
)
async def get_next_available_slot(
    instructor_id: int,
    response_obj: Response,
    duration_minutes: int = Query(60, description="Required duration in minutes"),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    instructor_service: InstructorService = Depends(get_instructor_service),
    db: Session = Depends(get_db),
):
    """
    Find the next available time slot for booking.

    This is a convenience endpoint for "Book Now" functionality.
    """
    # Validate instructor
    instructor_user = db.query(User).filter(User.id == instructor_id).first()
    if not instructor_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    instructor_profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
    if not instructor_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    # Search for next configured days
    search_days = settings.public_availability_days
    current_date = date.today()

    for _ in range(search_days):
        # Skip if blackout date
        if conflict_checker.check_blackout_date(instructor_id, current_date):
            current_date += timedelta(days=1)
            continue

        # Get available slots for this date
        slots = availability_service.repository.get_week_availability(instructor_id, current_date, current_date)

        if slots:
            # Get booked times
            booked_bookings = conflict_checker.repository.get_bookings_for_date(instructor_id, current_date)

            # Convert to time format
            booked_times = []
            for booking in booked_bookings:
                booked_times.append({"start_time": booking.start_time, "end_time": booking.end_time})

            # Find first slot that can accommodate the duration
            for slot in sorted(slots, key=lambda s: s.start_time):
                # Calculate slot duration in minutes
                slot_duration = (
                    datetime.combine(date.min, slot.end_time) - datetime.combine(date.min, slot.start_time)
                ).seconds // 60

                if slot_duration >= duration_minutes:
                    # Check if this slot is booked
                    is_booked = False
                    for booked in booked_times:
                        if slot.start_time < booked["end_time"] and slot.end_time > booked["start_time"]:
                            is_booked = True
                            break

                    if not is_booked:
                        # Found an available slot!
                        # Return the requested duration from the start of the slot
                        end_time = (
                            datetime.combine(date.min, slot.start_time) + timedelta(minutes=duration_minutes)
                        ).time()

                        result = {
                            "found": True,
                            "date": current_date.isoformat(),
                            "start_time": slot.start_time.strftime("%H:%M:%S"),
                            "end_time": end_time.strftime("%H:%M:%S"),
                            "duration_minutes": duration_minutes,
                        }

                        # Set cache headers for successful results (2 minutes for next-available)
                        response_obj.headers["Cache-Control"] = "public, max-age=120"

                        return result

        current_date += timedelta(days=1)

    result = {"found": False, "message": f"No available slots found in the next {search_days} days"}

    # Set cache headers for no-availability results (1 minute)
    response_obj.headers["Cache-Control"] = "public, max-age=60"

    return result
