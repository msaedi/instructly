"""Tests for M2M authentication."""

import pytest

from app.m2m_auth import M2MTokenClaims, has_scope, verify_m2m_token


class TestM2MAuth:
    def test_has_scope_single(self):
        claims = M2MTokenClaims(
            sub="client_01ABC",
            iss="https://api.workos.com",
            aud="https://api.instainstru.com",
            exp=9999999999,
            iat=1234567890,
            scope="mcp:read mcp:write",
        )
        assert has_scope(claims, "mcp:read")
        assert has_scope(claims, "mcp:write")
        assert not has_scope(claims, "admin:delete")

    def test_has_scope_empty(self):
        claims = M2MTokenClaims(
            sub="client_01ABC",
            iss="https://api.workos.com",
            aud="https://api.instainstru.com",
            exp=9999999999,
            iat=1234567890,
            scope="",
        )
        assert not has_scope(claims, "mcp:read")

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self):
        result = await verify_m2m_token("invalid-token")
        assert result is None
