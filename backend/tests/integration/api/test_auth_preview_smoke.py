from __future__ import annotations

import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pyotp
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.auth_service import AuthService
from app.services.two_factor_auth_service import TwoFactorAuthService
from app.utils.cookies import session_cookie_base_name

CSRF_COOKIE = "csrftoken"
CSRF_HEADER = "X-CSRFToken"
CSRF_ORIGIN = "https://preview.instainstru.com"


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = "previewtoken"
    client.cookies.set(CSRF_COOKIE, token)
    return {
        CSRF_HEADER: token,
        "Origin": CSRF_ORIGIN,
        "Referer": f"{CSRF_ORIGIN}/",
    }


def _register_user_with_2fa(db: Session, email: str) -> tuple[str, str]:
    auth_service = AuthService(db, None, None)
    user = auth_service.register_user(
        email=email,
        password="Preview123!",
        first_name="Preview",
        last_name="Smoke",
        zip_code="10001",
    )
    tfa_service = TwoFactorAuthService(db)
    setup = tfa_service.setup_initiate(user)
    secret = setup["secret"]
    code = pyotp.TOTP(secret).now()
    tfa_service.setup_verify(user, code)
    db.refresh(user)
    return user.id, secret


def _ensure_hosted_totp_key(monkeypatch) -> None:
    try:
        current = settings.totp_encryption_key.get_secret_value()
    except Exception:
        current = ""
    if current:
        return
    generated = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(settings, "totp_encryption_key", SecretStr(generated), raising=False)


def _extract_session_token_from_set_cookie(set_cookie_header: str, cookie_name: str) -> str:
    marker = f"{cookie_name}="
    assert marker in set_cookie_header
    return set_cookie_header.split(marker, 1)[1].split(";", 1)[0]


def test_preview_2fa_session_flow(client: TestClient, db: Session, monkeypatch) -> None:
    client.cookies.clear()
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "session_cookie_name", "sid", raising=False)
    monkeypatch.setattr(settings, "session_cookie_secure", True, raising=False)
    monkeypatch.setattr(settings, "session_cookie_samesite", "lax", raising=False)
    monkeypatch.setattr(settings, "session_cookie_domain", ".instainstru.com", raising=False)
    _ensure_hosted_totp_key(monkeypatch)

    email = f"preview+{uuid.uuid4().hex[:8]}@example.com"
    _, secret = _register_user_with_2fa(db, email)

    login_response = client.post(
        "/api/v1/auth/login-with-session",
        json={"email": email, "password": "Preview123!", "guest_session_id": "preview-guest"},
    )
    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["requires_2fa"] is True
    assert "access_token" not in payload
    assert login_response.headers.get("set-cookie") is None

    totp = pyotp.TOTP(secret)
    csrf_headers = _csrf_headers(client)
    csrf_headers["X-Trust-Browser"] = "true"
    verify_response = client.post(
        "/api/v1/2fa/verify-login",
        json={"temp_token": payload["temp_token"], "code": totp.now()},
        headers=csrf_headers,
    )
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert "access_token" not in body
    resolved_cookie_name = session_cookie_base_name("preview")
    set_cookie_headers = verify_response.headers.get_list("set-cookie")
    session_cookie_header = next(
        (h for h in set_cookie_headers if h.startswith(f"{resolved_cookie_name}=")),
        "",
    )
    assert session_cookie_header
    assert "Secure" in session_cookie_header
    trust_cookie_header = next((h for h in set_cookie_headers if "tfa_trusted=1" in h), "")
    assert trust_cookie_header
    assert "Secure" in trust_cookie_header
    assert "HttpOnly" in trust_cookie_header
    assert "Path=/" in trust_cookie_header
    assert "SameSite=lax" in trust_cookie_header or "SameSite=Lax" in trust_cookie_header
    session_token = _extract_session_token_from_set_cookie(
        session_cookie_header,
        resolved_cookie_name,
    )

    # TestClient runs over HTTP, so Secure cookies are not sent automatically.
    # Include the bearer token to prove authentication succeeds post-2FA.
    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {session_token}"})
    assert me_response.status_code == 200

    logout_headers = _csrf_headers(client)
    logout_headers["Cookie"] = f"{resolved_cookie_name}={session_token}"
    logout_response = client.post("/api/v1/public/logout", headers=logout_headers)
    assert logout_response.status_code == 204
    logout_cookies = logout_response.headers.get_list("set-cookie")
    logout_session_cookie = next(
        (h for h in logout_cookies if h.startswith(f"{resolved_cookie_name}=")),
        "",
    )
    assert logout_session_cookie
    assert "Max-Age=0" in logout_session_cookie
    assert "Secure" in logout_session_cookie
    assert "HttpOnly" in logout_session_cookie
    assert "Path=/" in logout_session_cookie
    assert "SameSite=lax" in logout_session_cookie or "SameSite=Lax" in logout_session_cookie

    revoked_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert revoked_response.status_code == 401
    assert revoked_response.json().get("detail") == "Token has been revoked"

    me_after_logout = client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401
