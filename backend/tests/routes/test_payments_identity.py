from __future__ import annotations

from typing import Dict
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.core import config as config_module
from app.main import fastapi_app


class TestIdentityReturnUrl:
    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_return_url_uses_frontend_url(
        self,
        mock_create_session,
        auth_headers_instructor: Dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Return URL should use settings.frontend_url, not the API request host."""
        mock_create_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }
        monkeypatch.setattr(config_module.settings, "frontend_url", "https://beta.instainstru.com")
        monkeypatch.setattr(
            config_module.settings,
            "identity_return_path",
            "/instructor/onboarding/verification?identity_return=true",
        )

        with TestClient(fastapi_app, base_url="https://api.instainstru.com") as client:
            response = client.post(
                "/api/v1/payments/identity/session",
                headers={**auth_headers_instructor, "host": "api.instainstru.com"},
            )

        assert response.status_code == status.HTTP_200_OK
        return_url = mock_create_session.call_args.kwargs["return_url"]
        assert return_url.startswith("https://beta.instainstru.com/")
        assert "api.instainstru.com" not in return_url

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_return_url_falls_back_to_request_host_when_no_frontend_url(
        self,
        mock_create_session,
        auth_headers_instructor: Dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When frontend_url is empty, fall back to request host (local dev)."""
        mock_create_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }
        monkeypatch.setattr(config_module.settings, "frontend_url", "")
        monkeypatch.setattr(
            config_module.settings,
            "identity_return_path",
            "/instructor/onboarding/verification?identity_return=true",
        )

        with TestClient(fastapi_app, base_url="http://localhost:8000") as client:
            response = client.post(
                "/api/v1/payments/identity/session",
                headers={**auth_headers_instructor, "host": "localhost:8000"},
            )

        assert response.status_code == status.HTTP_200_OK
        return_url = mock_create_session.call_args.kwargs["return_url"]
        assert return_url.startswith("http://localhost:8000/")

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_return_url_includes_identity_return_path(
        self,
        mock_create_session,
        auth_headers_instructor: Dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Return URL should include the configured identity_return_path."""
        mock_create_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }
        monkeypatch.setattr(config_module.settings, "frontend_url", "https://beta.instainstru.com")
        monkeypatch.setattr(
            config_module.settings,
            "identity_return_path",
            "/instructor/onboarding/verification?identity_return=true",
        )

        with TestClient(fastapi_app, base_url="https://api.instainstru.com") as client:
            response = client.post(
                "/api/v1/payments/identity/session",
                headers={**auth_headers_instructor, "host": "api.instainstru.com"},
            )

        assert response.status_code == status.HTTP_200_OK
        return_url = mock_create_session.call_args.kwargs["return_url"]
        assert (
            return_url
            == "https://beta.instainstru.com/instructor/onboarding/verification?identity_return=true"
        )
