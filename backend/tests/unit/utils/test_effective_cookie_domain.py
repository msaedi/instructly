"""Regression tests for _effective_cookie_domain and origin-aware set_auth_cookies.

These tests ensure the dynamic cookie domain logic never regresses:
- Production: session_cookie_domain is already set → Origin header is never read
- Local + localhost: no domain attribute on cookies
- Local + beta-local.instainstru.com: Domain=.instainstru.com
- Crafted/malicious origins must NOT trigger the domain widening
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.utils import cookies

# ---------------------------------------------------------------------------
# Shared fixture: local-mode settings (session_cookie_domain = None)
# ---------------------------------------------------------------------------

def _local_settings(**overrides):
    defaults = dict(
        site_mode="local",
        session_cookie_name="sid_local",
        session_cookie_samesite="lax",
        session_cookie_secure=False,
        session_cookie_domain=None,
        access_token_expire_minutes=15,
        refresh_token_lifetime_days=7,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _hosted_settings(**overrides):
    defaults = dict(
        site_mode="beta",
        session_cookie_name="sid",
        session_cookie_samesite="lax",
        session_cookie_secure=True,
        session_cookie_domain=".instainstru.com",
        access_token_expire_minutes=15,
        refresh_token_lifetime_days=7,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===================================================================
# _effective_cookie_domain — pure logic tests
# ===================================================================


class TestEffectiveCookieDomainProduction:
    """In production/hosted modes session_cookie_domain is already set.
    The Origin header must NEVER be consulted."""

    def test_returns_configured_domain_when_set(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _hosted_settings())
        assert cookies._effective_cookie_domain() == ".instainstru.com"

    def test_ignores_origin_when_domain_configured(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _hosted_settings())
        # Even with a completely different origin, returns the configured domain
        result = cookies._effective_cookie_domain("http://evil.example.com")
        assert result == ".instainstru.com"

    def test_ignores_none_origin_when_domain_configured(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _hosted_settings())
        assert cookies._effective_cookie_domain(None) == ".instainstru.com"

    @pytest.mark.parametrize("mode", ["prod", "production", "beta", "preview"])
    def test_all_hosted_modes_short_circuit(self, monkeypatch, mode):
        monkeypatch.setattr(
            cookies, "settings", _hosted_settings(site_mode=mode)
        )
        result = cookies._effective_cookie_domain("http://attacker.com")
        assert result == ".instainstru.com"


class TestEffectiveCookieDomainLocal:
    """In local mode (session_cookie_domain=None), the Origin is checked."""

    def test_none_origin_returns_none(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain(None) is None

    def test_empty_origin_returns_none(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain("") is None

    def test_localhost_origin_returns_none(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain("http://localhost:3000") is None

    def test_127_origin_returns_none(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain("http://127.0.0.1:3000") is None

    def test_beta_local_origin_returns_parent_domain(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://beta-local.instainstru.com:3000"
        )
        assert result == ".instainstru.com"

    def test_api_beta_local_origin_returns_parent_domain(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://api.beta-local.instainstru.com:8000"
        )
        assert result == ".instainstru.com"

    def test_bare_instainstru_com_returns_parent_domain(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain("https://instainstru.com")
        assert result == ".instainstru.com"


class TestEffectiveCookieDomainSecurityHardening:
    """Ensure crafted origins cannot trick the hostname check."""

    def test_rejects_suffix_attack(self, monkeypatch):
        """evil.instainstru.com.attacker.com must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://evil.instainstru.com.attacker.com"
        )
        assert result is None

    def test_rejects_prefix_attack(self, monkeypatch):
        """notinstainstru.com must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://notinstainstru.com"
        )
        assert result is None

    def test_rejects_substring_in_path(self, monkeypatch):
        """Domain in path (not hostname) must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://evil.com/instainstru.com"
        )
        assert result is None

    def test_rejects_substring_in_query(self, monkeypatch):
        """Domain in query string must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://evil.com?redirect=http://instainstru.com"
        )
        assert result is None

    def test_rejects_substring_in_fragment(self, monkeypatch):
        """Domain in fragment must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://evil.com#instainstru.com"
        )
        assert result is None

    def test_rejects_userinfo_attack(self, monkeypatch):
        """Domain in userinfo must NOT match."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        result = cookies._effective_cookie_domain(
            "http://instainstru.com@evil.com"
        )
        assert result is None

    def test_rejects_random_external_origin(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain("http://google.com") is None

    def test_rejects_empty_hostname(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        assert cookies._effective_cookie_domain("not-a-url") is None


# ===================================================================
# set_auth_cookies — integration with _effective_cookie_domain
# ===================================================================


class TestSetAuthCookiesOriginAware:
    """Verify set_auth_cookies propagates the dynamic domain correctly."""

    def test_localhost_origin_no_domain_on_cookies(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://localhost:3000",
        )

        # Both set_cookie calls should have NO domain key
        assert response.set_cookie.call_count == 2
        for call in response.set_cookie.call_args_list:
            assert "domain" not in call.kwargs, (
                f"Cookie should have no domain for localhost, got: {call.kwargs}"
            )

    def test_beta_local_origin_sets_parent_domain(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://beta-local.instainstru.com:3000",
        )

        assert response.set_cookie.call_count == 2
        for call in response.set_cookie.call_args_list:
            assert call.kwargs.get("domain") == ".instainstru.com", (
                f"Cookie should have .instainstru.com domain, got: {call.kwargs}"
            )

    def test_no_origin_no_domain(self, monkeypatch):
        """Backward compatibility: omitting origin keeps old behavior."""
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(response, "access-tok", "refresh-tok")

        assert response.set_cookie.call_count == 2
        for call in response.set_cookie.call_args_list:
            assert "domain" not in call.kwargs

    def test_production_origin_ignored_uses_configured_domain(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _hosted_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://malicious.example.com",
        )

        assert response.set_cookie.call_count == 2
        for call in response.set_cookie.call_args_list:
            assert call.kwargs.get("domain") == ".instainstru.com"

    def test_session_cookie_has_root_path(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://beta-local.instainstru.com:3000",
        )

        session_call = response.set_cookie.call_args_list[0]
        assert session_call.kwargs["path"] == "/"

    def test_refresh_cookie_has_scoped_path(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://beta-local.instainstru.com:3000",
        )

        refresh_call = response.set_cookie.call_args_list[1]
        assert refresh_call.kwargs["path"] == "/api/v1/auth/refresh"

    def test_httponly_always_set(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://beta-local.instainstru.com:3000",
        )

        for call in response.set_cookie.call_args_list:
            assert call.kwargs["httponly"] is True

    def test_samesite_always_lax(self, monkeypatch):
        monkeypatch.setattr(cookies, "settings", _local_settings())
        response = MagicMock()

        cookies.set_auth_cookies(
            response, "access-tok", "refresh-tok",
            origin="http://beta-local.instainstru.com:3000",
        )

        for call in response.set_cookie.call_args_list:
            assert call.kwargs["samesite"] == "lax"
