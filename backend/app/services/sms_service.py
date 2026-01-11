"""Service for sending SMS via Twilio."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.core.config import settings

if TYPE_CHECKING:
    from app.repositories.user_repository import UserRepository
    from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class SMSService:
    """Service for sending SMS via Twilio."""

    def __init__(self, cache_service: Optional["CacheService"] = None) -> None:
        self.cache_service = cache_service
        self.daily_limit = settings.sms_daily_limit_per_user

        auth_token = (
            settings.twilio_auth_token.get_secret_value() if settings.twilio_auth_token else ""
        )
        self.enabled = bool(
            settings.sms_enabled
            and settings.twilio_account_sid
            and auth_token
            and settings.twilio_phone_number
        )

        if self.enabled:
            self.client = Client(
                settings.twilio_account_sid,
                auth_token,
            )
            self.from_number = settings.twilio_phone_number
        else:
            self.client = None
            self.from_number = None
            logger.info("SMS service disabled - Twilio credentials not configured")

    async def send_sms(self, to_number: str, message: str) -> Optional[dict[str, Any]]:
        """
        Send an SMS message.

        Args:
            to_number: Recipient phone number in E.164 format (+1234567890)
            message: Message body (max 1600 chars, truncated if longer)
        """
        if not self.enabled:
            logger.debug("SMS disabled, would send to %s", to_number)
            return None

        if not to_number:
            logger.warning("Cannot send SMS: no phone number provided")
            return None

        if not to_number.startswith("+"):
            logger.warning("Invalid phone number format: %s", to_number)
            return None

        if len(message) > 1600:
            message = message[:1597] + "..."

        return await asyncio.to_thread(self._send_sms_sync, to_number, message)

    async def send_to_user(
        self,
        user_id: str,
        message: str,
        user_repository: Optional["UserRepository"] = None,
    ) -> Optional[dict[str, Any]]:
        """Send SMS to a user by ID with rate limiting."""
        if not self.enabled:
            logger.debug("SMS disabled, skipping send to user %s", user_id)
            return None
        if not await self._check_rate_limit(user_id):
            return None

        repo = user_repository
        if repo is None:
            logger.warning("No user repository provided for SMS lookup")
            return None

        user = await asyncio.to_thread(repo.get_by_id, user_id)
        if not user:
            logger.warning("User %s not found for SMS", user_id)
            return None

        if not getattr(user, "phone_verified", False):
            logger.debug("User %s phone not verified; skipping SMS", user_id)
            return None

        phone = getattr(user, "phone", None)
        if not phone:
            logger.debug("User %s has no phone number for SMS", user_id)
            return None

        result = await self.send_sms(phone, message)
        if result:
            await self._increment_rate_limit(user_id)
        return result

    def _send_sms_sync(self, to_number: str, message: str) -> Optional[dict[str, Any]]:
        if not self.client or not self.from_number:
            return None

        try:
            twilio_message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number,
            )
            logger.info("SMS sent to %s, SID: %s", to_number, twilio_message.sid)
            return {
                "sid": twilio_message.sid,
                "status": getattr(twilio_message, "status", None),
                "to": to_number,
            }
        except TwilioRestException as exc:
            logger.error("Twilio error sending SMS to %s: %s", to_number, exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Unexpected error sending SMS to %s: %s", to_number, exc)
            return None

    async def _check_rate_limit(self, user_id: str) -> bool:
        if not self.cache_service:
            return True

        key = f"sms_count:{user_id}:{self._current_date_key()}"
        value = await self.cache_service.get(key)
        try:
            count = int(value) if value is not None else 0
        except (TypeError, ValueError):
            count = 0

        if count >= self.daily_limit:
            logger.warning("User %s exceeded daily SMS limit (%s)", user_id, self.daily_limit)
            return False
        return True

    async def _increment_rate_limit(self, user_id: str) -> None:
        if not self.cache_service:
            return

        key = f"sms_count:{user_id}:{self._current_date_key()}"
        value = await self.cache_service.get(key)
        try:
            count = int(value) if value is not None else 0
        except (TypeError, ValueError):
            count = 0
        await self.cache_service.set(key, count + 1, ttl=86400)

    @staticmethod
    def _current_date_key() -> str:
        return datetime.now(timezone.utc).date().isoformat()
