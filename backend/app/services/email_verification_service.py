from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import secrets
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_email_verification_token, decode_email_verification_token
from app.core.constants import BRAND_NAME
from app.core.exceptions import ValidationException
from app.services.cache_service import CacheService
from app.services.email import EmailService
from app.services.email_subjects import EmailSubject
from app.services.template_registry import TemplateRegistry
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_CODE_TTL_SECONDS = 5 * 60
EMAIL_VERIFICATION_SEND_WINDOW_SECONDS = 10 * 60
EMAIL_VERIFICATION_SEND_MAX = 3
EMAIL_VERIFICATION_SEND_IP_WINDOW_SECONDS = 60 * 60
EMAIL_VERIFICATION_SEND_IP_MAX = 20
EMAIL_VERIFICATION_ATTEMPT_WINDOW_SECONDS = 10 * 60
EMAIL_VERIFICATION_ATTEMPT_MAX = 5
EMAIL_VERIFICATION_LOCK_TTL_SECONDS = 10 * 60
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS = 15 * 60


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_verification_code_key(email: str) -> str:
    return f"email_verify:{normalize_email(email)}"


def email_verification_send_key(email: str) -> str:
    return f"email_verify_send_count:{normalize_email(email)}"


def email_verification_send_ip_key(client_ip: str) -> str:
    return f"email_verify_send_ip_count:{client_ip.strip() or 'unknown'}"


def email_verification_attempts_key(email: str) -> str:
    return f"email_verify_attempts:{normalize_email(email)}"


def email_verification_lock_key(email: str) -> str:
    return f"email_verify_lock:{normalize_email(email)}"


def email_verification_token_jti_key(jti: str) -> str:
    return f"email_verify_token_jti:{jti.strip()}"


def _mask_email(email: str) -> str:
    normalized_email = normalize_email(email)
    local_part, _, domain = normalized_email.partition("@")
    if domain:
        return f"{local_part[:2]}***@{domain}"
    if normalized_email:
        return f"{normalized_email[:2]}***"
    return "***"


