from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

from ...models.notification import Notification
from ...repositories.notification_repository import NotificationRepository
from ...repositories.user_repository import UserRepository
from ..base import BaseService
from ..notification_templates import NotificationTemplate, render_notification
from ..push_notification_service import PushNotificationService
from ..sms_service import SMSService
from ..sms_templates import SMSTemplate
from .mixin_base import NotificationMixinBase


class NotificationInAppMixin(NotificationMixinBase):
    """In-app notifications — CRUD, dispatch, push fanout."""

    if TYPE_CHECKING:
        logger: logging.Logger
        notification_repository: NotificationRepository
        push_notification_service: PushNotificationService
        sms_service: SMSService | None
        user_repository: UserRepository

        def transaction(self) -> Any:
            ...

    @BaseService.measure_operation("notify_user")
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
        rendered = render_notification(template, **template_kwargs)
        notification = await self.create_notification(
            user_id=user_id,
            category=rendered["category"],
            notification_type=rendered["type"],
            title=rendered["title"],
            body=rendered["body"],
            data=rendered["data"],
            send_push=send_push,
        )

        if send_email and template.email_template is not None:
            should_send = await asyncio.to_thread(
                self._should_send_email,
                user_id,
                template.category,
                f"notify_user:{template.type}",
            )
            if should_send:
                await asyncio.to_thread(
                    self._send_notification_email, user_id, template, **template_kwargs
                )

        if send_sms and sms_template is not None and self.sms_service:
            should_send_sms = await asyncio.to_thread(
                self._should_send_sms,
                user_id,
                sms_template.category,
                f"notify_user:{template.type}:sms",
            )
            if should_send_sms:
                try:
                    message = self._render_sms_template(sms_template, **template_kwargs)
                except Exception as exc:
                    self.logger.warning(
                        "Failed to render SMS template for %s (%s): %s",
                        template.type,
                        user_id,
                        exc,
                    )
                else:
                    try:
                        await self.sms_service.send_to_user(
                            user_id=user_id,
                            message=message,
                            user_repository=self.user_repository,
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to send SMS for %s (%s): %s",
                            template.type,
                            user_id,
                            exc,
                        )

        return notification

    @BaseService.measure_operation("notify_user_best_effort")
    def notify_user_best_effort(
        self,
        user_id: str,
        template: NotificationTemplate,
        send_push: bool = True,
        send_email: bool = True,
        send_sms: bool = False,
        sms_template: SMSTemplate | None = None,
        **template_kwargs: Any,
    ) -> None:
        async def _notify() -> None:
            await self.notify_user(
                user_id=user_id,
                template=template,
                send_push=send_push,
                send_email=send_email,
                send_sms=send_sms,
                sms_template=sms_template,
                **template_kwargs,
            )

        self._run_async_task(_notify, f"sending notification {template.type} to {user_id}")

    @BaseService.measure_operation("create_in_app_notification")
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
        """Create an in-app notification, optionally send push, and broadcast SSE update."""

        def _create_notification_sync() -> tuple[Notification, bool]:
            push_enabled_local = False
            with self.transaction():
                notification_local: Notification = self.notification_repository.create_notification(
                    user_id=user_id,
                    category=category,
                    type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                )
                if send_push:
                    push_enabled_local = self._should_send_push(user_id, category)
            return notification_local, push_enabled_local

        notification, push_enabled = await asyncio.to_thread(_create_notification_sync)

        if send_push and push_enabled:
            push_url = None
            if data and isinstance(data, dict):
                url_value = data.get("url")
                if isinstance(url_value, str):
                    push_url = url_value
            try:
                self.push_notification_service.send_push_notification(
                    user_id=user_id,
                    title=title,
                    body=body or title,
                    url=push_url,
                    data=data,
                )
            except Exception as exc:
                self.logger.error("Push notification send failed: %s", exc)

        unread_count = await asyncio.to_thread(
            self.notification_repository.get_unread_count, user_id
        )
        from .. import notification_service as notification_service_module

        await cast(Any, notification_service_module).publish_to_user(
            user_id,
            {
                "type": "notification_update",
                "payload": {
                    "unread_count": unread_count,
                    "latest": self._serialize_notification(notification),
                },
            },
        )
        return notification

    @BaseService.measure_operation("get_notifications")
    def get_notifications(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[Notification]:
        """Get paginated notifications for a user."""
        notifications: list[Notification] = self.notification_repository.get_user_notifications(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )
        return notifications

    @BaseService.measure_operation("get_notification_count")
    def get_notification_count(self, user_id: str, unread_only: bool = False) -> int:
        """Get notification count for a user."""
        count: int = self.notification_repository.get_user_notification_count(
            user_id=user_id,
            unread_only=unread_only,
        )
        return count

    @BaseService.measure_operation("mark_notification_read")
    def mark_as_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a single notification as read."""
        with self.transaction():
            updated: bool = self.notification_repository.mark_as_read_for_user(
                user_id, notification_id
            )
            return updated

    @BaseService.measure_operation("mark_all_notifications_read")
    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        with self.transaction():
            updated_count: int = self.notification_repository.mark_all_as_read(user_id)
            return updated_count

    @BaseService.measure_operation("get_notification_unread_count")
    def get_unread_count(self, user_id: str) -> int:
        """Get unread notification count for a user."""
        unread_count: int = self.notification_repository.get_unread_count(user_id)
        return unread_count

    @BaseService.measure_operation("delete_notification")
    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        """Delete a notification."""
        with self.transaction():
            deleted: bool = self.notification_repository.delete_notification(
                user_id, notification_id
            )
            return deleted

    @BaseService.measure_operation("delete_all_notifications")
    def delete_all_notifications(self, user_id: str) -> int:
        """Delete all notifications for a user."""
        with self.transaction():
            deleted_count: int = self.notification_repository.delete_all_for_user(user_id)
            return deleted_count
