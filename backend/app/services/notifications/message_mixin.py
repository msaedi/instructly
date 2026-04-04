from __future__ import annotations

from typing import Any

from ...models.booking import Booking
from ..base import BaseService
from ..sms_templates import BOOKING_NEW_MESSAGE
from ..template_registry import TemplateRegistry
from .mixin_base import NotificationMixinBase


class NotificationMessageMixin(NotificationMixinBase):
    """Conversation message notifications — email, SMS, in-app, push."""

    def _load_message_notification_context(
        self, recipient_id: str, booking: Booking, sender_id: str, message_content: str
    ) -> dict[str, Any] | None:
        recipient = self.user_repository.get_by_id(recipient_id)
        sender = self.user_repository.get_by_id(sender_id)
        if not recipient or not sender:
            self.logger.error("Cannot send message notification: users not found")
            return None

        sender_role = "instructor" if sender_id == booking.instructor_id else "student"
        sender_name = sender.first_name or sender.email or "Someone"
        conversation = self.conversation_repository.find_by_pair(
            booking.student_id,
            booking.instructor_id,
        )
        message_preview = message_content.strip()
        if len(message_preview) > 200:
            message_preview = f"{message_preview[:197]}..."

        return {
            "recipient": recipient,
            "sender": sender,
            "sender_role": sender_role,
            "sender_name": sender_name,
            "conversation_id": getattr(conversation, "id", None),
            "message_preview": message_preview,
        }

    def _build_message_notification_data(
        self, recipient_id: str, booking: Booking, sender_id: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        notification_data: dict[str, Any] = {
            "booking_id": booking.id,
            "sender_id": sender_id,
        }
        conversation_id = context.get("conversation_id")
        if conversation_id:
            notification_data["conversation_id"] = conversation_id
            notification_data["url"] = (
                f"/instructor/messages?conversation={conversation_id}"
                if recipient_id == booking.instructor_id
                else f"/student/messages?conversation={conversation_id}"
            )
        return notification_data

    def _send_message_in_app(
        self,
        recipient_id: str,
        *,
        sender_name: str,
        message_preview: str,
        notification_data: dict[str, Any],
    ) -> None:
        async def _send_in_app_and_push() -> None:
            await self.create_notification(
                user_id=recipient_id,
                category="messages",
                notification_type="booking_new_message",
                title=f"New message from {sender_name}",
                body=message_preview,
                data=notification_data,
                send_push=True,
            )

        self._run_async_task(
            _send_in_app_and_push, f"sending message notification to {recipient_id}"
        )

    def _send_message_email(
        self,
        recipient_id: str,
        booking: Booking,
        context: dict[str, Any],
        *,
        should_send_email: bool,
    ) -> bool:
        if not should_send_email:
            return True

        recipient = context["recipient"]
        sender = context["sender"]
        local_dt = self._get_booking_local_datetime(booking)
        html_context = {
            "recipient_name": recipient.first_name,
            "sender_name": sender.first_name,
            "sender_role": context["sender_role"],
            "booking_date": local_dt.strftime("%B %d, %Y"),
            "booking_time": local_dt.strftime("%-I:%M %p"),
            "service_name": booking.service_name,
            "message_preview": context["message_preview"],
            "booking_id": booking.id,
            "frontend_url": self.frontend_url,
        }
        subject = f"New message from your {context['sender_role']} - {booking.service_name}"
        response = self.email_service.send_email(
            to_email=recipient.email,
            subject=subject,
            html_content=self.template_service.render_template(
                TemplateRegistry.BOOKING_NEW_MESSAGE, html_context
            ),
            template=TemplateRegistry.BOOKING_NEW_MESSAGE,
        )
        if response:
            self.logger.info("Message notification sent to %s", recipient.email)
            return True

        self.logger.warning("Failed to send message notification to %s", recipient.email)
        return False

    def _send_message_sms(
        self,
        recipient_id: str,
        booking: Booking,
        *,
        sender_name: str,
        message_preview: str,
    ) -> None:
        sms_service = self.sms_service
        if not sms_service or not self._should_send_sms(
            recipient_id, "messages", "booking_new_message"
        ):
            return

        sms_preview = (
            message_preview if len(message_preview) <= 120 else f"{message_preview[:117]}..."
        )
        try:
            sms_message = self._render_sms_template(
                BOOKING_NEW_MESSAGE,
                sender_name=sender_name,
                service_name=getattr(booking, "service_name", None) or "lesson",
                message_preview=sms_preview,
            )
        except Exception as exc:
            self.logger.warning("Failed to render message SMS for %s: %s", recipient_id, exc)
            return

        async def _send_sms() -> None:
            await sms_service.send_to_user(
                user_id=recipient_id,
                message=sms_message,
                user_repository=self.user_repository,
            )

        self._run_async_task(_send_sms, f"sending message SMS to {recipient_id}")

    @BaseService.measure_operation("send_message_notification")
    def send_message_notification(
        self, recipient_id: str, booking: Booking, sender_id: str, message_content: str
    ) -> bool:
        """Send email and SMS notifications for a new chat message."""
        try:
            should_send_email = self._should_send_email(
                recipient_id,
                "messages",
                "booking_new_message",
            )
            context = self._load_message_notification_context(
                recipient_id, booking, sender_id, message_content
            )
            if context is None:
                return False

            notification_data = self._build_message_notification_data(
                recipient_id, booking, sender_id, context
            )
            self._send_message_in_app(
                recipient_id,
                sender_name=context["sender_name"],
                message_preview=context["message_preview"],
                notification_data=notification_data,
            )
            email_sent = self._send_message_email(
                recipient_id,
                booking,
                context,
                should_send_email=should_send_email,
            )
            self._send_message_sms(
                recipient_id,
                booking,
                sender_name=context["sender_name"],
                message_preview=context["message_preview"],
            )
            return email_sent
        except Exception as exc:
            self.logger.error("Error sending message notification: %s", str(exc))
            return False
