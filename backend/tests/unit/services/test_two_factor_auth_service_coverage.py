# backend/tests/unit/services/test_two_factor_auth_service_coverage.py
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from app.auth import get_password_hash
from app.core.config import settings
from app.models.user import User
from app.services.two_factor_auth_service import TwoFactorAuthService, _derive_fallback_key


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


@pytest.fixture
def user(db):
    user = User(
        email="tfa@example.com",
        first_name="Tfa",
        last_name="User",
        hashed_password=get_password_hash("correct"),
        zip_code="10001",
        timezone="America/New_York",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_derive_fallback_key_when_secret_missing(monkeypatch):
    class _BadSecret:
        def get_secret_value(self) -> str:  # pragma: no cover - invoked via monkeypatch
            raise RuntimeError("boom")

    monkeypatch.setattr(settings, "secret_key", _BadSecret())
    key = _derive_fallback_key()
    assert isinstance(key, bytes)
    assert len(base64.urlsafe_b64decode(key)) == 32


def test_init_missing_key_hosted_context_raises(db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(settings, "totp_encryption_key", _Secret(""))
    with pytest.raises(RuntimeError, match="TOTP_ENCRYPTION_KEY must be set"):
        TwoFactorAuthService(db)


def test_init_invalid_key_hosted_context_raises(db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "totp_encryption_key", _Secret("bad-key"))
    with pytest.raises(RuntimeError, match="Invalid TOTP_ENCRYPTION_KEY"):
        TwoFactorAuthService(db)


def test_init_invalid_key_local_falls_back(db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(settings, "totp_encryption_key", _Secret("bad-key"))
    service = TwoFactorAuthService(db)
    token = service._encrypt("secret")
    assert service._decrypt(token) == "secret"


def test_init_missing_key_local_uses_fallback(db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(settings, "totp_encryption_key", _Secret(""))
    service = TwoFactorAuthService(db)
    token = service._encrypt("secret")
    assert service._decrypt(token) == "secret"


def test_init_secret_key_exception_local_uses_fallback(db, monkeypatch):
    class _BadSecret:
        def get_secret_value(self) -> str:  # pragma: no cover - invoked via monkeypatch
            raise RuntimeError("boom")

    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(settings, "totp_encryption_key", _BadSecret())
    service = TwoFactorAuthService(db)
    token = service._encrypt("secret")
    assert service._decrypt(token) == "secret"


def test_totp_valid_window_testing_mode(db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(settings, "totp_encryption_key", _Secret(""))
    monkeypatch.setattr(settings, "totp_valid_window", 0, raising=False)
    monkeypatch.setattr(settings, "is_testing", True, raising=False)
    service = TwoFactorAuthService(db)
    assert service._totp_valid_window == 1


def test_verify_totp_code_paths(db, user):
    service = TwoFactorAuthService(db)

    assert service.verify_totp_code(user, "123456") is False

    user.totp_secret = "not-a-token"
    assert service.verify_totp_code(user, "123456") is False

    secret = service.generate_totp_secret()
    user.totp_secret = service._encrypt(secret)
    assert service.verify_totp_code(user, "abc") is False

    code = pyotp.TOTP(secret).now()
    assert service.verify_totp_code(user, code) is True


def test_generate_qr_code_outputs(db):
    service = TwoFactorAuthService(db)
    data_url, otpauth_url = service.generate_qr_code(
        email="user@example.com", secret=service.generate_totp_secret()
    )
    assert data_url.startswith("data:image/png;base64,")
    assert "otpauth://" in otpauth_url


def test_setup_verify_invalid_code_raises(db, user):
    service = TwoFactorAuthService(db)
    secret = service.generate_totp_secret()
    user.totp_secret = service._encrypt(secret)
    with pytest.raises(ValueError, match="Invalid TOTP code"):
        service.setup_verify(user, "000000")


def test_setup_verify_sets_backup_codes(db, user):
    service = TwoFactorAuthService(db)
    secret = service.generate_totp_secret()
    user.totp_secret = service._encrypt(secret)

    code = pyotp.TOTP(secret).now()
    backup_codes = service.setup_verify(user, code)

    assert user.totp_enabled is True
    assert user.totp_verified_at is not None
    assert isinstance(user.backup_codes, list)
    assert len(backup_codes) == len(user.backup_codes)


def test_setup_initiate_sets_fields(db, user):
    service = TwoFactorAuthService(db)
    result = service.setup_initiate(user)
    assert "secret" in result
    assert user.totp_secret is not None
    assert user.totp_enabled is False
    assert user.two_factor_setup_at is not None


def test_disable_requires_password(db, user):
    service = TwoFactorAuthService(db)
    with pytest.raises(ValueError, match="Current password is incorrect"):
        service.disable(user, "wrong")


def test_disable_clears_fields(db, user):
    service = TwoFactorAuthService(db)
    user.totp_enabled = True
    user.totp_secret = service._encrypt("secret")
    user.totp_verified_at = datetime.now(timezone.utc)
    user.backup_codes = [get_password_hash("ABCD-EFGH-2345")]
    user.two_factor_last_used_at = datetime.now(timezone.utc) - timedelta(days=1)

    service.disable(user, "correct")
    assert user.totp_enabled is False
    assert user.totp_secret is None
    assert user.totp_verified_at is None
    assert user.backup_codes is None
    assert user.two_factor_last_used_at is None


def test_verify_login_with_totp_sets_last_used(db, user):
    service = TwoFactorAuthService(db)
    secret = service.generate_totp_secret()
    user.totp_secret = service._encrypt(secret)
    code = pyotp.TOTP(secret).now()

    assert service.verify_login(user, code, None) is True
    assert user.two_factor_last_used_at is not None
    assert user.two_factor_last_used_at.tzinfo == timezone.utc


def test_verify_login_with_backup_code_consumes(db, user):
    service = TwoFactorAuthService(db)
    backup_code = "ABCD-EFGH-2345"
    user.backup_codes = [get_password_hash(backup_code)]

    assert service.verify_login(user, None, backup_code) is True
    assert user.backup_codes == []
    assert user.two_factor_last_used_at is not None


def test_status_returns_state(db, user):
    service = TwoFactorAuthService(db)
    user.totp_enabled = True
    user.totp_verified_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    user.two_factor_last_used_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    status = service.status(user)
    assert status["enabled"] is True
    assert status["verified_at"] == "2024-01-01T00:00:00+00:00"
    assert status["last_used_at"] == "2024-01-02T00:00:00+00:00"


def test_verify_login_backup_code_handles_verify_error(db, user, monkeypatch):
    service = TwoFactorAuthService(db)
    user.backup_codes = ["bad-hash"]

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.two_factor_auth_service.verify_password", _boom)

    assert service.verify_login(user, None, "ABCD-EFGH-2345") is False


def test_check_2fa_required(db, user):
    service = TwoFactorAuthService(db)
    assert service.check_2fa_required(None) is False
    user.totp_enabled = True
    assert service.check_2fa_required(user) is True
