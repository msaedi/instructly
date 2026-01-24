from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.instructor import InstructorProfile
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.beta_service import BetaService
from app.services.config_service import ConfigService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService


class DummyRedis:
    def __init__(self) -> None:
        self.store = {}
        self.ttl = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl[key] = ttl


@pytest.fixture(autouse=True)
def _mcp_secret(monkeypatch):
    monkeypatch.setattr(settings, "mcp_token_secret", SecretStr("test-mcp-secret"))


@pytest.fixture
def dummy_redis(monkeypatch):
    redis = DummyRedis()

    async def _get_redis():
        return redis

    import app.ratelimit.redis_backend as redis_backend

    monkeypatch.setattr(redis_backend, "get_redis", _get_redis)
    return redis


def _preview_payload(test_instructor):
    return {
        "recipient_emails": [test_instructor.email, "prospect@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": "Looking forward to having you!",
    }


def test_preview_returns_structure(
    client: TestClient, auth_headers_admin, test_instructor, dummy_redis
):
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers_admin,
    )
    assert res.status_code == 200
    body = res.json()
    assert "meta" in body
    assert "data" in body
    assert body["data"]["recipient_count"] == 2
    assert body["data"]["confirm_token"]


def test_preview_detects_existing_and_cap(
    client: TestClient, auth_headers_admin, db, test_instructor, dummy_redis
):
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None
    profile.is_founding_instructor = True
    db.flush()

    config_service = ConfigService(db)
    pricing_config, _updated_at = config_service.get_pricing_config()
    cap_raw = pricing_config.get("founding_instructor_cap", 100)
    try:
        cap = int(cap_raw)
    except (TypeError, ValueError):
        cap = 100
    used = InstructorProfileRepository(db).count_founding_instructors()
    expected_remaining = max(0, cap - used)

    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers_admin,
    )
    assert res.status_code == 200
    data = res.json()["data"]

    existing = next(r for r in data["recipients"] if r["email"] == test_instructor.email.lower())
    assert existing["exists_in_system"] is True
    assert existing["user_id"] == test_instructor.id
    assert any("already exists" in warning for warning in data["warnings"])

    preview = data["invite_preview"]
    assert preview["founding_cap_remaining"] == expected_remaining


def test_preview_generates_valid_confirm_token(
    client: TestClient, auth_headers_admin, admin_user, test_instructor, db, dummy_redis
):
    payload = _preview_payload(test_instructor)
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=payload,
        headers=auth_headers_admin,
    )
    assert res.status_code == 200
    body = res.json()["data"]

    token = body["confirm_token"]
    expected_payload = {
        "recipient_emails": [test_instructor.email.lower(), "prospect@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": payload["message_note"],
    }
    service = MCPConfirmTokenService(db)
    assert service.validate_token(token, expected_payload, actor_id=admin_user.id) is True


def test_send_invites_flow_and_audit(
    client: TestClient, auth_headers_admin, admin_user, test_instructor, db, dummy_redis, monkeypatch
):
    sent = []

    class DummyInvite:
        def __init__(self, code: str) -> None:
            self.code = code

    def _fake_send(self, to_email, role, expires_in_days, source, base_url, grant_founding_status=True):
        sent.append(to_email)
        return DummyInvite(code=f"CODE-{to_email.split('@')[0]}"), "join", "welcome"

    monkeypatch.setattr(BetaService, "send_invite_email", _fake_send)

    preview = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers_admin,
    )
    assert preview.status_code == 200
    token = preview.json()["data"]["confirm_token"]

    headers = {**auth_headers_admin, "Idempotency-Key": "idem-123"}
    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-123"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["sent_count"] == 2
    assert data["failed_count"] == 0
    assert len(sent) == 2

    log = (
        db.query(AuditLog)
        .filter(AuditLog.action == "invites.send", AuditLog.entity_type == "mcp_invite")
        .order_by(AuditLog.occurred_at.desc())
        .first()
    )
    assert log is not None
    assert log.actor_id == admin_user.id
    assert "recipient_emails" not in (log.after or {})


def test_send_invites_idempotent(
    client: TestClient, auth_headers_admin, test_instructor, dummy_redis, monkeypatch
):
    counter = {"calls": 0}

    class DummyInvite:
        def __init__(self, code: str) -> None:
            self.code = code

    def _fake_send(self, to_email, role, expires_in_days, source, base_url, grant_founding_status=True):
        counter["calls"] += 1
        return DummyInvite(code=f"CODE-{to_email.split('@')[0]}"), "join", "welcome"

    monkeypatch.setattr(BetaService, "send_invite_email", _fake_send)

    preview = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers_admin,
    )
    token = preview.json()["data"]["confirm_token"]

    headers = {**auth_headers_admin, "Idempotency-Key": "idem-dup"}
    payload = {"confirm_token": token, "idempotency_key": "idem-dup"}

    first = client.post("/api/v1/admin/mcp/invites/send", json=payload, headers=headers)
    second = client.post("/api/v1/admin/mcp/invites/send", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert counter["calls"] == 2


def test_send_rejects_missing_idempotency_key(
    client: TestClient, auth_headers_admin, test_instructor, dummy_redis
):
    preview = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers_admin,
    )
    token = preview.json()["data"]["confirm_token"]
    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-missing"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 400


def test_send_rejects_expired_token(
    client: TestClient, auth_headers_admin, admin_user, db, dummy_redis, monkeypatch
):
    monkeypatch.setattr(MCPConfirmTokenService, "TOKEN_EXPIRY_MINUTES", -1)
    service = MCPConfirmTokenService(db)
    payload = {
        "recipient_emails": ["expired@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": None,
    }
    token, _ = service.generate_token(payload, actor_id=admin_user.id)

    headers = {**auth_headers_admin, "Idempotency-Key": "idem-exp"}
    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-exp"},
        headers=headers,
    )
    assert res.status_code == 400


def test_invites_permissions(client: TestClient, auth_headers, test_instructor, dummy_redis):
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=auth_headers,
    )
    assert res.status_code == 403

    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": "token", "idempotency_key": "idem"},
        headers=auth_headers,
    )
    assert res.status_code == 403
