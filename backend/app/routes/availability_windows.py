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
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime
from functools import wraps
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, ParamSpec, TypeVar, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from app.api.dependencies.authz import requires_roles as _requires_roles

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
from ..core.config import settings
from ..core.constants import ERROR_INSTRUCTOR_ONLY
from ..core.enums import RoleName
from ..core.exceptions import ConflictException, DomainException
from ..core.timezone_utils import get_user_today_by_id
from ..middleware.perf_counters import note_cache_miss
from ..models.user import User
from ..monitoring.availability_perf import (
    COPY_WEEK_ENDPOINT,
    WEEK_GET_ENDPOINT,
    WEEK_SAVE_ENDPOINT,
    availability_perf_span,
    estimate_payload_size_bytes,
)
from ..schemas.availability_responses import (
    ApplyToDateRangeResponse,
    BookedSlotsResponse,
    CopyWeekResponse,
    DeleteBlackoutResponse,
    DeleteWindowResponse,
    WeekAvailabilityResponse,
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
from ..services.availability_service import ALLOW_PAST as SERVICE_ALLOW_PAST, AvailabilityService
from ..services.bulk_operation_service import BulkOperationService
from ..services.cache_service import CacheService
from ..services.conflict_checker import ConflictChecker
from ..services.presentation_service import PresentationService
from ..services.slot_manager import SlotManager
from ..services.week_operation_service import WeekOperationService
from ..utils.bitset import windows_from_bits

P = ParamSpec("P")
R = TypeVar("R")

ALLOW_PAST = SERVICE_ALLOW_PAST
EXPOSE_HEADERS = "ETag, Last-Modified, X-Allow-Past"


def _set_bitmap_headers(
    response: Response, etag: str, last_modified: Optional[datetime], *, allow_past: bool
) -> None:
    response.headers["ETag"] = etag
    if last_modified is not None:
        response.headers["Last-Modified"] = format_datetime(last_modified.astimezone(timezone.utc))
    response.headers["X-Allow-Past"] = "true" if allow_past else "false"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS


def requires_roles(
    *roles: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Typed shim around authz.requires_roles for mypy route slice."""
    real_decorator = _requires_roles(*roles)

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        setattr(func, "_required_roles", list(roles))
        decorated: Callable[P, Awaitable[R]] = real_decorator(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return await decorated(*args, **kwargs)

        setattr(wrapper, "_required_roles", getattr(decorated, "_required_roles", list(roles)))
        return wrapper

    return decorator


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
    response_model=WeekAvailabilityResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def get_week_availability(
    response: Response,
    start_date: date = Query(..., description="Monday of the week"),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> WeekAvailabilityResponse:
    """
    Get availability for a specific week.

    Returns clean data structure without legacy fields.
    """
    verify_instructor(current_user)

    with availability_perf_span(
        "handler.get_week_availability",
        endpoint=WEEK_GET_ENDPOINT,
        instructor_id=current_user.id,
        payload_size_bytes=0,
    ):
        try:
            bits_by_day = availability_service.get_week_bits(current_user.id, start_date)
            version = availability_service.compute_week_version_bits(bits_by_day)
            last_mod = availability_service.get_week_bitmap_last_modified(
                current_user.id, start_date
            )
            _set_bitmap_headers(response, version, last_mod, allow_past=ALLOW_PAST)
            note_cache_miss(f"availability:bitmap:{current_user.id}:{start_date.isoformat()}")

            payload: Dict[str, List[TimeRange]] = {}
            for day, bits in bits_by_day.items():
                windows = windows_from_bits(bits)
                if not windows:
                    continue
                payload[day.isoformat()] = [
                    TimeRange(
                        start_time=time.fromisoformat(start),
                        end_time=time.fromisoformat(end),
                    )
                    for start, end in windows
                ]
            if settings.include_empty_days_in_tests:
                monday_anchor = min(bits_by_day.keys()) if bits_by_day else start_date
                monday_anchor = monday_anchor - timedelta(days=monday_anchor.weekday())
                for offset in range(7):
                    day_key = (monday_anchor + timedelta(days=offset)).isoformat()
                    payload.setdefault(day_key, [])
                payload = dict(sorted(payload.items()))
            return WeekAvailabilityResponse(payload)
        except DomainException as e:
            raise e.to_http_exception()
        except Exception as e:
            logger.error(f"Unexpected error getting bitmap week availability: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/week",
    response_model=WeekAvailabilityUpdateResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
@requires_roles("instructor")
async def save_week_availability(
    request: Request,
    response: Response,
    payload: WeekSpecificScheduleCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    availability_service: AvailabilityService = Depends(get_availability_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
    override: bool = Query(
        False,
        description="Set to true to bypass version conflict checks when saving availability",
    ),
) -> WeekAvailabilityUpdateResponse:
    """
    Save availability for specific dates in a week.

    Clean implementation with proper cache warming.
    """
    verify_instructor(current_user)
    payload_size = estimate_payload_size_bytes(payload)

    with availability_perf_span(
        "handler.save_week_availability",
        endpoint=WEEK_SAVE_ENDPOINT,
        instructor_id=current_user.id,
        payload_size_bytes=payload_size,
    ):
        # Determine Monday/week_end prior to persistence for use in exception handling
        schedule_dates: List[date] = []
        monday: date
        if payload.week_start:
            monday = payload.week_start
        else:
            for item in payload.schedule:
                raw_date = item.get("date")
                if raw_date is None:
                    continue
                try:
                    parsed_date = (
                        raw_date
                        if isinstance(raw_date, date)
                        else date.fromisoformat(str(raw_date))
                    )
                except Exception:
                    continue
                schedule_dates.append(parsed_date)

            reference_date = (
                min(schedule_dates)
                if schedule_dates
                else get_user_today_by_id(current_user.id, availability_service.db)
            )
            monday = reference_date - timedelta(days=reference_date.weekday())
        week_end = monday + timedelta(days=6)

        server_version: Optional[str] = None

        try:
            # Inject cache service if needed
            if not availability_service.cache_service and cache_service:
                availability_service.cache_service = cache_service

            # Version handshake: If-Match header or body-provided base_version
            client_version = (
                request.headers.get("if-match") or payload.base_version or payload.version
            )
            override_requested = override or bool(getattr(payload, "override", False))

            if client_version:
                payload.base_version = client_version
                payload.version = client_version
            payload.override = override_requested

            windows_by_day: Dict[date, List[tuple[str, str]]] = {}
            for item in payload.schedule:
                raw_date = item.get("date")
                if isinstance(raw_date, date):
                    slot_date = raw_date
                else:
                    slot_date = date.fromisoformat(str(raw_date))

                raw_start = item.get("start_time")
                if isinstance(raw_start, time):
                    start_str = raw_start.strftime("%H:%M:%S")
                else:
                    start_str = time.fromisoformat(str(raw_start)).strftime("%H:%M:%S")

                raw_end = item.get("end_time")
                if isinstance(raw_end, time):
                    end_str = raw_end.strftime("%H:%M:%S")
                else:
                    end_str = time.fromisoformat(str(raw_end)).strftime("%H:%M:%S")

                windows_by_day.setdefault(slot_date, []).append((start_str, end_str))

            try:
                save_result = availability_service.save_week_bits(
                    instructor_id=current_user.id,
                    week_start=monday,
                    windows_by_day=windows_by_day,
                    base_version=client_version,
                    override=override_requested,
                    clear_existing=bool(payload.clear_existing),
                    actor=current_user,
                )
            except ConflictException:
                server_bits = availability_service.get_week_bits(
                    current_user.id, monday, use_cache=False
                )
                server_version = availability_service.compute_week_version_bits(server_bits)
                raise HTTPException(
                    status_code=409,
                    detail={"error": "version_conflict", "current_version": server_version},
                    headers={
                        "ETag": server_version,
                        "X-Allow-Past": "true" if ALLOW_PAST else "false",
                        "Access-Control-Expose-Headers": EXPOSE_HEADERS,
                    },
                )

            new_version = save_result.version
            last_mod = availability_service.get_week_bitmap_last_modified(current_user.id, monday)
            _set_bitmap_headers(response, new_version, last_mod, allow_past=ALLOW_PAST)

            return WeekAvailabilityUpdateResponse(
                message="Saved weekly availability",
                week_start=monday,
                week_end=week_end,
                windows_created=save_result.windows_created,
                slots_created=save_result.slots_created,
                windows_updated=0,
                windows_deleted=0,
                days_written=save_result.days_written,
                weeks_affected=save_result.weeks_affected,
                edited_dates=save_result.edited_dates,
                skipped_dates=[d.isoformat() for d in save_result.skipped_dates],
                skipped_past_window=save_result.skipped_past_window,
                version=new_version,
                week_version=new_version,
            )
        except HTTPException as e:
            raise e
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
    payload: CopyWeekRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    week_operation_service: WeekOperationService = Depends(get_week_operation_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> CopyWeekResponse:
    """Copy availability from one week to another."""
    verify_instructor(current_user)
    payload_size = estimate_payload_size_bytes(payload)

    with availability_perf_span(
        "handler.copy_week_availability",
        endpoint=COPY_WEEK_ENDPOINT,
        instructor_id=current_user.id,
        payload_size_bytes=payload_size,
    ):
        try:
            if not week_operation_service.cache_service and cache_service:
                week_operation_service.cache_service = cache_service

            result = await week_operation_service.copy_week_availability(
                instructor_id=current_user.id,
                from_week_start=payload.from_week_start,
                to_week_start=payload.to_week_start,
                actor=current_user,
            )
            metadata = cast(dict[str, object], result.get("_metadata", {}))
            service_message = metadata.get("message")
            if service_message is None:
                service_message = result.get("message")
            if service_message is None:
                service_message = "Week copied successfully"
            slots_created = metadata.get("slots_created")
            if slots_created is None:
                slots_created = result.get("slots_created", 0)
            return CopyWeekResponse(
                message=str(service_message),
                source_week_start=payload.from_week_start,
                target_week_start=payload.to_week_start,
                windows_copied=int(cast(int | str | None, slots_created) or 0),
            )
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
    payload: ApplyToDateRangeRequest = Body(...),
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
            from_week_start=payload.from_week_start,
            start_date=payload.start_date,
            end_date=payload.end_date,
            actor=current_user,
        )
        windows_created_raw = result.get("windows_created", result.get("slots_created", 0))
        weeks_applied_raw = result.get("weeks_applied", 0)
        weeks_affected_raw = result.get("weeks_affected", 0)
        days_written_raw = result.get("days_written", windows_created_raw)
        skipped_past_targets_raw = result.get("skipped_past_targets", 0)
        edited_dates_raw = result.get("edited_dates", [])

        def _coerce_int(value: Any, fallback: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return fallback

        windows_created = _coerce_int(windows_created_raw, 0)
        weeks_applied = _coerce_int(weeks_applied_raw, 0)
        weeks_affected = _coerce_int(weeks_affected_raw, 0)
        days_written = _coerce_int(days_written_raw, windows_created)
        skipped_past_targets = _coerce_int(skipped_past_targets_raw, 0)
        edited_dates = [str(item) for item in edited_dates_raw] if edited_dates_raw else []
        dates_processed = _coerce_int(result.get("dates_processed", 0), 0)
        dates_with_windows = _coerce_int(
            result.get("dates_with_windows", result.get("dates_with_slots", 0)), 0
        )
        dates_with_slots = _coerce_int(
            result.get("dates_with_slots", dates_with_windows), dates_with_windows
        )
        written_dates = [str(item) for item in result.get("written_dates", [])]

        return ApplyToDateRangeResponse(
            message=str(result.get("message", "")),
            start_date=payload.start_date,
            end_date=payload.end_date,
            weeks_applied=weeks_applied,
            windows_created=windows_created,
            slots_created=windows_created,
            weeks_affected=weeks_affected,
            days_written=days_written,
            skipped_past_targets=skipped_past_targets,
            edited_dates=edited_dates,
            dates_processed=dates_processed,
            dates_with_windows=dates_with_windows,
            dates_with_slots=dates_with_slots,
            written_dates=written_dates,
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
    payload: SpecificDateAvailabilityCreate = Body(...),
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
            instructor_id=current_user.id, availability_data=payload
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
    payload: AvailabilityWindowUpdate = Body(...),
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
            start_time=payload.start_time,
            end_time=payload.end_time,
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
