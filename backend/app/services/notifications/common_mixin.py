from __future__ import annotations

import asyncio
from datetime import datetime
from functools import wraps
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, ParamSpec, TypeVar, cast

from app.services.sms_templates import render_sms

from ...models.booking import Booking
from ...models.notification import Notification
from ..notification_templates import NotificationTemplate
from ..timezone_service import TimezoneService
from .mixin_base import NotificationMixinBase

if TYPE_CHECKING:
    from ...repositories.user_repository import UserRepository
    from ..email import EmailService
    from ..notification_preference_service import NotificationPreferenceService
    from ..template_service import TemplateService


logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3, backoff_seconds: float = 1.0
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a failed synchronous operation with exponential backoff."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_attempts - 1:
                        wait_time = backoff_seconds * (2**attempt)

                        logger.warning(
                            "Attempt %s/%s failed for %s: %s. Retrying in %ss...",
                            attempt + 1,
                            max_attempts,
                            func.__name__,
                            str(exc),
                            wait_time,
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            "All %s attempts failed for %s: %s",
                            max_attempts,
                            func.__name__,
                            str(exc),
                        )

            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry failed without capturing exception")

        return wrapper

    return decorator


class NotificationCommonMixin(NotificationMixinBase):
    """Shared notification helpers — preferences, formatting, async dispatch."""

    if TYPE_CHECKING:
        logger: logging.Logger
        email_service: EmailService
        preference_service: NotificationPreferenceService
        template_service: TemplateService
        user_repository: UserRepository

    def _resolve_lesson_timezone(self, booking: Booking) -> str:
        lesson_tz = getattr(booking, "lesson_timezone", None) or getattr(
            booking, "instructor_tz_at_booking", None
        )
        instructor = getattr(booking, "instructor", None)
        instructor_user = getattr(instructor, "user", None) if instructor else None
        lesson_tz = lesson_tz or getattr(instructor_user, "timezone", None)
        return cast(str, lesson_tz or TimezoneService.DEFAULT_TIMEZONE)

    def _get_booking_start_utc(self, booking: Booking) -> datetime:
        if booking.booking_start_utc is None:
            raise ValueError(f"Booking {booking.id} missing booking_start_utc")
        return cast(datetime, booking.booking_start_utc)

    def _get_booking_local_datetime(self, booking: Booking) -> datetime:
        lesson_tz = self._resolve_lesson_timezone(booking)
        start_utc = self._get_booking_start_utc(booking)
        local_datetime: datetime = TimezoneService.utc_to_local(start_utc, lesson_tz)
        return local_datetime

    def _should_send_push(self, user_id: str, category: str) -> bool:
        enabled: bool = self.preference_service.is_enabled(user_id, category, "push")
        return enabled

    def _serialize_notification(self, notification: Notification) -> Dict[str, Any]:
        created_at = (
            notification.created_at.isoformat() if notification.created_at is not None else None
        )
        return {
            "id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "category": notification.category,
            "type": notification.type,
            "data": notification.data,
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
            "created_at": created_at,
        }

    def _should_send_email(self, user_id: str, category: str, context: str) -> bool:
        try:
            enabled = self.preference_service.is_enabled(user_id, category, "email")
        except Exception as exc:
            self.logger.warning(
                "Email preference lookup failed; sending anyway (user_id=%s context=%s): %s",
                user_id,
                context,
                exc,
            )
            return True

        if not enabled:
            self.logger.info(
                "Email skipped due to preferences (user_id=%s category=%s context=%s)",
                user_id,
                category,
                context,
            )

        result: bool = enabled
        return result

    def _should_send_sms(self, user_id: str, category: str, context: str) -> bool:
        try:
            enabled = self.preference_service.is_enabled(user_id, category, "sms")
        except Exception as exc:
            self.logger.warning(
                "SMS preference lookup failed; skipping (user_id=%s context=%s): %s",
                user_id,
                context,
                exc,
            )
            return False

        if not enabled:
            self.logger.info(
                "SMS skipped due to preferences (user_id=%s category=%s context=%s)",
                user_id,
                category,
                context,
            )

        result: bool = enabled
        return result

    def _send_notification_email(
        self, user_id: str, template: NotificationTemplate, **template_kwargs: Any
    ) -> bool:
        if template.email_template is None:
            return False

        user = self.user_repository.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            return False

        subject = template.title
        if template.email_subject_template:
            try:
                subject = template.email_subject_template.format(**template_kwargs)
            except Exception as exc:
                self.logger.warning(
                    "Failed to format email subject for %s (%s): %s",
                    template.type,
                    user_id,
                    exc,
                )

        context: Dict[str, Any] = {
            "user_name": user.first_name or user.email,
            "subject": subject,
            **template_kwargs,
        }

        try:
            html_content = self.template_service.render_template(template.email_template, context)
        except Exception as exc:
            self.logger.warning(
                "Failed to render email template for %s (%s): %s",
                template.type,
                user_id,
                exc,
            )
            return False

        try:
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                template=template.email_template,
            )
            return True
        except Exception as exc:
            self.logger.warning(
                "Failed to send notification email for %s (%s): %s",
                template.type,
                user_id,
                exc,
            )
            return False

    def _render_sms_template(self, template: Any, **template_kwargs: Any) -> str:
        return render_sms(template, **template_kwargs)

    def _run_async_task(
        self, coro_func: Callable[[], Coroutine[Any, Any, None]], error_context: str
    ) -> None:
        async def _with_error_handling() -> None:
            try:
                await coro_func()
            except Exception as exc:  # pragma: no cover - best effort logging
                self.logger.warning("Failed %s: %s", error_context, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_with_error_handling())
        except RuntimeError:
            try:
                asyncio.run(_with_error_handling())
            except Exception as exc:  # pragma: no cover - best effort logging
                self.logger.warning("Failed %s: %s", error_context, exc)
