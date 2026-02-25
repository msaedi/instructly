"""
Coverage tests for app/auth.py — targeting uncovered lines:
  L293: sub is not a string in create_refresh_token data
  L386: parse_token_iat returns None → early return
  L405: tokens_valid_after_ts is float → cast to int
  L452: request without cookies attribute
  L466: token payload sub is not a string → user_id = None
  L470-476: missing 'sub' field raises credentials exception
  L522: optional auth cookie fallback
  L537-538: optional auth missing sub → return None
  L553: optional auth non-revocation HTTPException re-raised

Bug hunts:
  - Corrupt argon2 hash (InvalidHashError)
  - Expired token handling
  - Missing claims
  - Blacklisted token
  - Refresh token with non-string sub
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
import jwt as pyjwt
import pytest
from starlette.requests import Request

from app.auth import (
    REVOCATION_DETAIL_INVALIDATED,
    REVOCATION_DETAIL_REVOKED,
    _apply_environment_claims,
    _enforce_revocation_and_user_invalidation,
    _token_claim_requirements,
    create_access_token,
    create_refresh_token,
    create_temp_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional,
    get_password_hash,
    is_access_token_payload,
    is_refresh_token_payload,
    password_needs_rehash,
    token_type,
    verify_password,
    verify_password_async,
)
from app.core.config import settings


def _make_request(path="/api/v1/test", cookies=None, headers=None):
    """Create a Starlette Request with optional cookies."""
    raw_headers = []
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode()))
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    scope = {
        "type": "http",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


# ──────────────────────────────────────────────────────────────
# Password verification edge cases
# ──────────────────────────────────────────────────────────────

class TestPasswordVerification:
    def test_verify_password_correct(self):
        hashed = get_password_hash("mypassword123")
        assert verify_password("mypassword123", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = get_password_hash("mypassword123")
        assert verify_password("wrong", hashed) is False

    def test_verify_password_invalid_hash_format(self):
        """Bug hunt: corrupt argon2 hash triggers InvalidHashError → returns False."""
        assert verify_password("anything", "not_a_valid_hash") is False

    def test_verify_password_empty_hash(self):
        """Edge case: empty string hash."""
        assert verify_password("password", "") is False

    @pytest.mark.asyncio
    async def test_verify_password_async_correct(self):
        hashed = get_password_hash("asynctest")
        result = await verify_password_async("asynctest", hashed)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_async_incorrect(self):
        hashed = get_password_hash("asynctest")
        result = await verify_password_async("wrong", hashed)
        assert result is False

    def test_password_needs_rehash_valid_hash(self):
        hashed = get_password_hash("test")
        # Should not need rehash with current settings
        assert password_needs_rehash(hashed) is False

    def test_password_needs_rehash_invalid_hash(self):
        """Edge case: broken hash returns False (not True)."""
        assert password_needs_rehash("broken") is False


# ──────────────────────────────────────────────────────────────
# Token creation and decoding
# ──────────────────────────────────────────────────────────────

class TestTokenCreation:
    def test_create_access_token_with_default_expiry(self):
        token = create_access_token({"sub": "user_01ABC"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user_01ABC"
        assert payload["typ"] == "access"
        assert "jti" in payload

    def test_create_access_token_with_custom_expiry(self):
        token = create_access_token(
            {"sub": "user_01ABC"}, expires_delta=timedelta(minutes=5)
        )
        payload = decode_access_token(token)
        assert payload["sub"] == "user_01ABC"

    def test_create_access_token_with_beta_claims(self):
        """L262: beta_claims are merged into token."""
        beta = {"beta_role": "instructor", "beta_phase": "closed"}
        token = create_access_token({"sub": "user_01ABC"}, beta_claims=beta)
        payload = decode_access_token(token)
        assert payload["beta_role"] == "instructor"

    def test_create_refresh_token_with_string_sub(self):
        """L293: sub is a string → included in token."""
        token = create_refresh_token({"sub": "user_01ABC"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user_01ABC"
        assert payload["typ"] == "refresh"

    def test_create_refresh_token_without_sub(self):
        """L293: sub not a string → omitted from token."""
        token = create_refresh_token({"other": "data"})
        payload = decode_access_token(token)
        assert "sub" not in payload
        assert payload["typ"] == "refresh"

    def test_create_refresh_token_with_int_sub(self):
        """L293: sub is int (not string) → omitted."""
        token = create_refresh_token({"sub": 12345})
        payload = decode_access_token(token)
        assert "sub" not in payload

    def test_create_refresh_token_with_custom_expiry(self):
        token = create_refresh_token(
            {"sub": "user_01ABC"}, expires_delta=timedelta(days=1)
        )
        payload = decode_access_token(token)
        assert payload["typ"] == "refresh"

    def test_create_temp_token(self):
        token = create_temp_token({"sub": "user_01ABC", "purpose": "2fa"})
        # Decode with the temp token secret
        from app.core.config import secret_or_plain
        secret_source = settings.temp_token_secret or settings.secret_key
        payload = pyjwt.decode(
            token,
            secret_or_plain(secret_source),
            algorithms=[settings.algorithm],
            audience=settings.temp_token_aud,
        )
        assert payload["sub"] == "user_01ABC"

    def test_create_temp_token_with_custom_expiry(self):
        token = create_temp_token(
            {"sub": "user_01ABC"}, expires_delta=timedelta(seconds=30)
        )
        from app.core.config import secret_or_plain
        secret_source = settings.temp_token_secret or settings.secret_key
        payload = pyjwt.decode(
            token,
            secret_or_plain(secret_source),
            algorithms=[settings.algorithm],
            audience=settings.temp_token_aud,
        )
        assert payload["sub"] == "user_01ABC"


# ──────────────────────────────────────────────────────────────
# Token type checks
# ──────────────────────────────────────────────────────────────

class TestTokenType:
    def test_token_type_access(self):
        assert token_type({"typ": "access"}) == "access"

    def test_token_type_refresh(self):
        assert token_type({"typ": "refresh"}) == "refresh"

    def test_token_type_missing(self):
        assert token_type({}) is None

    def test_token_type_non_string(self):
        assert token_type({"typ": 123}) is None

    def test_is_access_token_payload(self):
        assert is_access_token_payload({"typ": "access"}) is True
        assert is_access_token_payload({"typ": "refresh"}) is False

    def test_is_refresh_token_payload(self):
        assert is_refresh_token_payload({"typ": "refresh"}) is True
        assert is_refresh_token_payload({"typ": "access"}) is False


# ──────────────────────────────────────────────────────────────
# Token decode edge cases
# ──────────────────────────────────────────────────────────────

class TestDecodeAccessToken:
    def test_decode_valid_token(self):
        token = create_access_token({"sub": "user_01ABC"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user_01ABC"

    def test_decode_expired_token(self):
        """Bug hunt: expired token raises PyJWTError."""
        token = create_access_token(
            {"sub": "user_01ABC"}, expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_decode_tampered_token(self):
        """Bug hunt: tampered signature."""
        token = create_access_token({"sub": "user_01ABC"})
        # Tamper the signature portion more aggressively
        parts = token.split(".")
        assert len(parts) == 3
        # Reverse the signature to ensure it's invalid
        sig = parts[2]
        tampered_sig = sig[::-1] if sig != sig[::-1] else sig[1:] + "X"
        tampered = f"{parts[0]}.{parts[1]}.{tampered_sig}"
        with pytest.raises(Exception):
            decode_access_token(tampered)

    def test_decode_with_enforce_audience_false(self):
        """L174: explicit enforce_audience=False bypasses audience check."""
        token = create_access_token({"sub": "user_01ABC"})
        payload = decode_access_token(token, enforce_audience=False)
        assert payload["sub"] == "user_01ABC"


# ──────────────────────────────────────────────────────────────
# Environment claims
# ──────────────────────────────────────────────────────────────

class TestEnvironmentClaims:
    def test_apply_environment_claims_preview(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "preview")
        data = {}
        _apply_environment_claims(data)
        assert data.get("aud") == "preview"
        assert "preview" in (data.get("iss") or "")

    def test_apply_environment_claims_prod(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "prod")
        data = {}
        _apply_environment_claims(data)
        assert data.get("aud") == "prod"

    def test_apply_environment_claims_local(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "local")
        data = {}
        _apply_environment_claims(data)
        # Local mode adds no claims
        assert "aud" not in data
        assert "iss" not in data

    def test_token_claim_requirements_testing(self, monkeypatch):
        """In testing mode, enforcement is off."""
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setattr(settings, "is_testing", True, raising=False)
        enforce, aud, iss = _token_claim_requirements()
        assert enforce is False


# ──────────────────────────────────────────────────────────────
# Revocation enforcement
# ──────────────────────────────────────────────────────────────

class TestRevocationEnforcement:
    @pytest.mark.asyncio
    async def test_missing_jti_raises(self):
        """Token without jti → REVOCATION_DETAIL_FORMAT_OUTDATED."""
        payload = {"sub": "user_01ABC", "typ": "access"}
        with pytest.raises(HTTPException) as exc:
            await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")
        assert exc.value.status_code == 401
        assert "format outdated" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_revoked_jti_raises(self):
        """Blacklisted jti → REVOCATION_DETAIL_REVOKED."""
        payload = {"sub": "user_01ABC", "typ": "access", "jti": "revoked_jti_001", "iat": 1000000}
        with patch(
            "app.auth.TokenBlacklistService"
        ) as MockBlacklist:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(return_value=True)
            with pytest.raises(HTTPException) as exc:
                await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")
            assert exc.value.detail == REVOCATION_DETAIL_REVOKED

    @pytest.mark.asyncio
    async def test_blacklist_check_failure_fails_closed(self):
        """Bug hunt: blacklist service exception → token treated as revoked (fail-closed)."""
        payload = {"sub": "user_01ABC", "jti": "jti_001", "iat": 1000000}
        with patch("app.auth.TokenBlacklistService") as MockBlacklist:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(side_effect=RuntimeError("Redis down"))
            with pytest.raises(HTTPException) as exc:
                await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")
            assert exc.value.detail == REVOCATION_DETAIL_REVOKED

    @pytest.mark.asyncio
    async def test_iat_none_returns_early(self):
        """L386: parse_token_iat returns None → skip tokens_valid_after check."""
        payload = {"sub": "user_01ABC", "jti": "jti_002"}  # No 'iat' key
        with patch("app.auth.TokenBlacklistService") as MockBlacklist:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(return_value=False)
            # Should not raise
            await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")

    @pytest.mark.asyncio
    async def test_user_lookup_none_skips_check(self):
        """L389: user lookup returns None → skip tokens_valid_after (fail-open)."""
        payload = {"sub": "user_01ABC", "jti": "jti_003", "iat": 1000000}
        with patch("app.auth.TokenBlacklistService") as MockBlacklist, \
             patch("app.auth.lookup_user_by_id_nonblocking", new_callable=AsyncMock) as mock_lookup:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(return_value=False)
            mock_lookup.return_value = None
            # Should not raise (fail-open)
            await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")

    @pytest.mark.asyncio
    async def test_tokens_valid_after_float_cast_to_int(self):
        """L405: tokens_valid_after_ts is float → cast to int."""
        payload = {"sub": "user_01ABC", "jti": "jti_004", "iat": 500}
        user_data = {"tokens_valid_after_ts": 1000.5}
        with patch("app.auth.TokenBlacklistService") as MockBlacklist, \
             patch("app.auth.lookup_user_by_id_nonblocking", new_callable=AsyncMock) as mock_lookup:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(return_value=False)
            mock_lookup.return_value = user_data
            with pytest.raises(HTTPException) as exc:
                await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")
            assert exc.value.detail == REVOCATION_DETAIL_INVALIDATED

    @pytest.mark.asyncio
    async def test_tokens_valid_after_int_not_exceeded(self):
        """Token iat >= tokens_valid_after → no exception."""
        payload = {"sub": "user_01ABC", "jti": "jti_005", "iat": 2000}
        user_data = {"tokens_valid_after_ts": 1000}
        with patch("app.auth.TokenBlacklistService") as MockBlacklist, \
             patch("app.auth.lookup_user_by_id_nonblocking", new_callable=AsyncMock) as mock_lookup:
            instance = MockBlacklist.return_value
            instance.is_revoked = AsyncMock(return_value=False)
            mock_lookup.return_value = user_data
            await _enforce_revocation_and_user_invalidation(payload, "user_01ABC")


# ──────────────────────────────────────────────────────────────
# get_current_user
# ──────────────────────────────────────────────────────────────

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_token_raises_not_authenticated(self):
        """L461: no token and no cookie → 401."""
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, token=None)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Not authenticated"

    @pytest.mark.asyncio
    async def test_request_without_cookies_attr(self, monkeypatch):
        """L452: hasattr(request, 'cookies') is False → skip cookie."""
        monkeypatch.setenv("SITE_MODE", "local")

        class NoCookiesRequest:
            pass

        req = NoCookiesRequest()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req, token=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_sub_not_string_raises_credentials_error(self):
        """L466,L470-476: sub is not a string → raises credentials exception."""
        token = create_access_token({"sub": "user_01ABC"})
        # Decode and re-encode with non-string sub
        from app.core.config import secret_or_plain
        payload = pyjwt.decode(
            token,
            secret_or_plain(settings.secret_key),
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
        payload["sub"] = 12345  # non-string sub
        bad_token = pyjwt.encode(
            payload,
            secret_or_plain(settings.secret_key),
            algorithm=settings.algorithm,
        )
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, token=bad_token)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rejected_on_access_path(self):
        """Bug hunt: refresh token used on access endpoint → rejected."""
        token = create_refresh_token({"sub": "user_01ABC"})
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, token=token)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_cookie_fallback_when_no_bearer(self, monkeypatch):
        """L452-458: cookie-based auth when no Authorization header."""
        monkeypatch.setenv("SITE_MODE", "local")
        token = create_access_token({"sub": "user_01ABC"})
        request = _make_request(cookies={"access_token": token})

        with patch("app.auth._enforce_revocation_and_user_invalidation", new_callable=AsyncMock):
            user_id = await get_current_user(request, token=None)
        assert user_id == "user_01ABC"

    @pytest.mark.asyncio
    async def test_jwt_error_returns_invalid_credentials(self):
        """PyJWTError → 401 Could not validate credentials."""
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, token="completely_invalid_token")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Could not validate credentials"


# ──────────────────────────────────────────────────────────────
# get_current_user_optional
# ──────────────────────────────────────────────────────────────

class TestGetCurrentUserOptional:
    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        """L529: no token → returns None."""
        request = _make_request()
        result = await get_current_user_optional(request, token=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_id(self):
        """Happy path."""
        token = create_access_token({"sub": "user_01ABC"})
        request = _make_request()
        with patch("app.auth._enforce_revocation_and_user_invalidation", new_callable=AsyncMock):
            result = await get_current_user_optional(request, token=token)
        assert result == "user_01ABC"

    @pytest.mark.asyncio
    async def test_sub_missing_returns_none(self):
        """L537-538: payload missing sub → returns None."""
        from app.core.config import secret_or_plain
        # Create token without sub
        payload = {
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "jti": "test_jti",
            "typ": "access",
        }
        token = pyjwt.encode(
            payload,
            secret_or_plain(settings.secret_key),
            algorithm=settings.algorithm,
        )
        request = _make_request()
        result = await get_current_user_optional(request, token=token)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_access_token_returns_none(self):
        """Refresh token on optional auth → returns None."""
        token = create_refresh_token({"sub": "user_01ABC"})
        request = _make_request()
        result = await get_current_user_optional(request, token=token)
        assert result is None

    @pytest.mark.asyncio
    async def test_revocation_detail_suppressed(self):
        """L553: revocation HTTPException → suppressed, returns None."""
        token = create_access_token({"sub": "user_01ABC"})
        request = _make_request()
        with patch(
            "app.auth._enforce_revocation_and_user_invalidation",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401, detail=REVOCATION_DETAIL_REVOKED),
        ):
            result = await get_current_user_optional(request, token=token)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_revocation_http_exception_re_raised(self):
        """L553: non-revocation HTTPException → re-raised."""
        token = create_access_token({"sub": "user_01ABC"})
        request = _make_request()
        with patch(
            "app.auth._enforce_revocation_and_user_invalidation",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=403, detail="Forbidden"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_current_user_optional(request, token=token)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_jwt_error_returns_none(self):
        """PyJWTError → None (not raised)."""
        request = _make_request()
        result = await get_current_user_optional(request, token="bad_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_cookie_fallback_optional(self, monkeypatch):
        """L522: optional auth falls back to cookie."""
        monkeypatch.setenv("SITE_MODE", "local")
        token = create_access_token({"sub": "user_01ABC"})
        request = _make_request(cookies={"access_token": token})

        with patch("app.auth._enforce_revocation_and_user_invalidation", new_callable=AsyncMock):
            result = await get_current_user_optional(request, token=None)
        assert result == "user_01ABC"
