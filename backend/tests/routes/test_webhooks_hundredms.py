"""Integration tests for 100ms webhook endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock, patch

import pytest

from app.main import fastapi_app as app
from app.routes.v1 import webhooks_hundredms as webhooks_module
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
    event_id: str | None = "evt-001",
    room_name: str = "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
    timestamp: str | None = None,
    **extra_data: object,
) -> dict:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "version": "2.0",
        "id": event_id,
        "type": event_type,
        "timestamp": timestamp,
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
        mock_ledger.mark_processing.return_value = True
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
        assert response.headers.get("X-RateLimit-Policy") == "webhook_hundredms"

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

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_failed_processing_clears_cache_for_retry(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger.mark_processing.return_value = True
        mock_ledger_cls.return_value = mock_ledger

        mock_process.side_effect = [RuntimeError("transient"), (None, "processed")]
        payload = _webhook_payload(event_id="evt-retry-able")

        # First delivery fails -> 500
        first = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )
        assert first.status_code == 500

        # Retry should reprocess (cache rollback on failure)
        second = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )
        assert second.status_code == 200
        assert mock_process.call_count == 2

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_ledger_processed_event_short_circuits_processing(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        webhooks_module._delivery_cache.clear()

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="processed", retry_count=3, id="evt_db_1")
        mock_ledger_cls.return_value = mock_ledger

        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(_webhook_payload(event_id="evt-already-processed")),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 200
        mock_process.assert_not_called()

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_inflight_duplicate_returns_503_with_retry_after(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        webhooks_module._delivery_cache.clear()

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(
            status="received", retry_count=1, id="evt-ledger-inflight"
        )
        mock_ledger.mark_processing.return_value = False
        mock_ledger.get_event.return_value = MagicMock(status="processing")
        mock_ledger_cls.return_value = mock_ledger

        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(_webhook_payload(event_id="evt-inflight-dup")),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "processing_in_progress"
        assert response.headers.get("Retry-After") == "2"
        mock_process.assert_not_called()

    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_peer_join_with_invalid_user_id_is_skipped(
        self,
        mock_settings,
        mock_ledger_cls,
        client_with_mock_repo,
        mock_booking_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger.mark_processing.return_value = True
        mock_ledger_cls.return_value = mock_ledger

        video_session = MagicMock()
        video_session.instructor_joined_at = None
        video_session.student_joined_at = None
        video_session.provider_metadata = {}
        video_session.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        mock_booking_repo.get_video_session_by_booking_id.return_value = video_session
        mock_booking_repo.get_by_id.return_value = MagicMock(
            student_id="student_1",
            instructor_id="instructor_1",
            booking_start_utc=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc),
            duration_minutes=60,
        )

        payload = _webhook_payload(
            event_type="peer.join.success",
            event_id="evt-peer-invalid",
            role="host",
            peer_id="peer_1",
            joined_at="2024-06-15T14:00:00Z",
            metadata='{"user_id":"attacker"}',
        )
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 200
        assert video_session.instructor_joined_at is None

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_transient_processing_exception_returns_500(
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
        mock_ledger.mark_processing.return_value = True
        mock_ledger_cls.return_value = mock_ledger

        mock_process.side_effect = RuntimeError("boom")

        payload = _webhook_payload(event_id="evt-transient-500")
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        # Transient failures return 500 so 100ms retries
        assert response.status_code == 500

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_mark_processed_failure_returns_500_and_clears_cache(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger.mark_processing.return_value = True
        mock_ledger.mark_processed.side_effect = [RuntimeError("ledger write failed"), None]
        mock_ledger_cls.return_value = mock_ledger

        mock_process.return_value = (None, "processed")
        webhooks_module._delivery_cache.clear()
        payload = _webhook_payload(event_id="evt-ledger-fail")

        with patch(
            "app.routes.v1.webhooks_hundredms._unmark_delivery",
            wraps=webhooks_module._unmark_delivery,
        ) as mock_unmark_delivery:
            first = client_with_mock_repo.post(
                "/api/v1/webhooks/hundredms",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "x-hundredms-secret": "test-secret",
                },
            )
            assert first.status_code == 500
            mock_unmark_delivery.assert_called_with("evt-ledger-fail")
            mock_ledger.mark_failed.assert_called_once()

            # Retry should still process because failed attempt unmarked cache key
            second = client_with_mock_repo.post(
                "/api/v1/webhooks/hundredms",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "x-hundredms-secret": "test-secret",
                },
            )
            assert second.status_code == 200
            assert mock_process.call_count == 2

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_missing_event_id_uses_peer_aware_fallback_key(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger.mark_processing.return_value = True
        mock_ledger_cls.return_value = mock_ledger

        mock_process.return_value = (None, "processed")
        webhooks_module._delivery_cache.clear()

        payload_a = _webhook_payload(
            event_type="peer.join.success",
            event_id=None,
            role="guest",
            peer_id="peer-student",
        )
        payload_b = _webhook_payload(
            event_type="peer.join.success",
            event_id=None,
            role="host",
            peer_id="peer-instructor",
        )

        first = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload_a),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )
        second = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload_b),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_process.call_count == 2

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_missing_event_id_replay_after_cache_clear_dedupes_via_ledger(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        first_event = MagicMock(status="received", retry_count=0, id="01HZZZZZZZZZZZZZZZZZZZZZZ")
        replay_event = MagicMock(status="processed", retry_count=1, id="01HZZZZZZZZZZZZZZZZZZZZZZ")
        mock_ledger = MagicMock()
        mock_ledger.log_received.side_effect = [first_event, replay_event]
        mock_ledger.mark_processing.return_value = True
        mock_ledger_cls.return_value = mock_ledger
        mock_process.return_value = (None, "processed")

        payload = _webhook_payload(
            event_type="peer.join.success",
            event_id=None,
            role="guest",
            peer_id="peer-student",
        )

        webhooks_module._delivery_cache.clear()
        first = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )
        webhooks_module._delivery_cache.clear()
        second = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_process.call_count == 1
        assert len(mock_ledger.log_received.call_args_list) == 2
        first_call = mock_ledger.log_received.call_args_list[0].kwargs
        second_call = mock_ledger.log_received.call_args_list[1].kwargs
        assert first_call["idempotency_key"] is not None
        assert second_call["idempotency_key"] == first_call["idempotency_key"]

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_invalid_payload_encoding_returns_400(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=b"\xff\xfe\xfa",
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid payload encoding"

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_invalid_json_payload_returns_400(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content='{"type":"session.open.success","data":',
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid JSON payload"

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_stale_timestamp_returns_400(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        stale_timestamp = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat().replace(
            "+00:00", "Z"
        )
        payload = _webhook_payload(timestamp=stale_timestamp)
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Stale webhook timestamp"

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_invalid_room_name_shape_returns_400(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        payload = _webhook_payload(room_name="lesson-not-a-ulid")
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid webhook payload"

    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_invalid_session_id_type_returns_400(self, mock_settings, client_with_mock_repo):
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        payload = _webhook_payload(session_id=123)
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid webhook payload"

    @patch("app.routes.v1.webhooks_hundredms._process_hundredms_event")
    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_feature_flag_disabled_returns_200_without_processing(
        self,
        mock_settings,
        mock_ledger_cls,
        mock_process,
        client_with_mock_repo,
    ):
        mock_settings.hundredms_enabled = False

        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(_webhook_payload()),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        mock_ledger_cls.assert_not_called()
        mock_process.assert_not_called()

    @patch("app.routes.v1.webhooks_hundredms.WebhookLedgerService")
    @patch("app.routes.v1.webhooks_hundredms.settings")
    def test_invalid_room_name_returns_400_before_processing(
        self,
        mock_settings,
        mock_ledger_cls,
        client_with_mock_repo,
        mock_booking_repo,
    ):
        mock_settings.hundredms_webhook_secret = MagicMock()
        mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

        mock_ledger = MagicMock()
        mock_ledger.log_received.return_value = MagicMock(status="received", retry_count=0)
        mock_ledger_cls.return_value = mock_ledger

        # Invalid room name now fails schema validation before processing.
        payload = _webhook_payload(event_id="evt-permanent-200", room_name="unknown-room-format")
        response = client_with_mock_repo.post(
            "/api/v1/webhooks/hundredms",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "x-hundredms-secret": "test-secret",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid webhook payload"
