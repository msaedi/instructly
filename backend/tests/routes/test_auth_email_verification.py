from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

from fastapi.testclient import TestClient

from app.api.dependencies.services import get_cache_service_dep
from app.auth import create_email_verification_token, decode_email_verification_token
from app.main import fastapi_app as app
from app.middleware.beta_phase_header import invalidate_beta_settings_cache
from app.models.beta import BetaAccess, BetaInvite
from app.models.user import User
from app.repositories.beta_repository import BetaSettingsRepository
from app.routes.v1 import auth as auth_routes


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.expire_times: dict[str, int] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        current = int(self.store.get(key, 0) or 0)
        current += 1
        self.store[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.store:
                deleted += 1
            self.store.pop(key, None)
            self.expire_times.pop(key, None)
        return deleted


class FakeCacheService:
    def __init__(self, redis_client: Optional[FakeRedis] = None) -> None:
        self._redis = redis_client
        self.store: dict[str, Any] = {}

    async def get_redis_client(self) -> Optional[FakeRedis]:
        return self._redis

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        existed = key in self.store
        self.store.pop(key, None)
        return existed


@contextmanager
def _override_cache_service(fake_cache: FakeCacheService) -> Iterator[None]:
    previous_override = app.dependency_overrides.get(get_cache_service_dep)
    app.dependency_overrides[get_cache_service_dep] = lambda: fake_cache
    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_cache_service_dep, None)
        else:
            app.dependency_overrides[get_cache_service_dep] = previous_override


def _set_beta_phase(db, phase: str) -> None:
    repo = BetaSettingsRepository(db)
    settings_record = repo.get_singleton()
    settings_record.beta_phase = phase
    settings_record.allow_signup_without_invite = False
    db.commit()
    invalidate_beta_settings_cache()


def _create_invite(
    db,
    *,
    code: str,
    email: str | None,
    role: str = "instructor",
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> BetaInvite:
    invite = BetaInvite(
        code=code,
        email=email,
        role=role,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=1)),
        used_at=used_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def _seed_email_verification_token(fake_cache: FakeCacheService, email: str) -> str:
    token = create_email_verification_token(email)
    payload = decode_email_verification_token(token)
    fake_cache.store[
        auth_routes._email_verification_token_jti_key(str(payload["jti"]))
    ] = True
    return token


