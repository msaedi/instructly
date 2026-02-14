# backend/app/services/push_notification_service.py
"""
Push notification service for web push subscriptions and delivery.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from ..core.config import secret_or_plain, settings
from ..models.notification import PushSubscription
from ..repositories.notification_repository import NotificationRepository
from .base import BaseService

logger = logging.getLogger(__name__)

DEFAULT_ICON = "/icons/icon-192x192.png"
DEFAULT_BADGE = "/icons/badge-72x72.png"


class PushNotificationService(BaseService):
    """Service for managing web push notifications."""

    def __init__(
        self,
        db: Session,
        notification_repository: Optional[NotificationRepository] = None,
    ) -> None:
        super().__init__(db)
        self.notification_repository = notification_repository or NotificationRepository(db)
        self._last_send_expired = False
        self._frontend_base = settings.frontend_url.rstrip("/")

    def _resolve_asset_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not self._frontend_base:
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._frontend_base}{path}"

    @BaseService.measure_operation("subscribe")
    def subscribe(
        self,
        user_id: str,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: Optional[str] = None,
    ) -> PushSubscription:
        """
        Store a push subscription for a user.

        Called when user enables push notifications in their browser.
        Handles duplicate subscriptions gracefully (upsert behavior).
        """
        with self.transaction():
            return self.notification_repository.create_subscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                user_agent=user_agent,
            )

    @BaseService.measure_operation("unsubscribe")
    def unsubscribe(self, user_id: str, endpoint: str) -> bool:
        """
        Remove a push subscription.

        Called when user disables push notifications or subscription expires.
        Returns True if subscription was found and deleted.
        """
        with self.transaction():
            return self.notification_repository.delete_subscription(user_id, endpoint)

    @BaseService.measure_operation("unsubscribe_all")
    def unsubscribe_all(self, user_id: str) -> int:
        """
        Remove all push subscriptions for a user.

        Used when user wants to disable push on all devices.
        Returns count of deleted subscriptions.
        """
        with self.transaction():
            return self.notification_repository.delete_all_user_subscriptions(user_id)

    @BaseService.measure_operation("get_user_subscriptions")
    def get_user_subscriptions(self, user_id: str) -> List[PushSubscription]:
        """Get all active push subscriptions for a user."""
        return self.notification_repository.get_user_subscriptions(user_id)

    @BaseService.measure_operation("send_push_notification")
    def send_push_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        tag: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """
        Send push notification to all of a user's subscribed devices.

        Args:
            user_id: Target user
            title: Notification title
            body: Notification body text
            url: URL to open when notification clicked
            icon: Icon URL (defaults to app icon)
            badge: Badge icon URL
            tag: Tag for notification grouping/replacement
            data: Additional data payload

        Returns:
            dict with 'sent', 'failed', 'expired' counts
        """
        if not self.is_configured():
            self.logger.warning("Push notifications not configured; skipping send")
            return {"sent": 0, "failed": 0, "expired": 0}

        subscriptions = self.get_user_subscriptions(user_id)
        if not subscriptions:
            return {"sent": 0, "failed": 0, "expired": 0}

        payload = self._build_payload(
            title=title,
            body=body,
            url=url,
            icon=icon,
            badge=badge,
            tag=tag,
            data=data,
        )

        sent = 0
        failed = 0
        expired = 0

        for subscription in subscriptions:
            success = self._send_to_subscription(subscription, payload)
            if success:
                sent += 1
            elif self._last_send_expired:
                expired += 1
            else:
                failed += 1

        return {"sent": sent, "failed": failed, "expired": expired}

    def _send_to_subscription(self, subscription: PushSubscription, payload: str) -> bool:
        """
        Send push to a single subscription.

        Returns True if successful, False if failed.
        Automatically deletes expired/invalid subscriptions.
        """
        self._last_send_expired = False

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh_key,
                        "auth": subscription.auth_key,
                    },
                },
                data=payload,
                vapid_private_key=secret_or_plain(settings.vapid_private_key).strip(),
                vapid_claims={"sub": settings.vapid_claims_email},
            )
            return True
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                self._last_send_expired = True
                self.logger.info(
                    "Push subscription expired; deleting endpoint=%s user_id=%s",
                    subscription.endpoint,
                    subscription.user_id,
                )
                with self.transaction():
                    self.notification_repository.delete_subscription(
                        subscription.user_id,
                        subscription.endpoint,
                    )
                return False

            self.logger.error("Push send failed: %s", exc)
            return False
        except Exception as exc:
            self.logger.error("Push send failed: %s", exc)
            return False

    def _build_payload(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        tag: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build JSON payload for push notification."""
        payload_data: Dict[str, Any] = {}
        if data:
            payload_data.update(data)
        if url:
            payload_data.setdefault("url", url)

        payload: Dict[str, Any] = {
            "title": title,
            "body": body,
            "icon": self._resolve_asset_url(icon or DEFAULT_ICON),
            "badge": self._resolve_asset_url(badge or DEFAULT_BADGE),
            "tag": tag,
            "data": payload_data or None,
        }

        cleaned = {key: value for key, value in payload.items() if value is not None}
        return json.dumps(cleaned)

    @staticmethod
    @BaseService.measure_operation("get_vapid_public_key")
    def get_vapid_public_key() -> str:
        """
        Get the VAPID public key for client subscription.

        This is safe to expose to the frontend.
        """
        return settings.vapid_public_key

    @staticmethod
    @BaseService.measure_operation("is_configured")
    def is_configured() -> bool:
        """Check if VAPID keys are configured."""
        return bool(
            settings.vapid_public_key and secret_or_plain(settings.vapid_private_key).strip()
        )
