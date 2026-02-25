"""
Coverage tests for app/dependencies/mcp_auth.py — targeting uncovered lines:
  L66-70: service account not found after static token match
  L166: _mcp_resource_id edge cases (no digits, short parts, etc.)

Also covers:
  - audit_mcp_request generator behavior
  - _mcp_action_from_path various paths
  - _mcp_resource_id various paths

Bug hunts:
  - Empty token
  - Wrong service account
  - Malformed header
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import SecretStr
import pytest
from starlette.requests import Request

from app.dependencies.mcp_auth import (
    _mcp_action_from_path,
    _mcp_resource_id,
    audit_mcp_request,
    get_mcp_principal,
    require_mcp_scope,
)
from app.principal import ServicePrincipal, UserPrincipal


def _request_with_auth(auth_header: str | None, path: str = "/api/v1/admin/mcp/founding/funnel") -> Request:
    headers = []
    if auth_header is not None:
        headers.append((b"authorization", auth_header.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
    }
    return Request(scope)


# ──────────────────────────────────────────────────────────────
# get_mcp_principal edge cases
# ──────────────────────────────────────────────────────────────

class TestGetMcpPrincipal:
    @pytest.mark.asyncio
    async def test_missing_bearer_prefix(self, monkeypatch):
        """Non-Bearer auth header → 401."""
        monkeypatch.setattr(
            "app.dependencies.mcp_auth.settings",
            SimpleNamespace(mcp_service_token=SecretStr("svc")),
        )
        with pytest.raises(HTTPException) as exc:
            await get_mcp_principal(_request_with_auth("Basic dXNlcjpwYXNz"), db=object())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_service_account_not_found(self, monkeypatch):
        """L66-70: static token matches but service account user is missing → 500."""
        async def _verify(_token: str):
            return None

        class DummyRepo:
            def __init__(self, _db):
                pass
            def get_by_email(self, _email):
                return None  # Service account not found

        monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
        monkeypatch.setattr("app.dependencies.mcp_auth.UserRepository", DummyRepo)
        monkeypatch.setattr(
            "app.dependencies.mcp_auth.settings",
            SimpleNamespace(
                mcp_service_token=SecretStr("valid_token"),
                mcp_service_account_email="missing@example.com",
            ),
        )

        with pytest.raises(HTTPException) as exc:
            await get_mcp_principal(_request_with_auth("Bearer valid_token"), db=object())
        assert exc.value.status_code == 500
        assert "Service configuration error" in exc.value.detail

    @pytest.mark.asyncio
    async def test_m2m_token_empty_scope(self, monkeypatch):
        """M2M token with empty scope → empty tuple."""
        from app.m2m_auth import M2MTokenClaims

        claims = M2MTokenClaims(
            sub="client_01ABC",
            iss="https://api.workos.com",
            aud="https://api.instainstru.com",
            exp=9999999999,
            iat=1234567890,
            scope="",
        )

        async def _verify(_token: str):
            return claims

        monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
        monkeypatch.setattr(
            "app.dependencies.mcp_auth.settings",
            SimpleNamespace(mcp_service_token=SecretStr("svc")),
        )

        principal = await get_mcp_principal(_request_with_auth("Bearer jwt_token"), db=object())
        assert isinstance(principal, ServicePrincipal)
        assert principal.scopes == ()

    @pytest.mark.asyncio
    async def test_token_mismatch_falls_through(self, monkeypatch):
        """Static token doesn't match → 401."""
        async def _verify(_token: str):
            return None

        monkeypatch.setattr("app.dependencies.mcp_auth.verify_m2m_token", _verify)
        monkeypatch.setattr(
            "app.dependencies.mcp_auth.settings",
            SimpleNamespace(
                mcp_service_token=SecretStr("expected"),
                mcp_service_account_email="svc@example.com",
            ),
        )

        with pytest.raises(HTTPException) as exc:
            await get_mcp_principal(_request_with_auth("Bearer wrong_token"), db=object())
        assert exc.value.status_code == 401


# ──────────────────────────────────────────────────────────────
# require_mcp_scope
# ──────────────────────────────────────────────────────────────

