from __future__ import annotations

from datetime import datetime, timezone
import re
import time
import uuid

from fastapi.testclient import TestClient
import jwt
from pydantic import SecretStr
import pyotp
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.search_history import SearchHistory
from app.services.auth_service import AuthService
from app.services.two_factor_auth_service import TwoFactorAuthService


def _register_user_with_2fa(db: Session, email: str) -> tuple[str, str]:
    auth_service = AuthService(db, None, None)
    user = auth_service.register_user(
        email=email,
        password="Test1234!",
        first_name="Emma",
        last_name="Johnson",
        zip_code="10001",
    )
    tfa_service = TwoFactorAuthService(db)
    setup = tfa_service.setup_initiate(user)
    secret = setup["secret"]
    code = pyotp.TOTP(secret).now()
    tfa_service.setup_verify(user, code)
    db.refresh(user)
    return user.id, secret


def _seed_guest_search(db: Session, guest_session_id: str, query: str = "piano lessons") -> None:
    db.add(
        SearchHistory(
            guest_session_id=guest_session_id,
            search_query=query,
            normalized_query=query.lower(),
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


class TestLoginWithSessionTwoFactor:
    def test_totp_key_required_in_preview(self, db: Session, monkeypatch) -> None:
        monkeypatch.setenv("SITE_MODE", "preview")
        monkeypatch.setattr(settings, "totp_encryption_key", SecretStr(""), raising=False)
        message = "TOTP_ENCRYPTION_KEY must be set in hosted (preview/prod) environments"
        with pytest.raises(RuntimeError, match=re.escape(message)):
            TwoFactorAuthService(db)

    def test_requires_two_factor_when_enabled(self, client: TestClient, db: Session):
        client.cookies.clear()
        email = f"emma+{uuid.uuid4().hex[:6]}@example.com"
        _register_user_with_2fa(db, email)

        response = client.post(
            "/api/v1/auth/login-with-session",
            json={
                "email": email,
                "password": "Test1234!",
                "guest_session_id": "guest-requires-2fa",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["requires_2fa"] is True
        assert payload["temp_token"]
        assert payload["access_token"] is None
        assert response.headers.get("set-cookie") is None

    def test_verify_then_issues_session_and_converts_guests(self, client: TestClient, db: Session):
        client.cookies.clear()
        email = f"emma+{uuid.uuid4().hex[:6]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)
        guest_session_id = f"guest-{uuid.uuid4().hex[:6]}"
        _seed_guest_search(db, guest_session_id)

        login_response = client.post(
            "/api/v1/auth/login-with-session",
            json={
                "email": email,
                "password": "Test1234!",
                "guest_session_id": guest_session_id,
            },
        )
        temp_token = login_response.json()["temp_token"]

        totp = pyotp.TOTP(secret)

        def post_with_code(offset_seconds: int = 0):
            timestamp = int(time.time()) + offset_seconds
            code = totp.at(timestamp)
            return client.post(
                "/api/v1/2fa/verify-login",
                json={"temp_token": temp_token, "code": code},
                headers={"X-Trust-Browser": "true"},
            )

        verify_response = post_with_code()
        if verify_response.status_code == 400:
            # Single bounded retry one step back in case we crossed the boundary
            verify_response = post_with_code(-30)

        assert verify_response.status_code == 200
        access_token = verify_response.json()["access_token"]
        decoded = jwt.decode(
            access_token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
        assert decoded["sub"] == user_id
        set_cookie = verify_response.headers.get("set-cookie") or ""
        assert f"{settings.session_cookie_name}=" in set_cookie
        assert "tfa_trusted=1" in set_cookie

        guest_rows = db.query(SearchHistory).filter(
            SearchHistory.guest_session_id == guest_session_id
        ).all()
        assert guest_rows
        assert all(row.converted_to_user_id == user_id for row in guest_rows)
        assert (
            db.query(SearchHistory).filter(SearchHistory.user_id == user_id).count()
            >= len(guest_rows)
        )

        # Subsequent login should skip 2FA due to trust cookie
        follow_up = client.post(
            "/api/v1/auth/login-with-session",
            json={
                "email": email,
                "password": "Test1234!",
                "guest_session_id": guest_session_id,
            },
        )
        assert follow_up.status_code == 200
        follow_payload = follow_up.json()
        assert follow_payload["requires_2fa"] is False
        assert follow_payload["access_token"]

    def test_wrong_2fa_code_rejected(self, client: TestClient, db: Session):
        client.cookies.clear()
        email = f"emma+{uuid.uuid4().hex[:6]}@example.com"
        _register_user_with_2fa(db, email)

        login_response = client.post(
            "/api/v1/auth/login-with-session",
            json={
                "email": email,
                "password": "Test1234!",
                "guest_session_id": "guest-bad-code",
            },
        )
        temp_token = login_response.json()["temp_token"]

        bad_verify = client.post(
            "/api/v1/2fa/verify-login",
            json={"temp_token": temp_token, "code": "000000"},
        )

        assert bad_verify.status_code == 400
        assert bad_verify.headers.get("set-cookie") is None
