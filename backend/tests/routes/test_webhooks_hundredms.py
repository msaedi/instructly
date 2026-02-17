"""Integration tests for 100ms webhook endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.main import fastapi_app as app
from app.routes.v1.webhooks_hundredms import _get_booking_repository

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def mock_booking_repo():
    """Create a mock BookingRepository for webhook DI."""
    repo = MagicMock()
    repo.db = MagicMock()
    repo.get_video_session_by_booking_id.return_value = None
    repo.flush = MagicMock()
    return repo


@pytest.fixture()
def client_with_mock_repo(client, mock_booking_repo):
    """Override the booking repository dependency."""
    app.dependency_overrides[_get_booking_repository] = lambda: mock_booking_repo
    yield client
    app.dependency_overrides.pop(_get_booking_repository, None)


def _webhook_payload(
    event_type: str = "session.open.success",
    event_id: str = "evt-001",
    room_name: str = "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
    **extra_data: object,
) -> dict:
    return {
        "version": "2.0",
        "id": event_id,
        "type": event_type,
        "timestamp": "2024-06-15T14:00:00Z",
        "data": {
            "room_id": "room-123",
            "room_name": room_name,
            "session_id": "sess-456",
            **extra_data,
        },
    }


# ── Tests ─────────────────────────────────────────────────────────────


class TestHundredmsWebhookEndpoint:
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_returns_200_for_valid_event(
        self,
        mock_settings,
        mock_ledger_cls,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger_cls.return_value = mock_ledger

        payload = _webhook_payload()
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_returns_401_without_secret(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "secret"

        payload = _webhook_payload()
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401

    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_unhandled_event_type_returns_200(
        self,
        mock_settings,
        mock_ledger_cls,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        payload = _webhook_payload(event_type="recording.started")
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        # Ledger should NOT have been called for unhandled types
        mock_ledger_cls.assert_not_called()

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_returns_200_even_on_processing_error(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger_cls.return_value = mock_ledger

        mock_process.side_effect = RuntimeError("boom")

        payload = _webhook_payload()
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        # Webhooks always return 200
        assert response.status_code == 200
        assert response.json()["ok"] is True