class EmailVerificationService:
    def __init__(
        self,
        db: Session,
        cache_service: CacheService,
        email_service: EmailService | None = None,
    ) -> None:
        self.db = db
        self.cache_service = cache_service
        self.email_service = email_service

    async def _get_cache_count(self, key: str) -> int:
        cached_value = None
        try:
            redis_client = await self.cache_service.get_redis_client()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis unavailable while reading auth cache counter: %s", exc)
            redis_client = None

        if redis_client is not None:
            cached_value = await redis_client.get(key)
        if cached_value is None:
            cached_value = await self.cache_service.get(key)

        if isinstance(cached_value, bytes):
            cached_value = cached_value.decode("utf-8", errors="ignore")
        try:
            return int(cached_value) if cached_value is not None else 0
        except (TypeError, ValueError):
            return 0

    async def _increment_cache_counter(self, key: str, ttl: int) -> int:
        redis_client = None
        try:
            redis_client = await self.cache_service.get_redis_client()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis unavailable for auth cache counter: %s", exc)

        if redis_client is not None:
            value = await redis_client.incr(key)
            if value == 1:
                await redis_client.expire(key, ttl)
            return int(value)

        current_value = await self._get_cache_count(key)
        next_value = current_value + 1
        await self.cache_service.set(key, next_value, ttl=ttl)
        return next_value

    async def _delete_cache_keys(self, *keys: str) -> None:
        redis_client = None
        try:
            redis_client = await self.cache_service.get_redis_client()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis unavailable while deleting cache keys: %s", exc)

        if redis_client is not None:
            await redis_client.delete(*keys)

        for key in keys:
            await self.cache_service.delete(key)

    def _send_email_verification_email_sync(self, *, to_email: str, code: str) -> None:
        email_service = self.email_service
        if email_service is None:
            raise RuntimeError("Email service is required to send verification emails")

        template_service = TemplateService(self.db, None)
        html_content = template_service.render_template(
            TemplateRegistry.AUTH_EMAIL_VERIFICATION,
            context={
                "brand_name": BRAND_NAME,
                "code": code,
            },
        )
        email_service.send_email(
            to_email=to_email,
            subject=EmailSubject.email_verification(),
            html_content=html_content,
            text_content=(
                f"Your {BRAND_NAME} verification code is {code}. " "This code expires in 5 minutes."
            ),
            template=TemplateRegistry.AUTH_EMAIL_VERIFICATION,
        )

    async def check_send_rate_limit(self, email: str, client_ip: str) -> None:
        send_key = email_verification_send_key(email)
        if await self._get_cache_count(send_key) >= EMAIL_VERIFICATION_SEND_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Too many verification requests. Please try again later.",
                    "code": "EMAIL_VERIFICATION_RATE_LIMITED",
                    "details": {"retry_after_seconds": EMAIL_VERIFICATION_SEND_WINDOW_SECONDS},
                },
            )

        ip_send_key = email_verification_send_ip_key(client_ip)
        if await self._get_cache_count(ip_send_key) >= EMAIL_VERIFICATION_SEND_IP_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Too many verification requests. Please try again later.",
                    "code": "EMAIL_VERIFICATION_IP_RATE_LIMITED",
                    "details": {"retry_after_seconds": EMAIL_VERIFICATION_SEND_IP_WINDOW_SECONDS},
                },
            )

    async def generate_and_store_code(self, email: str) -> str:
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        await self.cache_service.set(
            email_verification_code_key(email),
            code,
            ttl=EMAIL_VERIFICATION_CODE_TTL_SECONDS,
        )
        await self._delete_cache_keys(
            email_verification_attempts_key(email),
            email_verification_lock_key(email),
        )
        return code

    async def send_verification_email(self, email: str, code: str) -> None:
        if self.email_service is None:
            raise RuntimeError("Email service is required to send verification emails")
        masked_email = _mask_email(email)
        try:
            await asyncio.to_thread(
                self._send_email_verification_email_sync,
                to_email=email,
                code=code,
            )
        except Exception:
            logger.warning("Email verification delivery failed for %s", masked_email, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Unable to send verification email. Please try again.",
                    "code": "EMAIL_VERIFICATION_DELIVERY_FAILED",
                },
            )

    async def _record_send(self, email: str, client_ip: str) -> None:
        await self._increment_cache_counter(
            email_verification_send_key(email),
            EMAIL_VERIFICATION_SEND_WINDOW_SECONDS,
        )
        await self._increment_cache_counter(
            email_verification_send_ip_key(client_ip),
            EMAIL_VERIFICATION_SEND_IP_WINDOW_SECONDS,
        )

    async def send_code(self, email: str, client_ip: str) -> None:
        await self.check_send_rate_limit(email, client_ip)
        code = await self.generate_and_store_code(email)
        await self.send_verification_email(email, code)
        await self._record_send(email, client_ip)

    async def verify_code(self, email: str, code: str) -> tuple[str, int]:
        code_key = email_verification_code_key(email)
        attempts_key = email_verification_attempts_key(email)
        lock_key = email_verification_lock_key(email)

        redis_client = None
        try:
            redis_client = await self.cache_service.get_redis_client()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis unavailable for email verification confirm: %s", exc)

        locked = False
        if redis_client is not None:
            locked = bool(await redis_client.get(lock_key))
            if not locked:
                locked = bool(await self.cache_service.get(lock_key))
        else:
            locked = bool(await self.cache_service.get(lock_key))

        if locked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Too many attempts. Please wait 10 minutes and try again.",
                    "code": "EMAIL_VERIFICATION_LOCKED",
                    "details": {"retry_after_seconds": EMAIL_VERIFICATION_LOCK_TTL_SECONDS},
                },
            )

        cached_code_raw = await self.cache_service.get(code_key)
        cached_code = (
            cached_code_raw.decode("utf-8", errors="ignore")
            if isinstance(cached_code_raw, bytes)
            else (str(cached_code_raw) if cached_code_raw is not None else "")
        )
        if not cached_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Verification code is invalid or expired.",
                    "code": "EMAIL_VERIFICATION_CODE_INVALID",
                    "details": {"expired": True},
                },
            )

        if not secrets.compare_digest(cached_code, code.strip()):
            attempts = await self._increment_cache_counter(
                attempts_key,
                EMAIL_VERIFICATION_ATTEMPT_WINDOW_SECONDS,
            )
            remaining_attempts = max(EMAIL_VERIFICATION_ATTEMPT_MAX - attempts, 0)
            if attempts >= EMAIL_VERIFICATION_ATTEMPT_MAX:
                await self.cache_service.set(
                    lock_key,
                    True,
                    ttl=EMAIL_VERIFICATION_LOCK_TTL_SECONDS,
                )
                await self.cache_service.delete(code_key)
                await self._delete_cache_keys(attempts_key)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Too many attempts. Please wait 10 minutes and try again.",
                        "code": "EMAIL_VERIFICATION_LOCKED",
                        "details": {"retry_after_seconds": EMAIL_VERIFICATION_LOCK_TTL_SECONDS},
                    },
                )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Invalid verification code.",
                    "code": "EMAIL_VERIFICATION_CODE_INVALID",
                    "details": {"remaining_attempts": remaining_attempts},
                },
            )

        await self._delete_cache_keys(code_key, attempts_key, lock_key)
        verification_token = create_email_verification_token(
            normalize_email(email),
            expires_delta=timedelta(seconds=EMAIL_VERIFICATION_TOKEN_TTL_SECONDS),
        )
        token_payload = decode_email_verification_token(verification_token)
        jti = str(token_payload.get("jti") or "").strip()
        stored = await self.cache_service.set(
            email_verification_token_jti_key(jti),
            True,
            ttl=EMAIL_VERIFICATION_TOKEN_TTL_SECONDS,
        )
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Unable to verify email. Please try again.",
                    "code": "EMAIL_VERIFICATION_UNAVAILABLE",
                },
            )

        return verification_token, EMAIL_VERIFICATION_TOKEN_TTL_SECONDS

    def validate_registration_token(self, email: str, token: str) -> dict[str, Any]:
        normalized_token = (token or "").strip()
        if not normalized_token:
            raise ValidationException(
                "Email verification token is required.",
                code="EMAIL_VERIFICATION_REQUIRED",
            )

        try:
            token_payload = decode_email_verification_token(normalized_token)
        except Exception as exc:
            logger.info("Email verification token rejected: %s", exc)
            raise ValidationException(
                "Email verification token is invalid or expired.",
                code="EMAIL_VERIFICATION_INVALID",
            ) from exc

        token_email = normalize_email(str(token_payload.get("sub") or ""))
        request_email = normalize_email(str(email))
        if not token_email or token_email != request_email:
            raise ValidationException(
                "Email verification token does not match the registration email.",
                code="EMAIL_VERIFICATION_EMAIL_MISMATCH",
            )
        return token_payload

    async def consume_token_jti(self, claims: dict[str, Any]) -> None:
        jti = str(claims.get("jti") or "").strip()
        if not jti:
            raise ValidationException(
                "Email verification token is invalid or expired.",
                code="EMAIL_VERIFICATION_INVALID",
            )

        consumed = await self.cache_service.delete(email_verification_token_jti_key(jti))
        if not consumed:
            raise ValidationException(
                "Email verification token is invalid or expired.",
                code="EMAIL_VERIFICATION_INVALID",
            )
