"""Tests for notification preference routes."""


def test_get_notification_preferences(client, auth_headers_instructor):
    response = client.get(
        "/api/v1/notification-preferences",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["lesson_updates"]["email"] is True
    assert payload["lesson_updates"]["push"] is True
    assert payload["lesson_updates"]["sms"] is False
    assert payload["messages"]["push"] is True
    assert payload["promotional"]["email"] is False


def test_update_notification_preference(client, auth_headers_instructor):
    response = client.put(
        "/api/v1/notification-preferences/promotional/push",
        headers=auth_headers_instructor,
        json={"enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["category"] == "promotional"
    assert payload["channel"] == "push"
    assert payload["enabled"] is True

    check = client.get(
        "/api/v1/notification-preferences",
        headers=auth_headers_instructor,
    )
    assert check.status_code == 200
    assert check.json()["promotional"]["push"] is True


def test_update_notification_preference_locked(client, auth_headers_instructor):
    response = client.put(
        "/api/v1/notification-preferences/messages/push",
        headers=auth_headers_instructor,
        json={"enabled": False},
    )

    assert response.status_code == 400


def test_update_notification_preferences_bulk(client, auth_headers_instructor):
    response = client.put(
        "/api/v1/notification-preferences",
        headers=auth_headers_instructor,
        json={
            "updates": [
                {"category": "lesson_updates", "channel": "push", "enabled": False},
                {"category": "promotional", "channel": "email", "enabled": True},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2

    check = client.get(
        "/api/v1/notification-preferences",
        headers=auth_headers_instructor,
    )
    assert check.status_code == 200
    assert check.json()["lesson_updates"]["push"] is False
    assert check.json()["promotional"]["email"] is True
