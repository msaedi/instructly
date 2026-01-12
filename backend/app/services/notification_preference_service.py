"""Service for managing notification preferences."""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.notification import (
    LOCKED_NOTIFICATION_PREFERENCES,
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_CHANNELS,
    NotificationPreference,
)
from ..repositories.notification_repository import (
    DEFAULT_PREFERENCES as DEFAULT_PREFERENCE_MATRIX,
    NotificationRepository,
)
from .base import BaseService, CacheInvalidationProtocol

DEFAULT_PREFERENCES = [
    {
        "category": category,
        "channel": channel,
        "enabled": DEFAULT_PREFERENCE_MATRIX[category][channel],
        "locked": (category, channel) in LOCKED_NOTIFICATION_PREFERENCES,
    }
    for category in NOTIFICATION_CATEGORIES
    for channel in NOTIFICATION_CHANNELS
]

DEFAULT_PREFERENCE_LOOKUP: dict[tuple[str, str], bool] = {
    (category, channel): DEFAULT_PREFERENCE_MATRIX[category][channel]
    for category in NOTIFICATION_CATEGORIES
    for channel in NOTIFICATION_CHANNELS
}

PREFERENCES_CACHE_TTL_SECONDS = 300


class NotificationPreferenceService(BaseService):
    """Service for notification preference operations."""

    def __init__(
        self,
        db: Session,
        notification_repository: NotificationRepository | None = None,
        cache: CacheInvalidationProtocol | None = None,
    ) -> None:
        super().__init__(db, cache)
        self.notification_repository = notification_repository or NotificationRepository(db)

    @staticmethod
    def _cache_key(user_id: str) -> str:
        return f"notification_prefs:{user_id}"

    def _invalidate_cache(self, user_id: str) -> None:
        if self.cache is None:
            return
        self.cache.delete(self._cache_key(user_id))

    @BaseService.measure_operation("get_notification_preferences")
    def get_user_preferences(self, user_id: str) -> List[NotificationPreference]:
        """Get all preferences for a user, creating defaults if missing."""
        preferences = self.notification_repository.get_user_preferences(user_id)
        expected_count = len(NOTIFICATION_CATEGORIES) * len(NOTIFICATION_CHANNELS)
        if len(preferences) == expected_count:
            return preferences

        with self.transaction():
            return self.notification_repository.create_default_preferences(user_id)

    @BaseService.measure_operation("get_notification_preferences_by_category")
    def get_preferences_by_category(self, user_id: str) -> Dict[str, Dict[str, bool]]:
        """Get preferences grouped by category for frontend consumption."""
        if self.cache is not None:
            cached = self.cache.get(self._cache_key(user_id))
            if isinstance(cached, dict):
                return cached

        preferences = self.get_user_preferences(user_id)

        result: Dict[str, Dict[str, bool]] = {
            category: {channel: False for channel in NOTIFICATION_CHANNELS}
            for category in NOTIFICATION_CATEGORIES
        }

        for pref in preferences:
            result.setdefault(pref.category, {})[pref.channel] = pref.enabled

        if self.cache is not None:
            self.cache.set(
                self._cache_key(user_id),
                result,
                ttl=PREFERENCES_CACHE_TTL_SECONDS,
            )

        return result

    @BaseService.measure_operation("update_notification_preference")
    def update_preference(
        self, user_id: str, category: str, channel: str, enabled: bool
    ) -> NotificationPreference:
        """Update a single notification preference."""
        try:
            with self.transaction():
                updated = self.notification_repository.upsert_preference(
                    user_id=user_id,
                    category=category,
                    channel=channel,
                    enabled=enabled,
                )
            self._invalidate_cache(user_id)
            return updated
        except RepositoryException as exc:
            raise ValueError(str(exc)) from exc

    @BaseService.measure_operation("update_notification_preferences_bulk")
    def update_preferences_bulk(
        self, user_id: str, updates: List[Dict[str, object]]
    ) -> List[NotificationPreference]:
        """Update multiple notification preferences at once."""
        results: List[NotificationPreference] = []
        with self.transaction():
            for update in updates:
                category = update.get("category")
                channel = update.get("channel")
                enabled = update.get("enabled")

                if not isinstance(category, str) or not isinstance(channel, str):
                    continue
                if not isinstance(enabled, bool):
                    continue

                try:
                    results.append(
                        self.notification_repository.upsert_preference(
                            user_id=user_id,
                            category=category,
                            channel=channel,
                            enabled=enabled,
                        )
                    )
                except RepositoryException:
                    continue

        self._invalidate_cache(user_id)
        return results

    @BaseService.measure_operation("is_notification_preference_enabled")
    def is_enabled(self, user_id: str, category: str, channel: str) -> bool:
        """Check if a notification preference is enabled for a user."""
        if self.cache is not None:
            cached = self.cache.get(self._cache_key(user_id))
            if isinstance(cached, dict):
                category_map = cached.get(category)
                if isinstance(category_map, dict):
                    value = category_map.get(channel)
                    if isinstance(value, bool):
                        return value

        preference = self.notification_repository.get_preference(user_id, category, channel)
        if preference is None:
            return DEFAULT_PREFERENCE_LOOKUP.get((category, channel), False)
        return bool(preference.enabled)
