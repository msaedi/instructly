from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.core.exceptions import ServiceException
from app.models.audit_log import AuditLog
from app.models.instructor import InstructorProfile
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.routes.v1.admin.mcp.invites import MAX_INVITE_BATCH_SIZE, preview_invites
from app.schemas.mcp import MCPInvitePreviewRequest
from app.services.beta_service import BetaService
from app.services.config_service import ConfigService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.mcp_invite_service import MCPInviteService


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


@pytest.fixture
def mock_founding_cap(monkeypatch):
    mock = MagicMock(return_value=10)
    monkeypatch.setattr(MCPInviteService, "get_founding_cap_remaining", mock)
    return mock


def _preview_payload(test_instructor):
    return {
        "recipient_emails": [test_instructor.email, "prospect@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": "Looking forward to having you!",
    }


def test_preview_returns_structure(
    client: TestClient, mcp_service_headers, test_instructor, dummy_redis
):
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert "meta" in body
    assert "data" in body
    assert body["data"]["recipient_count"] == 2
    assert body["data"]["confirm_token"]


def test_preview_detects_existing_and_cap(
    client: TestClient, mcp_service_headers, db, test_instructor, dummy_redis
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
        headers=mcp_service_headers,
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
    client: TestClient, mcp_service_headers, mcp_service_user, test_instructor, db, dummy_redis
):
    payload = _preview_payload(test_instructor)
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=payload,
        headers=mcp_service_headers,
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
    assert service.validate_token(token, expected_payload, actor_id=mcp_service_user.id) is True


def test_preview_rejects_too_many_recipients(
    client: TestClient, mcp_service_headers, dummy_redis
):
    emails = [f"user{i}@example.com" for i in range(101)]
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json={"recipient_emails": emails, "grant_founding_status": True},
        headers=mcp_service_headers,
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_preview_rejects_too_many_recipients_route_guard(mcp_service_user):
    emails = [f"user{i}@example.com" for i in range(MAX_INVITE_BATCH_SIZE + 1)]
    payload = MCPInvitePreviewRequest.model_construct(
        recipient_emails=emails,
        grant_founding_status=True,
        expires_in_days=14,
        message_note=None,
    )

    with pytest.raises(HTTPException) as exc:
        await preview_invites(payload=payload, current_user=mcp_service_user, db=None)
    assert exc.value.status_code == 400


def test_send_invites_flow_and_audit(
    client: TestClient,
    mcp_service_headers,
    mcp_service_user,
    test_instructor,
    db,
    dummy_redis,
    monkeypatch,
    mock_founding_cap,
):
    mock_founding_cap.return_value = 10
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
        headers=mcp_service_headers,
    )
    assert preview.status_code == 200
    token = preview.json()["data"]["confirm_token"]

    headers = {**mcp_service_headers, "Idempotency-Key": "idem-123"}
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
    assert log.actor_id == mcp_service_user.id
    assert "recipient_emails" not in (log.after or {})


def test_send_invites_idempotent(
    client: TestClient,
    mcp_service_headers,
    test_instructor,
    dummy_redis,
    monkeypatch,
    mock_founding_cap,
):
    mock_founding_cap.return_value = 10
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
        headers=mcp_service_headers,
    )
    token = preview.json()["data"]["confirm_token"]

    headers = {**mcp_service_headers, "Idempotency-Key": "idem-dup"}
    payload = {"confirm_token": token, "idempotency_key": "idem-dup"}

    first = client.post("/api/v1/admin/mcp/invites/send", json=payload, headers=headers)
    second = client.post("/api/v1/admin/mcp/invites/send", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert counter["calls"] == 2


def test_send_rejects_missing_idempotency_key(
    client: TestClient, mcp_service_headers, test_instructor, dummy_redis
):
    preview = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=mcp_service_headers,
    )
    token = preview.json()["data"]["confirm_token"]
    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-missing"},
        headers=mcp_service_headers,
    )
    assert res.status_code == 400


def test_send_rejects_expired_token(
    client: TestClient, mcp_service_headers, mcp_service_user, db, dummy_redis, monkeypatch
):
    monkeypatch.setattr(MCPConfirmTokenService, "TOKEN_EXPIRY_MINUTES", -1)
    service = MCPConfirmTokenService(db)
    payload = {
        "recipient_emails": ["expired@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": None,
    }
    token, _ = service.generate_token(payload, actor_id=mcp_service_user.id)

    headers = {**mcp_service_headers, "Idempotency-Key": "idem-exp"}
    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-exp"},
        headers=headers,
    )
    assert res.status_code == 400


def test_send_returns_503_when_idempotency_unavailable(
    client: TestClient,
    mcp_service_headers,
    test_instructor,
    dummy_redis,
    monkeypatch,
    mock_founding_cap,
):
    mock_founding_cap.return_value = 10

    preview = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers=mcp_service_headers,
    )
    assert preview.status_code == 200
    token = preview.json()["data"]["confirm_token"]

    async def _raise(*_args, **_kwargs):
        raise ServiceException(
            "Idempotency service temporarily unavailable",
            code="idempotency_unavailable",
        )

    monkeypatch.setattr(MCPIdempotencyService, "check_and_store", _raise)

    res = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "idem-unavailable"},
        headers={**mcp_service_headers, "Idempotency-Key": "idem-unavailable"},
    )
    assert res.status_code == 503


def test_invites_reject_invalid_token(
    client: TestClient, mcp_service_headers, test_instructor, dummy_redis
):
    res = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json=_preview_payload(test_instructor),
        headers={"Authorization": "Bearer invalid"},
    )
    assert res.status_code == 401


def test_send_rejects_if_founding_cap_exceeded_since_preview(
    client: TestClient, mcp_service_headers, mock_founding_cap, test_instructor, dummy_redis
):
    mock_founding_cap.return_value = 10
    preview_resp = client.post(
        "/api/v1/admin/mcp/invites/preview",
        json={
            "recipient_emails": ["a@example.com", "b@example.com"],
            "grant_founding_status": True,
        },
        headers=mcp_service_headers,
    )
    assert preview_resp.status_code == 200
    token = preview_resp.json()["data"]["confirm_token"]

    mock_founding_cap.return_value = 0

    send_resp = client.post(
        "/api/v1/admin/mcp/invites/send",
        json={"confirm_token": token, "idempotency_key": "test-key-123"},
        headers={**mcp_service_headers, "Idempotency-Key": "test-key-123"},
    )
    assert send_resp.status_code == 409
    assert "cap exceeded" in send_resp.json()["detail"].lower()
