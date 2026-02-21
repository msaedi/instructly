"""Tests for the lessons (video) routes."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app.core.exceptions import NotFoundException, ServiceException, ValidationException
from app.main import fastapi_app as app
from app.routes.v1.lessons import get_video_service, handle_domain_exception

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def mock_video_service():
    """Create a mock VideoService."""
    return Mock()


@pytest.fixture()
def client_with_mock_service(client, mock_video_service):
    """Override the video service dependency with a mock."""
    app.dependency_overrides[get_video_service] = lambda: mock_video_service
    yield client
    app.dependency_overrides.pop(get_video_service, None)


# ── POST /join ────────────────────────────────────────────────────────


class TestJoinLesson:
    @patch("app.routes.v1.lessons.settings")
    def test_join_returns_200_with_auth_token(
        self, mock_settings, client_with_mock_service, mock_video_service, auth_headers
    ):
        mock_settings.hundredms_enabled = True
        mock_video_service.join_lesson.return_value = {
            "auth_token": "tok_abc",
            "room_id": "room_123",
            "role": "guest",
            "booking_id": "01HF4G12ABCDEF3456789XYZAB",
        }

        response = client_with_mock_service.post(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/join",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auth_token"] == "tok_abc"
        assert data["room_id"] == "room_123"
        assert data["role"] == "guest"
        assert data["booking_id"] == "01HF4G12ABCDEF3456789XYZAB"
        assert response.headers.get("X-RateLimit-Policy") == "video"
        assert response.headers.get("X-RateLimit-Limit") is not None

    def test_join_returns_401_without_auth(self, client_with_mock_service):
        response = client_with_mock_service.post(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/join",
        )

        assert response.status_code == 401

    @patch("app.routes.v1.lessons.settings")
    def test_join_returns_503_when_disabled(
        self, mock_settings, client_with_mock_service, auth_headers
    ):
        mock_settings.hundredms_enabled = False

        response = client_with_mock_service.post(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/join",
            headers=auth_headers,
        )

        assert response.status_code == 503
        assert "not currently available" in response.json()["detail"]

    @patch("app.routes.v1.lessons.settings")
    def test_join_returns_404_for_nonexistent_booking(
        self, mock_settings, client_with_mock_service, mock_video_service, auth_headers
    ):
        mock_settings.hundredms_enabled = True
        mock_video_service.join_lesson.side_effect = NotFoundException("Booking not found")

        response = client_with_mock_service.post(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/join",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @patch("app.routes.v1.lessons.settings")
    def test_join_returns_400_for_validation_error(
        self, mock_settings, client_with_mock_service, mock_video_service, auth_headers
    ):
        mock_settings.hundredms_enabled = True
        mock_video_service.join_lesson.side_effect = ValidationException(
            "Booking is not confirmed"
        )

        response = client_with_mock_service.post(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/join",
            headers=auth_headers,
        )

        assert response.status_code == 400


# ── GET /video-session ────────────────────────────────────────────────


class TestGetVideoSession:
    def test_returns_200_with_session_data(
        self, client_with_mock_service, mock_video_service, auth_headers
    ):
        mock_video_service.get_video_session_status.return_value = {
            "room_id": "room_123",
            "session_started_at": "2026-03-01T14:00:00+00:00",
            "session_ended_at": None,
            "instructor_joined_at": "2026-03-01T14:00:30+00:00",
            "student_joined_at": None,
        }

        response = client_with_mock_service.get(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/video-session",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == "room_123"

    def test_returns_404_when_no_session(
        self, client_with_mock_service, mock_video_service, auth_headers
    ):
        mock_video_service.get_video_session_status.return_value = None

        response = client_with_mock_service.get(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/video-session",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "No video session found" in response.json()["detail"]

    def test_returns_401_without_auth(self, client_with_mock_service):
        response = client_with_mock_service.get(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/video-session",
        )

        assert response.status_code == 401

    @patch("app.routes.v1.lessons.settings")
    def test_returns_500_for_service_exception(
        self, mock_settings, client_with_mock_service, mock_video_service, auth_headers
    ):
        """ServiceException (e.g. 100ms API down) maps to 500."""
        mock_settings.hundredms_enabled = True
        mock_video_service.get_video_session_status.side_effect = ServiceException(
            "100ms API unreachable"
        )

        response = client_with_mock_service.get(
            "/api/v1/lessons/01HF4G12ABCDEF3456789XYZAB/video-session",
            headers=auth_headers,
        )

        assert response.status_code == 500


# ── DI factory tests ─────────────────────────────────────────────────


class TestGetVideoServiceFactory:
    """Tests for the get_video_service DI factory function.

    Verifies that the correct 100ms client (real vs fake) is wired
    based on settings. A bug here could silently use FakeHundredMsClient
    in production.
    """

    @patch("app.routes.v1.lessons.settings")
    def test_creates_real_client_when_enabled(self, mock_settings):
        from app.integrations.hundredms_client import HundredMsClient
        from app.services.video_service import VideoService

        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "real_key"
        mock_settings.hundredms_app_secret = "real_secret_value_for_hmac_test"
        mock_settings.hundredms_base_url = "https://api.100ms.live/v2"
        mock_settings.hundredms_template_id = "tmpl_123"

        mock_db = Mock()
        service = get_video_service(db=mock_db)

        assert isinstance(service, VideoService)
        assert isinstance(service.hundredms_client, HundredMsClient)

    @patch("app.routes.v1.lessons.settings")
    def test_creates_fake_client_when_disabled(self, mock_settings):
        from app.integrations.hundredms_client import FakeHundredMsClient
        from app.services.video_service import VideoService

        mock_settings.hundredms_enabled = False
        mock_settings.hundredms_access_key = None

        mock_db = Mock()
        service = get_video_service(db=mock_db)

        assert isinstance(service, VideoService)
        assert isinstance(service.hundredms_client, FakeHundredMsClient)

    @patch("app.routes.v1.lessons.settings")
    def test_returns_503_when_enabled_but_missing_credentials(self, mock_settings):
        """Enabled mode must fail closed without leaking missing field names."""
        from fastapi import HTTPException
        from pydantic import SecretStr

        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "key-present"
        mock_settings.hundredms_app_secret = SecretStr("")
        mock_settings.hundredms_template_id = None

        mock_db = Mock()
        with pytest.raises(HTTPException) as exc_info:
            get_video_service(db=mock_db)
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Video service is temporarily unavailable"


# ── handle_domain_exception tests ────────────────────────────────────


class TestHandleDomainException:
    def test_converts_domain_exception_to_http(self):
        """DomainException with to_http_exception is converted correctly."""
        from fastapi import HTTPException

        exc = NotFoundException("Booking not found")

        with pytest.raises(HTTPException) as exc_info:
            handle_domain_exception(exc)

        assert exc_info.value.status_code == 404

    def test_fallback_for_bare_domain_exception(self):
        """DomainException without to_http_exception gets 500.

        This covers the defensive fallback path — ensures bare
        DomainException subclasses don't crash the route handler.
        """
        from fastapi import HTTPException

        class BareException:
            """Exception-like object that lacks to_http_exception."""

            def __str__(self) -> str:
                return "bare error"

        with pytest.raises(HTTPException) as exc_info:
            handle_domain_exception(BareException())  # type: ignore[arg-type]

        assert exc_info.value.status_code == 500
        assert "bare error" in exc_info.value.detail
