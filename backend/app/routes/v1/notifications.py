# backend/app/routes/v1/notifications.py
"""Notification inbox routes - API v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...database import get_db
from ...models.user import User
from ...schemas.notifications import (
    NotificationListResponse,
    NotificationResponse,
    NotificationStatusResponse,
    NotificationUnreadCountResponse,
)
from ...services.notification_service import NotificationService

router = APIRouter(tags=["notifications-v1"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationListResponse:
    """List notifications for the current user."""
    service = NotificationService(db)
    notifications = service.get_notifications(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    total = service.get_notification_count(current_user.id, unread_only=unread_only)
    unread_count = service.get_unread_count(current_user.id)

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(item) for item in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationUnreadCountResponse:
    """Get unread notification count for the current user."""
    service = NotificationService(db)
    unread_count = service.get_unread_count(current_user.id)
    return NotificationUnreadCountResponse(unread_count=unread_count)


@router.post("/read-all", response_model=NotificationStatusResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationStatusResponse:
    """Mark all notifications as read."""
    service = NotificationService(db)
    count = service.mark_all_as_read(current_user.id)
    return NotificationStatusResponse(
        success=True,
        message=f"Marked {count} notifications as read",
    )


@router.delete("", response_model=NotificationStatusResponse)
def delete_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationStatusResponse:
    """Delete all notifications for the current user."""
    service = NotificationService(db)
    deleted = service.delete_all_notifications(current_user.id)
    return NotificationStatusResponse(
        success=True,
        message=f"Deleted {deleted} notifications",
    )


@router.post("/{notification_id}/read", response_model=NotificationStatusResponse)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationStatusResponse:
    """Mark a notification as read."""
    service = NotificationService(db)
    updated = service.mark_as_read(current_user.id, notification_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationStatusResponse(success=True, message="Notification marked as read")


@router.delete("/{notification_id}", response_model=NotificationStatusResponse)
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationStatusResponse:
    """Delete a notification."""
    service = NotificationService(db)
    deleted = service.delete_notification(current_user.id, notification_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationStatusResponse(success=True, message="Notification deleted")
