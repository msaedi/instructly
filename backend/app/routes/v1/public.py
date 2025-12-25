# backend/app/routes/v1/public.py
"""
V1 Public routes for InstaInstru platform.

These routes do not require authentication and are designed for
student-facing features like viewing instructor availability.

Key Design Decisions:
1. No authentication required - these are public endpoints
2. No internal IDs exposed except instructor_id
3. Heavy caching for performance
4. Only shows actually bookable slots (accounts for existing bookings)
5. Respects blackout dates
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
from typing import Any, Dict, List, Mapping, Optional, Tuple, TypedDict, Union, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session
import ulid

from ...core.config import settings
from ...core.timezone_utils import get_user_today
from ...database import get_db
from ...schemas.public_availability import (
    NextAvailableSlotResponse,
    PublicDayAvailability,
    PublicInstructorAvailability,
    PublicTimeSlot,
)
from ...schemas.public_session import GuestSessionResponse
from ...schemas.referrals import ReferralSendError, ReferralSendRequest, ReferralSendResponse
from ...services.availability_service import AvailabilityService
from ...services.cache_service import CacheService
from ...services.conflict_checker import ConflictChecker
from ...services.email import EmailService
from ...services.instructor_service import InstructorService
from ...utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)

# V1 router - mounted at /api/v1/public
router = APIRouter(tags=["public"])


class AvailabilitySummaryEntry(TypedDict):
    date: str
    morning_available: bool
    afternoon_available: bool
    evening_available: bool
    total_hours: float


def get_availability_service(db: Session = Depends(get_db)) -> AvailabilityService:
    """Get availability service instance."""
    return AvailabilityService(db)


def get_conflict_checker(db: Session = Depends(get_db)) -> ConflictChecker:
    """Get conflict checker instance."""
    return ConflictChecker(db)


def get_instructor_service(db: Session = Depends(get_db)) -> InstructorService:
    """Get instructor service instance."""
    return InstructorService(db)


def get_cache_service_dep(db: Session = Depends(get_db)) -> Optional[CacheService]:
    """Get cache service instance."""
    try:
        from ...services.cache_service import get_cache_service

        return get_cache_service(db)
    except Exception:
        return None


@router.post("/session/guest", response_model=GuestSessionResponse)
def create_guest_session(
    response_obj: Response, request: Request
) -> Response | GuestSessionResponse:
    """Issue a first-party guest_id cookie used for optional auth endpoints.

    Sets cookie attributes appropriate for cross-site subdomains in preview/prod.
    """
    guest_id: Optional[str] = None
    if hasattr(request, "cookies"):
        cookies = cast(Mapping[str, str], request.cookies)
        guest_id = cookies.get("guest_id")
    if guest_id:
        # Idempotent: if already set, return 204 No Content with empty body
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    # Create new guest id
    guest_id = str(ulid.ULID())

    # Cookie defaults
    import os as _os

    site_mode = (_os.getenv("SITE_MODE", "").lower().strip()) or "local"
    cookie_kwargs: Dict[str, Union[str, bool, int]] = {
        "httponly": True,
        "samesite": "lax",
        "path": "/",
        "max_age": 60 * 60 * 24 * 30,
    }
    if site_mode in {"preview", "prod", "production", "live"}:
        cookie_kwargs["secure"] = True
        cookie_kwargs["domain"] = ".instainstru.com"

    # Set cookie and return typed response model
    response_obj.set_cookie("guest_id", guest_id, **cookie_kwargs)
    return GuestSessionResponse(guest_id=guest_id)


@router.post("/logout")
def public_logout(response_obj: Response, request: Request) -> Response:
    """Clear known session cookies. Public to support cross-origin preview logout.

    This does not revoke server sessions; it only instructs the browser to drop cookies.
    """
    secure_flag = bool(settings.session_cookie_secure)
    samesite = settings.session_cookie_samesite or "lax"
    domain = settings.session_cookie_domain

    resp = Response(status_code=status.HTTP_204_NO_CONTENT)

    def _delete_session_cookie(name: str, *, domain: str | None = None) -> None:
        resp.delete_cookie(
            key=name,
            path="/",
            domain=domain,
            secure=secure_flag,
            httponly=True,
            samesite=samesite,
        )

    # Clear guest cookie
    resp.delete_cookie(
        "guest_id",
        path="/",
        secure=secure_flag,
        httponly=True,
        samesite=samesite,
        domain=domain,
    )
    # Clear session cookies by env
    session_names = session_cookie_candidates(settings.site_mode)
    if session_names:
        _delete_session_cookie(session_names[0])

    if len(session_names) > 1:
        for legacy_name in session_names[1:]:
            legacy_domain = None
            if settings.site_mode in {"preview", "prod"}:
                legacy_domain = ".instainstru.com"
            if legacy_name.startswith("__Host-"):
                legacy_domain = None
            _delete_session_cookie(legacy_name, domain=legacy_domain)
    return resp


@router.get(
    "/instructors/{instructor_id}/availability",
    response_model=PublicInstructorAvailability,
    response_model_exclude_none=True,
    summary="Get instructor availability for students",
    description="Public endpoint to view instructor's available time slots for booking. No authentication required. Response detail level depends on configuration.",
)
async def get_instructor_public_availability(
    instructor_id: str,
    request: Request,
    response_obj: Response,
    start_date: date = Query(..., description="Start date for availability search"),
    end_date: Optional[date] = Query(
        None, description="End date (defaults to configured days from start)"
    ),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    instructor_service: InstructorService = Depends(get_instructor_service),
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
    db: Session = Depends(get_db),
) -> PublicInstructorAvailability:
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
    # Validate instructor exists and has profile using service layer
    try:
        instructor_user = await asyncio.to_thread(
            instructor_service.get_instructor_user, instructor_id
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")
    # Canonicalize to instructor user_id for downstream queries/caching.
    instructor_id = instructor_user.id

    # Validate dates using instructor's timezone
    instructor_today = get_user_today(instructor_user)
    if start_date < instructor_today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date cannot be in the past (instructor timezone)",
        )

    # If end_date is provided, validate it
    if end_date:
        if end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be after start date"
            )

        # Check if range is too large
        if (end_date - start_date).days > 90:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Date range cannot exceed 90 days"
            )

    # NOW set default end_date if not provided
    if not end_date:
        end_date = start_date + timedelta(
            days=settings.public_availability_days - 1
        )  # -1 because range is inclusive

    # Enforce configured maximum even if user requests more
    max_end_date = start_date + timedelta(days=settings.public_availability_days - 1)
    if end_date > max_end_date:
        end_date = max_end_date

    # Initialize response_data for type checking
    response_data: Optional[PublicInstructorAvailability] = None

    # Check cache first - include detail level in cache key
    cache_key = f"public_availability:{instructor_id}:{start_date}:{end_date}:{settings.public_availability_detail_level}"
    if cache_service:
        try:
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for public availability: {cache_key}")
                cached_result = cast(Dict[str, Any], cached_data)
                response_data = PublicInstructorAvailability(**cached_result)

                # Generate ETag for cached response
                response_json = response_data.model_dump_json(exclude_none=True)
                etag_data = f"{instructor_id}:{start_date}:{end_date}:{response_json}"
                etag_hash = hashlib.md5(etag_data.encode()).hexdigest()
                etag = f'W/"{etag_hash}"'

                # Check If-None-Match for 304 response
                if_none_match = request.headers.get("If-None-Match")
                if if_none_match and if_none_match == etag:
                    response_obj.headers["ETag"] = etag
                    response_obj.headers["Cache-Control"] = "private, no-cache, must-revalidate"
                    response_obj.headers["Vary"] = "Accept-Encoding"
                    response_obj.status_code = status.HTTP_304_NOT_MODIFIED
                    return response_data

                # Return cached response (skip DB computation)
                response_obj.headers["Cache-Control"] = "private, no-cache, must-revalidate"
                response_obj.headers["ETag"] = etag
                response_obj.headers["Vary"] = "Accept-Encoding"
                return response_data
        except Exception as e:
            logger.warning(f"Cache error: {e}")

    # Cache miss - compute fresh data below

    # Build response based on detail level
    if settings.public_availability_detail_level == "minimal":
        # Minimal: Just check if any availability exists
        all_slots = await asyncio.to_thread(
            availability_service.get_week_windows_as_slot_like,
            instructor_id,
            start_date,
            end_date,
        )

        response_data = PublicInstructorAvailability(
            instructor_id=instructor_id,
            instructor_first_name=(
                instructor_user.first_name
                if settings.public_availability_show_instructor_name
                else None
            ),
            instructor_last_initial=(
                instructor_user.last_name[0]
                if (settings.public_availability_show_instructor_name and instructor_user.last_name)
                else None
            ),
            detail_level="minimal",
            has_availability=len(all_slots) > 0,
            earliest_available_date=all_slots[0]["specific_date"].isoformat()
            if all_slots
            else None,
            timezone="America/New_York",
        )

    elif settings.public_availability_detail_level == "summary":
        # Summary: Show counts and time ranges, not specific slots
        all_slots = await asyncio.to_thread(
            availability_service.get_week_windows_as_slot_like,
            instructor_id,
            start_date,
            end_date,
        )

        # Group by morning/afternoon/evening
        availability_summary: Dict[str, AvailabilitySummaryEntry] = {}
        for slot in all_slots:
            date_str = slot["specific_date"].isoformat()
            if date_str not in availability_summary:
                availability_summary[date_str] = {
                    "date": date_str,
                    "morning_available": False,  # Before noon
                    "afternoon_available": False,  # Noon to 5pm
                    "evening_available": False,  # After 5pm
                    "total_hours": 0,
                }

            # Categorize time slots
            start_time = slot["start_time"]
            end_time = slot["end_time"]
            if start_time.hour < 12:
                availability_summary[date_str]["morning_available"] = True
            elif start_time.hour < 17:
                availability_summary[date_str]["afternoon_available"] = True
            else:
                availability_summary[date_str]["evening_available"] = True

            # Add hours
            duration = (
                datetime.combine(date.min, end_time, tzinfo=timezone.utc)
                - datetime.combine(date.min, start_time, tzinfo=timezone.utc)
            ).seconds / 3600
            availability_summary[date_str]["total_hours"] += duration

        response_data = PublicInstructorAvailability(
            instructor_id=instructor_id,
            instructor_first_name=(
                instructor_user.first_name
                if settings.public_availability_show_instructor_name
                else None
            ),
            instructor_last_initial=(
                instructor_user.last_name[0]
                if (settings.public_availability_show_instructor_name and instructor_user.last_name)
                else None
            ),
            detail_level="summary",
            availability_summary=availability_summary,
            timezone="America/New_York",
            total_available_days=len(availability_summary),
        )

    else:  # "full" detail level
        # Build availability data
        availability_by_date: Dict[str, PublicDayAvailability] = {}
        total_available_slots = 0
        earliest_available_date: Optional[str] = None

        # Get blackout dates
        blackout_dates = await asyncio.to_thread(
            availability_service.get_blackout_dates, instructor_id
        )
        blackout_date_set = {b.date for b in blackout_dates}

        # Compute merged and booked-subtracted intervals via service
        computed: Dict[str, List[Tuple[time, time]]] = await asyncio.to_thread(
            availability_service.compute_public_availability,
            instructor_id,
            start_date,
            end_date,
        )

        # Process each date in the range
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()

            # Check blackout
            if current_date in blackout_date_set:
                availability_by_date[date_str] = PublicDayAvailability(
                    date=date_str, available_slots=[], is_blackout=True
                )
                current_date += timedelta(days=1)
                continue

            intervals = computed.get(date_str, [])
            available_slots: List[PublicTimeSlot] = [
                PublicTimeSlot(start_time=st.strftime("%H:%M"), end_time=en.strftime("%H:%M"))
                for st, en in intervals
            ]

            total_available_slots += len(available_slots)
            if available_slots and not earliest_available_date:
                earliest_available_date = date_str

            availability_by_date[date_str] = PublicDayAvailability(
                date=date_str, available_slots=available_slots, is_blackout=False
            )

            current_date += timedelta(days=1)

        # Build response - use privacy-protected name fields
        response_data = PublicInstructorAvailability(
            instructor_id=instructor_id,
            instructor_first_name=(
                instructor_user.first_name
                if settings.public_availability_show_instructor_name
                else None
            ),
            instructor_last_initial=(
                instructor_user.last_name[0]
                if (settings.public_availability_show_instructor_name and instructor_user.last_name)
                else None
            ),
            detail_level="full",
            availability_by_date=availability_by_date,
            timezone="America/New_York",  # NYC-based platform
            total_available_slots=total_available_slots,
            earliest_available_date=earliest_available_date,
        )

    # At this point, we have freshly computed response_data (cache miss path)
    assert response_data is not None

    # Use model_dump_json with exclude_none to keep responses clean
    response_json = response_data.model_dump_json(exclude_none=True)

    # Generate ETag based on response content
    # Include instructor_id, date range, and response data in the hash
    etag_data = f"{instructor_id}:{start_date}:{end_date}:{response_json}"
    etag_hash = hashlib.md5(etag_data.encode()).hexdigest()
    etag = f'W/"{etag_hash}"'  # Weak ETag as content may vary slightly

    # Check If-None-Match header for conditional requests
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and if_none_match == etag:
        # Set headers on the response object and return the current data
        # The client will handle the 304 logic based on ETag matching
        response_obj.headers["ETag"] = etag
        response_obj.headers["Cache-Control"] = "private, no-cache, must-revalidate"
        response_obj.headers["Vary"] = "Accept-Encoding"
        response_obj.status_code = status.HTTP_304_NOT_MODIFIED
        # Return the existing data - FastAPI will handle 304 response properly
        return response_data

    # Cache the freshly computed response (we only reach here on cache miss)
    if cache_service:
        try:
            await cache_service.set(
                cache_key,
                response_data.model_dump(exclude_none=True),
                ttl=settings.public_availability_cache_ttl,
            )
        except Exception as e:
            logger.warning(f"Failed to cache public availability: {e}")

    # Set headers - disable browser caching so changes are seen immediately
    response_obj.headers["Cache-Control"] = "private, no-cache, must-revalidate"
    response_obj.headers["ETag"] = etag
    response_obj.headers["Vary"] = "Accept-Encoding"

    return response_data


@router.get(
    "/instructors/{instructor_id}/next-available",
    response_model=NextAvailableSlotResponse,
    summary="Get next available slot for an instructor",
    description="Quick endpoint to find the next available booking slot",
)
async def get_next_available_slot(
    instructor_id: str,
    response_obj: Response,
    duration_minutes: int = Query(60, description="Required duration in minutes"),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    instructor_service: InstructorService = Depends(get_instructor_service),
    db: Session = Depends(get_db),
) -> NextAvailableSlotResponse:
    """
    Find the next available time slot for booking.

    This is a convenience endpoint for "Book Now" functionality.
    """
    # Validate instructor using service layer
    try:
        instructor_user = await asyncio.to_thread(
            instructor_service.get_instructor_user, instructor_id
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")
    # Canonicalize to instructor user_id for downstream queries.
    instructor_id = instructor_user.id

    # Search for next configured days using instructor's timezone
    search_days = settings.public_availability_days
    current_date = get_user_today(instructor_user)

    for _ in range(search_days):
        # Skip if blackout date
        if await asyncio.to_thread(
            conflict_checker.check_blackout_date, instructor_id, current_date
        ):
            current_date += timedelta(days=1)
            continue

        availability_map = await asyncio.to_thread(
            availability_service.compute_public_availability,
            instructor_id,
            current_date,
            current_date,
        )
        slots = availability_map.get(current_date.isoformat(), [])

        if slots:
            # Find first slot that can accommodate the duration
            for slot_start_time, slot_end_time in sorted(slots, key=lambda s: s[0]):
                # Calculate slot duration in minutes
                slot_duration = (
                    datetime.combine(date.min, slot_end_time, tzinfo=timezone.utc)
                    - datetime.combine(date.min, slot_start_time, tzinfo=timezone.utc)
                ).seconds // 60

                if slot_duration >= duration_minutes:
                    # Found an available slot!
                    # Return the requested duration from the start of the slot
                    end_time = (
                        datetime.combine(date.min, slot_start_time, tzinfo=timezone.utc)
                        + timedelta(minutes=duration_minutes)
                    ).time()

                    # Set cache headers for successful results (2 minutes for next-available)
                    response_obj.headers["Cache-Control"] = "public, max-age=120"

                    return NextAvailableSlotResponse(
                        found=True,
                        date=current_date.isoformat(),
                        start_time=slot_start_time.strftime("%H:%M:%S"),
                        end_time=end_time.strftime("%H:%M:%S"),
                        duration_minutes=duration_minutes,
                    )

        current_date += timedelta(days=1)

    # Set cache headers for no-availability results (1 minute)
    response_obj.headers["Cache-Control"] = "public, max-age=60"

    return NextAvailableSlotResponse(
        found=False, message=f"No available slots found in the next {search_days} days"
    )


@router.post(
    "/referrals/send",
    response_model=ReferralSendResponse,
    summary="Send referral invites",
    description="Send referral invitation emails to one or more recipients.",
)
async def send_referral_invites(
    payload: ReferralSendRequest,
    db: Session = Depends(get_db),
) -> ReferralSendResponse:
    """
    Send referral invite emails to a list of recipients.

    Payload: { "emails": ["a@b.com"], "referral_link": "https://instainstru.com/ref/ABC123", "from_name": "Emma" }
    """
    emails: List[str] = list(payload.emails)
    referral_link = str(payload.referral_link)
    from_name = payload.from_name or "A friend"

    if not isinstance(emails, list) or not emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No recipient emails provided"
        )

    logger.info(
        f"[Referrals] Sending invites: count={len(emails)} link={referral_link} from={from_name}"
    )
    email_service = EmailService(db)
    try:
        await asyncio.to_thread(email_service.validate_email_config)
        logger.info("[Referrals] Email config validated")
    except Exception as e:
        logger.error(f"[Referrals] Email config invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Email not configured"
        )

    sent = 0
    failures = 0
    error_details: list[ReferralSendError] = []
    for to_email in emails:
        try:
            await asyncio.to_thread(
                email_service.send_referral_invite,
                to_email=to_email,
                referral_link=referral_link,
                inviter_name=from_name,
            )
            sent += 1
        except Exception as e:
            # continue to next
            logger.error(f"Failed to send referral to {to_email}: {e}")
            failures += 1
            try:
                error_details.append(ReferralSendError(email=to_email, error=str(e)))
            except Exception:
                pass

    logger.info(f"[Referrals] Completed: sent={sent} failed={failures}")
    return ReferralSendResponse(status="ok", sent=sent, failed=failures, errors=error_details)
