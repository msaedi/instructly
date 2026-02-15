"""Additional coverage tests for cookie utilities."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.utils import cookies


def test_session_cookie_base_name_preview(monkeypatch):
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="access_token",
            session_cookie_samesite="lax",
            session_cookie_secure=True,
            session_cookie_domain=None,
        ),
    )

    assert cookies.session_cookie_base_name() == "sid_preview"


def test_session_cookie_base_name_custom(monkeypatch):
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="prod",
            session_cookie_name="custom",
            session_cookie_samesite="lax",
            session_cookie_secure=False,
            session_cookie_domain=None,
        ),
    )

    assert cookies.session_cookie_base_name("prod") == "custom"


def test_session_cookie_candidates_dedup(monkeypatch):
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="sid_preview",
            session_cookie_samesite="lax",
            session_cookie_secure=False,
            session_cookie_domain=None,
        ),
    )

    candidates = cookies.session_cookie_candidates()

    assert candidates == ["sid_preview"]


def test_set_session_cookie_host_prefix_drops_domain(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="access_token",
            session_cookie_samesite="lax",
            session_cookie_secure=True,
            session_cookie_domain="example.com",
        ),
    )

    name = cookies.set_session_cookie(
        response,
        "__Host-session",
        "value",
        domain="api.example.com",
    )

    assert name == "__Host-session"
    kwargs = response.set_cookie.call_args.kwargs
    assert "domain" not in kwargs
    assert kwargs["secure"] is True


def test_set_session_cookie_includes_domain(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="prod",
            session_cookie_name="access_token",
            session_cookie_samesite="lax",
            session_cookie_secure=False,
            session_cookie_domain="example.com",
        ),
    )

    name = cookies.set_session_cookie(response, "sid", "value")

    assert name == "sid"
    kwargs = response.set_cookie.call_args.kwargs
    assert kwargs["domain"] == "example.com"


def test_refresh_cookie_base_name_modes(monkeypatch):
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="sid",
            session_cookie_samesite="lax",
            session_cookie_secure=True,
            session_cookie_domain=".instainstru.com",
        ),
    )
    assert cookies.refresh_cookie_base_name("preview") == "rid_preview"
    assert cookies.refresh_cookie_base_name("prod") == "rid"
    assert cookies.refresh_cookie_base_name("local") == "rid"


def test_set_refresh_cookie_scoped_path(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="sid",
            session_cookie_samesite="lax",
            session_cookie_secure=True,
            session_cookie_domain=".instainstru.com",
        ),
    )

    name = cookies.set_refresh_cookie(response, "refresh-token")
    assert name == "rid_preview"
    kwargs = response.set_cookie.call_args.kwargs
    assert kwargs["path"] == "/api/v1/auth/refresh"
    assert kwargs["domain"] == ".instainstru.com"
    assert kwargs["secure"] is True


def test_delete_refresh_cookie_scoped_path(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(
        cookies,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            session_cookie_name="sid",
            session_cookie_samesite="lax",
            session_cookie_secure=True,
            session_cookie_domain=".instainstru.com",
        ),
    )

    name = cookies.delete_refresh_cookie(response)
    assert name == "rid_preview"
    kwargs = response.delete_cookie.call_args.kwargs
    assert kwargs["path"] == "/api/v1/auth/refresh"
    assert kwargs["domain"] == ".instainstru.com"
