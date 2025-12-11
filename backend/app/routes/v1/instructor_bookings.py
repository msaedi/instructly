# backend/app/routes/v1/instructor_bookings.py
"""
Instructor booking management endpoints - API v1

Versioned instructor-side booking operations under /api/v1/instructor-bookings.
All business logic delegated to repositories and services.

Endpoints:
    GET /pending-completion - Bookings awaiting completion
    GET /upcoming - Upcoming confirmed bookings
    GET /completed - Completed bookings
    GET / - List instructor bookings with filters
    POST /{booking_id}/complete - Mark lesson as complete
    POST /{booking_id}/dispute - Dispute completion status
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies import get_current_active_user
from ...api.dependencies.auth import require_beta_access
from ...core.enums import PermissionName
from ...database import get_db
from ...models.booking import Booking, BookingStatus
from ...models.user import User
from ...ratelimit.dependency import rate_limit
from ...repositories.factory import RepositoryFactory
from ...schemas.base_responses import PaginatedResponse
from ...schemas.booking import BookingResponse
from ...services.booking_service import BookingService
from ...services.permission_service import PermissionService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["instructor-bookings-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def get_booking_service(db: Session = Depends(get_db)) -> BookingService:
    """Get an instance of the booking service."""
    return BookingService(db)


def check_permission(user: User, permission: PermissionName, db: Session) -> None:
    """Check if user has the specified permission."""
    permission_service = PermissionService(db)
    if not permission_service.user_has_permission(user.id, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have required permission: {permission}",
        )


def _paginate_bookings(
    bookings: List[Booking],
    *,
    page: int,
    per_page: int,
) -> PaginatedResponse[BookingResponse]:
    """Paginate booking results."""
    total = len(bookings)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = bookings[start:end]

    return PaginatedResponse(
        items=[BookingResponse.from_booking(b) for b in paginated],
        total=total,
        page=page,
        per_page=per_page,
        has_next=end < total,
        has_prev=page > 1,
    )


# ============================================================================
# SECTION 1: Static routes (no path parameters)
# ============================================================================


@router.get(
    "/pending-completion",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("read"))],
)
async def get_pending_completion_bookings(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[BookingResponse]:
    """
    Get all bookings that are pending completion by the instructor.

    Returns bookings that:
    - Are confirmed status
    - Have ended (based on date/time)
    - Haven't been marked complete yet
    """
    check_permission(current_user, PermissionName.VIEW_INCOMING_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)

    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id, status=BookingStatus.CONFIRMED
    )

    now = datetime.now(timezone.utc)
    pending_bookings = [
        booking
        for booking in bookings
        if datetime.combine(booking.booking_date, booking.end_time) <= now
    ]

    return _paginate_bookings(pending_bookings, page=page, per_page=per_page)


@router.get(
    "/upcoming",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("read"))],
)
async def get_upcoming_bookings(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[BookingResponse]:
    """Return instructor's upcoming confirmed bookings."""
    check_permission(current_user, PermissionName.VIEW_INCOMING_BOOKINGS, db)
    booking_repo = RepositoryFactory.get_booking_repository(db)

    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id,
        status=BookingStatus.CONFIRMED,
        upcoming_only=True,
    )
    return _paginate_bookings(bookings, page=page, per_page=per_page)


@router.get(
    "/completed",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("read"))],
)
async def get_completed_bookings(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[BookingResponse]:
    """Get instructor's completed bookings."""
    check_permission(current_user, PermissionName.VIEW_INCOMING_BOOKINGS, db)
    booking_repo = RepositoryFactory.get_booking_repository(db)

    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id,
        status=BookingStatus.COMPLETED,
        upcoming_only=False,
        include_past_confirmed=True,
    )
    return _paginate_bookings(bookings, page=page, per_page=per_page)


# ============================================================================
# SECTION 2: Root routes (no path parameters, but placed after static routes)
# ============================================================================


@router.get(
    "",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("read"))],
)
async def list_instructor_bookings(
    status: Optional[BookingStatus] = Query(
        None, description="Filter by booking status (COMPLETED, CONFIRMED, etc.)"
    ),
    upcoming: bool = Query(False, description="Only include upcoming confirmed bookings"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    include_past_confirmed: bool = False,
) -> PaginatedResponse[BookingResponse]:
    """List instructor bookings with filters."""
    check_permission(current_user, PermissionName.VIEW_INCOMING_BOOKINGS, db)
    booking_repo = RepositoryFactory.get_booking_repository(db)

    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id,
        status=status,
        upcoming_only=upcoming,
        include_past_confirmed=include_past_confirmed,
    )
    return _paginate_bookings(bookings, page=page, per_page=per_page)


# ============================================================================
# SECTION 3: Dynamic routes (with path parameters - placed last)
# ============================================================================


@router.post(
    "/{booking_id}/complete",
    response_model=BookingResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={404: {"description": "Booking not found"}},
)
async def mark_lesson_complete(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Mark a lesson as completed by the instructor.

    This triggers the 24-hour payment capture timer. The payment will be
    captured 24 hours after this endpoint is called, giving the student
    time to dispute if needed.

    Args:
        booking_id: The booking to mark as complete
        notes: Optional completion notes from instructor

    Returns:
        Updated booking information

    Raises:
        404: Booking not found
        422: Booking cannot be marked complete (wrong status, not instructor's booking)
    """
    from ...core.exceptions import BusinessRuleException, NotFoundException, ValidationException

    check_permission(current_user, PermissionName.COMPLETE_BOOKINGS, db)

    try:
        booking = booking_service.instructor_mark_complete(
            booking_id=booking_id,
            instructor=current_user,
            notes=notes,
        )
        return BookingResponse.from_booking(booking)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BusinessRuleException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post(
    "/{booking_id}/dispute",
    response_model=BookingResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={404: {"description": "Booking not found"}},
)
async def dispute_completion(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    """
    Dispute a lesson completion as an instructor.

    Used when a student marks a lesson as complete but the instructor disagrees.
    This pauses payment capture pending resolution.

    Args:
        booking_id: The booking to dispute
        reason: Reason for disputing the completion

    Returns:
        Updated booking information
    """
    from ...core.exceptions import NotFoundException, ValidationException

    check_permission(current_user, PermissionName.COMPLETE_BOOKINGS, db)

    try:
        booking = booking_service.instructor_dispute_completion(
            booking_id=booking_id,
            instructor=current_user,
            reason=reason,
        )
        return BookingResponse.from_booking(booking)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
