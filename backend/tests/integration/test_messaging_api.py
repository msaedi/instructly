"""
Integration tests for messaging API endpoints.

Tests cover all messaging bugs fixed during Phase 4:
- Bug #4: delivered_at field in API responses
- Bug #5: read_by field persistence and API responses
- Inbox state with unread_conversations count
- ETag caching for inbox state
"""

from fastapi.testclient import TestClient
import pytest


@pytest.mark.parametrize("client_type", ["client"])
class TestMessagingAPI:
    """Integration tests for messaging API endpoints."""

    def test_send_message_returns_delivered_at(
        self, client_type, request, auth_headers_instructor, test_booking
    ):
        """Bug #4: API response must include delivered_at."""
        client: TestClient = request.getfixturevalue(client_type)

        response = client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Hello"},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 201
        data = response.json()
        assert "message" in data
        assert "delivered_at" in data["message"]
        assert data["message"]["delivered_at"] is not None

    def test_message_history_includes_delivered_at(
        self, client_type, request, auth_headers_instructor, auth_headers_student, test_booking
    ):
        """Bug #4: Message history must include delivered_at field."""
        client: TestClient = request.getfixturevalue(client_type)

        # Send a message
        client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Hello student"},
            headers=auth_headers_instructor,
        )

        # Get message history
        response = client.get(
            f"/api/v1/messages/history/{test_booking.id}",
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        messages = data.get("messages", [])
        assert len(messages) > 0
        assert "delivered_at" in messages[0]
        assert messages[0]["delivered_at"] is not None

    def test_message_history_includes_read_by(
        self, client_type, request, auth_headers_instructor, auth_headers_student, test_booking
    ):
        """Bug #5: Message history must include read_by field."""
        client: TestClient = request.getfixturevalue(client_type)

        # Send message
        client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Hello"},
            headers=auth_headers_instructor,
        )

        # Student marks as read
        client.post(
            "/api/v1/messages/mark-read",
            json={"booking_id": test_booking.id},
            headers=auth_headers_student,
        )

        # Get message history
        response = client.get(
            f"/api/v1/messages/history/{test_booking.id}",
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        messages = data.get("messages", [])
        assert len(messages) > 0
        assert "read_by" in messages[0]

    def test_inbox_state_includes_unread_conversations(
        self, client_type, request, auth_headers_instructor
    ):
        """Inbox state must include conversation count, not just message count."""
        client: TestClient = request.getfixturevalue(client_type)

        response = client.get(
            "/api/v1/messages/inbox-state",
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        assert "unread_conversations" in data
        assert "total_unread" in data
        # unread_conversations <= total_unread always
        assert data["unread_conversations"] <= data["total_unread"]

    def test_inbox_state_etag_caching(
        self, client_type, request, auth_headers_instructor
    ):
        """ETag caching should return 304 when unchanged."""
        client: TestClient = request.getfixturevalue(client_type)

        # First request
        response1 = client.get(
            "/api/v1/messages/inbox-state",
            headers=auth_headers_instructor,
        )
        assert response1.status_code == 200
        etag = response1.headers.get("ETag")
        assert etag is not None

        # Second request with If-None-Match
        response2 = client.get(
            "/api/v1/messages/inbox-state",
            headers={
                **auth_headers_instructor,
                "If-None-Match": etag,
            },
        )

        # Should return 304 Not Modified
        assert response2.status_code == 304

    def test_send_message_creates_notification(
        self, client_type, request, auth_headers_instructor, auth_headers_student, test_booking
    ):
        """Sent messages should create notifications for recipients."""
        client: TestClient = request.getfixturevalue(client_type)

        # Send message from instructor
        client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Hello student"},
            headers=auth_headers_instructor,
        )

        # Student checks inbox state
        response = client.get(
            "/api/v1/messages/inbox-state",
            headers=auth_headers_student,
        )

        assert response.status_code == 200
        data = response.json()
        # Should have at least 1 unread message
        assert data["total_unread"] >= 1

    def test_mark_as_read_clears_notifications(
        self, client_type, request, auth_headers_instructor, auth_headers_student, test_booking
    ):
        """Marking messages as read should clear notifications."""
        client: TestClient = request.getfixturevalue(client_type)

        # Send message from instructor
        client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Hello"},
            headers=auth_headers_instructor,
        )

        # Student marks as read
        mark_read_response = client.post(
            "/api/v1/messages/mark-read",
            json={"booking_id": test_booking.id},
            headers=auth_headers_student,
        )

        assert mark_read_response.status_code in [200, 204]

        # Student checks inbox state
        response = client.get(
            "/api/v1/messages/inbox-state",
            headers=auth_headers_student,
        )

        assert response.status_code == 200
        data = response.json()
        # Should have 0 unread from this booking
        # (may have other unread from other bookings, but this one should be read)
        # Check if the conversation is in the list and has 0 unread
        conversations = data.get("conversations", [])
        this_conversation = next(
            (c for c in conversations if c["id"] == test_booking.id),
            None
        )
        if this_conversation:
            assert this_conversation["unread_count"] == 0

    def test_message_history_pagination(
        self, client_type, request, auth_headers_instructor, test_booking
    ):
        """Message history should support pagination."""
        client: TestClient = request.getfixturevalue(client_type)

        # Send multiple messages
        for i in range(5):
            client.post(
                "/api/v1/messages/send",
                json={"booking_id": test_booking.id, "content": f"Message {i}"},
                headers=auth_headers_instructor,
            )

        # Get first 2 messages
        response = client.get(
            f"/api/v1/messages/history/{test_booking.id}",
            params={"limit": 2, "offset": 0},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        messages = data.get("messages", [])
        assert len(messages) <= 2

    def test_unread_count_includes_only_other_user_messages(
        self, client_type, request, auth_headers_instructor, auth_headers_student, test_booking
    ):
        """Unread count should not include user's own messages."""
        client: TestClient = request.getfixturevalue(client_type)

        # Instructor sends message
        client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "From instructor"},
            headers=auth_headers_instructor,
        )

        # Instructor checks inbox (should not count own message as unread)
        response = client.get(
            "/api/v1/messages/inbox-state",
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        conversations = data.get("conversations", [])
        this_conversation = next(
            (c for c in conversations if c["id"] == test_booking.id),
            None
        )
        if this_conversation:
            # Should be 0 unread for instructor (own message)
            assert this_conversation["unread_count"] == 0

    def test_reaction_endpoint(
        self, client_type, request, auth_headers_student, test_booking
    ):
        """Test reaction endpoint."""
        client: TestClient = request.getfixturevalue(client_type)

        # Create a message first
        message_response = client.post(
            "/api/v1/messages/send",
            json={"booking_id": test_booking.id, "content": "Test message"},
            headers=auth_headers_student,
        )

        assert message_response.status_code == 201
        message_id = message_response.json()["message"]["id"]

        # Add reaction
        reaction_response = client.post(
            f"/api/v1/messages/{message_id}/reactions",
            json={"emoji": "👍"},
            headers=auth_headers_student,
        )

        # Should succeed
        assert reaction_response.status_code in [200, 201, 204]
