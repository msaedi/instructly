"""Tests for the lessons (video) routes."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app.core.exceptions import NotFoundException, ValidationException
from app.main import fastapi_app as app
from app.routes.v1.lessons import get_video_service

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
