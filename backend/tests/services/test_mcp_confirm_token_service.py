from datetime import datetime, timezone

from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.core.exceptions import MCPTokenError
from app.services.mcp_confirm_token_service import MCPConfirmTokenService


@pytest.fixture
def confirm_service(db, monkeypatch):
    monkeypatch.setattr(settings, "mcp_token_secret", SecretStr("test-mcp-secret"))
    return MCPConfirmTokenService(db)


def _payload() -> dict:
    return {
        "recipient_emails": ["prospect@example.com"],
        "grant_founding_status": True,
        "expires_in_days": 14,
        "message_note": None,
    }


def test_generate_token_format(confirm_service):
    token, expires_at = confirm_service.generate_token(_payload(), actor_id="user_123")
    assert isinstance(token, str)
    assert token
    assert expires_at.tzinfo is not None
    assert expires_at > datetime.now(timezone.utc)


def test_validate_token_success(confirm_service):
    payload = _payload()
    token, _ = confirm_service.generate_token(payload, actor_id="user_123")
    assert confirm_service.validate_token(token, payload, actor_id="user_123") is True


def test_validate_token_expired(db, monkeypatch):
    monkeypatch.setattr(settings, "mcp_token_secret", SecretStr("test-mcp-secret"))
    monkeypatch.setattr(MCPConfirmTokenService, "TOKEN_EXPIRY_MINUTES", -1)
    service = MCPConfirmTokenService(db)
    payload = _payload()
    token, _ = service.generate_token(payload, actor_id="user_123")
    with pytest.raises(MCPTokenError) as exc:
        service.validate_token(token, payload, actor_id="user_123")
    assert exc.value.reason == "expired"


def test_validate_token_wrong_payload(confirm_service):
    payload = _payload()
    token, _ = confirm_service.generate_token(payload, actor_id="user_123")
    wrong_payload = {**payload, "expires_in_days": 7}
    with pytest.raises(MCPTokenError) as exc:
        confirm_service.validate_token(token, wrong_payload, actor_id="user_123")
    assert exc.value.reason == "payload_mismatch"


def test_validate_token_wrong_actor(confirm_service):
    payload = _payload()
    token, _ = confirm_service.generate_token(payload, actor_id="user_123")
    with pytest.raises(MCPTokenError) as exc:
        confirm_service.validate_token(token, payload, actor_id="user_456")
    assert exc.value.reason == "actor_mismatch"


def test_validate_token_tampered_signature(confirm_service):
    payload = _payload()
    token, _ = confirm_service.generate_token(payload, actor_id="user_123")
    token_data = confirm_service.decode_token(token)
    token_data["signature"] = "bad"
    tampered = MCPConfirmTokenService._b64encode(token_data)
    with pytest.raises(MCPTokenError) as exc:
        confirm_service.validate_token(tampered, payload, actor_id="user_123")
    assert exc.value.reason == "invalid_signature"
