import base64
from datetime import datetime, timezone
import io
import logging
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
import pyotp
import qrcode
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.core.config import settings
from app.models.user import User
from app.repositories.factory import RepositoryFactory

from .base import BaseService

logger = logging.getLogger(__name__)


class TwoFactorAuthService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)
        # Ensure Fernet key is valid length (44 url-safe base64 bytes). Expect provided via env.
        key = (
            settings.totp_encryption_key.get_secret_value() if settings.totp_encryption_key else ""
        )
        if not key:
            # Generate ephemeral key in dev if not provided
            self._fernet: Fernet = Fernet(Fernet.generate_key())
        else:
            try:
                self._fernet = Fernet(key)
            except Exception:
                # Fall back to ephemeral to avoid startup failures
                self._fernet = Fernet(Fernet.generate_key())

        default_window = 1 if getattr(settings, "is_testing", False) else 0
        env_window = os.getenv("TOTP_VALID_WINDOW")
        if env_window is not None:
            try:
                default_window = int(env_window)
            except ValueError:
                logger.warning(
                    "Invalid TOTP_VALID_WINDOW value '%s', using default %s",
                    env_window,
                    default_window,
                )
        self._totp_valid_window = max(0, default_window)

    def _encrypt(self, value: str) -> str:
        token: bytes = self._fernet.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    def _decrypt(self, token: str) -> str:
        decrypted: bytes = self._fernet.decrypt(token.encode("utf-8"))
        return decrypted.decode("utf-8")

    @BaseService.measure_operation("tfa_generate_secret")
    def generate_totp_secret(self) -> str:
        secret: str = pyotp.random_base32()
        return secret

    @BaseService.measure_operation("tfa_generate_qr")
    def generate_qr_code(
        self, email: str, secret: str, issuer: str = "InstaInstru"
    ) -> tuple[str, str]:
        totp = pyotp.TOTP(secret)
        otpauth_url = totp.provisioning_uri(name=email, issuer_name=issuer)
        img = qrcode.make(otpauth_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
        return data_url, otpauth_url

    @BaseService.measure_operation("tfa_setup_initiate")
    def setup_initiate(self, user: User) -> Dict[str, str]:
        secret = self.generate_totp_secret()
        data_url, otpauth_url = self.generate_qr_code(email=user.email, secret=secret)
        encrypted = self._encrypt(secret)
        with self.transaction():
            user.totp_secret = encrypted
            user.totp_enabled = False
            user.two_factor_setup_at = datetime.now(timezone.utc)
            # repo-pattern-ignore: commit handled by BaseService.transaction context manager
        return {"secret": secret, "qr_code_data_url": data_url, "otpauth_url": otpauth_url}

    @BaseService.measure_operation("tfa_verify_code")
    def verify_totp_code(self, user: User, code: str) -> bool:
        if not user.totp_secret:
            return False
        try:
            secret = self._decrypt(user.totp_secret)
        except Exception:
            return False
        token = (code or "").strip()
        if not token.isdigit():
            return False
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(token, valid_window=self._totp_valid_window))

    @BaseService.measure_operation("tfa_generate_backup_codes")
    def generate_backup_codes(self, count: int = 10) -> list[str]:
        import secrets

        codes: list[str] = []
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for _ in range(count):
            code = "-".join(
                ["".join(secrets.choice(alphabet) for _ in range(4)) for __ in range(3)]
            )  # e.g., ABCD-EFGH-2345
            codes.append(code)
        return codes

    @BaseService.measure_operation("tfa_setup_verify")
    def setup_verify(self, user: User, code: str) -> list[str]:
        if not self.verify_totp_code(user, code):
            raise ValueError("Invalid TOTP code")
        backup_codes_plain = self.generate_backup_codes()
        # Hash backup codes with bcrypt using existing password hasher
        backup_codes_hashed = [get_password_hash(c) for c in backup_codes_plain]
        with self.transaction():
            user.totp_enabled = True
            user.totp_verified_at = datetime.now(timezone.utc)
            user.backup_codes = backup_codes_hashed
            # repo-pattern-ignore: commit handled by BaseService.transaction context manager
        return backup_codes_plain

    @BaseService.measure_operation("tfa_disable")
    def disable(self, user: User, current_password: str) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Current password is incorrect")
        with self.transaction():
            user.totp_enabled = False
            user.totp_secret = None
            user.totp_verified_at = None
            user.backup_codes = None
            user.two_factor_last_used_at = None
            # repo-pattern-ignore: commit handled by BaseService.transaction context manager

    @BaseService.measure_operation("tfa_status")
    def status(self, user: User) -> Dict[str, Any]:
        return {
            "enabled": bool(user.totp_enabled),
            "verified_at": user.totp_verified_at.isoformat() if user.totp_verified_at else None,
            "last_used_at": user.two_factor_last_used_at.isoformat()
            if user.two_factor_last_used_at
            else None,
        }

    @BaseService.measure_operation("tfa_verify_login")
    def verify_login(self, user: User, code: Optional[str], backup_code: Optional[str]) -> bool:
        # Try TOTP first if provided
        if code and self.verify_totp_code(user, code):
            with self.transaction():
                user.two_factor_last_used_at = datetime.now(timezone.utc)
                # repo-pattern-ignore: commit handled by BaseService.transaction context manager
            return True
        # Fallback to backup code
        if backup_code and user.backup_codes:
            # Verify against any hashed code and invalidate if used
            for idx, hashed in enumerate(list(user.backup_codes)):
                try:
                    if verify_password(backup_code, hashed):
                        with self.transaction():
                            codes = list(user.backup_codes)
                            codes.pop(idx)
                            user.backup_codes = codes
                            user.two_factor_last_used_at = datetime.now(timezone.utc)
                            # repo-pattern-ignore: commit handled by BaseService.transaction context manager
                        return True
                except Exception:
                    continue
        return False

    @BaseService.measure_operation("tfa_check_required")
    def check_2fa_required(self, user: Optional[User]) -> bool:
        return bool(user and user.totp_enabled)
