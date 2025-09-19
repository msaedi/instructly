# backend/app/routes/availability_windows.py
"""
Availability management routes for InstaInstru - Clean Architecture Implementation.

COMPLETELY REWRITTEN without legacy patterns.
All manual response building removed. Clean schema serialization only.

Key Changes:
- No more is_available, is_recurring, day_of_week in responses
- Proper schema serialization using AvailabilityWindowResponse
- Removed dead code and legacy patterns
- Clean separation of concerns

Key Features:
    - Week-based availability viewing and editing
    - Copy availability from one week to another
    - Apply patterns to date ranges
    - Specific date availability management
    - Bulk operations for efficiency
    - Blackout date management for vacations
    - Validation before applying changes
    - Cache warming for performance

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
from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ConfigDict

from ..api.dependencies.auth import get_current_active_user, require_beta_access
from ..api.dependencies.services import (
    get_availability_service,
    get_bulk_operation_service,
    get_cache_service_dep,
    get_conflict_checker,
    get_presentation_service,
    get_slot_manager,
    get_week_operation_service,
)
from ..core.constants import ERROR_INSTRUCTOR_ONLY
from ..core.enums import RoleName
from ..core.exceptions import DomainException
from ..models.user import User
from ..schemas.availability_responses import (
    ApplyToDateRangeResponse,
    BookedSlotsResponse,
    CopyWeekResponse,
    DeleteBlackoutResponse,
    DeleteWindowResponse,
    WeekAvailabilityUpdateResponse,
)
from ..schemas.availability_window import (
    ApplyToDateRangeRequest,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    BlackoutDateCreate,
    BlackoutDateResponse,
    BulkUpdateRequest,
    BulkUpdateResponse,
    CopyWeekRequest,
    SpecificDateAvailabilityCreate,
    TimeRange,
    ValidateWeekRequest,
    WeekSpecificScheduleCreate,
    WeekValidationResponse,
)
from ..services.availability_service import AvailabilityService
from ..services.bulk_operation_service import BulkOperationService
from ..services.cache_service import CacheService
from ..services.conflict_checker import ConflictChecker
from ..services.presentation_service import PresentationService
from ..services.slot_manager import SlotManager
from ..services.week_operation_service import WeekOperationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instructors/availability", tags=["availability"])


def verify_instructor(current_user: User) -> User:
    """Verify the current user is an instructor."""
    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        logger.warning(
            f"Non-instructor user {current_user.email} attempted to access instructor-only endpoint"
        )
        raise HTTPException(status_code=403, detail=ERROR_INSTRUCTOR_ONLY)
    return current_user


@router.get(
    "/week",
    response_model=Dict[str, List[TimeRange]],
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def get_week_availability(
    response: Response,
    start_date: date = Query(..., description="Monday of the week"),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> Dict[str, List[TimeRange]]:
    """
    Get availability for a specific week.

    Returns clean data structure without legacy fields.
    """
    verify_instructor(current_user)

    try:
        week_map = cast(
            Dict[str, List[TimeRange]],
            availability_service.get_week_availability(
                instructor_id=current_user.id, start_date=start_date
            ),
        )
        # Compute version and attach as header
        version = availability_service.compute_week_version(
            current_user.id, start_date, start_date + timedelta(days=6)
        )
        response.headers["ETag"] = version
        # Compute Last-Modified from server data for cross-tab consistency
        last_mod = availability_service.get_week_last_modified(
            current_user.id, start_date, start_date + timedelta(days=6)
        )
        if last_mod:
            # RFC 1123 format via http-date: use strftime with GMT
            response.headers["Last-Modified"] = last_mod.astimezone(tz=None).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
        # Allow browsers to read ETag and Last-Modified via CORS
        response.headers["Access-Control-Expose-Headers"] = "ETag, Last-Modified"
        return week_map
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting week availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/week",
    response_model=WeekAvailabilityUpdateResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def save_week_availability(
    week_data: WeekSpecificScheduleCreate,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> WeekAvailabilityUpdateResponse:
    """
    Save availability for specific dates in a week.

    Clean implementation with proper cache warming.
    """
    verify_instructor(current_user)

    try:
        # Inject cache service if needed
        if not availability_service.cache_service and cache_service:
            availability_service.cache_service = cache_service

        # Compute week start/end (Monday..Sunday)
        from datetime import date as _date, timedelta as _timedelta

        from app.core.timezone_utils import get_user_today_by_id

        if week_data.week_start:
            monday = week_data.week_start
        else:
            # Derive from the earliest schedule date
            dates = []
            for item in week_data.schedule:
                try:
                    dates.append(_date.fromisoformat(str(item["date"])))
                except Exception:
                    continue
            # Use user's timezone-aware 'today' when deriving default week
            monday = (
                min(dates)
                if dates
                else get_user_today_by_id(current_user.id, availability_service.db)
            )
            monday = monday - _timedelta(days=monday.weekday())
        week_end = monday + _timedelta(days=6)

        # Get pre-save summary
        pre_summary = availability_service.get_availability_summary(
            current_user.id, monday, week_end
        )
        pre_total = sum(pre_summary.values())

        await availability_service.save_week_availability(
            instructor_id=current_user.id, week_data=week_data
        )

        # Get post-save summary
        post_summary = availability_service.get_availability_summary(
            current_user.id, monday, week_end
        )
        post_total = sum(post_summary.values())

        created = max(0, post_total - pre_total)
        deleted = max(0, pre_total - post_total)
        updated = 0  # Not tracked precisely in this endpoint

        # Compute and attach new version
        new_version = availability_service.compute_week_version(current_user.id, monday, week_end)
        response.headers["ETag"] = new_version
        # Compute and attach Last-Modified after save
        last_mod = availability_service.get_week_last_modified(current_user.id, monday, week_end)
        if last_mod:
            response.headers["Last-Modified"] = last_mod.astimezone(tz=None).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
        response.headers["Access-Control-Expose-Headers"] = "ETag, Last-Modified"

        return WeekAvailabilityUpdateResponse(
            message="Saved weekly availability",
            week_start=monday,
            week_end=week_end,
            windows_created=created,
            windows_updated=updated,
            windows_deleted=deleted,
        )

    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error saving week availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/copy-week",
    response_model=CopyWeekResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def copy_week_availability(
    copy_data: CopyWeekRequest,
    current_user: User = Depends(get_current_active_user),
    week_operation_service: WeekOperationService = Depends(get_week_operation_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> CopyWeekResponse:
    """Copy availability from one week to another."""
    verify_instructor(current_user)

    try:
        if not week_operation_service.cache_service and cache_service:
            week_operation_service.cache_service = cache_service

        result = await week_operation_service.copy_week_availability(
            instructor_id=current_user.id,
            from_week_start=copy_data.from_week_start,
            to_week_start=copy_data.to_week_start,
        )
        return result
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error copying week: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/apply-to-date-range",
    response_model=ApplyToDateRangeResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def apply_to_date_range(
    apply_data: ApplyToDateRangeRequest,
    current_user: User = Depends(get_current_active_user),
    week_operation_service: WeekOperationService = Depends(get_week_operation_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> ApplyToDateRangeResponse:
    """Apply a week's pattern to a date range."""
    verify_instructor(current_user)

    try:
        if not week_operation_service.cache_service and cache_service:
            week_operation_service.cache_service = cache_service

        result = await week_operation_service.apply_pattern_to_date_range(
            instructor_id=current_user.id,
            from_week_start=apply_data.from_week_start,
            start_date=apply_data.start_date,
            end_date=apply_data.end_date,
        )
        # Map service result to response schema
        # Compute weeks_applied as ceiling of days/7 over the inclusive date range
        days = (apply_data.end_date - apply_data.start_date).days + 1
        weeks_applied = (days + 6) // 7
        windows_created = int(result.get("slots_created", 0))

        return ApplyToDateRangeResponse(
            message=result.get("message", "Successfully applied schedule"),
            start_date=apply_data.start_date,
            end_date=apply_data.end_date,
            weeks_applied=weeks_applied,
            windows_created=windows_created,
        )
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error applying pattern: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/specific-date",
    response_model=AvailabilityWindowResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
