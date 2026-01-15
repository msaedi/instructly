# tests/unit/services/messaging/test_sse_stream.py
"""
Tests for Redis-only SSE stream (v3.1 architecture).

Tests:
- Event formatting (new_message gets id:, others don't)
- Message catch-up from database
- Heartbeat injection
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.repositories.message_repository import MessageRepository
from app.services.messaging.sse_stream import (
    create_sse_stream,
    ensure_db_health,
    fetch_messages_after,
    format_message_from_db,
    format_redis_event,
    publish_to_user,
)


class TestFormatRedisEvent:
    """Test SSE event formatting from Redis events."""

    def test_new_message_has_id(self) -> None:
        """new_message events should include SSE id field."""
        event = {
            "type": "new_message",
            "schema_version": 1,
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": {
                "message": {
                    "id": "01ABC123DEF456GH789",
                    "content": "Hello",
                    "sender_id": "01USER123",
                    "booking_id": "01BOOKING123",
                },
                "conversation_id": "01BOOKING123",
            },
        }
        user_id = "01OTHER_USER"

        result = format_redis_event(event, user_id)

        assert result["id"] == "01ABC123DEF456GH789"
        assert result["event"] == "new_message"
        assert "data" in result

        # Verify is_mine flag is added
        data = json.loads(result["data"])
        assert data["is_mine"] is False

    def test_new_message_is_mine_flag(self) -> None:
        """new_message should set is_mine=True when sender matches user."""
        event = {
            "type": "new_message",
            "payload": {
                "message": {
                    "id": "01ABC123",
                    "content": "Hello",
                    "sender_id": "01USER123",
                },
            },
        }
        user_id = "01USER123"  # Same as sender

        result = format_redis_event(event, user_id)
        data = json.loads(result["data"])

        assert data["is_mine"] is True

    def test_reaction_update_no_id(self) -> None:
        """reaction_update events should NOT include SSE id field."""
        event = {
            "type": "reaction_update",
            "payload": {
                "message_id": "01ABC123",
                "user_id": "01USER123",
                "emoji": "👍",
                "action": "added",
            },
        }
        user_id = "01OTHER_USER"

        result = format_redis_event(event, user_id)

        assert "id" not in result
        assert result["event"] == "reaction_update"

    def test_read_receipt_no_id(self) -> None:
        """read_receipt events should NOT include SSE id field."""
        event = {
            "type": "read_receipt",
            "payload": {
                "conversation_id": "01BOOKING123",
                "reader_id": "01USER123",
                "message_ids": ["01MSG1", "01MSG2"],
            },
        }
        user_id = "01OTHER_USER"

        result = format_redis_event(event, user_id)

        assert "id" not in result
        assert result["event"] == "read_receipt"

    def test_typing_status_no_id(self) -> None:
        """typing_status events should NOT include SSE id field."""
        event = {
            "type": "typing_status",
            "payload": {
                "conversation_id": "01BOOKING123",
                "user_id": "01USER123",
                "is_typing": True,
            },
        }
        user_id = "01OTHER_USER"

        result = format_redis_event(event, user_id)

        assert "id" not in result
        assert result["event"] == "typing_status"

    def test_message_edited_no_id(self) -> None:
        """message_edited events should NOT include SSE id field."""
        event = {
            "type": "message_edited",
            "payload": {
                "conversation_id": "01BOOKING123",
                "message_id": "01MSG123",
                "new_content": "Updated content",
                "edited_at": "2024-01-01T12:00:00Z",
            },
        }
        user_id = "01OTHER_USER"

        result = format_redis_event(event, user_id)

        assert "id" not in result
        assert result["event"] == "message_edited"

    def test_unknown_event_type_no_id(self) -> None:
        """Unknown event types should pass through without id."""
        event = {
            "type": "custom_event",
            "payload": {"data": "test"},
        }
        user_id = "01USER123"

        result = format_redis_event(event, user_id)

        assert "id" not in result
        assert result["event"] == "custom_event"

    def test_message_deleted_event(self) -> None:
        event = {
            "type": "message_deleted",
            "payload": {"message_id": "01MSG"},
        }

        result = format_redis_event(event, "01USER")

        assert result["event"] == "message_deleted"

    def test_notification_update_event(self) -> None:
        event = {
            "type": "notification_update",
            "payload": {"count": 1},
        }

        result = format_redis_event(event, "01USER")

        assert result["event"] == "notification_update"


class TestFormatMessageFromDb:
    """Test message formatting for catch-up from database."""

    def test_includes_id_field(self) -> None:
        """Catch-up messages should include SSE id field."""
        message = Mock()
        message.id = "01ABC123DEF456GH789"
        message.content = "Hello"
        message.sender_id = "01SENDER123"
        message.booking_id = "01BOOKING123"
        message.conversation_id = "01CONVERSATION123"
        message.message_type = "user"
        message.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message.edited_at = None

        user_id = "01OTHER_USER"
        result = format_message_from_db(message, user_id)

        assert result["id"] == "01ABC123DEF456GH789"
        assert result["event"] == "new_message"

    def test_is_mine_flag_false(self) -> None:
        """is_mine should be False when user is not sender."""
        message = Mock()
        message.id = "01MSG123"
        message.content = "Hello"
        message.sender_id = "01SENDER123"
        message.booking_id = "01BOOKING123"
        message.conversation_id = "01CONVERSATION123"
        message.message_type = "user"
        message.created_at = datetime.now(timezone.utc)
        message.edited_at = None

        user_id = "01OTHER_USER"  # Different from sender
        result = format_message_from_db(message, user_id)
        data = json.loads(result["data"])

        assert data["is_mine"] is False

    def test_is_mine_flag_true(self) -> None:
        """is_mine should be True when user is sender."""
        message = Mock()
        message.id = "01MSG123"
        message.content = "Hello"
        message.sender_id = "01SENDER123"
        message.booking_id = "01BOOKING123"
        message.conversation_id = "01CONVERSATION123"
        message.message_type = "user"
        message.created_at = datetime.now(timezone.utc)
        message.edited_at = None

        user_id = "01SENDER123"  # Same as sender
        result = format_message_from_db(message, user_id)
        data = json.loads(result["data"])

        assert data["is_mine"] is True

    def test_includes_message_data(self) -> None:
        """Catch-up messages should include all message fields."""
        message = Mock()
        message.id = "01MSG123"
        message.content = "Test content"
        message.sender_id = "01SENDER123"
        message.booking_id = "01BOOKING123"
        message.conversation_id = "01CONVERSATION123"
        message.message_type = "user"
        message.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message.edited_at = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)

        result = format_message_from_db(message, "01USER")
        data = json.loads(result["data"])

        assert data["message"]["id"] == "01MSG123"
        assert data["message"]["content"] == "Test content"
        assert data["message"]["sender_id"] == "01SENDER123"
        assert data["message"]["booking_id"] == "01BOOKING123"
        assert data["message"]["created_at"] == "2024-01-01T12:00:00+00:00"
        assert data["message"]["edited_at"] == "2024-01-01T13:00:00+00:00"
        assert data["conversation_id"] == "01CONVERSATION123"


class TestLastEventIdBehavior:
    """Test that Last-Event-ID only works with new_message events.

    This is critical for the v3.1 architecture:
    - new_message events get id: field → browser tracks for Last-Event-ID
    - Other events don't get id: → browser doesn't track them

    This means on reconnect, only missed MESSAGES are caught up,
    not reactions/read receipts/typing (which are ephemeral anyway).
    """

    def test_only_new_message_has_id(self) -> None:
        """Verify only new_message events have id field."""
        events = [
            {"type": "new_message", "payload": {"message": {"id": "01MSG"}}},
            {"type": "reaction_update", "payload": {}},
            {"type": "read_receipt", "payload": {}},
            {"type": "typing_status", "payload": {}},
            {"type": "message_edited", "payload": {}},
        ]

        for event in events:
            result = format_redis_event(event, "01USER")
            if event["type"] == "new_message":
                assert "id" in result, "new_message should have id"
            else:
                assert "id" not in result, f"{event['type']} should NOT have id"


def test_sse_sets_id_only_for_messages() -> None:
    """Explicit check that only new_message events include SSE id field."""
    user_id = "01USER"
    events = {
        "new_message": {"type": "new_message", "payload": {"message": {"id": "01MSG"}}},
        "reaction_update": {"type": "reaction_update", "payload": {"message_id": "01MSG"}},
        "typing_status": {"type": "typing_status", "payload": {"conversation_id": "01BOOK"}},
        "read_receipt": {
            "type": "read_receipt",
            "payload": {"conversation_id": "01BOOK", "message_ids": ["01MSG"]},
        },
        "heartbeat": {"type": "heartbeat", "payload": {"ts": "now"}},
    }

    results = {name: format_redis_event(evt, user_id) for name, evt in events.items()}

    assert "id" in results["new_message"]
    assert "id" not in results["reaction_update"]
    assert "id" not in results["typing_status"]
    assert "id" not in results["read_receipt"]
    assert "id" not in results["heartbeat"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_fetch_messages_after_returns_newer_messages(db, test_booking, test_student) -> None:
    """DB catch-up returns only messages newer than the provided Last-Event-ID."""
    repo = MessageRepository(db)
    from app.repositories.conversation_repository import ConversationRepository

    conversation_repo = ConversationRepository(db)
    conversation, _ = conversation_repo.get_or_create(
        student_id=str(test_student.id),
        instructor_id=str(test_booking.instructor_id),
    )

    msg1 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="First",
    )
    msg2 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="Second",
    )
    msg3 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="Third",
    )
    db.commit()

    results = await fetch_messages_after(
        db=db,
        user_id=str(test_student.id),
        after_message_id=str(msg1.id),
    )

    returned_ids = [str(m.id) for m in results]
    assert returned_ids == [str(msg2.id), str(msg3.id)]
    assert all(m.booking_id == test_booking.id for m in results)


class TestSseStreamFailures:
    @pytest.mark.asyncio
    async def test_ensure_db_health_raises_http_exception(self) -> None:
        class BadDb:
            def execute(self, _stmt):
                raise RuntimeError("db down")

        with pytest.raises(Exception) as exc:
            await ensure_db_health(BadDb())

        assert "Service temporarily unavailable" in str(exc.value)

    @pytest.mark.asyncio
    async def test_stream_handles_invalid_json(self, monkeypatch) -> None:
        class FakeEvent:
            def __init__(self, message: str) -> None:
                self.message = message

        class FakeSubscriber:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if hasattr(self, "_done"):
                    raise StopAsyncIteration
                self._done = True
                return FakeEvent("not-json")

        @asynccontextmanager
        async def fake_subscribe(channel: str):
            yield FakeSubscriber()

        mock_broadcast = MagicMock()
        mock_broadcast.subscribe = fake_subscribe
        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", lambda: mock_broadcast)

        events = []
        async for event in create_sse_stream("01USER", missed_messages=None):
            events.append(event)

        assert events[0]["event"] == "connected"

    @pytest.mark.asyncio
    async def test_stream_handles_reader_error(self, monkeypatch) -> None:
        class ErrorSubscriber:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ValueError("boom")

        @asynccontextmanager
        async def fake_subscribe(channel: str):
            yield ErrorSubscriber()

        mock_broadcast = MagicMock()
        mock_broadcast.subscribe = fake_subscribe
        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", lambda: mock_broadcast)

        events = []
        async for event in create_sse_stream("01USER", missed_messages=None):
            events.append(event)

        assert events[0]["event"] == "connected"

    @pytest.mark.asyncio
    async def test_stream_generator_cleanup_runtime_error(self, monkeypatch) -> None:
        def _raise_generator() -> None:
            raise RuntimeError("generator is closing")

        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", _raise_generator)

        events = []
        async for event in create_sse_stream("01USER", missed_messages=None):
            events.append(event)

        assert events[0]["event"] == "connected"

    @pytest.mark.asyncio
    async def test_stream_unexpected_error_is_raised(self, monkeypatch) -> None:
        def _raise_error() -> None:
            raise ValueError("unexpected")

        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", _raise_error)

        with pytest.raises(ValueError):
            async for _event in create_sse_stream("01USER", missed_messages=None):
                pass


class TestPublishToUser:
    @pytest.mark.asyncio
    async def test_publish_to_user_success(self, monkeypatch) -> None:
        mock_broadcast = MagicMock()
        mock_broadcast.publish = AsyncMock()

        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", lambda: mock_broadcast)

        await publish_to_user("01USER", {"type": "ping"})

        mock_broadcast.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_to_user_handles_error(self, monkeypatch) -> None:
        mock_broadcast = MagicMock()
        mock_broadcast.publish = AsyncMock(side_effect=Exception("boom"))

        monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", lambda: mock_broadcast)

        await publish_to_user("01USER", {"type": "ping"})


class TestFetchMessagesAfter:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_conversations(self, db, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.repositories.conversation_repository.ConversationRepository.find_for_user",
            lambda _self, _user_id, _limit, _offset: [],
        )

        result = await fetch_messages_after(db, "01USER", "01MSG")

        assert result == []
