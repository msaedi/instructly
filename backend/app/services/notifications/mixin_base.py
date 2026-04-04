from __future__ import annotations

from collections.abc import Callable, Coroutine
from contextlib import AbstractContextManager
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from ...models.booking import Booking
from ...models.notification import Notification
from ...models.user import User
from ...repositories.booking_repository import BookingRepository
from ...repositories.conversation_repository import ConversationRepository
from ...repositories.notification_repository import NotificationRepository
from ...repositories.user_repository import UserRepository
from ..email import EmailService
from ..notification_preference_service import NotificationPreferenceService
from ..notification_templates import NotificationTemplate
from ..push_notification_service import PushNotificationService
from ..sms_service import SMSService
from ..sms_templates import SMSTemplate
from ..template_service import TemplateService


class NotificationMixinBase:
    """Typing-only base for notification mixins."""

    db: Session
    logger: logging.Logger
    frontend_url: str
    email_service: EmailService
    sms_service: SMSService | None
    template_service: TemplateService
    booking_repository: BookingRepository
    user_repository: UserRepository
    conversation_repository: ConversationRepository
    notification_repository: NotificationRepository
    push_notification_service: PushNotificationService
    preference_service: NotificationPreferenceService

    if TYPE_CHECKING:

        def transaction(self) -> AbstractContextManager[Session]:
            ...

    def _require_booking_participants(
        self, booking: Booking, operation: str
    ) -> tuple[User, User] | None:
        student = getattr(booking, "student", None)
        instructor = getattr(booking, "instructor", None)
        if student is None or instructor is None:
            self.logger.error(
                "Cannot %s for booking %s: missing %s",
                operation,
                getattr(booking, "id", "?"),
                "student" if student is None else "instructor",
            )
            return None
        return student, instructor

    def _get_booking_local_datetime(self, booking: Booking) -> Any:
        raise NotImplementedError

    def _run_async_task(
        self, coro_func: Callable[[], Coroutine[Any, Any, None]], error_context: str
    ) -> None:
        raise NotImplementedError

    def _should_send_email(self, user_id: str, category: str, context: str) -> bool:
        raise NotImplementedError

    def _should_send_sms(self, user_id: str, category: str, context: str) -> bool:
        raise NotImplementedError

    def _should_send_push(self, user_id: str, category: str) -> bool:
        raise NotImplementedError

    def _send_notification_email(
        self, user_id: str, template: NotificationTemplate, **template_kwargs: Any
    ) -> bool:
        raise NotImplementedError

    def _render_sms_template(self, template: SMSTemplate, **template_kwargs: Any) -> str:
        raise NotImplementedError

    def _serialize_notification(self, notification: Notification) -> dict[str, Any]:
        raise NotImplementedError

    async def create_notification(
        self,
        user_id: str,
        category: str,
        notification_type: str,
        title: str,
        body: str | None,
        data: dict[str, Any] | None = None,
        send_push: bool = True,
    ) -> Notification:
        raise NotImplementedError

    async def notify_user(
        self,
        user_id: str,
        template: NotificationTemplate,
        send_push: bool = True,
        send_email: bool = True,
        send_sms: bool = False,
        sms_template: SMSTemplate | None = None,
        **template_kwargs: Any,
    ) -> Notification:
        raise NotImplementedError

    def _send_student_reminder(self, booking: Booking, *, reminder_type: str = "24h") -> bool:
        raise NotImplementedError

    def _send_instructor_reminder(self, booking: Booking, *, reminder_type: str = "24h") -> bool:
        raise NotImplementedError

    def _send_student_booking_confirmation(self, booking: Booking) -> bool:
        raise NotImplementedError

    def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        raise NotImplementedError

    def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        raise NotImplementedError

    def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        raise NotImplementedError

    def _send_student_completion_notification(self, booking: Booking) -> bool:
        raise NotImplementedError

    def _send_instructor_completion_notification(self, booking: Booking) -> bool:
        raise NotImplementedError
