from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import SecretStr
import pytest
from starlette.requests import Request

from app.dependencies.mcp_auth import get_mcp_principal, require_mcp_scope
from app.m2m_auth import M2MTokenClaims
from app.principal import ServicePrincipal, UserPrincipal


def _request_with_auth(auth_header: str | None) -> Request:
    headers = []
    if auth_header is not None:
        headers.append((b"authorization", auth_header.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/mcp/founding/funnel",
        "headers": headers,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_missing_auth_header(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.mcp_auth.settings",
        SimpleNamespace(mcp_service_token=SecretStr("svc")),
    )
    with pytest.raises(HTTPException) as exc:
        await get_mcp_principal(_request_with_auth(None), db=object())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_m2m_jwt_valid(monkeypatch):
    claims = M2MTokenClaims(
        sub="client_01ABC",
        iss="https://api.workos.com",
        aud="https://api.instainstru.com",
        exp=9999999999,
        iat=1234567890,
        scope="mcp:read mcp:write",
        org_id="org_123",
    )

    async def _verify(_token: str):
        return claims

    monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
    monkeypatch.setattr(
        "app.dependencies.mcp_auth.settings",
        SimpleNamespace(mcp_service_token=SecretStr("svc")),
    )

    principal = await get_mcp_principal(_request_with_auth("Bearer token"), db=object())
    assert principal.id == "client_01ABC"
    assert principal.principal_type == "service"
    assert principal.scopes == ("mcp:read", "mcp:write")


@pytest.mark.asyncio
async def test_static_token_fallback(monkeypatch):
    async def _verify(_token: str):
        return None

    class DummyUser:
        id = "user_123"
        email = "service@example.com"

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_email(self, _email):
            return DummyUser()

    monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
    monkeypatch.setattr("app.dependencies.mcp_auth.UserRepository", DummyRepo)
    monkeypatch.setattr(
        "app.dependencies.mcp_auth.settings",
        SimpleNamespace(
            mcp_service_token=SecretStr("svc"),
            mcp_service_account_email="svc@example.com",
        ),
    )

    principal = await get_mcp_principal(_request_with_auth("Bearer svc"), db=object())
    assert isinstance(principal, UserPrincipal)
    assert principal.id == "user_123"
    assert principal.identifier == "service@example.com"


@pytest.mark.asyncio
async def test_invalid_token(monkeypatch):
    async def _verify(_token: str):
        return None

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_email(self, _email):
            return None

    monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
    monkeypatch.setattr("app.dependencies.mcp_auth.UserRepository", DummyRepo)
    monkeypatch.setattr(
        "app.dependencies.mcp_auth.settings",
        SimpleNamespace(
            mcp_service_token=SecretStr("svc"),
            mcp_service_account_email="svc@example.com",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await get_mcp_principal(_request_with_auth("Bearer wrong"), db=object())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_scope_enforcement(monkeypatch):
    principal = ServicePrincipal(client_id="client_1", org_id="org_1", scopes=("mcp:read",))
    checker = require_mcp_scope("mcp:write")

    with pytest.raises(HTTPException) as exc:
        await checker(principal=principal)
    assert exc.value.status_code == 403
