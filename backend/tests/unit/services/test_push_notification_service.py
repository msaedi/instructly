"""Tests for PushNotificationService."""

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