def test_send_email_verification_returns_generic_success_for_new_and_existing_email(
    client: TestClient, db, monkeypatch
) -> None:
    fake_cache = FakeCacheService()
    monkeypatch.setattr(
        "app.routes.v1.auth._send_email_verification_email_sync",
        lambda **_kwargs: None,
    )

    existing_user = User(
        email="existing-verify@example.com",
        hashed_password="hashed",
        first_name="Existing",
        last_name="User",
        zip_code="10001",
        email_verified=True,
    )
    db.add(existing_user)
    db.commit()

    with _override_cache_service(fake_cache):
        first = client.post(
            "/api/v1/auth/send-email-verification",
            json={"email": "new-verify@example.com"},
        )
        second = client.post(
            "/api/v1/auth/send-email-verification",
            json={"email": "existing-verify@example.com"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"message": "Verification code sent"}
    assert second.json() == {"message": "Verification code sent"}
    assert "email_verify:new-verify@example.com" in fake_cache.store
    assert "email_verify:existing-verify@example.com" in fake_cache.store


def test_send_email_verification_rate_limits_after_three_sends(
    client: TestClient, monkeypatch
) -> None:
    fake_cache = FakeCacheService(FakeRedis())
    monkeypatch.setattr(
        "app.routes.v1.auth._send_email_verification_email_sync",
        lambda **_kwargs: None,
    )

    with _override_cache_service(fake_cache):
        for _ in range(3):
            response = client.post(
                "/api/v1/auth/send-email-verification",
                json={"email": "limited@example.com"},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/api/v1/auth/send-email-verification",
            json={"email": "limited@example.com"},
        )

    assert blocked.status_code == 429
    payload = blocked.json()
    assert payload["code"] == "EMAIL_VERIFICATION_RATE_LIMITED"


def test_send_email_verification_surfaces_delivery_failure(
    client: TestClient, monkeypatch
) -> None:
    fake_cache = FakeCacheService()

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("email down")

    monkeypatch.setattr(
        "app.routes.v1.auth._send_email_verification_email_sync",
        _boom,
    )

    with _override_cache_service(fake_cache):
        response = client.post(
            "/api/v1/auth/send-email-verification",
            json={"email": "delivery-fail@example.com"},
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "EMAIL_VERIFICATION_DELIVERY_FAILED"


def test_send_email_verification_rate_limits_per_ip(client: TestClient, monkeypatch) -> None:
    fake_cache = FakeCacheService(FakeRedis())
    monkeypatch.setattr(
        "app.routes.v1.auth._send_email_verification_email_sync",
        lambda **_kwargs: None,
    )

    with _override_cache_service(fake_cache):
        for index in range(auth_routes.EMAIL_VERIFICATION_SEND_IP_MAX):
            response = client.post(
                "/api/v1/auth/send-email-verification",
                json={"email": f"ip-limit-{index}@example.com"},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/api/v1/auth/send-email-verification",
            json={"email": "ip-limit-blocked@example.com"},
        )

    assert blocked.status_code == 429
    payload = blocked.json()
    assert payload["code"] == "EMAIL_VERIFICATION_IP_RATE_LIMITED"


def test_verify_email_code_returns_token_and_invalidates_code(client: TestClient) -> None:
    fake_cache = FakeCacheService()
    fake_cache.store["email_verify:verify-me@example.com"] = "123456"

    with _override_cache_service(fake_cache):
        response = client.post(
            "/api/v1/auth/verify-email-code",
            json={"email": "verify-me@example.com", "code": "123456"},
        )

        second = client.post(
            "/api/v1/auth/verify-email-code",
            json={"email": "verify-me@example.com", "code": "123456"},
        )

    assert response.status_code == 200
    payload = decode_email_verification_token(response.json()["verification_token"])
    assert payload["sub"] == "verify-me@example.com"
    assert fake_cache.store.get(
        auth_routes._email_verification_token_jti_key(str(payload["jti"]))
    ) is True
    assert second.status_code == 400
    assert second.json()["code"] == "EMAIL_VERIFICATION_CODE_INVALID"


def test_verify_email_code_tracks_attempts_and_locks(client: TestClient) -> None:
    fake_cache = FakeCacheService(FakeRedis())
    fake_cache.store["email_verify:attempts@example.com"] = "123456"

    with _override_cache_service(fake_cache):
        first = client.post(
            "/api/v1/auth/verify-email-code",
            json={"email": "attempts@example.com", "code": "000000"},
        )
        assert first.status_code == 400
        assert first.json()["errors"]["remaining_attempts"] == 4

        last_response = None
        for _ in range(4):
            last_response = client.post(
                "/api/v1/auth/verify-email-code",
                json={"email": "attempts@example.com", "code": "000000"},
            )

        locked = client.post(
            "/api/v1/auth/verify-email-code",
            json={"email": "attempts@example.com", "code": "123456"},
        )

    assert last_response is not None
    assert last_response.status_code == 400
    assert last_response.json()["code"] == "EMAIL_VERIFICATION_LOCKED"
    assert locked.status_code == 400
    assert locked.json()["code"] == "EMAIL_VERIFICATION_LOCKED"


def test_verify_email_code_expired_when_missing_from_cache(client: TestClient) -> None:
    fake_cache = FakeCacheService()

    with _override_cache_service(fake_cache):
        response = client.post(
            "/api/v1/auth/verify-email-code",
            json={"email": "expired@example.com", "code": "123456"},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "EMAIL_VERIFICATION_CODE_INVALID"
    assert payload["errors"]["expired"] is True


def test_register_requires_email_verification_token(client: TestClient, db) -> None:
    _set_beta_phase(db, "public")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "missing-token@example.com",
            "password": "StrongPass123!",
            "first_name": "Missing",
            "last_name": "Token",
            "zip_code": "10001",
            "role": "student",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EMAIL_VERIFICATION_REQUIRED"
    assert db.query(User).filter_by(email="missing-token@example.com").first() is None


def test_register_rejects_expired_or_mismatched_email_verification_token(
    client: TestClient, db
) -> None:
    _set_beta_phase(db, "public")
    expired_token = create_email_verification_token(
        "expired@example.com",
        expires_delta=timedelta(seconds=-1),
    )
    expired_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired@example.com",
            "password": "StrongPass123!",
            "first_name": "Expired",
            "last_name": "Token",
            "zip_code": "10001",
            "role": "student",
            "email_verification_token": expired_token,
        },
    )
    assert expired_response.status_code == 400
    assert expired_response.json()["code"] == "EMAIL_VERIFICATION_INVALID"

    mismatch_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "actual@example.com",
            "password": "StrongPass123!",
            "first_name": "Mismatch",
            "last_name": "Token",
            "zip_code": "10001",
            "role": "student",
            "email_verification_token": create_email_verification_token("different@example.com"),
        },
    )
    assert mismatch_response.status_code == 400
    assert mismatch_response.json()["code"] == "EMAIL_VERIFICATION_EMAIL_MISMATCH"


