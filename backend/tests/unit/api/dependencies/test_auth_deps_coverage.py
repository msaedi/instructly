"""
Coverage tests for app/api/dependencies/auth.py — targeting uncovered lines:
  L94-95: _extract_hostname exception path (returns empty string)
  L154: staff preview token validation via hmac
  L241-243: legacy fallback get_by_id returns None → try get_by_email
  L267: testing mode user lookup fallback email
  L307-309: audit log failure during logout (N/A — not in this file)
  L392: request.state has current_user in optional path
  L417: optional auth inactive user returns None

Bug hunts:
  - Malformed Authorization header
  - Revocation check exception (fail-closed)
  - Inactive user
  - Bearer token extraction edge cases
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest
from starlette.requests import Request

import app.api.dependencies.auth as auth_module
from app.models.user import User


def _make_request(path="/api/v1/test", headers=None, host="testserver"):
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    scope = {
        "type": "http",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "server": (host, 80),
        "scheme": "http",
    }
    return Request(scope)


def _make_user(
    email="test@example.com",
    is_active=True,
    is_staff=False,
    is_instructor=False,
    is_student=True,
    is_admin=False,
    account_status="active",
):
    user = User(
        email=email,
        hashed_password="hash",
        first_name="Test",
        last_name="User",
        zip_code="10001",
        is_active=is_active,
        account_status=account_status,
        totp_enabled=False,
        phone_verified=False,
    )
    user.is_staff = is_staff
    user._cached_is_instructor = is_instructor
    user._cached_is_student = is_student
    user._cached_is_admin = is_admin
    return user


# ──────────────────────────────────────────────────────────────
# Bearer token extraction
# ──────────────────────────────────────────────────────────────

class TestBearerTokenExtraction:
    def test_no_auth_header(self):
        assert auth_module._get_bearer_token(None) is None

    def test_empty_auth_header(self):
        assert auth_module._get_bearer_token("") is None

    def test_valid_bearer(self):
        assert auth_module._get_bearer_token("Bearer my_token_123") == "my_token_123"

    def test_wrong_scheme(self):
        """Not 'Bearer' prefix → None."""
        assert auth_module._get_bearer_token("Basic dXNlcjpwYXNz") is None

    def test_too_many_parts(self):
        """More than 2 parts → None."""
        assert auth_module._get_bearer_token("Bearer token extra") is None

    def test_bearer_with_empty_token(self):
        """'Bearer ' with whitespace-only token → None."""
        assert auth_module._get_bearer_token("Bearer   ") is None


# ──────────────────────────────────────────────────────────────
# _extract_hostname edge cases
# ──────────────────────────────────────────────────────────────

class TestExtractHostname:
    def test_simple_url(self):
        assert auth_module._extract_hostname("https://example.com") == "example.com"

    def test_url_with_port(self):
        assert auth_module._extract_hostname("https://example.com:8080/path") == "example.com"

    def test_url_without_scheme(self):
        assert auth_module._extract_hostname("example.com") == "example.com"

    def test_empty_string(self):
        """L94-95: empty string → returns empty."""
        assert auth_module._extract_hostname("") == ""


# ──────────────────────────────────────────────────────────────
# get_current_active_user
# ──────────────────────────────────────────────────────────────

class TestGetCurrentActiveUser:
    @pytest.mark.asyncio
    async def test_active_user_passes(self):
        user = _make_user(is_active=True)
        result = await auth_module.get_current_active_user(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_inactive_user_raises(self):
        user = _make_user(is_active=False)
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_current_active_user(current_user=user)
        assert exc.value.status_code == 400
        assert "Inactive" in exc.value.detail


# ──────────────────────────────────────────────────────────────
# get_current_instructor / get_current_student
# ──────────────────────────────────────────────────────────────

class TestRoleChecks:
    @pytest.mark.asyncio
    async def test_instructor_passes(self):
        user = _make_user(is_instructor=True, is_student=False)
        result = await auth_module.get_current_instructor(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_non_instructor_raises(self):
        user = _make_user(is_instructor=False)
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_current_instructor(current_user=user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_student_passes(self):
        user = _make_user(is_student=True)
        result = await auth_module.get_current_student(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_non_student_raises(self):
        user = _make_user(is_student=False)
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_current_student(current_user=user)
        assert exc.value.status_code == 403


# ──────────────────────────────────────────────────────────────
# require_admin
# ──────────────────────────────────────────────────────────────

class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_admin_passes(self):
        user = _make_user(is_admin=True)
        result = await auth_module.require_admin(user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_non_admin_raises(self):
        user = _make_user(is_admin=False)
        with pytest.raises(HTTPException) as exc:
            await auth_module.require_admin(user=user)
        assert exc.value.status_code == 403


# ──────────────────────────────────────────────────────────────
# get_current_active_user_optional
# ──────────────────────────────────────────────────────────────

class TestGetCurrentActiveUserOptional:
    @pytest.mark.asyncio
    async def test_no_user_id_returns_none(self):
        result = await auth_module.get_current_active_user_optional(
            request=None, current_user_id=None, db=MagicMock()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_request_state_has_active_user(self):
        """L392: request.state.current_user already set → returned directly."""
        user = _make_user(is_active=True)
        request = _make_request()
        request.state.current_user = user
        result = await auth_module.get_current_active_user_optional(
            request=request, current_user_id="user_01ABC", db=MagicMock()
        )
        assert result is user

    @pytest.mark.asyncio
    async def test_request_state_inactive_user_not_used(self):
        """L392: request.state.current_user is inactive → falls through to lookup."""
        user = _make_user(is_active=False)
        request = _make_request()
        request.state.current_user = user
        # In testing mode, it should look up the user from DB
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = user  # Still inactive
        original_is_testing = getattr(auth_module.settings, "is_testing", False)
        try:
            auth_module.settings.is_testing = True  # type: ignore[attr-defined]
            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                result = await auth_module.get_current_active_user_optional(
                    request=request, current_user_id="user_01ABC", db=MagicMock()
                )
        finally:
            auth_module.settings.is_testing = original_is_testing  # type: ignore[attr-defined]
        # Inactive user returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_testing_mode_user_lookup_by_email(self):
        """L417: testing mode looks up user by email."""
        user = _make_user(is_active=True)
        original = getattr(auth_module.settings, "is_testing", False)
        try:
            auth_module.settings.is_testing = True  # type: ignore[attr-defined]
            mock_repo = MagicMock()
            mock_repo.get_by_email.return_value = user
            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                result = await auth_module.get_current_active_user_optional(
                    request=None, current_user_id="test@example.com", db=MagicMock()
                )
        finally:
            auth_module.settings.is_testing = original  # type: ignore[attr-defined]
        assert result is user

    @pytest.mark.asyncio
    async def test_testing_mode_user_id_fallback_to_email(self):
        """L267: get_by_id returns None → falls back to get_by_email."""
        user = _make_user(is_active=True)
        original = getattr(auth_module.settings, "is_testing", False)
        try:
            auth_module.settings.is_testing = True  # type: ignore[attr-defined]
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            mock_repo.get_by_email.return_value = user
            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                result = await auth_module.get_current_active_user_optional(
                    request=None, current_user_id="user_01ABC", db=MagicMock()
                )
        finally:
            auth_module.settings.is_testing = original  # type: ignore[attr-defined]
        assert result is user

    @pytest.mark.asyncio
    async def test_testing_mode_user_not_found(self):
        """User not found → returns None."""
        original = getattr(auth_module.settings, "is_testing", False)
        try:
            auth_module.settings.is_testing = True  # type: ignore[attr-defined]
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            mock_repo.get_by_email.return_value = None
            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                result = await auth_module.get_current_active_user_optional(
                    request=None, current_user_id="user_01ABC", db=MagicMock()
                )
        finally:
            auth_module.settings.is_testing = original  # type: ignore[attr-defined]
        assert result is None


# ──────────────────────────────────────────────────────────────
# _testing_bypass
# ──────────────────────────────────────────────────────────────

def _setattr_settings(key, value, monkeypatch):
    """Helper to set an attribute on Settings using monkeypatch + object.__setattr__."""
    monkeypatch.setattr(auth_module, "settings", auth_module.settings, raising=False)
    object.__setattr__(auth_module.settings, key, value)


class TestTestingBypass:
    def test_testing_bypass_active_in_testing(self):
        """is_testing is already True in test environment."""
        request = _make_request()
        assert auth_module._testing_bypass(request) is True

    def test_testing_bypass_override_with_header(self):
        """x-enforce-beta-checks=1 disables testing bypass."""
        request = _make_request(headers={"x-enforce-beta-checks": "1"})
        assert auth_module._testing_bypass(request) is False

    def test_testing_bypass_disabled_in_production(self):
        original = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", False)
            request = _make_request()
            assert auth_module._testing_bypass(request) is False
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original)

    def test_testing_bypass_none_request(self):
        assert auth_module._testing_bypass(None) is True


# ──────────────────────────────────────────────────────────────
# _preview_bypass edge cases
# ──────────────────────────────────────────────────────────────

class TestPreviewBypass:
    def test_bypass_disabled_by_env(self, monkeypatch):
        """Kill switch disables bypass."""
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "false")
        request = _make_request()
        assert auth_module._preview_bypass(request, None) is False

    def test_bypass_wrong_site_mode(self, monkeypatch):
        """Non-preview site mode → bypass False."""
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
        monkeypatch.setenv("SITE_MODE", "prod")
        request = _make_request()
        assert auth_module._preview_bypass(request, None) is False

    def test_bypass_webhook_path_rejected(self, monkeypatch):
        """Webhook path → bypass False even in preview."""
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
        monkeypatch.setenv("SITE_MODE", "preview")
        monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
        monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")
        request = _make_request(
            path="/api/v1/webhook/stripe",
            headers={
                "origin": "https://preview.example.com",
                "x-forwarded-host": "api.preview.example.com",
            },
            host="api.preview.example.com",
        )
        assert auth_module._preview_bypass(request, None) is False


# ──────────────────────────────────────────────────────────────
# require_beta_access
# ──────────────────────────────────────────────────────────────

class TestRequireBetaAccess:
    @pytest.mark.asyncio
    async def test_preview_mode_bypasses(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "preview")
        user = _make_user()
        verify = auth_module.require_beta_access()
        result = await verify(
            request=_make_request(),
            current_user=user,
            db=MagicMock(),
        )
        assert result is user

    @pytest.mark.asyncio
    async def test_beta_disabled_bypasses(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "false")
        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", False)
            object.__setattr__(auth_module.settings, "beta_disabled", True)
            user = _make_user()
            verify = auth_module.require_beta_access()
            result = await verify(
                request=_make_request(),
                current_user=user,
                db=MagicMock(),
            )
            assert result is user
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)
            try:
                delattr(auth_module.settings, "beta_disabled")
            except Exception:
                object.__setattr__(auth_module.settings, "beta_disabled", False)

    @pytest.mark.asyncio
    async def test_no_beta_access_raises(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "false")
        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", False)
            object.__setattr__(auth_module.settings, "beta_disabled", False)

            user = _make_user()
            mock_repo = MagicMock()
            mock_repo.get_latest_for_user.return_value = None

            verify = auth_module.require_beta_access()
            with patch.object(auth_module, "BetaAccessRepository", return_value=mock_repo):
                with pytest.raises(HTTPException) as exc:
                    await verify(
                        request=_make_request(),
                        current_user=user,
                        db=MagicMock(),
                    )
            assert exc.value.status_code == 403
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)

    @pytest.mark.asyncio
    async def test_wrong_role_raises(self, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "false")
        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", False)
            object.__setattr__(auth_module.settings, "beta_disabled", False)

            user = _make_user()
            beta_access = SimpleNamespace(role="student")
            mock_repo = MagicMock()
            mock_repo.get_latest_for_user.return_value = beta_access

            verify = auth_module.require_beta_access(role="instructor")
            with patch.object(auth_module, "BetaAccessRepository", return_value=mock_repo):
                with pytest.raises(HTTPException) as exc:
                    await verify(
                        request=_make_request(),
                        current_user=user,
                        db=MagicMock(),
                    )
            assert exc.value.status_code == 403
            assert "instructor" in exc.value.detail
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)


# ──────────────────────────────────────────────────────────────
# L94-95: _extract_hostname exception path
# ──────────────────────────────────────────────────────────────

class TestExtractHostnameException:
    def test_malformed_url_returns_empty(self):
        """L94-95: urlparse raises on extremely malformed input → returns ''."""
        # urlparse is very lenient and rarely raises. We patch it to raise.
        with patch("urllib.parse.urlparse", side_effect=ValueError("bad")):
            result = auth_module._extract_hostname("https://example.com")
        assert result == ""


# ──────────────────────────────────────────────────────────────
# L154->178: preview header token validation path
# ──────────────────────────────────────────────────────────────

class TestPreviewBypassHeaderToken:
    def test_preview_bypass_header_token_valid(self, monkeypatch):
        """L151-177: Valid staff preview token via header triggers bypass."""
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
        monkeypatch.setenv("SITE_MODE", "preview")
        monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
        monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")
        monkeypatch.setattr(auth_module.settings, "allow_preview_header", True)
        monkeypatch.setattr(auth_module.settings, "staff_preview_token", "secret-token-123")

        # Non-staff user with valid header token
        user = _make_user(is_staff=False)
        request = _make_request(
            path="/api/v1/test",
            headers={
                "origin": "https://preview.example.com",
                "x-forwarded-host": "api.preview.example.com",
                "x-staff-preview-token": "secret-token-123",
            },
            host="api.preview.example.com",
        )
        result = auth_module._preview_bypass(request, user)
        assert result is True

    def test_preview_bypass_header_token_invalid(self, monkeypatch):
        """L154: Invalid token → no bypass."""
        monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
        monkeypatch.setenv("SITE_MODE", "preview")
        monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
        monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")
        monkeypatch.setattr(auth_module.settings, "allow_preview_header", True)
        monkeypatch.setattr(auth_module.settings, "staff_preview_token", "secret-token-123")

        user = _make_user(is_staff=False)
        request = _make_request(
            path="/api/v1/test",
            headers={
                "origin": "https://preview.example.com",
                "x-forwarded-host": "api.preview.example.com",
                "x-staff-preview-token": "wrong-token",
            },
            host="api.preview.example.com",
        )
        result = auth_module._preview_bypass(request, user)
        assert result is False


# ──────────────────────────────────────────────────────────────
# L241-243: legacy call pattern fallback get_by_id → get_by_email
# ──────────────────────────────────────────────────────────────

class TestLegacyCallPattern:
    @pytest.mark.asyncio
    async def test_legacy_call_pattern_id_fallback_to_email(self):
        """L241-243: get_by_id returns None → falls back to get_by_email."""
        user = _make_user(is_active=True)
        mock_db = MagicMock()
        mock_db.query = MagicMock()  # Has 'query' attribute
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_repo.get_by_email.return_value = user

        with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
            # Legacy call: get_current_user("user_id", db)
            # In legacy mode: request=string, current_user_id=db
            result = await auth_module.get_current_user(
                request="USER_01ABC",  # type: ignore[arg-type]
                current_user_id=mock_db,  # type: ignore[arg-type]
                db=mock_db,
            )
        assert result is user
        mock_repo.get_by_id.assert_called_once()
        mock_repo.get_by_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_legacy_call_pattern_email_lookup(self):
        """L236-238: legacy call with @ in identifier → direct email lookup."""
        user = _make_user(is_active=True)
        mock_db = MagicMock()
        mock_db.query = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_email.return_value = user

        with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
            result = await auth_module.get_current_user(
                request="test@example.com",  # type: ignore[arg-type]
                current_user_id=mock_db,  # type: ignore[arg-type]
                db=mock_db,
            )
        assert result is user

    @pytest.mark.asyncio
    async def test_legacy_call_pattern_not_found_raises(self):
        """L244-245: user not found in legacy mode → 404."""
        mock_db = MagicMock()
        mock_db.query = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_repo.get_by_email.return_value = None

        with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
            with pytest.raises(HTTPException) as exc:
                await auth_module.get_current_user(
                    request="USER_MISSING",  # type: ignore[arg-type]
                    current_user_id=mock_db,  # type: ignore[arg-type]
                    db=mock_db,
                )
        assert exc.value.status_code == 404


# ──────────────────────────────────────────────────────────────
# L307-309: impersonation exception path (non-fatal)
# ──────────────────────────────────────────────────────────────

class TestImpersonationExceptionPath:
    @pytest.mark.asyncio
    async def test_impersonation_exception_caught_silently(self):
        """L307-309: Exception during impersonation lookup → non-fatal, returns user."""
        user = _make_user(is_active=True, is_staff=True)
        mock_db = MagicMock()
        mock_db.query = MagicMock()

        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", True)
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = user

            # Make _preview_bypass raise to trigger L307-309
            request = _make_request(
                headers={"x-impersonate-user-id": "IMP_01"},
            )
            request.state.current_user = None  # force DB lookup

            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                with patch.object(auth_module, "_preview_bypass", side_effect=RuntimeError("boom")):
                    result = await auth_module.get_current_user(
                        request=request,
                        current_user_id="USER_01",
                        db=mock_db,
                    )
            # Should still return the user despite the exception
            assert result is user
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)

    @pytest.mark.asyncio
    async def test_get_current_user_request_state_has_user(self):
        """L218-220: request.state.current_user already set → returned directly."""
        user = _make_user(is_active=True)
        request = _make_request()
        request.state.current_user = user

        result = await auth_module.get_current_user(
            request=request,
            current_user_id="USER_01",
            db=MagicMock(),
        )
        assert result is user


# ──────────────────────────────────────────────────────────────
# L267: testing mode get_by_id→get_by_email fallback in get_current_user
# ──────────────────────────────────────────────────────────────

class TestGetCurrentUserTestingModeFallback:
    @pytest.mark.asyncio
    async def test_testing_mode_id_fallback_to_email(self):
        """L265-267: get_by_id returns None → falls back to get_by_email."""
        user = _make_user(is_active=True)
        mock_db = MagicMock()
        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", True)
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            mock_repo.get_by_email.return_value = user

            request = _make_request()
            request.state.current_user = None

            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                result = await auth_module.get_current_user(
                    request=request,
                    current_user_id="USER_01",
                    db=mock_db,
                )
            assert result is user
            mock_repo.get_by_id.assert_called_once()
            mock_repo.get_by_email.assert_called_once_with("USER_01")
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)

    @pytest.mark.asyncio
    async def test_testing_mode_not_found_raises(self):
        """L268-269: testing mode user not found → 404."""
        mock_db = MagicMock()
        original_testing = getattr(auth_module.settings, "is_testing", True)
        try:
            object.__setattr__(auth_module.settings, "is_testing", True)
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            mock_repo.get_by_email.return_value = None

            request = _make_request()
            request.state.current_user = None

            with patch("app.repositories.user_repository.UserRepository", return_value=mock_repo):
                with pytest.raises(HTTPException) as exc:
                    await auth_module.get_current_user(
                        request=request,
                        current_user_id="UNKNOWN",
                        db=mock_db,
                    )
            assert exc.value.status_code == 404
        finally:
            object.__setattr__(auth_module.settings, "is_testing", original_testing)
