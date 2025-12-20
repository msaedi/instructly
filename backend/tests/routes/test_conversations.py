# tests/routes/test_conversations.py
"""
Conversations API routes tests.

Tests the per-user-pair conversation endpoints:
- GET /api/v1/conversations - List conversations
- POST /api/v1/conversations - Create conversation
- GET /api/v1/conversations/{id} - Get conversation details
- GET /api/v1/conversations/{id}/messages - Get messages
- POST /api/v1/conversations/{id}/messages - Send message
"""

from datetime import datetime, timedelta, timezone

from app.models.conversation import Conversation
from app.models.message import MESSAGE_TYPE_USER, Message


class TestListConversations:
    """Tests for GET /api/v1/conversations."""

    def test_list_conversations_empty(self, client, db, auth_headers):
        """Returns empty list when user has no conversations."""
        res = client.get("/api/v1/conversations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["conversations"] == []
        assert data["next_cursor"] is None

    def test_list_conversations_returns_conversations(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns conversations for the authenticated user."""
        # Create a conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        db.commit()

        res = client.get("/api/v1/conversations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["id"] == conversation.id

    def test_list_conversations_requires_auth(self, client):
        """Returns 401 without authentication."""
        res = client.get("/api/v1/conversations")
        assert res.status_code == 401

    def test_list_conversations_respects_limit(
        self, client, db, test_student, test_instructor_with_availability, test_instructor_2, auth_headers
    ):
        """Respects the limit parameter."""
        # Create two conversations
        conv1 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            last_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        conv2 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_2.id,
            last_message_at=datetime.now(timezone.utc),
        )
        db.add_all([conv1, conv2])
        db.commit()

        res = client.get("/api/v1/conversations?limit=1", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["conversations"]) == 1
        # Should return most recent first
        assert data["conversations"][0]["id"] == conv2.id
        # Should have next_cursor since there's more
        assert data["next_cursor"] is not None


class TestGetConversation:
    """Tests for GET /api/v1/conversations/{conversation_id}."""

    def test_get_conversation_success(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns conversation details for a participant."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == conversation.id
        assert "other_user" in data
        assert data["state"] == "active"

    def test_get_conversation_invalid_id_format(self, client, auth_headers):
        """Returns 422 for invalid conversation ID format."""
        res = client.get("/api/v1/conversations/nonexistent-id", headers=auth_headers)
        assert res.status_code == 422  # Invalid ULID format

    def test_get_conversation_not_found(self, client, auth_headers):
        """Returns 404 for non-existent conversation with valid ULID format."""
        # Use a valid ULID format that doesn't exist (Crockford Base32: 0-9A-HJKMNP-TV-Z)
        valid_nonexistent_id = "01JE5000000000000000000000"
        res = client.get(f"/api/v1/conversations/{valid_nonexistent_id}", headers=auth_headers)
        assert res.status_code == 404

    def test_get_conversation_not_participant(
        self, client, db, test_instructor_with_availability, test_instructor_2, auth_headers
    ):
        """Returns 404 when user is not a participant."""
        # Create conversation between two instructors
        conversation = Conversation(
            student_id=test_instructor_with_availability.id,
            instructor_id=test_instructor_2.id,
        )
        db.add(conversation)
        db.commit()

        # Try to access with student's auth (not a participant)
        res = client.get(f"/api/v1/conversations/{conversation.id}", headers=auth_headers)
        assert res.status_code == 404

    def test_get_conversation_requires_auth(self, client, db, test_student, test_instructor_with_availability):
        """Returns 401 without authentication."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}")
        assert res.status_code == 401


class TestCreateConversation:
    """Tests for POST /api/v1/conversations."""

    def test_create_conversation_new(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Creates a new conversation between student and instructor."""
        res = client.post(
            "/api/v1/conversations",
            json={"instructor_id": test_instructor_with_availability.id},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["created"] is True
        assert "id" in data

    def test_create_conversation_existing(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns existing conversation if one exists."""
        # Create a conversation first
        existing = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(existing)
        db.commit()

        res = client.post(
            "/api/v1/conversations",
            json={"instructor_id": test_instructor_with_availability.id},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["created"] is False
        assert data["id"] == existing.id

    def test_create_conversation_with_initial_message(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Creates conversation with an initial message."""
        res = client.post(
            "/api/v1/conversations",
            json={
                "instructor_id": test_instructor_with_availability.id,
                "initial_message": "Hello, I'd like to book a lesson!",
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["created"] is True

        # Verify message was created
        conversation = db.query(Conversation).filter(Conversation.id == data["id"]).first()
        messages = db.query(Message).filter(Message.conversation_id == conversation.id).all()
        assert len(messages) == 1
        assert messages[0].content == "Hello, I'd like to book a lesson!"

    def test_create_conversation_requires_auth(self, client, test_instructor_with_availability):
        """Returns 401 without authentication."""
        res = client.post(
            "/api/v1/conversations",
            json={"instructor_id": test_instructor_with_availability.id},
        )
        assert res.status_code == 401


class TestGetMessages:
    """Tests for GET /api/v1/conversations/{id}/messages."""

    def test_get_messages_success(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns messages for a conversation."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.flush()

        # Create a message
        message = Message(
            conversation_id=conversation.id,
            sender_id=test_student.id,
            content="Test message",
            message_type=MESSAGE_TYPE_USER,
        )
        db.add(message)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}/messages", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["messages"]) == 1
        msg = data["messages"][0]
        assert msg["conversation_id"] == conversation.id
        assert msg["content"] == "Test message"
        assert msg["is_from_me"] is True
        assert msg["edited_at"] is None
        assert msg["is_deleted"] is False

    def test_get_messages_includes_deleted(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Includes soft-deleted messages and redacts their content."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.flush()

        db.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    sender_id=test_student.id,
                    content="Visible message",
                    message_type=MESSAGE_TYPE_USER,
                    created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ),
                Message(
                    conversation_id=conversation.id,
                    sender_id=test_student.id,
                    content="Original content should not leak",
                    message_type=MESSAGE_TYPE_USER,
                    is_deleted=True,
                    deleted_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}/messages", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["messages"]) == 2

        deleted = next(m for m in data["messages"] if m["is_deleted"] is True)
        assert deleted["conversation_id"] == conversation.id
        assert deleted["content"] == "This message was deleted"

    def test_get_messages_empty(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns empty list for conversation with no messages."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}/messages", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["messages"] == []
        assert data["has_more"] is False

    def test_get_messages_not_participant(
        self, client, db, test_instructor_with_availability, test_instructor_2, auth_headers
    ):
        """Returns 404 when user is not a participant."""
        conversation = Conversation(
            student_id=test_instructor_with_availability.id,
            instructor_id=test_instructor_2.id,
        )
        db.add(conversation)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}/messages", headers=auth_headers)
        assert res.status_code == 404

    def test_get_messages_pagination(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Respects limit parameter for pagination."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.flush()

        # Create multiple messages
        for i in range(5):
            message = Message(
                conversation_id=conversation.id,
                sender_id=test_student.id,
                content=f"Message {i}",
                message_type=MESSAGE_TYPE_USER,
                created_at=datetime.now(timezone.utc) + timedelta(minutes=i),
            )
            db.add(message)
        db.commit()

        res = client.get(f"/api/v1/conversations/{conversation.id}/messages?limit=3", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["messages"]) == 3
        assert data["has_more"] is True
        assert data["next_cursor"] is not None


class TestSendMessage:
    """Tests for POST /api/v1/conversations/{id}/messages."""

    def test_send_message_success(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Successfully sends a message."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.post(
            f"/api/v1/conversations/{conversation.id}/messages",
            json={"content": "Hello!"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert "created_at" in data

    def test_send_message_not_participant(
        self, client, db, test_instructor_with_availability, test_instructor_2, auth_headers
    ):
        """Returns 404 when user is not a participant."""
        conversation = Conversation(
            student_id=test_instructor_with_availability.id,
            instructor_id=test_instructor_2.id,
        )
        db.add(conversation)
        db.commit()

        res = client.post(
            f"/api/v1/conversations/{conversation.id}/messages",
            json={"content": "Hello!"},
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_send_message_empty_content(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Returns 422 for empty content."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.post(
            f"/api/v1/conversations/{conversation.id}/messages",
            json={"content": ""},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_send_message_updates_last_message_at(
        self, client, db, test_student, test_instructor_with_availability, auth_headers
    ):
        """Sending a message updates conversation's last_message_at."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        original_last_message_at = conversation.last_message_at

        res = client.post(
            f"/api/v1/conversations/{conversation.id}/messages",
            json={"content": "Hello!"},
            headers=auth_headers,
        )
        assert res.status_code == 200

        # Refresh the conversation
        db.expire(conversation)
        assert conversation.last_message_at is not None
        assert conversation.last_message_at != original_last_message_at

    def test_send_message_requires_auth(self, client, db, test_student, test_instructor_with_availability):
        """Returns 401 without authentication."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        res = client.post(
            f"/api/v1/conversations/{conversation.id}/messages",
            json={"content": "Hello!"},
        )
        assert res.status_code == 401
