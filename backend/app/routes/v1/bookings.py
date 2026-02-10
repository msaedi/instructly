# backend/app/routes/v1/bookings.py
"""
Student booking routes - API v1

Versioned booking endpoints under /api/v1/bookings.
All business logic delegated to BookingService.

Endpoints:
    GET /upcoming - Dashboard widget for upcoming bookings
    GET /stats - Booking statistics
    POST /check-availability - Check if time range is available
    POST /send-reminders - Admin endpoint for reminder emails
    GET / - List bookings with filters and pagination
    POST / - Create instant booking with time range
    GET /{booking_id}/preview - Quick preview for calendar display
    GET /{booking_id} - Full booking details
    PATCH /{booking_id} - Update booking (instructor notes/location)
    POST /{booking_id}/cancel - Cancel a booking
    POST /{booking_id}/reschedule - Reschedule a booking
    POST /{booking_id}/complete - Mark booking as completed
    POST /{booking_id}/no-show - Report a no-show
    POST /{booking_id}/no-show/dispute - Dispute a no-show report
    POST /{booking_id}/confirm-payment - Confirm payment method
    PATCH /{booking_id}/payment-method - Update booking payment method
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, NoReturn, Optional, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.params import Path

from ...api.dependencies import get_booking_service, get_current_active_user
from ...api.dependencies.auth import require_beta_phase_access
from ...core.booking_lock import booking_lock
from ...core.config import settings
from ...core.constants import VALID_LOCATION_TYPES
from ...core.enums import PermissionName
from ...core.exceptions import DomainException, NotFoundException, ValidationException
from ...dependencies.permissions import require_permission
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.booking import BookingStatus, PaymentStatus
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
from ...schemas.base_responses import PaginatedResponse
from ...schemas.booking import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingCancel,
    BookingConfirmPayment,
    BookingCreate,
    BookingCreateResponse,
    BookingPaymentMethodUpdate,
    BookingRescheduleRequest,
    BookingResponse,
    BookingStatsResponse,
    BookingUpdate,
    NoShowDisputeRequest,
    NoShowDisputeResponse,
    NoShowReportRequest,
    NoShowReportResponse,
    RetryPaymentResponse,
    UpcomingBookingResponse,
)
from ...schemas.booking_responses import BookingPreviewResponse, SendRemindersResponse
from ...schemas.pricing_preview import PricingPreviewOut
from ...services.booking_service import BookingService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["bookings-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def handle_domain_exception(exc: DomainException) -> NoReturn:
    """Convert domain exceptions to HTTP exceptions."""
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def _safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _safe_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) else None


# ============================================================================
# SECTION 1: Static routes (no path parameters)
# ============================================================================


@router.get(
    "/upcoming",
    response_model=PaginatedResponse[UpcomingBookingResponse],
    dependencies=[Depends(new_rate_limit("read"))],
)
async def get_upcoming_bookings(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> PaginatedResponse[UpcomingBookingResponse]:
    """Get upcoming bookings for dashboard widget."""
    try:
        bookings = await asyncio.to_thread(
            booking_service.get_bookings_for_user,
            user=current_user,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=limit,
        )

        # Transform bookings to include names from relationships
        upcoming_bookings = []
        for booking in bookings:
            if isinstance(booking, dict):
                # Handle cached dictionary
                is_student = current_user.id == booking.get("student_id")
                is_instructor = current_user.id == booking.get("instructor_id")

                student_last_name = (
                    booking.get("student", {}).get("last_name", "")
                    if booking.get("student")
                    else ""
                )
                instructor_last_name = (
                    booking.get("instructor", {}).get("last_name", "")
                    if booking.get("instructor")
                    else ""
                )

                total_price_raw = booking.get("total_price", 0)
                try:
                    _tp = (
                        float(total_price_raw.amount)
                        if hasattr(total_price_raw, "amount")
                        else float(total_price_raw or 0)
                    )
                except Exception:
                    _tp = 0.0

                upcoming_bookings.append(
                    UpcomingBookingResponse(
                        id=booking["id"],
                        instructor_id=booking.get("instructor_id"),
                        booking_date=booking["booking_date"],
                        start_time=booking["start_time"],
                        end_time=booking["end_time"],
                        service_name=booking["service_name"],
                        total_price=_tp,
                        student_first_name=booking.get("student", {}).get("first_name", "Unknown")
                        if booking.get("student")
                        else "Unknown",
                        student_last_name=student_last_name
                        if is_student
                        else student_last_name[0]
                        if student_last_name
                        else "",
                        instructor_first_name=booking.get("instructor", {}).get(
                            "first_name", "Unknown"
                        )
                        if booking.get("instructor")
                        else "Unknown",
                        instructor_last_name=instructor_last_name
                        if is_instructor
                        else instructor_last_name[0]
                        if instructor_last_name
                        else "",
                        meeting_location=booking["meeting_location"],
                    )
                )
            else:
                # Handle SQLAlchemy object
                is_student = current_user.id == booking.student_id
                is_instructor = current_user.id == booking.instructor_id

                total_price_raw = getattr(booking, "total_price", 0)
                try:
                    _tp = (
                        float(total_price_raw.amount)
                        if hasattr(total_price_raw, "amount")
                        else float(total_price_raw or 0)
                    )
                except Exception:
                    _tp = 0.0

                upcoming_bookings.append(
                    UpcomingBookingResponse(
                        id=booking.id,
                        instructor_id=booking.instructor_id,
                        booking_date=booking.booking_date,
                        start_time=booking.start_time,
                        end_time=booking.end_time,
                        service_name=booking.service_name,
                        total_price=_tp,
                        student_first_name=booking.student.first_name
                        if booking.student
                        else "Unknown",
                        student_last_name=booking.student.last_name
                        if is_student and booking.student
                        else booking.student.last_name[0]
                        if booking.student and booking.student.last_name
                        else "",
                        instructor_first_name=booking.instructor.first_name
                        if booking.instructor
                        else "Unknown",
                        instructor_last_name=booking.instructor.last_name
                        if is_instructor and booking.instructor
                        else booking.instructor.last_name[0]
                        if booking.instructor and booking.instructor.last_name
                        else "",
                        meeting_location=booking.meeting_location,
                    )
                )

        return PaginatedResponse(
            items=upcoming_bookings,
            total=len(upcoming_bookings),
            page=1,
            per_page=limit,
            has_next=False,
            has_prev=False,
        )
    except DomainException as e:
        handle_domain_exception(e)


@router.get(
    "/stats",
    response_model=BookingStatsResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
async def get_booking_stats(
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingStatsResponse:
    """Get booking statistics (requires instructor role)."""
    try:
        if not current_user.is_instructor:
            raise ValidationException("Only instructors can view booking stats")

        stats = await asyncio.to_thread(
            booking_service.get_booking_stats_for_instructor, current_user.id
        )
        return BookingStatsResponse(**stats)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/check-availability",
    response_model=AvailabilityCheckResponse,
    dependencies=[Depends(new_rate_limit("search"))],
)
@rate_limit(
    "30/minute",
    key_type=RateLimitKeyType.USER,
    error_message="Too many availability checks. Please slow down.",
)
async def check_availability(
    request: Request,
    check_data: AvailabilityCheckRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> AvailabilityCheckResponse:
    """
    Check if a time range is available for booking.

    Rate limited to prevent abuse of expensive availability checks.
    """
    try:
        result = await asyncio.to_thread(
            booking_service.check_availability,
            check_data.instructor_id,
            check_data.booking_date,
            check_data.start_time,
            check_data.end_time,
            check_data.instructor_service_id,
            None,
        )

        return AvailabilityCheckResponse(**result)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/send-reminders",
    response_model=SendRemindersResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(new_rate_limit("write"))],
)
@rate_limit(
    "1/hour",
    key_type=RateLimitKeyType.IP,
    error_message="Reminder emails can only be triggered once per hour.",
)
async def send_reminder_emails(
    request: Request,
    current_user: User = Depends(require_permission(PermissionName.MANAGE_ALL_BOOKINGS)),
    booking_service: BookingService = Depends(get_booking_service),
) -> SendRemindersResponse:
    """
    Send 24-hour reminder emails for tomorrow's bookings.

    Should be called by scheduled job/cron.
    Rate limited to prevent email spam.

    Requires: MANAGE_ALL_BOOKINGS permission (admin only)
    """
    try:
        count = await asyncio.to_thread(booking_service.send_booking_reminders)
        return SendRemindersResponse(
            message=f"Successfully sent {count} reminder emails",
            reminders_sent=count,
            failed_reminders=0,
        )
    except Exception as e:
        logger.error(f"Failed to send reminder emails: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reminder emails",
        )


# ============================================================================
# SECTION 2: Root routes (no path parameters, but placed after static routes)
# ============================================================================


@router.get(
    "",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_phase_access()), Depends(new_rate_limit("read"))],
)
async def get_bookings(
    status: Optional[BookingStatus] = None,
    upcoming_only: Optional[bool] = None,
    upcoming: Optional[bool] = None,
    exclude_future_confirmed: bool = False,
    include_past_confirmed: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> PaginatedResponse[BookingResponse]:
    """
    Get bookings for the current user with advanced filtering.

    Parameters:
    - status: Filter by specific booking status
    - upcoming/upcoming_only: Only return future bookings (accepts both parameter names)
    - exclude_future_confirmed: Exclude future confirmed bookings (for History tab)
    - include_past_confirmed: Include past confirmed bookings (for BookAgain)
    - page/per_page: Pagination parameters

    Returns: Standardized PaginatedResponse with BookingResponse items
    """
    try:
        # Handle both upcoming and upcoming_only parameters
        if upcoming is not None:
            upcoming_only = upcoming
        elif upcoming_only is None:
            upcoming_only = False

        bookings = await asyncio.to_thread(
            booking_service.get_bookings_for_user,
            user=current_user,
            status=status,
            upcoming_only=upcoming_only,
            exclude_future_confirmed=exclude_future_confirmed,
            include_past_confirmed=include_past_confirmed,
        )

        # Apply pagination
        total = len(bookings)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_bookings = bookings[start:end]

        # Convert to BookingResponse objects with privacy protection
        booking_responses: list[BookingResponse | dict[str, Any]] = []
        for booking in paginated_bookings:
            try:
                if isinstance(booking, dict) and booking.get("_from_cache", False):
                    # Cached data might need privacy adjustments
                    cached_booking = dict(booking)
                    is_instructor = current_user.id == cached_booking.get("instructor_id")

                    instructor_payload = cached_booking.get("instructor")
                    if isinstance(instructor_payload, dict):
                        instructor = dict(instructor_payload)
                        instructor_last_name = instructor.get("last_name", "")
                        instructor["last_initial"] = (
                            instructor_last_name
                            if is_instructor
                            else instructor_last_name[0]
                            if instructor_last_name
                            else ""
                        )
                        instructor.pop("last_name", None)
                        cached_booking["instructor"] = instructor

                    # Guard against malformed cache payloads causing 500s during response serialization.
                    if hasattr(BookingResponse, "model_validate"):
                        BookingResponse.model_validate(cached_booking)
                    else:  # pragma: no cover - pydantic v1 compatibility
                        BookingResponse.parse_obj(cached_booking)

                    booking_responses.append(cached_booking)
                else:
                    # Fresh SQLAlchemy object - use from_booking for privacy protection
                    booking_responses.append(BookingResponse.from_booking(booking))
            except Exception as e:
                logger.error(f"Failed to process booking {getattr(booking, 'id', 'unknown')}: {e}")
                continue

        return PaginatedResponse(
            items=booking_responses,
            total=total,
            page=page,
            per_page=per_page,
            has_next=page * per_page < total,
            has_prev=page > 1,
        )
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "",
    response_model=BookingCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_beta_phase_access()), Depends(new_rate_limit("booking"))],
    responses={
        404: {"description": "Instructor or service not found"},
        409: {"description": "Time slot not available"},
        422: {"description": "Business rule violation (e.g., invalid duration)"},
    },
)
@rate_limit(
    f"{settings.rate_limit_booking_per_minute}/minute",
    key_type=RateLimitKeyType.USER,
    error_message="Too many booking attempts. Please wait a moment and try again.",
)
async def create_booking(
    request: Request,
    booking_data: BookingCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingCreateResponse:
    """
    Create a booking with payment setup (Phase 2.1).

    Two-step flow:
    1. Creates booking with 'pending_payment' status
    2. Returns SetupIntent client_secret for card collection
    3. Frontend collects card details
    4. Call /bookings/{id}/confirm-payment to complete

    Rate limited per user to prevent booking spam.
    """
    try:
        # Check roles and scopes (inline since decorators don't work on dependencies)
        if not current_user.is_student:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can create bookings",
            )

        selected_duration = booking_data.selected_duration

        # Create booking with pending_payment status
        booking = await asyncio.to_thread(
            booking_service.create_booking_with_payment_setup,
            current_user,
            booking_data,
            selected_duration,
        )

        # Build response with SetupIntent details
        setup_intent_client_secret = getattr(booking, "setup_intent_client_secret", None)
        response = BookingCreateResponse.from_booking(
            booking, setup_intent_client_secret=setup_intent_client_secret
        )

        return response
    except DomainException as e:
        handle_domain_exception(e)


# ============================================================================
# SECTION 3: Dynamic routes (with path parameters - placed last)
# ============================================================================


@router.get(
    "/{booking_id}/preview",
    response_model=BookingPreviewResponse,
    dependencies=[Depends(new_rate_limit("read"))],
    responses={404: {"description": "Booking not found"}},
)
async def get_booking_preview(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingPreviewResponse:
    """Get preview information for a booking."""
    try:
        booking = await asyncio.to_thread(
            booking_service.get_booking_for_user, booking_id, current_user
        )
        if not booking:
            raise NotFoundException("Booking not found")

        # Determine if the current user is the instructor to show full name
        is_instructor = current_user.id == booking.instructor_id

        return BookingPreviewResponse(
            booking_id=booking.id,
            student_first_name=booking.student.first_name,
            student_last_name=booking.student.last_name,
            instructor_first_name=booking.instructor.first_name,
            instructor_last_name=booking.instructor.last_name
            if is_instructor
            else booking.instructor.last_name[0]
            if booking.instructor.last_name
            else "",
            service_name=booking.service_name,
            booking_date=booking.booking_date.isoformat(),
            start_time=str(booking.start_time),
            end_time=str(booking.end_time),
            duration_minutes=booking.duration_minutes,
            location_type=booking.location_type or "online",
            location_type_display=booking.location_type_display
            if booking.location_type
            else "Online",
            meeting_location=booking.meeting_location,
            location_address=_safe_str(getattr(booking, "location_address", None)),
            location_lat=_safe_float(getattr(booking, "location_lat", None)),
            location_lng=_safe_float(getattr(booking, "location_lng", None)),
            location_place_id=_safe_str(getattr(booking, "location_place_id", None)),
            service_area=booking.service_area,
            status=booking.status,
            student_note=booking.student_note,
            total_price=float(booking.total_price),
        )
    except DomainException as e:
        handle_domain_exception(e)


@router.get(
    "/{booking_id}/pricing",
    response_model=PricingPreviewOut,
    dependencies=[Depends(new_rate_limit("read"))],
    responses={404: {"description": "Booking not found"}, 403: {"description": "Access denied"}},
)
async def get_booking_pricing(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    applied_credit_cents: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> PricingPreviewOut:
    """Return a pricing preview for the requested booking."""
    try:
        result = await asyncio.to_thread(
            booking_service.get_booking_pricing_preview,
            booking_id,
            current_user.id,
            applied_credit_cents,
        )

        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if result.get("error") == "access_denied":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        return PricingPreviewOut(**result)
    except DomainException as exc:
        raise exc.to_http_exception() from exc


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("read"))],
    responses={404: {"description": "Booking not found"}},
)
async def get_booking_details(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """Get full booking details with privacy protection for students."""
    try:
        # Service method returns booking + payment summary (no direct db access needed)
        result = await asyncio.to_thread(
            booking_service.get_booking_with_payment_summary, booking_id, current_user
        )
        if not result:
            raise NotFoundException("Booking not found")

        booking, payment_summary_data = result
        return BookingResponse.from_booking(booking, payment_summary=payment_summary_data)
    except DomainException as e:
        handle_domain_exception(e)


@router.patch(
    "/{booking_id}",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={404: {"description": "Booking not found"}},
)
async def update_booking(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    update_data: BookingUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """Update booking details (instructor only)."""
    try:
        booking = await asyncio.to_thread(
            booking_service.update_booking,
            booking_id,
            current_user,
            update_data,
        )
        return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={404: {"description": "Booking not found"}},
)
async def cancel_booking(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    cancel_data: BookingCancel = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """Cancel a booking."""
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            booking = await asyncio.to_thread(
                booking_service.cancel_booking,
                booking_id,
                current_user,
                cancel_data.reason,
            )
            return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/reschedule",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={404: {"description": "Booking not found"}, 409: {"description": "Time conflict"}},
)
async def reschedule_booking(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    payload: BookingRescheduleRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Reschedule flow (server-orchestrated):
    - Validates access to the original booking
    - Cancels the original booking according to policy
    - Creates a new booking with the requested time
    - Returns the new booking
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            # Load original booking
            original = await asyncio.to_thread(
                booking_service.get_booking_for_user, booking_id, current_user
            )
            if not original:
                raise NotFoundException("Booking not found")

            # Part 5: Block second reschedule - a booking can only be rescheduled once
            await asyncio.to_thread(booking_service.validate_reschedule_allowed, original)

            # Pre-validate the requested slot
            start_dt = datetime.combine(  # tz-pattern-ok: duration math only
                payload.booking_date, payload.start_time, tzinfo=timezone.utc
            )
            end_dt = start_dt + timedelta(minutes=payload.selected_duration)
            proposed_end_time = end_dt.time()

            availability = await asyncio.to_thread(
                booking_service.check_availability,
                original.instructor_id,
                payload.booking_date,
                payload.start_time,
                proposed_end_time,
                payload.instructor_service_id or original.instructor_service_id,
                original.id,
            )

            if isinstance(availability, dict):
                available_flag = availability.get("available", False)
            else:
                try:
                    available_flag = bool(availability)
                except Exception:
                    available_flag = False

            if not available_flag:
                reason = None
                if isinstance(availability, dict):
                    reason = availability.get("reason")
                reason = reason or "Requested time is unavailable"
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)

            # Check student self-conflict (using service method, no direct repo access)
            has_student_conflict = await asyncio.to_thread(
                booking_service.check_student_time_conflict,
                student_id=current_user.id,
                booking_date=payload.booking_date,
                start_time=payload.start_time,
                end_time=proposed_end_time,
                exclude_booking_id=original.id,
            )

            if has_student_conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You already have a booking scheduled at this time",
                )

            _student_note = (
                original.student_note
                if isinstance(getattr(original, "student_note", None), str)
                else None
            )
            _meeting_location = (
                original.meeting_location
                if isinstance(getattr(original, "meeting_location", None), str)
                else None
            )
            _location_type_raw = getattr(original, "location_type", None)
            # Validate location_type is canonical (no legacy mapping - clean break)
            if isinstance(_location_type_raw, str):
                if _location_type_raw in VALID_LOCATION_TYPES:
                    _location_type = _location_type_raw
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid location_type: '{_location_type_raw}'. Must be one of: {', '.join(sorted(VALID_LOCATION_TYPES))}",
                    )
            else:
                _location_type = "online"
            _location_address = _safe_str(getattr(original, "location_address", None))
            _location_lat = _safe_float(getattr(original, "location_lat", None))
            _location_lng = _safe_float(getattr(original, "location_lng", None))
            _location_place_id = _safe_str(getattr(original, "location_place_id", None))

            new_booking_data = BookingCreate(
                instructor_id=original.instructor_id,
                instructor_service_id=payload.instructor_service_id
                or original.instructor_service_id,
                booking_date=payload.booking_date,
                start_time=payload.start_time,
                selected_duration=payload.selected_duration,
                student_note=_student_note,
                meeting_location=_meeting_location,
                location_type=_location_type,
                location_address=_location_address,
                location_lat=_location_lat,
                location_lng=_location_lng,
                location_place_id=_location_place_id,
            )

            raw_payment_intent_id = getattr(original, "payment_intent_id", None)
            raw_payment_status = getattr(original, "payment_status", None)
            normalized_payment_status = raw_payment_status
            if raw_payment_status == "requires_capture":
                normalized_payment_status = PaymentStatus.AUTHORIZED.value
            elif raw_payment_status == "succeeded":
                normalized_payment_status = PaymentStatus.SETTLED.value
            reuse_payment = (
                isinstance(raw_payment_intent_id, str)
                and raw_payment_intent_id.startswith("pi_")
                and isinstance(normalized_payment_status, str)
                and normalized_payment_status
                in {PaymentStatus.AUTHORIZED.value, PaymentStatus.SETTLED.value}
            )

            initiator_role = "student" if current_user.id == original.student_id else "instructor"
            hours_until_original = await asyncio.to_thread(
                booking_service.get_hours_until_start, original
            )
            should_lock = await asyncio.to_thread(
                booking_service.should_trigger_lock, original, initiator_role
            )

            force_stripe_cancel = initiator_role == "student" and hours_until_original < 12

            if should_lock:
                await asyncio.to_thread(booking_service.activate_lock_for_reschedule, original.id)
                new_booking = await asyncio.to_thread(
                    booking_service.create_rescheduled_booking_with_locked_funds,
                    current_user,
                    new_booking_data,
                    payload.selected_duration,
                    original.id,
                )
            elif reuse_payment and not force_stripe_cancel:
                new_booking = await asyncio.to_thread(
                    booking_service.create_rescheduled_booking_with_existing_payment,
                    current_user,
                    new_booking_data,
                    payload.selected_duration,
                    original.id,
                    cast(str, raw_payment_intent_id),
                    cast(Optional[str], normalized_payment_status),
                    cast(Optional[str], getattr(original, "payment_method_id", None)),
                )
            else:
                # Preflight: Check payment method (using service method, no direct db access)
                has_payment_method, stripe_pm_id = await asyncio.to_thread(
                    booking_service.validate_reschedule_payment_method,
                    current_user.id,
                )

                if not has_payment_method or not stripe_pm_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "code": "payment_method_required_for_reschedule",
                            "message": "A payment method is required to reschedule this lesson. Please add a payment method and try again.",
                        },
                    )

                new_booking = await asyncio.to_thread(
                    booking_service.create_booking_with_payment_setup,
                    current_user,
                    new_booking_data,
                    payload.selected_duration,
                    original.id,
                )

                # Auto-confirm payment
                try:
                    new_booking = await asyncio.to_thread(
                        booking_service.confirm_booking_payment,
                        new_booking.id,
                        current_user,
                        stripe_pm_id,
                        False,
                    )
                except Exception as e:
                    logger.error(f"Failed to confirm payment for rescheduled booking: {e}")
                    # Abort the pending booking (using service method, no direct db access)
                    await asyncio.to_thread(booking_service.abort_pending_booking, new_booking.id)

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "code": "payment_confirmation_failed",
                            "message": "We couldn't process your payment method. Please try again or update your payment method.",
                        },
                    )

            # Cancel original booking
            try:
                if should_lock:
                    await asyncio.to_thread(
                        booking_service.cancel_booking_without_stripe,
                        booking_id,
                        current_user,
                        "Rescheduled",
                    )
                elif reuse_payment and not force_stripe_cancel:
                    await asyncio.to_thread(
                        booking_service.cancel_booking_without_stripe,
                        booking_id,
                        current_user,
                        "Rescheduled",
                        clear_payment_intent=True,
                    )
                else:
                    await asyncio.to_thread(
                        booking_service.cancel_booking, booking_id, current_user, "Rescheduled"
                    )
            except DomainException as e:
                raise e
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return BookingResponse.from_booking(new_booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/complete",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={
        403: {"description": "Permission denied"},
        404: {"description": "Booking not found"},
    },
)
async def complete_booking(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(require_permission(PermissionName.COMPLETE_BOOKINGS)),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Mark a booking as completed.

    Requires: COMPLETE_BOOKINGS permission (instructor only)
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            booking = await asyncio.to_thread(
                booking_service.complete_booking, booking_id, current_user
            )
            return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/no-show",
    response_model=NoShowReportResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={
        403: {"description": "Permission denied"},
        404: {"description": "Booking not found"},
    },
)
async def report_no_show(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    request: NoShowReportRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> NoShowReportResponse:
    """
    Report a no-show for a booking.

    - Student can report instructor no-show
    - Admin can report either type
    - Must be within reporting window
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            result = await asyncio.to_thread(
                booking_service.report_no_show,
                booking_id=booking_id,
                reporter=current_user,
                no_show_type=request.no_show_type,
                reason=request.reason,
            )
            return NoShowReportResponse.model_validate(result)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/no-show/dispute",
    response_model=NoShowDisputeResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={
        403: {"description": "Permission denied"},
        404: {"description": "Booking not found"},
    },
)
async def dispute_no_show(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    request: NoShowDisputeRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> NoShowDisputeResponse:
    """
    Dispute a no-show report.

    Only the accused party can dispute within 24 hours of report.
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            result = await asyncio.to_thread(
                booking_service.dispute_no_show,
                booking_id=booking_id,
                disputer=current_user,
                reason=request.reason,
            )
            return NoShowDisputeResponse.model_validate(result)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/confirm-payment",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("payment"))],
    responses={404: {"description": "Booking not found"}},
    deprecated=True,
)
async def confirm_booking_payment(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    payment_data: BookingConfirmPayment = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Confirm payment method for a booking (Phase 2.1).

    Deprecated: use /api/v1/payments/checkout instead.
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            booking = await asyncio.to_thread(
                booking_service.confirm_booking_payment,
                booking_id,
                current_user,
                payment_data.payment_method_id,
                payment_data.save_payment_method,
            )

            return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.patch(
    "/{booking_id}/payment-method",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("payment"))],
    responses={404: {"description": "Booking not found"}},
)
async def update_booking_payment_method(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    payment_data: BookingPaymentMethodUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Update booking payment method and retry authorization immediately.

    - Verifies ownership (student)
    - Saves payment method (optional set_as_default)
    - Retries authorization off-session (immediate if <24h)
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            booking = await asyncio.to_thread(
                booking_service.confirm_booking_payment,
                booking_id,
                current_user,
                payment_data.payment_method_id,
                payment_data.set_as_default,
            )
            return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/retry-payment",
    response_model=RetryPaymentResponse,
    dependencies=[Depends(new_rate_limit("payment"))],
    responses={404: {"description": "Booking not found"}},
)
async def retry_payment_authorization(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> RetryPaymentResponse:
    """
    Retry payment authorization after a failed attempt.
    """
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            result = await asyncio.to_thread(
                booking_service.retry_authorization,
                booking_id=booking_id,
                user=current_user,
            )
            return RetryPaymentResponse.model_validate(result)
    except DomainException as e:
        handle_domain_exception(e)
