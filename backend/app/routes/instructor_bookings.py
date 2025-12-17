"""
Instructor booking management endpoints.

Handles instructor-side booking operations including:
- Marking lessons as complete (triggers 24hr payment capture)
- Viewing pending completion bookings
- Disputing completion status
- Managing payment capture flow

These endpoints are separate from the instructor profile management
endpoints in instructors.py.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.api.dependencies.auth import require_beta_access
from app.core.enums import PermissionName
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.base_responses import PaginatedResponse
from app.schemas.booking import BookingResponse
from app.services.badge_award_service import BadgeAwardService
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/instructors/bookings", tags=["instructor-bookings"])
# Mirror routes under /api for environments that mount the backend behind that prefix
api_router = APIRouter(prefix="/api", tags=["instructor-bookings"])


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


@router.post(
    "/{booking_id}/complete",
    response_model=BookingResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def mark_lesson_complete(
    booking_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
    # NOTE: This route is currently the only mechanism that transitions a booking
    # from CONFIRMED to COMPLETED. Automated completion has not been implemented yet.
    # Check permission
    check_permission(current_user, PermissionName.COMPLETE_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)
    payment_repo = RepositoryFactory.get_payment_repository(db)

    # Get the booking
    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    # Verify this is the instructor's booking
    if booking.instructor_id != current_user.id:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="You can only mark your own lessons as complete",
        )

    # Verify booking is in correct status
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail=f"Cannot mark booking as complete. Current status: {booking.status}",
        )

    # Verify lesson has ended
    now = datetime.now(timezone.utc)
    lesson_end = datetime.combine(booking.booking_date, booking.end_time)
    if lesson_end > now:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Cannot mark lesson as complete before it ends",
        )

    # Mark as completed
    booking.status = BookingStatus.COMPLETED
    booking.completed_at = now

    if notes:
        booking.instructor_note = notes

    # Record completion event
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="instructor_marked_complete",
        event_data={
            "instructor_id": current_user.id,
            "completed_at": now.isoformat(),
            "notes": notes,
            "payment_capture_scheduled_for": (now + timedelta(hours=24)).isoformat(),
        },
    )

    # Trigger badge checks before commit
    badge_service = BadgeAwardService(db)
    booked_at = booking.confirmed_at or booking.created_at or now
    category_slug = None
    try:
        instructor_service = booking.instructor_service
        if instructor_service and instructor_service.catalog_entry:
            category = instructor_service.catalog_entry.category
            if category:
                category_slug = category.slug
    except AttributeError:
        category_slug = None

    badge_service.check_and_award_on_lesson_completed(
        student_id=booking.student_id,
        lesson_id=booking.id,
        instructor_id=booking.instructor_id,
        category_slug=category_slug,
        booked_at_utc=booked_at,
        completed_at_utc=now,
    )

    db.commit()

    # Return the updated booking
    db.refresh(booking)
    return BookingResponse.from_booking(booking)


@router.get(
    "/pending-completion",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
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
    "/",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
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
    check_permission(current_user, PermissionName.VIEW_INCOMING_BOOKINGS, db)
    booking_repo = RepositoryFactory.get_booking_repository(db)

    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id,
        status=status,
        upcoming_only=upcoming,
        include_past_confirmed=include_past_confirmed,
    )
    return _paginate_bookings(bookings, page=page, per_page=per_page)


@router.get(
    "/upcoming",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def get_upcoming_bookings(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[BookingResponse]:
    """Return instructor's upcoming confirmed bookings."""
    return await list_instructor_bookings(
        status=BookingStatus.CONFIRMED,
        upcoming=True,
        page=page,
        per_page=per_page,
        db=db,
        current_user=current_user,
    )


@router.get(
    "/completed",
    response_model=PaginatedResponse[BookingResponse],
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def get_completed_bookings(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[BookingResponse]:
    """
    Get instructor's completed bookings.

    Args:
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        List of completed bookings
    """
    return await list_instructor_bookings(
        status=BookingStatus.COMPLETED,
        upcoming=False,
        page=page,
        per_page=per_page,
        db=db,
        current_user=current_user,
        include_past_confirmed=True,
    )


@router.post(
    "/{booking_id}/dispute",
    response_model=BookingResponse,
    dependencies=[Depends(require_beta_access("instructor"))],
)
async def dispute_completion(
    booking_id: str,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
    check_permission(current_user, PermissionName.COMPLETE_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)
    payment_repo = RepositoryFactory.get_payment_repository(db)

    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    # Verify this is the instructor's booking
    if booking.instructor_id != current_user.id:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="You can only dispute your own lessons",
        )

    # Record dispute event
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="completion_disputed",
        event_data={
            "disputed_by": current_user.id,
            "reason": reason,
            "disputed_at": datetime.now(timezone.utc).isoformat(),
            "payment_capture_paused": True,
        },
    )

    # Update payment status to prevent capture
    if booking.payment_status == "authorized":
        booking.payment_status = "disputed"

    db.commit()

    # Return the updated booking
    db.refresh(booking)
    return BookingResponse.from_booking(booking)


api_router.include_router(router)  # type: ignore[attr-defined]