def test_register_enforces_invite_for_required_role_and_phase(client: TestClient, db) -> None:
    email = "invite-required@example.com"
    _set_beta_phase(db, "instructor_only")

    no_invite = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "first_name": "Invite",
            "last_name": "Missing",
            "zip_code": "10001",
            "role": "instructor",
            "email_verification_token": create_email_verification_token(email),
        },
    )
    assert no_invite.status_code == 400
    assert no_invite.json()["code"] == "INVITE_REQUIRED"

    invalid_invite = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "first_name": "Invite",
            "last_name": "Invalid",
            "zip_code": "10001",
            "role": "instructor",
            "email_verification_token": create_email_verification_token(email),
            "metadata": {"invite_code": "BADCODE"},
        },
    )
    assert invalid_invite.status_code == 400
    assert invalid_invite.json()["code"] == "INVITE_INVALID"

    _create_invite(
        db,
        code="USEDINV1",
        email=email,
        used_at=datetime.now(timezone.utc),
    )
    used = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "first_name": "Invite",
            "last_name": "Used",
            "zip_code": "10001",
            "role": "instructor",
            "email_verification_token": create_email_verification_token(email),
            "metadata": {"invite_code": "USEDINV1"},
        },
    )
    assert used.status_code == 400
    assert used.json()["code"] == "INVITE_INVALID"

    _create_invite(
        db,
        code="EXPIRED1",
        email=email,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    expired = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "first_name": "Invite",
            "last_name": "Expired",
            "zip_code": "10001",
            "role": "instructor",
            "email_verification_token": create_email_verification_token(email),
            "metadata": {"invite_code": "EXPIRED1"},
        },
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "INVITE_INVALID"

    _create_invite(db, code="MISMATCH1", email="other@example.com")
    mismatch = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "first_name": "Invite",
            "last_name": "Mismatch",
            "zip_code": "10001",
            "role": "instructor",
            "email_verification_token": create_email_verification_token(email),
            "metadata": {"invite_code": "MISMATCH1"},
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "INVITE_INVALID"


def test_register_creates_verified_user_and_consumes_invite(client: TestClient, db) -> None:
    email = "verified-instructor@example.com"
    _set_beta_phase(db, "instructor_only")
    invite = _create_invite(db, code="VALID123", email=email)
    fake_cache = FakeCacheService()
    token = _seed_email_verification_token(fake_cache, email)

    with _override_cache_service(fake_cache):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123!",
                "first_name": "Verified",
                "last_name": "Instructor",
                "zip_code": "10001",
                "role": "instructor",
                "phone": "+12125550000",
                "email_verification_token": token,
                "metadata": {"invite_code": "VALID123"},
            },
        )

    assert response.status_code == 200
    user = db.query(User).filter_by(email=email).first()
    assert user is not None
    assert user.email_verified is True

    db.refresh(invite)
    assert invite.used_at is not None
    assert invite.used_by_user_id == user.id

    access = db.query(BetaAccess).filter_by(user_id=user.id).first()
    assert access is not None
    assert access.invited_by_code == "VALID123"


def test_register_rejects_reused_email_verification_token(client: TestClient, db) -> None:
    email = "single-use@example.com"
    _set_beta_phase(db, "public")
    fake_cache = FakeCacheService()
    token = _seed_email_verification_token(fake_cache, email)

    with _override_cache_service(fake_cache):
        first = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123!",
                "first_name": "Single",
                "last_name": "Use",
                "zip_code": "10001",
                "role": "student",
                "phone": "+12125550001",
                "email_verification_token": token,
            },
        )
        payload = decode_email_verification_token(token)
        assert (
            fake_cache.store.get(auth_routes._email_verification_token_jti_key(str(payload["jti"])))
            is None
        )
        second = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123!",
                "first_name": "Single",
                "last_name": "Use",
                "zip_code": "10001",
                "role": "student",
                "phone": "+12125550001",
                "email_verification_token": token,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["code"] == "EMAIL_VERIFICATION_INVALID"


def test_register_allows_student_without_invite_in_public_phase(client: TestClient, db) -> None:
    email = "public-student@example.com"
    _set_beta_phase(db, "public")
    fake_cache = FakeCacheService()
    token = _seed_email_verification_token(fake_cache, email)

    with _override_cache_service(fake_cache):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123!",
                "first_name": "Public",
                "last_name": "Student",
                "zip_code": "10001",
                "role": "student",
                "phone": "+12125550000",
                "email_verification_token": token,
            },
        )

    assert response.status_code == 200
    user = db.query(User).filter_by(email=email).first()
    assert user is not None
    assert user.email_verified is True
