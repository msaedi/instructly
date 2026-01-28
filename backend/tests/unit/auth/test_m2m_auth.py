"""Tests for M2M authentication."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.m2m_auth import JWKSCache, M2MTokenClaims, has_scope, verify_m2m_token


class TestJWKSCache:
    """Tests for JWKSCache class."""

    @pytest.fixture
    def cache(self):
        """Create a fresh JWKSCache instance."""
        return JWKSCache()

    def test_should_refresh_no_keys(self, cache):
        """Test _should_refresh returns True when no keys cached."""
        assert cache._should_refresh() is True

    def test_should_refresh_no_fetched_at(self, cache):
        """Test _should_refresh returns True when fetched_at is None."""
        cache._keys = {"kid1": {}}
        cache._fetched_at = None
        assert cache._should_refresh() is True

    def test_should_refresh_expired(self, cache):
        """Test _should_refresh returns True when TTL expired."""
        cache._keys = {"kid1": {}}
        cache._fetched_at = datetime.now(timezone.utc) - timedelta(hours=2)
        assert cache._should_refresh() is True

    def test_should_refresh_valid(self, cache):
        """Test _should_refresh returns False when within TTL."""
        cache._keys = {"kid1": {}}
        cache._fetched_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert cache._should_refresh() is False

    @pytest.mark.asyncio
    async def test_get_signing_key_no_jwks_url(self, cache, monkeypatch):
        """Test get_signing_key raises when JWKS URL not configured."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url=None),
        )
        with pytest.raises(ValueError, match="WorkOS JWKS URL not configured"):
            await cache.get_signing_key("some-token")

    @pytest.mark.asyncio
    async def test_get_signing_key_no_kid_in_header(self, cache, monkeypatch):
        """Test get_signing_key raises when token has no kid."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url="https://workos.test/jwks"),
        )
        monkeypatch.setattr(
            "app.m2m_auth.jwt.get_unverified_header",
            lambda _: {"alg": "RS256"},  # No kid
        )
        with pytest.raises(ValueError, match="Missing kid in token header"):
            await cache.get_signing_key("some-token")

    @pytest.mark.asyncio
    async def test_get_signing_key_unknown_kid(self, cache, monkeypatch):
        """Test get_signing_key raises for unknown key id."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url="https://workos.test/jwks"),
        )
        monkeypatch.setattr(
            "app.m2m_auth.jwt.get_unverified_header",
            lambda _: {"kid": "unknown-kid", "alg": "RS256"},
        )

        # Mock _fetch_jwks to set keys without the requested kid
        async def mock_fetch():
            cache._keys = {"other-kid": {"kid": "other-kid"}}
            cache._fetched_at = datetime.now(timezone.utc)

        cache._fetch_jwks = mock_fetch

        with pytest.raises(ValueError, match="Unknown signing key: unknown-kid"):
            await cache.get_signing_key("some-token")

    @pytest.mark.asyncio
    async def test_get_signing_key_success(self, cache, monkeypatch):
        """Test get_signing_key returns key when found."""
        expected_key = {"kid": "test-kid", "kty": "RSA", "n": "abc", "e": "AQAB"}
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url="https://workos.test/jwks"),
        )
        monkeypatch.setattr(
            "app.m2m_auth.jwt.get_unverified_header",
            lambda _: {"kid": "test-kid", "alg": "RS256"},
        )
        cache._keys = {"test-kid": expected_key}
        cache._fetched_at = datetime.now(timezone.utc)

        result = await cache.get_signing_key("some-token")
        assert result == expected_key

    @pytest.mark.asyncio
    async def test_fetch_jwks_success(self, cache, monkeypatch):
        """Test _fetch_jwks fetches and caches keys."""
        jwks_response = {
            "keys": [
                {"kid": "key1", "kty": "RSA"},
                {"kid": "key2", "kty": "RSA"},
                {"kty": "RSA"},  # Missing kid, should be skipped
            ]
        }
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url="https://workos.test/jwks"),
        )

        mock_response = MagicMock()
        mock_response.json.return_value = jwks_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await cache._fetch_jwks()

        assert cache._keys == {"key1": {"kid": "key1", "kty": "RSA"}, "key2": {"kid": "key2", "kty": "RSA"}}
        assert cache._fetched_at is not None

    @pytest.mark.asyncio
    async def test_fetch_jwks_skips_if_valid(self, cache, monkeypatch):
        """Test _fetch_jwks skips fetch if cache is valid."""
        cache._keys = {"existing": {"kid": "existing"}}
        cache._fetched_at = datetime.now(timezone.utc)
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url="https://workos.test/jwks"),
        )

        with patch("httpx.AsyncClient") as mock_client:
            await cache._fetch_jwks()
            # Should not have made any HTTP calls
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_jwks_no_url_configured(self, cache, monkeypatch):
        """Test _fetch_jwks raises when URL not configured."""
        cache._keys = None  # Force refresh
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(workos_jwks_url=None),
        )

        with pytest.raises(ValueError, match="WorkOS JWKS URL not configured"):
            await cache._fetch_jwks()


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

    @pytest.mark.asyncio
    async def test_verify_empty_token(self):
        """Test verify_m2m_token returns None for empty token."""
        result = await verify_m2m_token("")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_missing_settings(self, monkeypatch):
        """Test verify_m2m_token returns None when settings not configured."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url=None,
                workos_m2m_audience=None,
                workos_issuer=None,
            ),
        )
        result = await verify_m2m_token("some-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_missing_audience(self, monkeypatch):
        """Test verify_m2m_token returns None when audience not configured."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url="https://workos.test/jwks",
                workos_m2m_audience=None,
                workos_issuer="https://api.workos.com",
            ),
        )
        result = await verify_m2m_token("some-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_missing_issuer(self, monkeypatch):
        """Test verify_m2m_token returns None when issuer not configured."""
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url="https://workos.test/jwks",
                workos_m2m_audience="https://api.instainstru.com",
                workos_issuer=None,
            ),
        )
        result = await verify_m2m_token("some-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_success(self, monkeypatch):
        """Test verify_m2m_token returns claims on success."""
        async def _get_key(_token: str):
            return {"kid": "test-key", "kty": "RSA"}

        def _from_jwk(_payload: str):
            return MagicMock()

        expected_payload = {
            "sub": "client_01ABC",
            "iss": "https://api.workos.com",
            "aud": "https://api.instainstru.com",
            "exp": 9999999999,
            "iat": 1234567890,
            "scope": "mcp:read",
        }

        def _decode(*_args, **_kwargs):
            return expected_payload

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

        result = await verify_m2m_token("valid-token")
        assert result is not None
        assert result.sub == "client_01ABC"
        assert result.scope == "mcp:read"

    @pytest.mark.asyncio
    async def test_verify_generic_exception(self, monkeypatch):
        """Test verify_m2m_token returns None on generic exception."""
        async def _get_key(_token: str):
            raise Exception("Unexpected error")

        monkeypatch.setattr("app.m2m_auth._jwks_cache.get_signing_key", _get_key)
        monkeypatch.setattr(
            "app.m2m_auth.settings",
            SimpleNamespace(
                workos_jwks_url="https://workos.test/jwks",
                workos_m2m_audience="https://api.instainstru.com",
                workos_issuer="https://api.workos.com",
            ),
        )

        result = await verify_m2m_token("some-token")
        assert result is None
