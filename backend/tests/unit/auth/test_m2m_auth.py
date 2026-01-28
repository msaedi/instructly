"""Tests for M2M authentication."""

from types import SimpleNamespace

import jwt
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

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, monkeypatch):
        async def _get_key(_token: str):
            return {"kid": "test-key"}

        def _from_jwk(_payload: str):
            return object()

        def _decode(*_args, **_kwargs):
            raise jwt.ExpiredSignatureError()

        monkeypatch.setattr("app.m2m_auth._jwks_cache.get_signing_key", _get_key)
        monkeypatch.setattr("app.m2m_auth.RSAAlgorithm.from_jwk", _from_jwk)
        monkeypatch.setattr("app.m2m_auth.jwt.decode", _decode)
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url="https://workos.test/jwks",
                workos_m2m_audience="https://api.instainstru.com",
                workos_issuer="https://api.workos.com",
            ),
        )

        result = await verify_m2m_token("expired-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_wrong_audience(self, monkeypatch):
        async def _get_key(_token: str):
            return {"kid": "test-key"}

        def _from_jwk(_payload: str):
            return object()

        def _decode(*_args, **_kwargs):
            raise jwt.InvalidAudienceError()

        monkeypatch.setattr("app.m2m_auth._jwks_cache.get_signing_key", _get_key)
        monkeypatch.setattr("app.m2m_auth.RSAAlgorithm.from_jwk", _from_jwk)
        monkeypatch.setattr("app.m2m_auth.jwt.decode", _decode)
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url="https://workos.test/jwks",
                workos_m2m_audience="https://api.instainstru.com",
                workos_issuer="https://api.workos.com",
            ),
        )

        result = await verify_m2m_token("wrong-aud-token")
        assert result is None
