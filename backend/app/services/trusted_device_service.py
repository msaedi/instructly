"""Helpers and service logic for server-side trusted devices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.trusted_device import TrustedDevice
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.utils.cookies import effective_cookie_domain

TRUSTED_DEVICE_COOKIE_NAME = "tfa_device_trust"


@dataclass(frozen=True)
class TrustedDeviceSignature:
    """Coarse user-agent signature for trusted-device matching."""

    browser_family: str
    os_family: str
    device_name: str


class TrustedDeviceService:
    """Issue, validate, revoke, and clean up trusted-device records."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = RepositoryFactory.create_trusted_device_repository(db)

    @staticmethod
    def generate_device_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_device_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _trust_cookie_max_age() -> int:
        return settings.two_factor_trust_days * 24 * 60 * 60

    @staticmethod
    def parse_user_agent(user_agent: str | None) -> TrustedDeviceSignature:
        raw = (user_agent or "").strip()
        lowered = raw.lower()

        browser = "Unknown browser"
        if "edg/" in lowered or "edge/" in lowered:
            browser = "Edge"
        elif "opr/" in lowered or "opera" in lowered:
            browser = "Opera"
        elif "firefox/" in lowered:
            browser = "Firefox"
        elif "chrome/" in lowered or "crios/" in lowered:
            browser = "Chrome"
        elif "safari/" in lowered:
            browser = "Safari"

        os_name = "Unknown OS"
        if "iphone" in lowered:
            os_name = "iPhone"
        elif "ipad" in lowered:
            os_name = "iPad"
        elif "android" in lowered:
            os_name = "Android"
        elif "mac os x" in lowered or "macintosh" in lowered:
            os_name = "macOS"
        elif "windows" in lowered:
            os_name = "Windows"
        elif "linux" in lowered or "x11" in lowered:
            os_name = "Linux"

        return TrustedDeviceSignature(
            browser_family=browser,
            os_family=os_name,
            device_name=f"{browser} on {os_name}",
        )

    def issue_trust_cookie(self, response: Response, request: Request, token: str) -> None:
        response.set_cookie(
            key=TRUSTED_DEVICE_COOKIE_NAME,
            value=token,
            max_age=self._trust_cookie_max_age(),
            httponly=True,
            secure=bool(settings.session_cookie_secure),
            samesite="lax",
            path="/",
            domain=effective_cookie_domain(request.headers.get("origin")),
        )

    @staticmethod
    def clear_trust_cookie(response: Response, request: Request) -> None:
        response.delete_cookie(
            key=TRUSTED_DEVICE_COOKIE_NAME,
            path="/",
            domain=effective_cookie_domain(request.headers.get("origin")),
            secure=bool(settings.session_cookie_secure),
            httponly=True,
            samesite="lax",
        )

    def trust_current_device(
        self, user: User, request: Request, response: Response
    ) -> TrustedDevice:
        token = self.generate_device_token()
        signature = self.parse_user_agent(request.headers.get("user-agent"))
        trusted_device = self.repository.create(
            user_id=user.id,
            device_token_hash=self.hash_device_token(token),
            device_name=signature.device_name,
            user_agent=request.headers.get("user-agent", "") or "",
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.two_factor_trust_days),
        )
        self.issue_trust_cookie(response, request, token)
        return trusted_device

    def list_user_devices(self, user_id: str) -> list[TrustedDevice]:
        return self.repository.find_by_user(user_id)

    def validate_request_trust(self, user: User, request: Request, response: Response) -> bool:
        token = request.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
        if not token:
            return False

        trusted_device = self.repository.find_by_token_hash(self.hash_device_token(token))
        if trusted_device is None:
            self.clear_trust_cookie(response, request)
            return False

        if trusted_device.user_id != user.id:
            self.clear_trust_cookie(response, request)
            return False

        now = datetime.now(timezone.utc)
        if trusted_device.expires_at <= now:
            self.repository.delete(trusted_device.id)
            self.clear_trust_cookie(response, request)
            return False

        current_signature = self.parse_user_agent(request.headers.get("user-agent"))
        stored_signature = self.parse_user_agent(trusted_device.user_agent)
        if (
            current_signature.browser_family != stored_signature.browser_family
            or current_signature.os_family != stored_signature.os_family
        ):
            self.repository.delete(trusted_device.id)
            self.clear_trust_cookie(response, request)
            return False

        self.repository.update_last_used(trusted_device.id, used_at=now)
        return True

    def revoke_device_for_user(self, user_id: str, device_id: str) -> TrustedDevice | None:
        trusted_device = self.repository.get_by_id(device_id, load_relationships=False)
        if trusted_device is None or trusted_device.user_id != user_id:
            return None
        self.repository.delete(device_id)
        return trusted_device

    def revoke_all_for_user(self, user_id: str) -> int:
        return self.repository.delete_all_for_user(user_id)

    def current_cookie_matches_device(
        self,
        *,
        user_id: str,
        device_id: str,
        request: Request,
    ) -> bool:
        token = request.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
        if not token:
            return False

        trusted_device = self.repository.find_by_token_hash(self.hash_device_token(token))
        if trusted_device is None:
            return False
        return bool(trusted_device.user_id == user_id and trusted_device.id == device_id)

    def delete_expired_devices(self) -> int:
        return self.repository.delete_expired()
