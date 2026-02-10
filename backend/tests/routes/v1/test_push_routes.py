"""Tests for push notification API routes."""

from unittest.mock import patch

from app.services.push_notification_service import PushNotificationService


def test_get_vapid_public_key(client):
    """Test getting VAPID public key."""
    with patch("app.routes.v1.push.PushNotificationService.is_configured", return_value=True):
        with patch(
            "app.routes.v1.push.PushNotificationService.get_vapid_public_key",
            return_value="test_key",
        ):
            response = client.get("/api/v1/push/vapid-public-key")

    assert response.status_code == 200
    assert response.json()["public_key"] == "test_key"


def test_get_vapid_public_key_not_configured(client):
    """Test getting VAPID key when not configured returns 503."""
    with patch("app.routes.v1.push.PushNotificationService.is_configured", return_value=False):
        response = client.get("/api/v1/push/vapid-public-key")

    assert response.status_code == 503


def test_subscribe_requires_auth(client):
    """Test subscribe endpoint requires authentication."""
    response = client.post(
        "/api/v1/push/subscribe",
        json={
            "endpoint": "https://example.com",
            "p256dh": "key",
            "auth": "auth",
        },
    )

    assert response.status_code in (401, 403)


def test_subscribe_success(client, auth_headers_instructor):
    """Test successful subscription."""
    response = client.post(
        "/api/v1/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_unsubscribe_success(client, auth_headers_instructor, db, test_instructor):
    """Test successful unsubscription."""
    service = PushNotificationService(db)
    service.subscribe(
        user_id=test_instructor.id,
        endpoint="https://fcm.googleapis.com/fcm/send/abc123",
        p256dh_key="key",
        auth_key="auth",
    )

    response = client.request(
        "DELETE",
        "/api/v1/push/unsubscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc123"},
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_list_subscriptions(client, auth_headers_instructor, db, test_instructor):
    """Test listing user's subscriptions."""
    service = PushNotificationService(db)
    service.subscribe(
        user_id=test_instructor.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device1",
        p256dh_key="key1",
        auth_key="auth1",
    )
    service.subscribe(
        user_id=test_instructor.id,
        endpoint="https://fcm.googleapis.com/fcm/send/device2",
        p256dh_key="key2",
        auth_key="auth2",
    )

    response = client.get(
        "/api/v1/push/subscriptions",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_subscribe_service_error_returns_400(client, auth_headers_instructor):
    with patch(
        "app.routes.v1.push.PushNotificationService.subscribe",
        side_effect=RuntimeError("bad-subscribe"),
    ):
        response = client.post(
            "/api/v1/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
                "p256dh": "key",
                "auth": "auth",
            },
            headers=auth_headers_instructor,
        )

    assert response.status_code == 400


def test_unsubscribe_not_found_returns_false(client, auth_headers_instructor):
    response = client.request(
        "DELETE",
        "/api/v1/push/unsubscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/not-found"},
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
