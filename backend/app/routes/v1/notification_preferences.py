# backend/app/routes/v1/notification_preferences.py
"""Notification preference routes - API v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...database import get_db
from ...models.user import User
from ...schemas.notification_preferences import (
    BulkUpdateRequest,
    PreferenceResponse,
    PreferencesByCategory,
    UpdatePreferenceRequest,
)
from ...services.notification_preference_service import NotificationPreferenceService

router = APIRouter(tags=["notification-preferences-v1"])


def _get_preference_service(db: Session) -> NotificationPreferenceService:
    return NotificationPreferenceService(db)


@router.get("", response_model=PreferencesByCategory)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferencesByCategory:
    """Get all notification preferences for current user, grouped by category."""
    service = _get_preference_service(db)
    preferences = service.get_preferences_by_category(current_user.id)
    return PreferencesByCategory.model_validate(preferences)


@router.put("", response_model=list[PreferenceResponse])
def update_preferences_bulk(
    request: BulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[PreferenceResponse]:
    """Update multiple notification preferences at once."""
    service = _get_preference_service(db)
    updates = [item.model_dump() for item in request.updates]
    preferences = service.update_preferences_bulk(current_user.id, updates)
    return [PreferenceResponse.model_validate(pref) for pref in preferences]


@router.put("/{category}/{channel}", response_model=PreferenceResponse)
def update_preference(
    category: str,
    channel: str,
    request: UpdatePreferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferenceResponse:
    """Update a single notification preference."""
    service = _get_preference_service(db)
    try:
        preference = service.update_preference(
            user_id=current_user.id,
            category=category,
            channel=channel,
            enabled=request.enabled,
        )
        return PreferenceResponse.model_validate(preference)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
