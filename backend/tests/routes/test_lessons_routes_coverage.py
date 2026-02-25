"""Coverage tests for lessons routes — HMS secret missing in prod, FakeHundredMsClient fallback."""

from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.core.exceptions import DomainException
from app.routes.v1 import lessons as routes


# ---- L53-56: Missing HMS secret in prod → 503 ----
@pytest.mark.asyncio
async def test_get_video_service_missing_secret_prod(monkeypatch):
    monkeypatch.setattr(routes.settings, "hundredms_enabled", True)
    monkeypatch.setattr(routes.settings, "hundredms_access_key", "key")
    monkeypatch.setattr(routes.settings, "hundredms_app_secret", None)
    monkeypatch.setenv("SITE_MODE", "prod")

    with pytest.raises(HTTPException) as exc:
        routes.get_video_service(db=None)
    assert exc.value.status_code == 503


# ---- L64: FakeHundredMsClient fallback in non-prod when disabled ----
def test_get_video_service_disabled_returns_fake(monkeypatch):
    monkeypatch.setattr(routes.settings, "hundredms_enabled", False)

    service = routes.get_video_service(db=None)
    assert service is not None
    assert isinstance(service.hundredms_client, routes.FakeHundredMsClient)


# ---- Missing secret in non-prod → warning, empty secret fallback → 503 (missing fields) ----
def test_get_video_service_missing_secret_non_prod(monkeypatch):
    monkeypatch.setattr(routes.settings, "hundredms_enabled", True)
    monkeypatch.setattr(routes.settings, "hundredms_access_key", "key")
    monkeypatch.setattr(routes.settings, "hundredms_app_secret", None)
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(routes.settings, "hundredms_template_id", "tmpl")
    monkeypatch.setattr(routes.settings, "hundredms_base_url", "https://api.100ms.live")

    # Empty secret → missing HUNDREDMS_APP_SECRET → 503
    with pytest.raises(HTTPException) as exc:
        routes.get_video_service(db=None)
    assert exc.value.status_code == 503


# ---- Missing access_key → 503 ----
def test_get_video_service_missing_access_key(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(routes.settings, "hundredms_enabled", True)
    monkeypatch.setattr(routes.settings, "hundredms_access_key", "")
    monkeypatch.setattr(routes.settings, "hundredms_app_secret", SecretStr("secret"))
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(routes.settings, "hundredms_template_id", "tmpl")

    with pytest.raises(HTTPException) as exc:
        routes.get_video_service(db=None)
    assert exc.value.status_code == 503


# ---- handle_domain_exception converts DomainException ----
def test_handle_domain_exception_converts_to_http():
    exc = DomainException("test error")
    with pytest.raises(HTTPException) as http_exc:
        routes.handle_domain_exception(exc)
    assert http_exc.value.status_code == 500


# ---- With SecretStr raw_secret ----
def test_get_video_service_with_secret_str(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(routes.settings, "hundredms_enabled", True)
    monkeypatch.setattr(routes.settings, "hundredms_access_key", "key")
    monkeypatch.setattr(routes.settings, "hundredms_app_secret", SecretStr("secret"))
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(routes.settings, "hundredms_template_id", "tmpl")
    monkeypatch.setattr(routes.settings, "hundredms_base_url", "https://api.100ms.live")

    service = routes.get_video_service(db=None)
    assert service is not None


# ---- With plain string raw_secret ----
def test_get_video_service_with_plain_string_secret(monkeypatch):
    monkeypatch.setattr(routes.settings, "hundredms_enabled", True)
    monkeypatch.setattr(routes.settings, "hundredms_access_key", "key")
    monkeypatch.setattr(routes.settings, "hundredms_app_secret", "plainsecret")
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(routes.settings, "hundredms_template_id", "tmpl")
    monkeypatch.setattr(routes.settings, "hundredms_base_url", "https://api.100ms.live")

    service = routes.get_video_service(db=None)
    assert service is not None
