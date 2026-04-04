from __future__ import annotations

from datetime import datetime
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Sequence

from ...core.constants import BRAND_NAME
from ...models.user import User
from ...repositories.user_repository import UserRepository
from ..base import BaseService
from ..email import EmailService
from ..email_subjects import EmailSubject
from ..sms_service import SMSService
from ..sms_templates import (
    SECURITY_2FA_CHANGED,
    SECURITY_NEW_DEVICE_LOGIN,
    SECURITY_PW_CHANGED,
)
from ..template_registry import TemplateRegistry
from ..template_service import TemplateService
from .mixin_base import NotificationMixinBase


class NotificationAccountSecurityMixin(NotificationMixinBase):
    """Account events, security alerts, and badge emails."""

    if TYPE_CHECKING:
        logger: logging.Logger
        email_service: EmailService
        sms_service: SMSService | None
        template_service: TemplateService
        user_repository: UserRepository
        frontend_url: str

    @BaseService.measure_operation("send_welcome_email")
    def send_welcome_email(self, user_id: str, role: str = "student") -> bool:
        """Send welcome email after account creation."""
        user = self.user_repository.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            self.logger.warning("Welcome email skipped: user not found (%s)", user_id)
            return False

        context = {
            "user": SimpleNamespace(first_name=user.first_name or user.email, role=role),
            "frontend_url": self.frontend_url,
        }
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.AUTH_WELCOME, context
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=EmailSubject.welcome(),
                html_content=html_content,
                template=TemplateRegistry.AUTH_WELCOME,
            )
            self.logger.info("Welcome email sent to %s", user.email)
            return True
        except Exception as exc:
            self.logger.error("Failed to send welcome email to %s: %s", user.email, exc)
            return False

    @BaseService.measure_operation("send_new_device_login_notification")
    def send_new_device_login_notification(
        self,
        user_id: str,
        ip_address: str | None,
        user_agent: str | None,
        login_time: datetime,
    ) -> bool:
        """Send new-device login alert (always-on email + optional SMS)."""
        user = self.user_repository.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            self.logger.warning("New device login skipped: user not found (%s)", user_id)
            return False

        context = {
            "user_name": user.first_name or user.email,
            "login_time": login_time,
            "ip_address": ip_address or "Unknown",
            "user_agent": user_agent or "Unknown",
        }
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.SECURITY_NEW_DEVICE_LOGIN,
                context,
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=f"New login to your {BRAND_NAME} account",
                html_content=html_content,
                template=TemplateRegistry.SECURITY_NEW_DEVICE_LOGIN,
            )
            self.logger.info("New device login email sent to %s", user.email)
        except Exception as exc:
            self.logger.error("Failed to send new device login email to %s: %s", user.email, exc)
            return False

        sms_service = self.sms_service
        if sms_service:
            try:
                sms_message = self._render_sms_template(
                    SECURITY_NEW_DEVICE_LOGIN,
                    security_url=f"{self.frontend_url}/forgot-password",
                )
            except Exception as exc:
                self.logger.warning("Failed to render new device SMS for %s: %s", user_id, exc)
            else:

                async def _send_sms() -> None:
                    await sms_service.send_to_user(
                        user_id=user_id,
                        message=sms_message,
                        user_repository=self.user_repository,
                    )

                self._run_async_task(_send_sms, f"sending new device SMS to {user_id}")

        return True

    @BaseService.measure_operation("send_password_changed_notification")
    def send_password_changed_notification(
        self,
        user_id: str,
        changed_at: datetime,
    ) -> bool:
        """Send password-changed confirmation (always-on email + optional SMS)."""
        user = self.user_repository.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            self.logger.warning(
                "Password change notification skipped: user not found (%s)", user_id
            )
            return False

        context = {"user_name": user.first_name or user.email, "changed_at": changed_at}
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.SECURITY_PW_CHANGED,
                context,
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=f"Your {BRAND_NAME} password was changed",
                html_content=html_content,
                template=TemplateRegistry.SECURITY_PW_CHANGED,
            )
            self.logger.info("Password change email sent to %s", user.email)
        except Exception as exc:
            self.logger.error("Failed to send password change email to %s: %s", user.email, exc)
            return False

        sms_service = self.sms_service
        if sms_service:
            try:
                sms_message = self._render_sms_template(
                    SECURITY_PW_CHANGED,
                    reset_url=f"{self.frontend_url}/forgot-password",
                )
            except Exception as exc:
                self.logger.warning("Failed to render password change SMS for %s: %s", user_id, exc)
            else:

                async def _send_sms() -> None:
                    await sms_service.send_to_user(
                        user_id=user_id,
                        message=sms_message,
                        user_repository=self.user_repository,
                    )

                self._run_async_task(_send_sms, f"sending password change SMS to {user_id}")

        return True

    @BaseService.measure_operation("send_two_factor_changed_notification")
    def send_two_factor_changed_notification(
        self,
        user_id: str,
        enabled: bool,
        changed_at: datetime,
    ) -> bool:
        """Send 2FA enabled/disabled confirmation (always-on email + optional SMS)."""
        user = self.user_repository.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            self.logger.warning("2FA change notification skipped: user not found (%s)", user_id)
            return False

        status_text = "enabled" if enabled else "disabled"
        context = {
            "user_name": user.first_name or user.email,
            "status_text": status_text,
            "changed_at": changed_at,
        }
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.SECURITY_2FA_CHANGED,
                context,
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=f"Two-factor authentication {status_text}",
                html_content=html_content,
                template=TemplateRegistry.SECURITY_2FA_CHANGED,
            )
            self.logger.info("2FA change email sent to %s", user.email)
        except Exception as exc:
            self.logger.error("Failed to send 2FA change email to %s: %s", user.email, exc)
            return False

        sms_service = self.sms_service
        if sms_service and getattr(user, "phone_verified", False):
            try:
                sms_message = self._render_sms_template(
                    SECURITY_2FA_CHANGED,
                    status=status_text,
                    security_url=f"{self.frontend_url}/forgot-password",
                )
            except Exception as exc:
                self.logger.warning("Failed to render 2FA change SMS for %s: %s", user_id, exc)
            else:

                async def _send_sms() -> None:
                    await sms_service.send_to_user(
                        user_id=user_id,
                        message=sms_message,
                        user_repository=self.user_repository,
                    )

                self._run_async_task(_send_sms, f"sending 2FA change SMS to {user_id}")

        return True

    @BaseService.measure_operation("send_badge_awarded_email")
    def send_badge_awarded_email(self, user: User, badge_name: str) -> bool:
        try:
            user_id = getattr(user, "id", None)
            if not user_id:
                return False
            if not self._should_send_email(user_id, "promotional", "badge_awarded"):
                return False

            subject = f"You earned the {badge_name} badge!"
            html_content = (
                f"<p>Congratulations {user.first_name or user.email},</p>"
                f"<p>You just unlocked the <strong>{badge_name}</strong> badge. Keep up the great work!</p>"
            )
            text_content = (
                f"Congratulations {user.first_name or user.email}, "
                f"you just unlocked the {badge_name} badge!"
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
            return True
        except Exception as exc:
            self.logger.error("Failed to send badge award email: %s", exc)
            return False

    @BaseService.measure_operation("send_badge_digest_email")
    def send_badge_digest_email(self, user: User, items: Sequence[dict[str, Any]]) -> bool:
        try:
            user_id = getattr(user, "id", None)
            if not user_id:
                return False
            if not self._should_send_email(user_id, "promotional", "badge_digest"):
                return False
            if not items:
                return False

            subject = "You're close to unlocking new badges"
            list_items = "".join(
                f"<li><strong>{item.get('name')}</strong>: {int(item.get('percent', 0))}% complete, "
                f"{item.get('remaining')} remaining</li>"
                for item in items
            )
            html_content = (
                f"<p>Hi {user.first_name or user.email},</p>"
                "<p>You're making great progress. Here are the badges you're closest to earning:</p>"
                f"<ul>{list_items}</ul>"
                "<p>Finish a lesson this week to keep the streak going!</p>"
            )
            text_content = "\n".join(
                f"- {item.get('name')}: {int(item.get('percent', 0))}% complete, {item.get('remaining')} remaining"
                for item in items
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
            return True
        except Exception as exc:
            self.logger.error("Failed to send badge digest email: %s", exc)
            return False
