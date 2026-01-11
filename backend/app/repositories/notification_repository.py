"""Repository for notification preferences, inbox entries, and push subscriptions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.notification import (
    LOCKED_NOTIFICATION_PREFERENCES,
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_CHANNELS,
    Notification,
    NotificationPreference,
    PushSubscription,
)
from .base_repository import BaseRepository

DEFAULT_PREFERENCES: Dict[str, Dict[str, bool]] = {
    "lesson_updates": {"email": True, "push": True, "sms": False},
    "messages": {"email": False, "push": True, "sms": False},
    "learning_tips": {"email": True, "push": True, "sms": False},
    "system_updates": {"email": True, "push": False, "sms": False},
    "promotional": {"email": False, "push": False, "sms": False},
}


class NotificationRepository(BaseRepository[Notification]):
    """Data access for notification preferences, inbox entries, and push subscriptions."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Notification)

    def _validate_category(self, category: str) -> None:
        if category not in NOTIFICATION_CATEGORIES:
            raise RepositoryException(f"Invalid notification category: {category}")

    def _validate_channel(self, channel: str) -> None:
        if channel not in NOTIFICATION_CHANNELS:
            raise RepositoryException(f"Invalid notification channel: {channel}")

    # Preferences
    def get_user_preferences(self, user_id: str) -> List[NotificationPreference]:
        query = (
            self.db.query(NotificationPreference)
            .filter(NotificationPreference.user_id == user_id)
            .order_by(NotificationPreference.category.asc(), NotificationPreference.channel.asc())
        )
        return cast(List[NotificationPreference], query.all())

    def get_preference(
        self, user_id: str, category: str, channel: str
    ) -> Optional[NotificationPreference]:
        query = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
            NotificationPreference.channel == channel,
        )
        return cast(Optional[NotificationPreference], query.first())

    def upsert_preference(
        self, user_id: str, category: str, channel: str, enabled: bool
    ) -> NotificationPreference:
        self._validate_category(category)
        self._validate_channel(channel)

        preference = self.get_preference(user_id, category, channel)
        if preference is not None:
            if preference.locked and preference.enabled != enabled:
                raise RepositoryException("Preference is locked and cannot be updated")
            preference.enabled = enabled
            self.db.flush()
            return preference

        locked = (category, channel) in LOCKED_NOTIFICATION_PREFERENCES
        if locked and not enabled:
            raise RepositoryException("Preference is locked and cannot be disabled")

        preference = NotificationPreference(
            user_id=user_id,
            category=category,
            channel=channel,
            enabled=enabled,
            locked=locked,
        )
        self.db.add(preference)
        self.db.flush()
        return preference

    def create_default_preferences(self, user_id: str) -> List[NotificationPreference]:
        created: List[NotificationPreference] = []

        for category in NOTIFICATION_CATEGORIES:
            for channel in NOTIFICATION_CHANNELS:
                enabled = DEFAULT_PREFERENCES[category][channel]
                locked = (category, channel) in LOCKED_NOTIFICATION_PREFERENCES
                preference = self.get_preference(user_id, category, channel)
                if preference is None:
                    preference = NotificationPreference(
                        user_id=user_id,
                        category=category,
                        channel=channel,
                        enabled=enabled,
                        locked=locked,
                    )
                    self.db.add(preference)
                created.append(preference)

        self.db.flush()
        return created

    # Notifications
    def create_notification(
        self,
        user_id: str,
        category: str,
        type: str,
        title: str,
        body: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Notification:
        self._validate_category(category)
        notification = Notification(
            user_id=user_id,
            category=category,
            type=type,
            title=title,
            body=body,
            data=data,
        )
        self.db.add(notification)
        self.db.flush()
        self.db.refresh(notification)
        return notification

    def get_user_notifications(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[Notification]:
        query = self.db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            query = query.filter(Notification.read_at.is_(None))
        query = (
            query.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return cast(List[Notification], query.all())

    def get_user_notification_count(self, user_id: str, unread_only: bool = False) -> int:
        query = self.db.query(func.count(Notification.id)).filter(Notification.user_id == user_id)
        if unread_only:
            query = query.filter(Notification.read_at.is_(None))
        count = query.scalar()
        return int(count or 0)

    def get_unread_count(self, user_id: str) -> int:
        count = (
            self.db.query(func.count(Notification.id))
            .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
            .scalar()
        )
        return int(count or 0)

    def mark_as_read(self, notification_id: str) -> bool:
        now = datetime.now(timezone.utc)
        updated = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id, Notification.read_at.is_(None))
            .update({"read_at": now}, synchronize_session="fetch")
        )
        return bool(updated)

    def mark_as_read_for_user(self, user_id: str, notification_id: str) -> bool:
        now = datetime.now(timezone.utc)
        updated = (
            self.db.query(Notification)
            .filter(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .update({"read_at": now}, synchronize_session="fetch")
        )
        return bool(updated)

    def mark_all_as_read(self, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        updated = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
            .update({"read_at": now}, synchronize_session="fetch")
        )
        return int(updated or 0)

    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        deleted = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.id == notification_id,
            )
            .delete(synchronize_session=False)
        )
        return bool(deleted)

    def delete_all_for_user(self, user_id: str) -> int:
        deleted = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id)
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)

    # Push Subscriptions
    def create_subscription(
        self,
        user_id: str,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: str | None = None,
    ) -> PushSubscription:
        query = self.db.query(PushSubscription).filter(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
        existing = cast(Optional[PushSubscription], query.first())
        if existing is not None:
            existing.p256dh_key = p256dh_key
            existing.auth_key = auth_key
            existing.user_agent = user_agent
            existing.updated_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing

        subscription = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh_key=p256dh_key,
            auth_key=auth_key,
            user_agent=user_agent,
        )
        self.db.add(subscription)
        self.db.flush()
        return subscription

    def get_user_subscriptions(self, user_id: str) -> List[PushSubscription]:
        query = (
            self.db.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .order_by(PushSubscription.created_at.desc(), PushSubscription.id.desc())
        )
        return cast(List[PushSubscription], query.all())

    def delete_subscription(self, user_id: str, endpoint: str) -> bool:
        deleted = (
            self.db.query(PushSubscription)
            .filter(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint == endpoint,
            )
            .delete(synchronize_session=False)
        )
        return bool(deleted)

    def delete_all_user_subscriptions(self, user_id: str) -> int:
        deleted = (
            self.db.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)


__all__ = ["NotificationRepository"]
