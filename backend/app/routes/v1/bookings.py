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
    POST /{booking_id}/no-show - Mark booking as no-show (instructor only)
    POST /{booking_id}/confirm-payment - Confirm payment method
    PATCH /{booking_id}/payment-method - Update booking payment method
"""

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, NoReturn, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies import get_booking_service, get_current_active_user, get_db
from ...api.dependencies.auth import require_beta_phase_access
from ...core.config import settings
from ...core.enums import PermissionName
from ...core.exceptions import DomainException, NotFoundException, ValidationException
from ...dependencies.permissions import require_permission
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.booking import BookingStatus
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
from ...repositories.factory import RepositoryFactory
from ...repositories.review_repository import ReviewTipRepository
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
    PaymentSummary,
    UpcomingBookingResponse,
)
from ...schemas.booking_responses import BookingPreviewResponse, SendRemindersResponse
from ...schemas.pricing_preview import PricingPreviewOut
from ...services.booking_service import BookingService
from ...services.config_service import ConfigService
from ...services.payment_summary_service import build_student_payment_summary

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["bookings-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def handle_domain_exception(exc: DomainException) -> NoReturn:
    """Convert domain exceptions to HTTP exceptions."""
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


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
        from ...core.enums import RoleName

        if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
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
        result = await booking_service.check_availability(
            instructor_id=check_data.instructor_id,
            booking_date=check_data.booking_date,
            start_time=check_data.start_time,
            end_time=check_data.end_time,
            service_id=check_data.instructor_service_id,
            exclude_booking_id=None,
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
        count = await booking_service.send_booking_reminders()
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
                    is_instructor = current_user.id == booking.get("instructor_id")

                    if "instructor" in booking and isinstance(booking["instructor"], dict):
                        instructor_last_name = booking["instructor"].get("last_name", "")
                        booking["instructor"]["last_initial"] = (
                            instructor_last_name
                            if is_instructor
                            else instructor_last_name[0]
                            if instructor_last_name
                            else ""
                        )
                        if "last_name" in booking["instructor"]:
                            del booking["instructor"]["last_name"]

                    booking_responses.append(booking)
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
        if not any(role.name == "student" for role in current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can create bookings",
            )

        selected_duration = booking_data.selected_duration

        # Create booking with pending_payment status
        booking = await booking_service.create_booking_with_payment_setup(
            student=current_user, booking_data=booking_data, selected_duration=selected_duration
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
            location_type=booking.location_type or "neutral",
            location_type_display=booking.location_type_display
            if booking.location_type
            else "Neutral Location",
            meeting_location=booking.meeting_location,
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
    from ...schemas.pricing_preview import PricingPreviewData
    from ...services.pricing_service import PricingService

    booking = await asyncio.to_thread(booking_service.repository.get_by_id, booking_id, False)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    allowed_participants = {booking.student_id, booking.instructor_id}
    if current_user.id not in allowed_participants:
        logger.warning(
            "pricing_preview.forbidden",
            extra={
                "booking_id": booking_id,
                "requested_by": current_user.id,
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    pricing_service = PricingService(booking_service.db)
    try:
        pricing_data: PricingPreviewData = await asyncio.to_thread(
            pricing_service.compute_booking_pricing,
            booking_id,
            applied_credit_cents,
            False,
        )
    except DomainException as exc:
        raise exc.to_http_exception() from exc

    return PricingPreviewOut(**pricing_data)


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
    db: Session = Depends(get_db),
) -> BookingResponse:
    """Get full booking details with privacy protection for students."""
    try:
        booking = await asyncio.to_thread(
            booking_service.get_booking_for_user, booking_id, current_user
        )
        if not booking:
            raise NotFoundException("Booking not found")

        payment_summary_data: PaymentSummary | None = None
        if booking.student_id == current_user.id:
            config_service = ConfigService(db)
            pricing_config, _ = await asyncio.to_thread(config_service.get_pricing_config)
            payment_repo = RepositoryFactory.create_payment_repository(db)
            tip_repo = ReviewTipRepository(db)
            payment_summary_data = build_student_payment_summary(
                booking=booking,
                pricing_config=pricing_config,
                payment_repo=payment_repo,
                review_tip_repo=tip_repo,
            )

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
        booking = await booking_service.cancel_booking(
            booking_id=booking_id, user=current_user, reason=cancel_data.reason
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
        # Load original booking
        original = booking_service.get_booking_for_user(booking_id, current_user)
        if not original:
            raise NotFoundException("Booking not found")

        # Pre-validate the requested slot
        start_dt = datetime.combine(payload.booking_date, payload.start_time)
        end_dt = start_dt + timedelta(minutes=payload.selected_duration)
        proposed_end_time = end_dt.time()

        availability = await booking_service.check_availability(
            instructor_id=original.instructor_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=proposed_end_time,
            service_id=payload.instructor_service_id or original.instructor_service_id,
            exclude_booking_id=original.id,
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

        # Check student self-conflict
        try:
            has_student_conflict = bool(
                booking_service.repository.check_student_time_conflict(
                    student_id=current_user.id,
                    booking_date=payload.booking_date,
                    start_time=payload.start_time,
                    end_time=proposed_end_time,
                    exclude_booking_id=original.id,
                )
            )
        except Exception:
            has_student_conflict = False

        if has_student_conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a booking scheduled at this time",
            )

        # Preflight: Check payment method
        from ...services.config_service import ConfigService as _ConfigService
        from ...services.pricing_service import PricingService as _PricingService
        from ...services.stripe_service import StripeService as _StripeService

        config_service = _ConfigService(booking_service.db)
        pricing_service = _PricingService(booking_service.db)
        stripe_service = _StripeService(
            booking_service.db,
            config_service=config_service,
            pricing_service=pricing_service,
        )

        default_pm = stripe_service.payment_repository.get_default_payment_method(current_user.id)

        if not default_pm or not default_pm.stripe_payment_method_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "payment_method_required_for_reschedule",
                    "message": "A payment method is required to reschedule this lesson. Please add a payment method and try again.",
                },
            )

        # Create new booking
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
        _location_type = (
            _location_type_raw
            if isinstance(_location_type_raw, str)
            and _location_type_raw in ["student_home", "instructor_location", "neutral"]
            else "neutral"
        )

        new_booking_data = BookingCreate(
            instructor_id=original.instructor_id,
            instructor_service_id=payload.instructor_service_id or original.instructor_service_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            selected_duration=payload.selected_duration,
            student_note=_student_note,
            meeting_location=_meeting_location,
            location_type=_location_type,
        )

        new_booking = await booking_service.create_booking_with_payment_setup(
            student=current_user,
            booking_data=new_booking_data,
            selected_duration=payload.selected_duration,
            rescheduled_from_booking_id=original.id,
        )

        # Auto-confirm payment
        try:
            new_booking = await booking_service.confirm_booking_payment(
                booking_id=new_booking.id,
                student=current_user,
                payment_method_id=default_pm.stripe_payment_method_id,
                save_payment_method=False,
            )
        except Exception as e:
            logger.error(f"Failed to confirm payment for rescheduled booking: {e}")
            try:
                booking_service.db.delete(new_booking)
                booking_service.db.commit()
            except Exception:
                pass

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "payment_confirmation_failed",
                    "message": "We couldn't process your payment method. Please try again or update your payment method.",
                },
            )

        # Cancel original booking
        try:
            await booking_service.cancel_booking(
                booking_id=booking_id, user=current_user, reason="Rescheduled"
            )
        except DomainException as e:
            raise e
        except Exception:
            pass

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
        booking = await asyncio.to_thread(
            booking_service.complete_booking, booking_id, current_user
        )
        return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/no-show",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("write"))],
    responses={
        403: {"description": "Permission denied"},
        404: {"description": "Booking not found"},
    },
)
async def mark_booking_no_show(
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
    Mark a booking as no-show (student didn't attend).

    Only the instructor for this booking can mark it as no-show.
    The booking must be in CONFIRMED status.

    Requires: COMPLETE_BOOKINGS permission (instructor only)
    """
    try:
        booking = await asyncio.to_thread(booking_service.mark_no_show, booking_id, current_user)
        return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)


@router.post(
    "/{booking_id}/confirm-payment",
    response_model=BookingResponse,
    dependencies=[Depends(new_rate_limit("payment"))],
    responses={404: {"description": "Booking not found"}},
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

    Called after frontend collects card details via SetupIntent.
    This completes the booking creation flow.
    """
    try:
        booking = await booking_service.confirm_booking_payment(
            booking_id=booking_id,
            student=current_user,
            payment_method_id=payment_data.payment_method_id,
            save_payment_method=payment_data.save_payment_method,
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
        booking = await booking_service.confirm_booking_payment(
            booking_id=booking_id,
            student=current_user,
            payment_method_id=payment_data.payment_method_id,
            save_payment_method=payment_data.set_as_default,
        )
        return BookingResponse.from_booking(booking)
    except DomainException as e:
        handle_domain_exception(e)
