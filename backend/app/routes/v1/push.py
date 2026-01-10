# backend/app/routes/v1/push.py
"""Push notification routes - API v1."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...database import get_db
from ...models.user import User
from ...schemas.push import (
    PushStatusResponse,
    PushSubscribeRequest,
    PushSubscriptionResponse,
    PushUnsubscribeRequest,
    VapidPublicKeyResponse,
)
from ...services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

# V1 router - mounted at /api/v1/push
router = APIRouter(tags=["push-v1"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key() -> VapidPublicKeyResponse:
    """
    Get the VAPID public key for push subscription.

    This endpoint is public - the key is needed by the browser
    to subscribe to push notifications.
    """
    if not PushNotificationService.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications not configured",
        )

    return VapidPublicKeyResponse(public_key=PushNotificationService.get_vapid_public_key())


@router.post("/subscribe", response_model=PushStatusResponse)
def subscribe_to_push(
    request: PushSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PushStatusResponse:
    """
    Subscribe to push notifications.

    Called by the frontend after the user grants notification permission
    and the browser creates a push subscription.
    """
    service = PushNotificationService(db)

    try:
        service.subscribe(
            user_id=current_user.id,
            endpoint=request.endpoint,
            p256dh_key=request.p256dh_key,
            auth_key=request.auth_key,
            user_agent=request.user_agent,
        )
        return PushStatusResponse(success=True, message="Subscribed to push notifications")
    except Exception as exc:
        logger.error("Failed to subscribe to push notifications: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.delete("/unsubscribe", response_model=PushStatusResponse)
def unsubscribe_from_push(
    request: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PushStatusResponse:
    """
    Unsubscribe from push notifications.

    Called when user disables notifications or subscription expires.
    """
    service = PushNotificationService(db)

    deleted = service.unsubscribe(user_id=current_user.id, endpoint=request.endpoint)

    if deleted:
        return PushStatusResponse(success=True, message="Unsubscribed from push notifications")
    return PushStatusResponse(success=False, message="Subscription not found")


@router.get("/subscriptions", response_model=list[PushSubscriptionResponse])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[PushSubscriptionResponse]:
    """
    List all push subscriptions for the current user.

    Users may have multiple subscriptions (different devices/browsers).
    """
    service = PushNotificationService(db)
    subscriptions = service.get_user_subscriptions(current_user.id)
    return [PushSubscriptionResponse.model_validate(item) for item in subscriptions]
