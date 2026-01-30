"""Tests for PushNotificationService."""

import json
import logging
from unittest.mock import Mock, patch

from pywebpush import WebPushException

from app.services.push_notification_service import PushNotificationService


class TestPushNotificationService:
    """Tests for push notification service."""

    def test_subscribe_creates_subscription(self, db, test_student):
        """Test subscribing creates a push subscription."""
        service = PushNotificationService(db)

        subscription = service.subscribe(
            user_id=test_student.id,
            endpoint="https://fcm.googleapis.com/fcm/send/abc123",
            p256dh_key="p256dh-key",
            auth_key="auth-key",
            user_agent="Mozilla/5.0 Chrome/120.0.0.0",
        )

        assert subscription is not None
        assert subscription.user_id == test_student.id
        assert subscription.endpoint == "https://fcm.googleapis.com/fcm/send/abc123"

    def test_subscribe_duplicate_endpoint_updates(self, db, test_student):
        """Test subscribing with same endpoint updates existing subscription."""
        service = PushNotificationService(db)
        endpoint = "https://fcm.googleapis.com/fcm/send/abc123"

        service.subscribe(
            user_id=test_student.id,
            endpoint=endpoint,
            p256dh_key="key1",
            auth_key="auth1",
        )

        service.subscribe(
            user_id=test_student.id,
            endpoint=endpoint,
            p256dh_key="key2",
            auth_key="auth2",
        )

        subscriptions = service.get_user_subscriptions(test_student.id)
        assert len(subscriptions) == 1
        assert subscriptions[0].p256dh_key == "key2"
        assert subscriptions[0].auth_key == "auth2"

    def test_unsubscribe_removes_subscription(self, db, test_student):
        """Test unsubscribing removes the subscription."""
        service = PushNotificationService(db)
        endpoint = "https://fcm.googleapis.com/fcm/send/abc123"

        service.subscribe(
            user_id=test_student.id,
            endpoint=endpoint,
            p256dh_key="key",
            auth_key="auth",
        )

        result = service.unsubscribe(test_student.id, endpoint)

        assert result is True
        assert len(service.get_user_subscriptions(test_student.id)) == 0

    def test_unsubscribe_nonexistent_returns_false(self, db, test_student):
        """Test unsubscribing nonexistent subscription returns False."""
        service = PushNotificationService(db)

        result = service.unsubscribe(test_student.id, "https://nonexistent.com")

        assert result is False

    def test_unsubscribe_all_removes_subscriptions(self, db, test_student):
        """Test unsubscribing all removes all subscriptions."""
        service = PushNotificationService(db)

        for i in range(2):
            service.subscribe(
                user_id=test_student.id,
                endpoint=f"https://fcm.googleapis.com/fcm/send/device{i}",
                p256dh_key=f"key{i}",
                auth_key=f"auth{i}",
            )

        deleted = service.unsubscribe_all(test_student.id)

        assert deleted == 2
        assert service.get_user_subscriptions(test_student.id) == []

    def test_get_user_subscriptions_returns_all(self, db, test_student):
        """Test getting all subscriptions for a user."""
        service = PushNotificationService(db)

        for i in range(3):
            service.subscribe(
                user_id=test_student.id,
                endpoint=f"https://fcm.googleapis.com/fcm/send/device{i}",
                p256dh_key=f"key{i}",
                auth_key=f"auth{i}",
            )

        subscriptions = service.get_user_subscriptions(test_student.id)

        assert len(subscriptions) == 3

    @patch("app.services.push_notification_service.webpush")
    def test_send_push_notification_success(self, mock_webpush, db, test_student):
        """Test sending push notification to user's devices."""
        service = PushNotificationService(db)

        service.subscribe(
            user_id=test_student.id,
            endpoint="https://fcm.googleapis.com/fcm/send/abc123",
            p256dh_key="key",
            auth_key="auth",
        )

        mock_webpush.return_value = Mock(status_code=201)

        with patch.object(service, "is_configured", return_value=True):
            result = service.send_push_notification(
                user_id=test_student.id,
                title="Test Notification",
                body="This is a test",
            )

        assert result["sent"] == 1
        assert result["failed"] == 0
        assert result["expired"] == 0

    @patch("app.services.push_notification_service.webpush")
    def test_send_push_removes_expired_subscription(self, mock_webpush, db, test_student):
        """Test that expired subscriptions (410 Gone) are removed."""
        service = PushNotificationService(db)
        endpoint = "https://fcm.googleapis.com/fcm/send/expired"

        service.subscribe(
            user_id=test_student.id,
            endpoint=endpoint,
            p256dh_key="key",
            auth_key="auth",
        )

        mock_response = Mock()
        mock_response.status_code = 410
        mock_webpush.side_effect = WebPushException("Gone", response=mock_response)

        with patch.object(service, "is_configured", return_value=True):
            result = service.send_push_notification(
                user_id=test_student.id,
                title="Test",
                body="Test",
            )

        assert result["expired"] == 1
        assert len(service.get_user_subscriptions(test_student.id)) == 0

    def test_send_push_notification_not_configured_skips(self, db, test_student, caplog):
        """If VAPID keys missing, sending should warn and skip."""
        service = PushNotificationService(db)

        with patch.object(PushNotificationService, "is_configured", return_value=False):
            with caplog.at_level(logging.WARNING):
                result = service.send_push_notification(
                    user_id=test_student.id,
                    title="Test",
                    body="Test",
                )

        assert result == {"sent": 0, "failed": 0, "expired": 0}
        assert "Push notifications not configured" in caplog.text

    @patch("app.services.push_notification_service.webpush")
    def test_send_push_notification_no_subscriptions(self, mock_webpush, db, test_student):
        """Configured sends with no subscriptions should no-op."""
        service = PushNotificationService(db)

        with patch.object(PushNotificationService, "is_configured", return_value=True):
            result = service.send_push_notification(
                user_id=test_student.id,
                title="Test",
                body="Test",
            )

        assert result == {"sent": 0, "failed": 0, "expired": 0}
        mock_webpush.assert_not_called()

    @patch("app.services.push_notification_service.webpush")
    def test_send_push_notification_webpush_error_counts_failed(
        self, mock_webpush, db, test_student, caplog
    ):
        """Non-expired WebPushException increments failed count."""
        service = PushNotificationService(db)
        service.subscribe(
            user_id=test_student.id,
            endpoint="https://fcm.googleapis.com/fcm/send/fail",
            p256dh_key="key",
            auth_key="auth",
        )

        mock_response = Mock()
        mock_response.status_code = 500
        mock_webpush.side_effect = WebPushException("Server error", response=mock_response)

        with patch.object(PushNotificationService, "is_configured", return_value=True):
            with caplog.at_level(logging.ERROR):
                result = service.send_push_notification(
                    user_id=test_student.id,
                    title="Test",
                    body="Test",
                )

        assert result["failed"] == 1
        assert result["expired"] == 0
        assert "Push send failed" in caplog.text

    @patch("app.services.push_notification_service.webpush")
    def test_send_push_notification_generic_exception_counts_failed(
        self, mock_webpush, db, test_student, caplog
    ):
        """Unexpected errors should log and increment failed count."""
        service = PushNotificationService(db)
        service.subscribe(
            user_id=test_student.id,
            endpoint="https://fcm.googleapis.com/fcm/send/fail",
            p256dh_key="key",
            auth_key="auth",
        )

        mock_webpush.side_effect = RuntimeError("Boom")

        with patch.object(PushNotificationService, "is_configured", return_value=True):
            with caplog.at_level(logging.ERROR):
                result = service.send_push_notification(
                    user_id=test_student.id,
                    title="Test",
                    body="Test",
                )

        assert result["failed"] == 1
        assert result["expired"] == 0
        assert "Push send failed" in caplog.text

    def test_resolve_asset_url_variants(self, db):
        """Resolve asset URLs with/without base and absolute URLs."""
        service = PushNotificationService(db)
        service._frontend_base = "https://frontend.test"

        assert (
            service._resolve_asset_url("icons/alert.png")
            == "https://frontend.test/icons/alert.png"
        )
        assert (
            service._resolve_asset_url("https://cdn.test/icon.png")
            == "https://cdn.test/icon.png"
        )

        service._frontend_base = ""
        assert service._resolve_asset_url("/icons/icon.png") == "/icons/icon.png"

    def test_build_payload_merges_data_and_url(self, db):
        """Payload should merge data/url and resolve assets."""
        with patch("app.services.push_notification_service.settings") as mock_settings:
            mock_settings.frontend_url = "https://frontend.test/"
            mock_settings.vapid_private_key = "key"
            mock_settings.vapid_claims_email = "mailto:test@example.com"
            mock_settings.vapid_public_key = "pub"

            service = PushNotificationService(db)
            payload = service._build_payload(
                title="Hello",
                body="World",
                url="https://example.com",
                icon="icons/custom.png",
                badge="https://cdn.test/badge.png",
                tag="tag-1",
                data={"foo": "bar"},
            )

        parsed = json.loads(payload)
        assert parsed["icon"] == "https://frontend.test/icons/custom.png"
        assert parsed["badge"] == "https://cdn.test/badge.png"
        assert parsed["tag"] == "tag-1"
        assert parsed["data"]["foo"] == "bar"
        assert parsed["data"]["url"] == "https://example.com"

    def test_is_configured_without_keys(self):
        """Test is_configured returns False without VAPID keys."""
        with patch("app.services.push_notification_service.settings") as mock_settings:
            mock_settings.vapid_public_key = ""
            mock_settings.vapid_private_key = ""

            assert PushNotificationService.is_configured() is False

    def test_get_vapid_public_key(self):
        """Test getting VAPID public key."""
        with patch("app.services.push_notification_service.settings") as mock_settings:
            mock_settings.vapid_public_key = "test_public_key"

            key = PushNotificationService.get_vapid_public_key()

            assert key == "test_public_key"
