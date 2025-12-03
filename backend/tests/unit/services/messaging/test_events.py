# backend/tests/unit/services/messaging/test_events.py
"""Unit tests for messaging event builders."""

from datetime import datetime, timezone

from app.services.messaging.events import (
    SCHEMA_VERSION,
    EventType,
    build_event,
    build_message_edited_event,
    build_new_message_event,
    build_reaction_update_event,
    build_read_receipt_event,
    build_typing_status_event,
)


class TestBuildEvent:
    """Tests for the base build_event function."""

    def test_build_event_structure(self) -> None:
        """Verify event has required fields."""
        event = build_event(EventType.NEW_MESSAGE, {"test": "data"})

        assert event["type"] == "new_message"
        assert event["schema_version"] == SCHEMA_VERSION
        assert "timestamp" in event
        assert event["payload"] == {"test": "data"}

    def test_build_event_timestamp_is_utc_iso(self) -> None:
        """Verify timestamp is in ISO 8601 format with UTC timezone."""
        event = build_event(EventType.TYPING_STATUS, {})

        timestamp = event["timestamp"]
        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_build_event_preserves_payload(self) -> None:
        """Verify complex payloads are preserved."""
        payload = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42,
            "boolean": True,
            "null": None,
        }
        event = build_event(EventType.NEW_MESSAGE, payload)

        assert event["payload"] == payload


class TestBuildNewMessageEvent:
    """Tests for build_new_message_event."""

    def test_build_new_message_event_structure(self) -> None:
        """Verify new_message event structure."""
        created_at = datetime.now(timezone.utc)
        event = build_new_message_event(
            message_id="01ABC123",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01SENDER", "01RECIPIENT"],
            created_at=created_at,
        )

        assert event["type"] == "new_message"
        assert event["schema_version"] == 1
        assert event["payload"]["message"]["id"] == "01ABC123"
        assert event["payload"]["message"]["content"] == "Hello"
        assert event["payload"]["message"]["sender_id"] == "01SENDER"
        assert event["payload"]["message"]["booking_id"] == "01BOOKING"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["sender_id"] == "01SENDER"
        assert event["payload"]["recipient_ids"] == ["01SENDER", "01RECIPIENT"]

    def test_build_new_message_event_with_reactions(self) -> None:
        """Verify reactions are included when provided."""
        created_at = datetime.now(timezone.utc)
        reactions = [{"emoji": "👍", "user_id": "01USER"}]
        event = build_new_message_event(
            message_id="01ABC123",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01RECIPIENT"],
            created_at=created_at,
            reactions=reactions,
        )

        assert event["payload"]["message"]["reactions"] == reactions

    def test_build_new_message_event_default_reactions(self) -> None:
        """Verify reactions default to empty list."""
        created_at = datetime.now(timezone.utc)
        event = build_new_message_event(
            message_id="01ABC123",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01RECIPIENT"],
            created_at=created_at,
        )

        assert event["payload"]["message"]["reactions"] == []

    def test_build_new_message_event_edited_at_is_none(self) -> None:
        """Verify new messages have edited_at as None."""
        created_at = datetime.now(timezone.utc)
        event = build_new_message_event(
            message_id="01ABC123",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=[],
            created_at=created_at,
        )

        assert event["payload"]["message"]["edited_at"] is None


class TestBuildTypingStatusEvent:
    """Tests for build_typing_status_event."""

    def test_build_typing_status_event_typing_true(self) -> None:
        """Verify typing_status event with is_typing=True."""
        event = build_typing_status_event(
            conversation_id="01BOOKING",
            user_id="01USER",
            is_typing=True,
        )

        assert event["type"] == "typing_status"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["user_id"] == "01USER"
        assert event["payload"]["is_typing"] is True

    def test_build_typing_status_event_typing_false(self) -> None:
        """Verify typing_status event with is_typing=False."""
        event = build_typing_status_event(
            conversation_id="01BOOKING",
            user_id="01USER",
            is_typing=False,
        )

        assert event["payload"]["is_typing"] is False

    def test_build_typing_status_event_default_is_typing(self) -> None:
        """Verify is_typing defaults to True."""
        event = build_typing_status_event(
            conversation_id="01BOOKING",
            user_id="01USER",
        )

        assert event["payload"]["is_typing"] is True


class TestBuildReactionUpdateEvent:
    """Tests for build_reaction_update_event."""

    def test_build_reaction_update_event_added(self) -> None:
        """Verify reaction_update event with action=added."""
        event = build_reaction_update_event(
            conversation_id="01BOOKING",
            message_id="01MSG",
            user_id="01USER",
            emoji="👍",
            action="added",
        )

        assert event["type"] == "reaction_update"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["user_id"] == "01USER"
        assert event["payload"]["emoji"] == "👍"
        assert event["payload"]["action"] == "added"

    def test_build_reaction_update_event_removed(self) -> None:
        """Verify reaction_update event with action=removed."""
        event = build_reaction_update_event(
            conversation_id="01BOOKING",
            message_id="01MSG",
            user_id="01USER",
            emoji="❤️",
            action="removed",
        )

        assert event["payload"]["action"] == "removed"
        assert event["payload"]["emoji"] == "❤️"


class TestBuildMessageEditedEvent:
    """Tests for build_message_edited_event."""

    def test_build_message_edited_event_structure(self) -> None:
        """Verify message_edited event structure."""
        edited_at = datetime.now(timezone.utc)
        event = build_message_edited_event(
            conversation_id="01BOOKING",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=edited_at,
        )

        assert event["type"] == "message_edited"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["new_content"] == "Updated content"
        assert event["payload"]["editor_id"] == "01EDITOR"
        assert event["payload"]["edited_at"] == edited_at.isoformat()


class TestBuildReadReceiptEvent:
    """Tests for build_read_receipt_event."""

    def test_build_read_receipt_event_structure(self) -> None:
        """Verify read_receipt event structure."""
        event = build_read_receipt_event(
            conversation_id="01BOOKING",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2", "01MSG3"],
        )

        assert event["type"] == "read_receipt"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["reader_id"] == "01READER"
        assert event["payload"]["message_ids"] == ["01MSG1", "01MSG2", "01MSG3"]
        assert "read_at" in event["payload"]

    def test_build_read_receipt_event_empty_message_ids(self) -> None:
        """Verify read_receipt event with empty message_ids."""
        event = build_read_receipt_event(
            conversation_id="01BOOKING",
            reader_id="01READER",
            message_ids=[],
        )

        assert event["payload"]["message_ids"] == []