class TestRequireMcpScope:
    @pytest.mark.asyncio
    async def test_user_principal_always_passes(self):
        """UserPrincipal has no scopes → scope check is skipped."""
        principal = UserPrincipal(user_id="user_01ABC", email="test@example.com")
        checker = require_mcp_scope("mcp:admin")
        result = await checker(principal=principal)
        assert result is principal

    @pytest.mark.asyncio
    async def test_service_principal_sufficient_scope(self):
        principal = ServicePrincipal(client_id="c1", org_id="o1", scopes=("mcp:read", "mcp:write"))
        checker = require_mcp_scope("mcp:read")
        result = await checker(principal=principal)
        assert result is principal

    @pytest.mark.asyncio
    async def test_service_principal_insufficient_scope(self):
        principal = ServicePrincipal(client_id="c1", org_id="o1", scopes=("mcp:read",))
        checker = require_mcp_scope("mcp:admin")
        with pytest.raises(HTTPException) as exc:
            await checker(principal=principal)
        assert exc.value.status_code == 403


# ──────────────────────────────────────────────────────────────
# _mcp_action_from_path
# ──────────────────────────────────────────────────────────────

class TestMcpActionFromPath:
    def test_exact_prefix(self):
        assert _mcp_action_from_path("/api/v1/admin/mcp") == "mcp.root"

    def test_subpath(self):
        assert _mcp_action_from_path("/api/v1/admin/mcp/booking/detail") == "mcp.booking.detail"

    def test_non_mcp_path(self):
        """L166: path not under /api/v1/admin/mcp → mcp.unknown."""
        assert _mcp_action_from_path("/api/v1/users/profile") == "mcp.unknown"

    def test_trailing_slash(self):
        assert _mcp_action_from_path("/api/v1/admin/mcp/") == "mcp.root"


# ──────────────────────────────────────────────────────────────
# _mcp_resource_id
# ──────────────────────────────────────────────────────────────

class TestMcpResourceId:
    def test_non_mcp_path(self):
        """L166: non-MCP path → None."""
        assert _mcp_resource_id("/api/v1/users/profile") is None

    def test_no_parts(self):
        """Empty suffix → None."""
        assert _mcp_resource_id("/api/v1/admin/mcp") is None

    def test_digit_last_part(self):
        """Last part is all digits → returned as resource ID."""
        assert _mcp_resource_id("/api/v1/admin/mcp/booking/12345") == "12345"

    def test_ulid_last_part(self):
        """Last part is ULID-like (>= 6 chars with digits) → returned."""
        assert _mcp_resource_id("/api/v1/admin/mcp/user/01K2GY3VEVJWKZDV") == "01K2GY3VEVJWKZDV"

    def test_short_non_digit_part(self):
        """Short part without digits → None."""
        assert _mcp_resource_id("/api/v1/admin/mcp/list") is None

    def test_long_alpha_only_part(self):
        """Long part with no digits → None."""
        assert _mcp_resource_id("/api/v1/admin/mcp/bookings") is None

    def test_trailing_slash_mcp(self):
        assert _mcp_resource_id("/api/v1/admin/mcp/") is None


# ──────────────────────────────────────────────────────────────
# audit_mcp_request
# ──────────────────────────────────────────────────────────────

class TestAuditMcpRequest:
    @pytest.mark.asyncio
    async def test_audit_success(self):
        """Normal flow — no exception."""
        request = _request_with_auth("Bearer token", path="/api/v1/admin/mcp/test")
        principal = UserPrincipal(user_id="user_01ABC", email="test@example.com")

        with patch("app.dependencies.mcp_auth.get_db_session") as mock_session_ctx:
            mock_db = MagicMock()
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            gen = audit_mcp_request(request=request, principal=principal)
            await gen.__anext__()
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

    @pytest.mark.asyncio
    async def test_audit_with_exception(self):
        """Exception flow — audit records failure."""
        request = _request_with_auth("Bearer token", path="/api/v1/admin/mcp/test")
        principal = UserPrincipal(user_id="user_01ABC", email="test@example.com")

        with patch("app.dependencies.mcp_auth.get_db_session") as mock_session_ctx:
            mock_db = MagicMock()
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            gen = audit_mcp_request(request=request, principal=principal)
            await gen.__anext__()
            with pytest.raises(RuntimeError):
                await gen.athrow(RuntimeError("test error"))