def add_specific_date_availability(
    availability_data: SpecificDateAvailabilityCreate,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> AvailabilityWindowResponse:
    """
    Add availability for a specific date.

    Returns clean response using schema.
    """
    verify_instructor(current_user)

    try:
        slot = availability_service.add_specific_date_availability(
            instructor_id=current_user.id, availability_data=availability_data
        )

        # Pydantic v2 way - use model_validate instead of from_orm
        return AvailabilityWindowResponse.model_validate(slot)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error adding specific date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/",
    response_model=List[AvailabilityWindowResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
)
def get_all_availability(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> List[AvailabilityWindowResponse]:
    """
    Get all availability windows.

    CLEAN ARCHITECTURE: Returns only meaningful fields.
    No legacy patterns.
    """
    verify_instructor(current_user)

    try:
        slots = availability_service.get_all_instructor_availability(
            instructor_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        # FIX: Map model fields to schema fields correctly
        result = []
        for slot in slots:
            result.append(
                AvailabilityWindowResponse(
                    id=slot.id,
                    instructor_id=slot.instructor_id,
                    specific_date=slot.specific_date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                )
            )
        return result

    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting all availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch(
    "/bulk-update",
    response_model=BulkUpdateResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def bulk_update_availability(
    update_data: BulkUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    bulk_operation_service: BulkOperationService = Depends(get_bulk_operation_service),
) -> BulkUpdateResponse:
    """Bulk update availability slots."""
    verify_instructor(current_user)

    try:
        result = await bulk_operation_service.process_bulk_update(
            instructor_id=current_user.id, update_data=update_data
        )
        return BulkUpdateResponse(**result)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error in bulk update: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch(
    "/{window_id}",
    response_model=AvailabilityWindowResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
def update_availability_window(
    window_id: str,
    update_data: AvailabilityWindowUpdate,
    current_user: User = Depends(get_current_active_user),
    slot_manager: SlotManager = Depends(get_slot_manager),
) -> AvailabilityWindowResponse:
    """
    Update an availability time slot.

    CLEAN ARCHITECTURE: Returns proper schema response.
    No manual response building.
    """
    verify_instructor(current_user)

    try:
        # Update the slot - note that AvailabilityWindowUpdate only has start_time and end_time
        updated_slot = slot_manager.update_slot(
            slot_id=window_id,
            start_time=update_data.start_time,
            end_time=update_data.end_time,
        )

        # FIX: Map model fields to schema fields correctly
        return AvailabilityWindowResponse(
            id=updated_slot.id,
            instructor_id=updated_slot.instructor_id,
            specific_date=updated_slot.specific_date,
            start_time=updated_slot.start_time,
            end_time=updated_slot.end_time,
        )

    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error updating slot: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/{window_id}",
    response_model=DeleteWindowResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
def delete_availability_window(
    window_id: str,
    current_user: User = Depends(get_current_active_user),
    slot_manager: SlotManager = Depends(get_slot_manager),
) -> DeleteWindowResponse:
    """Delete an availability time slot."""
    verify_instructor(current_user)

    try:
        slot_manager.delete_slot(slot_id=window_id)
        return DeleteWindowResponse(window_id=window_id)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error deleting slot: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/week/booked-slots",
    response_model=BookedSlotsResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def get_week_booked_slots(
    start_date: date = Query(..., description="Start date (Monday) of the week"),
    current_user: User = Depends(get_current_active_user),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    presentation_service: PresentationService = Depends(get_presentation_service),
) -> BookedSlotsResponse:
    """Get all booked slots for a week with preview information."""
    verify_instructor(current_user)

    try:
        booked_slots_by_date = conflict_checker.get_booked_times_for_week(
            instructor_id=current_user.id, week_start=start_date
        )

        # Format for frontend display
        formatted_slots = presentation_service.format_booked_slots_from_service_data(
            booked_slots_by_date
        )

        from datetime import timedelta

        week_end = start_date + timedelta(days=6)
        return BookedSlotsResponse(
            week_start=start_date, week_end=week_end, booked_slots=formatted_slots
        )

    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting booked slots: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/week/validate-changes",
    response_model=WeekValidationResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def validate_week_changes(
    validation_data: ValidateWeekRequest,
    current_user: User = Depends(get_current_active_user),
    bulk_operation_service: BulkOperationService = Depends(get_bulk_operation_service),
) -> WeekValidationResponse:
    """Validate planned changes to week availability."""
    verify_instructor(current_user)

    try:
        result = await bulk_operation_service.validate_week_changes(
            instructor_id=current_user.id, validation_data=validation_data
        )
        return WeekValidationResponse(**result)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error validating changes: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Blackout dates endpoints
@router.get(
    "/blackout-dates",
    response_model=List[BlackoutDateResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
)
def get_blackout_dates(
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> List[BlackoutDateResponse]:
    """Get instructor's blackout dates."""
    verify_instructor(current_user)

    try:
        blackout_dates = availability_service.get_blackout_dates(instructor_id=current_user.id)
        return [BlackoutDateResponse.model_validate(bd) for bd in blackout_dates]
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error getting blackout dates: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/blackout-dates",
    response_model=BlackoutDateResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
def add_blackout_date(
    blackout_data: BlackoutDateCreate,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> BlackoutDateResponse:
    """Add a blackout date (vacation/unavailable)."""
    verify_instructor(current_user)

    try:
        result = availability_service.add_blackout_date(
            instructor_id=current_user.id, blackout_data=blackout_data
        )
        return BlackoutDateResponse.model_validate(result)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error adding blackout date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/blackout-dates/{blackout_id}",
    response_model=DeleteBlackoutResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
def delete_blackout_date(
    blackout_id: str,
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> DeleteBlackoutResponse:
    """Delete a blackout date."""
    verify_instructor(current_user)

    try:
        availability_service.delete_blackout_date(
            instructor_id=current_user.id, blackout_id=blackout_id
        )
        return DeleteBlackoutResponse(blackout_id=blackout_id)
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error deleting blackout date: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
