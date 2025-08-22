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
from app.core.enums import PermissionName
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.base_responses import PaginatedResponse
from app.schemas.booking import BookingResponse
from app.services.permission_service import PermissionService

router = APIRouter(
    prefix="/instructors/bookings",
    tags=["instructor-bookings"],
)


def check_permission(user: User, permission: PermissionName, db: Session) -> None:
    """Check if user has the specified permission."""
    permission_service = PermissionService(db)
    if not permission_service.user_has_permission(user.id, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"User does not have required permission: {permission}"
        )


@router.post("/{booking_id}/complete", response_model=BookingResponse)
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
    # Check permission
    check_permission(current_user, PermissionName.UPDATE_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)
    payment_repo = RepositoryFactory.get_payment_repository(db)

    # Get the booking
    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    # Verify this is the instructor's booking
    if booking.instructor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You can only mark your own lessons as complete"
        )

    # Verify booking is in correct status
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot mark booking as complete. Current status: {booking.status}",
        )

    # Verify lesson has ended
    now = datetime.now(timezone.utc)
    lesson_end = datetime.combine(booking.booking_date, booking.end_time)
    if lesson_end > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot mark lesson as complete before it ends"
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

    db.commit()

    # Return the updated booking
    db.refresh(booking)
    return BookingResponse.from_booking(booking)


@router.get("/pending-completion", response_model=PaginatedResponse[BookingResponse])
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

    Returns:
        List of bookings pending completion
    """
    check_permission(current_user, PermissionName.VIEW_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)

    # Get instructor's confirmed bookings
    bookings = booking_repo.get_instructor_bookings(instructor_id=current_user.id, status=BookingStatus.CONFIRMED)

    # Filter to only past lessons
    now = datetime.now(timezone.utc)
    pending_bookings = []

    for booking in bookings:
        lesson_end = datetime.combine(booking.booking_date, booking.end_time)
        if lesson_end <= now:
            pending_bookings.append(booking)

    # Calculate pagination
    total = len(pending_bookings)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_bookings = pending_bookings[start:end]

    # Return paginated response
    return PaginatedResponse(
        items=[BookingResponse.from_booking(b) for b in paginated_bookings],
        total=total,
        page=page,
        per_page=per_page,
        has_next=end < total,
        has_prev=page > 1,
    )


@router.get("/completed", response_model=PaginatedResponse[BookingResponse])
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
    check_permission(current_user, PermissionName.VIEW_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)

    # Calculate pagination
    offset = (page - 1) * per_page

    # Get bookings with pagination
    bookings = booking_repo.get_instructor_bookings(
        instructor_id=current_user.id, status=BookingStatus.COMPLETED, limit=per_page, offset=offset
    )

    # Get total count
    total_bookings = booking_repo.get_instructor_bookings(instructor_id=current_user.id, status=BookingStatus.COMPLETED)
    total = len(total_bookings)

    # Return paginated response
    return PaginatedResponse(
        items=[BookingResponse.from_booking(b) for b in bookings],
        total=total,
        page=page,
        per_page=per_page,
        has_next=page * per_page < total,
        has_prev=page > 1,
    )


@router.post("/{booking_id}/dispute", response_model=BookingResponse)
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
    check_permission(current_user, PermissionName.UPDATE_BOOKINGS, db)

    booking_repo = RepositoryFactory.get_booking_repository(db)
    payment_repo = RepositoryFactory.get_payment_repository(db)

    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    # Verify this is the instructor's booking
    if booking.instructor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You can only dispute your own lessons"
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
