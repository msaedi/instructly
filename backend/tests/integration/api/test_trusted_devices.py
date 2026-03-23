from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import uuid

from fastapi.testclient import TestClient
import pyotp
from sqlalchemy.orm import Session

from app.models.trusted_device import TrustedDevice
from app.services.auth_service import AuthService
from app.services.trusted_device_service import (
    TRUSTED_DEVICE_COOKIE_NAME,
    TrustedDeviceService,
)
from app.services.two_factor_auth_service import TwoFactorAuthService

DEFAULT_PASSWORD = "Test1234!"


def _register_user(db: Session, email: str):
    auth_service = AuthService(db, None, None)
    user = auth_service.register_user(
        email=email,
        password=DEFAULT_PASSWORD,
        first_name="Taylor",
        last_name="Jordan",
        zip_code="10001",
    )
    assert user is not None
    db.refresh(user)
    return user


def _register_user_with_2fa(db: Session, email: str) -> tuple[str, str]:
    user = _register_user(db, email)
    tfa_service = TwoFactorAuthService(db)
    setup = tfa_service.setup_initiate(user)
    secret = setup["secret"]
    tfa_service.setup_verify(user, pyotp.TOTP(secret).now())
    db.refresh(user)
    return user.id, secret


def _login_requires_2fa(
    client: TestClient,
    email: str,
    *,
    password: str = DEFAULT_PASSWORD,
    user_agent: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    headers = dict(extra_headers or {})
    if user_agent:
        headers["User-Agent"] = user_agent
    response = client.post(
        "/api/v1/auth/login-with-session",
        json={"email": email, "password": password},
        headers=headers or None,
    )
    assert response.status_code == 200
    return {
        "response": response,
        "payload": response.json(),
    }


def _verify_login_with_trust(
    client: TestClient,
    *,
    temp_token: str,
    secret: str,
    user_agent: str | None = None,
):
    totp = pyotp.TOTP(secret)
    headers = {"X-Trust-Browser": "true"}
    if user_agent:
        headers["User-Agent"] = user_agent

    def _post(offset_seconds: int = 0):
        timestamp = int(time.time()) + offset_seconds
        return client.post(
            "/api/v1/2fa/verify-login",
            json={"temp_token": temp_token, "code": totp.at(timestamp)},
            headers=headers,
        )

    response = _post()
    if response.status_code == 400:
        response = _post(-30)
    assert response.status_code == 200
    return response


def _create_trusted_device(
    db: Session,
    *,
    user_id: str,
    token: str,
    user_agent: str,
    expires_at: datetime,
) -> None:
    TrustedDeviceService(db).repository.create(
        user_id=user_id,
        device_token_hash=TrustedDeviceService.hash_device_token(token),
        device_name=TrustedDeviceService.parse_user_agent(user_agent).device_name,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.commit()


def _clear_cookie_header_present(response) -> bool:
    return any(
        TRUSTED_DEVICE_COOKIE_NAME in header and "Max-Age=0" in header
        for header in response.headers.get_list("set-cookie")
    )


class TestTrustedDevices:
    def test_valid_trust_cookie_skips_two_factor(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"valid+{uuid.uuid4().hex[:8]}@example.com"
        user_id, _ = _register_user_with_2fa(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"
        token = "valid-trust-token"
        _create_trusted_device(
            db,
            user_id=user_id,
            token=token,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)

        login = _login_requires_2fa(client, email, user_agent=user_agent)
        assert login["payload"]["requires_2fa"] is False

    def test_expired_trust_cookie_requires_two_factor_and_cleans_up(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"expired+{uuid.uuid4().hex[:8]}@example.com"
        user_id, _ = _register_user_with_2fa(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"
        token = "expired-trust-token"
        _create_trusted_device(
            db,
            user_id=user_id,
            token=token,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)

        login = _login_requires_2fa(client, email, user_agent=user_agent)
        assert login["payload"]["requires_2fa"] is True
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(login["response"])

    def test_forged_trust_cookie_requires_two_factor_and_clears_cookie(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"forged+{uuid.uuid4().hex[:8]}@example.com"
        _register_user_with_2fa(db, email)
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, "forged-trust-token")

        login = _login_requires_2fa(client, email, user_agent="Mozilla/5.0 Chrome/123.0 Windows")
        assert login["payload"]["requires_2fa"] is True
        assert _clear_cookie_header_present(login["response"])

    def test_cross_user_trust_cookie_requires_two_factor_and_keeps_owner_row(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email_a = f"owner+{uuid.uuid4().hex[:8]}@example.com"
        email_b = f"other+{uuid.uuid4().hex[:8]}@example.com"
        user_a_id, _ = _register_user_with_2fa(db, email_a)
        user_b_id, _ = _register_user_with_2fa(db, email_b)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"
        token = "cross-user-trust-token"
        _create_trusted_device(
            db,
            user_id=user_a_id,
            token=token,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)

        login = _login_requires_2fa(client, email_b, user_agent=user_agent)
        assert login["payload"]["requires_2fa"] is True
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_a_id).count() == 1
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_b_id).count() == 0
        assert _clear_cookie_header_present(login["response"])

        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)
        owner_follow_up = _login_requires_2fa(client, email_a, user_agent=user_agent)
        assert owner_follow_up["payload"]["requires_2fa"] is False

    def test_verify_login_with_trust_creates_trusted_device_row_and_cookie(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"trusted+{uuid.uuid4().hex[:8]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"

        login = _login_requires_2fa(client, email, user_agent=user_agent)
        assert login["payload"]["requires_2fa"] is True

        verify_response = _verify_login_with_trust(
            client,
            temp_token=str(login["payload"]["temp_token"]),
            secret=secret,
            user_agent=user_agent,
        )

        cookie_value = client.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
        assert cookie_value
        assert any(
            f"{TRUSTED_DEVICE_COOKIE_NAME}=" in header
            for header in verify_response.headers.get_list("set-cookie")
        )

        trusted_devices = db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).all()
        assert len(trusted_devices) == 1
        assert trusted_devices[0].device_token_hash == TrustedDeviceService.hash_device_token(
            cookie_value
        )
        assert trusted_devices[0].device_name == "Chrome on macOS"
        assert trusted_devices[0].user_agent == user_agent

    def test_x_trusted_bypass_header_has_no_effect(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"header+{uuid.uuid4().hex[:8]}@example.com"
        _register_user_with_2fa(db, email)

        login = _login_requires_2fa(
            client,
            email,
            user_agent="Mozilla/5.0 Chrome/123.0 Macintosh",
            extra_headers={"X-Trusted-Bypass": "true"},
        )
        assert login["payload"]["requires_2fa"] is True

    def test_user_agent_mismatch_requires_two_factor_and_deletes_device(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"mismatch+{uuid.uuid4().hex[:8]}@example.com"
        user_id, _ = _register_user_with_2fa(db, email)
        token = "ua-mismatch-token"
        _create_trusted_device(
            db,
            user_id=user_id,
            token=token,
            user_agent="Mozilla/5.0 Chrome/123.0 Macintosh",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)

        login = _login_requires_2fa(client, email, user_agent="Mozilla/5.0 Firefox/124.0 Macintosh")
        assert login["payload"]["requires_2fa"] is True
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(login["response"])

    def test_revoke_single_trusted_device_clears_cookie(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"single+{uuid.uuid4().hex[:8]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"

        login = _login_requires_2fa(client, email, user_agent=user_agent)
        assert login["payload"]["requires_2fa"] is True
        _verify_login_with_trust(
            client,
            temp_token=str(login["payload"]["temp_token"]),
            secret=secret,
            user_agent=user_agent,
        )

        list_response = client.get("/api/v1/2fa/trusted-devices")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert len(items) == 1
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 1

        revoke_response = client.delete(f"/api/v1/2fa/trusted-devices/{items[0]['id']}")
        assert revoke_response.status_code == 200
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(revoke_response)

        follow_up = _login_requires_2fa(client, email, user_agent=user_agent)
        assert follow_up["payload"]["requires_2fa"] is True

    def test_revoke_all_trusted_devices_removes_all_rows(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"all+{uuid.uuid4().hex[:8]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"

        login = _login_requires_2fa(client, email, user_agent=user_agent)
        _verify_login_with_trust(
            client,
            temp_token=str(login["payload"]["temp_token"]),
            secret=secret,
            user_agent=user_agent,
        )
        _create_trusted_device(
            db,
            user_id=user_id,
            token="second-trust-token",
            user_agent="Mozilla/5.0 Safari/17.0 iPhone",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 2

        revoke_response = client.delete("/api/v1/2fa/trusted-devices")
        assert revoke_response.status_code == 200
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(revoke_response)

    def test_disable_two_factor_clears_trusted_devices(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"disable+{uuid.uuid4().hex[:8]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)

        login = _login_requires_2fa(client, email)
        _verify_login_with_trust(
            client,
            temp_token=str(login["payload"]["temp_token"]),
            secret=secret,
        )
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 1

        disable_response = client.post(
            "/api/v1/2fa/disable",
            json={"current_password": DEFAULT_PASSWORD},
        )
        assert disable_response.status_code == 200
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(disable_response)

    def test_setup_verify_clears_trusted_devices(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"setup+{uuid.uuid4().hex[:8]}@example.com"
        user = _register_user(db, email)
        user_agent = "Mozilla/5.0 Chrome/123.0 Macintosh"
        token = "setup-verify-trust-token"
        _create_trusted_device(
            db,
            user_id=user.id,
            token=token,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        client.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, token)

        login_response = client.post(
            "/api/v1/auth/login-with-session",
            json={"email": email, "password": DEFAULT_PASSWORD},
        )
        assert login_response.status_code == 200
        assert login_response.json()["requires_2fa"] is False
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).count() == 1

        initiate_response = client.post("/api/v1/2fa/setup/initiate")
        assert initiate_response.status_code == 200
        secret = initiate_response.json()["secret"]

        verify_response = client.post(
            "/api/v1/2fa/setup/verify",
            json={"code": pyotp.TOTP(secret).now()},
            headers={"User-Agent": user_agent},
        )
        assert verify_response.status_code == 200
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).count() == 0
        assert _clear_cookie_header_present(verify_response)

    def test_change_password_clears_trusted_devices(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"password+{uuid.uuid4().hex[:8]}@example.com"
        user_id, secret = _register_user_with_2fa(db, email)

        login = _login_requires_2fa(client, email)
        _verify_login_with_trust(
            client,
            temp_token=str(login["payload"]["temp_token"]),
            secret=secret,
        )
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 1

        change_response = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "Stronger123",
            },
        )
        assert change_response.status_code == 200
        assert db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).count() == 0
        assert _clear_cookie_header_present(change_response)

    def test_legacy_cookie_is_ignored_for_login(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        client.cookies.clear()
        email = f"legacy+{uuid.uuid4().hex[:8]}@example.com"
        _register_user_with_2fa(db, email)
        legacy_cookie_key = "tfa_" + "trusted"
        client.cookies.set(legacy_cookie_key, "1")

        login = _login_requires_2fa(client, email)
        assert login["payload"]["requires_2fa"] is True
