"""
Coverage tests for messaging/sse_stream.py targeting missed lines.

Targets:
  - L148-161: stream message event types
  - L167: done message handling
  - L185-186: GeneratorExit during heartbeat
  - L268: unknown event type passthrough
"""

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

import pytest

from app.services.messaging.sse_stream import (
    format_message_from_db,
    format_redis_event,
)


@pytest.mark.unit
class TestFormatRedisEvent:
    """Cover format_redis_event branches for all event types."""

    def test_new_message_with_id(self):
        """L257-270: new_message event -> includes id field."""
        event = {
            "type": "new_message",
            "payload": {
                "message": {
                    "id": "MSG_01",
                    "sender_id": "USR_01",
                    "content": "Hello",
                },
            },
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "new_message"
        assert result["id"] == "MSG_01"
        parsed = json.loads(result["data"])
        assert parsed["is_mine"] is True

    def test_new_message_not_mine(self):
        """new_message from another user -> is_mine=False."""
        event = {
            "type": "new_message",
            "payload": {
                "message": {
                    "id": "MSG_01",
                    "sender_id": "USR_02",
                    "content": "Hello",
                },
            },
        }
        result = format_redis_event(event, "USR_01")
        parsed = json.loads(result["data"])
        assert parsed["is_mine"] is False

    def test_new_message_no_message_id(self):
        """new_message without message id -> no 'id' in SSE result."""
        event = {
            "type": "new_message",
            "payload": {
                "message": {
                    "sender_id": "USR_01",
                    "content": "Hello",
                },
            },
        }
        result = format_redis_event(event, "USR_01")
        assert "id" not in result

    def test_reaction_update(self):
        """L272-276: reaction_update event."""
        event = {
            "type": "reaction_update",
            "payload": {"reaction": "thumbs_up"},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "reaction_update"
        assert "id" not in result

    def test_read_receipt(self):
        """L278-282: read_receipt event."""
        event = {
            "type": "read_receipt",
            "payload": {"message_id": "MSG_01"},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "read_receipt"

    def test_typing_status(self):
        """L284-288: typing_status event."""
        event = {
            "type": "typing_status",
            "payload": {"is_typing": True},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "typing_status"

    def test_message_edited(self):
        """L290-294: message_edited event."""
        event = {
            "type": "message_edited",
            "payload": {"message_id": "MSG_01", "new_content": "Updated"},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "message_edited"

    def test_message_deleted(self):
        """L295-299: message_deleted event."""
        event = {
            "type": "message_deleted",
            "payload": {"message_id": "MSG_01"},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "message_deleted"

    def test_notification_update(self):
        """L300-304: notification_update event."""
        event = {
            "type": "notification_update",
            "payload": {"count": 5},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "notification_update"

    def test_unknown_event_type(self):
        """L306-312: unknown event type -> pass through."""
        event = {
            "type": "custom_event",
            "payload": {"data": "test"},
        }
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "custom_event"

    def test_missing_type_key(self):
        """L253: missing 'type' key -> defaults to 'unknown'."""
        event = {"payload": {"data": "test"}}
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "unknown"

    def test_missing_payload_key(self):
        """L254: missing 'payload' key -> uses entire event as payload."""
        event = {"type": "reaction_update"}
        result = format_redis_event(event, "USR_01")
        assert result["event"] == "reaction_update"


@pytest.mark.unit
class TestFormatMessageFromDb:
    """Cover format_message_from_db branches."""

    def test_normal_message(self):
        """Standard message formatting."""
        msg = MagicMock()
        msg.id = "MSG_01"
        msg.content = "Hello world"
        msg.sender_id = "USR_01"
        msg.booking_id = "BOOK_01"
        msg.conversation_id = "CONV_01"
        msg.message_type = "user"
        msg.__dict__ = {
            "id": "MSG_01",
            "content": "Hello world",
            "sender_id": "USR_01",
            "booking_id": "BOOK_01",
            "conversation_id": "CONV_01",
            "message_type": "user",
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "edited_at": None,
            "delivered_at": None,
        }

        result = format_message_from_db(msg, "USR_01")
        assert result["event"] == "new_message"
        assert result["id"] == "MSG_01"
        parsed = json.loads(result["data"])
        assert parsed["is_mine"] is True
        assert parsed["message"]["content"] == "Hello world"

    def test_deleted_message(self):
        """Deleted message -> content replaced."""
        msg = MagicMock()
        msg.id = "MSG_02"
        msg.content = "Secret content"
        msg.sender_id = "USR_02"
        msg.booking_id = "BOOK_01"
        msg.conversation_id = "CONV_01"
        msg.message_type = "user"
        msg.__dict__ = {
            "id": "MSG_02",
            "content": "Secret content",
            "sender_id": "USR_02",
            "booking_id": "BOOK_01",
            "conversation_id": "CONV_01",
            "message_type": "user",
            "is_deleted": True,
            "deleted_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
            "deleted_by": "USR_02",
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "edited_at": None,
            "delivered_at": None,
        }

        result = format_message_from_db(msg, "USR_01")
        parsed = json.loads(result["data"])
        assert parsed["message"]["content"] == "This message was deleted"
        assert parsed["message"]["is_deleted"] is True
        assert parsed["is_mine"] is False

    def test_message_without_optional_fields(self):
        """Message without optional fields in __dict__."""
        msg = MagicMock()
        msg.id = "MSG_03"
        msg.content = "Test"
        msg.sender_id = "USR_01"
        msg.booking_id = None
        msg.conversation_id = None
        msg.message_type = None
        msg.__dict__ = {
            "id": "MSG_03",
            "content": "Test",
            "sender_id": "USR_01",
            "booking_id": None,
        }

        result = format_message_from_db(msg, "USR_01")
        parsed = json.loads(result["data"])
        assert parsed["message"]["is_deleted"] is False
        assert parsed["message"]["message_type"] == "user"  # defaults to "user"

    def test_system_message_type(self):
        """Message with message_type='system'."""
        msg = MagicMock()
        msg.id = "MSG_04"
        msg.content = "System notification"
        msg.sender_id = "SYSTEM"
        msg.booking_id = "BOOK_01"
        msg.conversation_id = "CONV_01"
        msg.message_type = "system"
        msg.__dict__ = {
            "id": "MSG_04",
            "content": "System notification",
            "sender_id": "SYSTEM",
            "booking_id": "BOOK_01",
            "conversation_id": "CONV_01",
            "message_type": "system",
        }

        result = format_message_from_db(msg, "USR_01")
        parsed = json.loads(result["data"])
        assert parsed["message"]["message_type"] == "system"
        assert parsed["message_type"] == "system"
