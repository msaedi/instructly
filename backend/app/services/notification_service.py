# backend/app/services/notification_service.py
"""
Notification Service for InstaInstru Platform (Refactored)

Handles all platform notifications using Jinja2 templates with proper
error handling, metrics, and resilience patterns.

Changes from original:
- Inherits from BaseService for consistency
- Added performance metrics with @measure_operation
- Improved exception handling with specific exceptions
- Added retry logic for email sending
- Split long methods for maintainability
- Added comprehensive type hints
- Uses dependency injection for TemplateService (no singleton)
"""

import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.messaging.sse_stream import publish_to_user
from app.services.notifications.common_mixin import retry
from app.services.sms_templates import render_sms

from ..core.config import settings
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.notification_repository import NotificationRepository
from ..repositories.user_repository import UserRepository
from ..services.base import BaseService
from ..services.cache_service import CacheService, CacheServiceSyncAdapter
from ..services.email import EmailService
from ..services.notification_preference_service import NotificationPreferenceService
from ..services.push_notification_service import PushNotificationService
from ..services.sms_service import SMSService
from ..services.template_service import TemplateService
from .notifications.account_security_mixin import NotificationAccountSecurityMixin
from .notifications.booking_cancellation_mixin import NotificationBookingCancellationMixin
from .notifications.booking_confirmation_mixin import NotificationBookingConfirmationMixin
from .notifications.booking_followups_mixin import NotificationBookingFollowupsMixin
from .notifications.common_mixin import NotificationCommonMixin
from .notifications.in_app_mixin import NotificationInAppMixin
from .notifications.message_mixin import NotificationMessageMixin
from .notifications.payment_mixin import NotificationPaymentMixin
from .notifications.scheduling_mixin import NotificationSchedulingMixin

logger = logging.getLogger(__name__)

__all__ = [
    "NotificationService",
    "publish_to_user",
    "render_sms",
    "retry",
    "time",
]


class NotificationService(
    NotificationCommonMixin,
    NotificationBookingConfirmationMixin,
    NotificationBookingCancellationMixin,
    NotificationBookingFollowupsMixin,
    NotificationSchedulingMixin,
    NotificationPaymentMixin,
    NotificationMessageMixin,
    NotificationAccountSecurityMixin,
    NotificationInAppMixin,
    BaseService,
):
    """
    Central notification service for the platform using Jinja2 templates.

    Inherits from BaseService for consistent architecture, metrics collection,
    and standardized error handling. Uses dependency injection for TemplateService.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        cache: Any | None = None,
        template_service: Optional[TemplateService] = None,
        email_service: Optional[EmailService] = None,
        notification_repository: Optional[NotificationRepository] = None,
        push_service: Optional[PushNotificationService] = None,
        preference_service: Optional[NotificationPreferenceService] = None,
        sms_service: Optional[SMSService] = None,
    ) -> None:
        """
        Initialize the notification service.

        Args:
            db: Optional database session for loading additional data
            cache: Optional cache service (not used but kept for consistency)
            template_service: Optional TemplateService instance (will create if not provided)
            email_service: Optional EmailService instance (will create if not provided)
        """
        db = self._resolve_db(db)
        cache_service, cache_adapter = self._resolve_cache(cache)
        super().__init__(db, cache_adapter)

        self._init_email_service(db, cache_adapter, email_service)
        self._init_template_service(db, cache_adapter, template_service)
        self._init_repositories(db, notification_repository)
        self._init_push_service(db, push_service)
        self._init_preference_service(db, preference_service, cache_adapter)
        self._init_sms_service(sms_service, cache_service)

        self.frontend_url = settings.frontend_url

    def _resolve_db(self, db: Optional[Session]) -> Session:
        if db is None:
            from app.database import SessionLocal

            self._owns_db = True
            return SessionLocal()

        self._owns_db = False
        return db

    def _resolve_cache(
        self, cache: Any | None
    ) -> tuple[CacheService | None, CacheServiceSyncAdapter | None]:
        cache_service: CacheService | None = None
        cache_adapter: CacheServiceSyncAdapter | None = None

        if isinstance(cache, CacheService):
            cache_service = cache
            cache_adapter = CacheServiceSyncAdapter(cache_service)
        elif isinstance(cache, CacheServiceSyncAdapter):
            cache_adapter = cache
            cache_service = getattr(cache, "_cache_service", None)

        if cache_adapter is None and cache_service is None:
            try:
                cache_service = CacheService()
                cache_adapter = CacheServiceSyncAdapter(cache_service)
            except Exception:
                cache_service = None
                cache_adapter = None

        return cache_service, cache_adapter

    def _init_email_service(
        self,
        db: Session,
        cache_adapter: CacheServiceSyncAdapter | None,
        email_service: Optional[EmailService],
    ) -> None:
        if email_service is None:
            self.email_service = EmailService(db, cache_adapter)
            self._owns_email_service = True
            return

        self.email_service = email_service
        self._owns_email_service = False

    def _init_template_service(
        self,
        db: Session,
        cache_adapter: CacheServiceSyncAdapter | None,
        template_service: Optional[TemplateService],
    ) -> None:
        if template_service is None:
            self.template_service = TemplateService(db, cache_adapter)
            self._owns_template_service = True
            return

        self.template_service = template_service
        self._owns_template_service = False

    def _init_repositories(
        self,
        db: Session,
        notification_repository: Optional[NotificationRepository],
    ) -> None:
        self.notification_repository = notification_repository or NotificationRepository(db)
        self.conversation_repository = ConversationRepository(db)
        self.user_repository = UserRepository(db)

    def _init_push_service(
        self, db: Session, push_service: Optional[PushNotificationService]
    ) -> None:
        self.push_notification_service = push_service or PushNotificationService(
            db, self.notification_repository
        )

    def _init_preference_service(
        self,
        db: Session,
        preference_service: Optional[NotificationPreferenceService],
        cache_adapter: CacheServiceSyncAdapter | None,
    ) -> None:
        self.preference_service = preference_service or NotificationPreferenceService(
            db, self.notification_repository, cache_adapter
        )

    def _init_sms_service(
        self,
        sms_service: Optional[SMSService],
        cache_service: CacheService | None,
    ) -> None:
        if sms_service is None:
            self.sms_service = SMSService(cache_service)
            return

        if cache_service is not None and getattr(sms_service, "cache_service", None) is None:
            sms_service.cache_service = cache_service
        self.sms_service = sms_service

    def __del__(self) -> None:
        """Clean up the database session if we created it."""
        if hasattr(self, "_owns_db") and self._owns_db and hasattr(self, "db"):
            self.db.close()
