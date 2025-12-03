# backend/tests/unit/services/messaging/test_publisher.py
"""Unit tests for publisher functions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.messaging.publisher import (
    publish_message_edited,
    publish_new_message,
    publish_reaction_update,
    publish_read_receipt,
    publish_typing_status,
)


@pytest.fixture
def mock_pubsub_manager() -> AsyncMock:
    """Mock the pubsub manager."""
    with patch("app.services.messaging.publisher.pubsub_manager") as mock:
        mock.publish_to_users = AsyncMock(return_value={})
        yield mock


class TestPublishNewMessage:
    """Tests for publish_new_message."""

    @pytest.mark.asyncio
    async def test_publish_new_message_sends_to_all_participants(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify message published to sender and all recipients."""
        await publish_new_message(
            message_id="01MSG",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01SENDER", "01RECIPIENT"],
            created_at=datetime.now(timezone.utc),
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both sender and recipient (deduplicated)
        assert "01SENDER" in user_ids
        assert "01RECIPIENT" in user_ids

    @pytest.mark.asyncio
    async def test_publish_new_message_event_structure(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify event structure is correct."""
        created_at = datetime.now(timezone.utc)
        await publish_new_message(
            message_id="01MSG",
            content="Hello world",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01RECIPIENT"],
            created_at=created_at,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "new_message"
        assert event["schema_version"] == 1
        assert event["payload"]["message"]["id"] == "01MSG"
        assert event["payload"]["message"]["content"] == "Hello world"
        assert event["payload"]["conversation_id"] == "01BOOKING"

    @pytest.mark.asyncio
    async def test_publish_new_message_deduplicates_sender(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify sender is not duplicated when in recipient list."""
        await publish_new_message(
            message_id="01MSG",
            content="Hello",
            sender_id="01SENDER",
            booking_id="01BOOKING",
            recipient_ids=["01SENDER", "01RECIPIENT"],  # Sender appears in recipients
            created_at=datetime.now(timezone.utc),
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should be deduplicated
        assert user_ids.count("01SENDER") == 1


class TestPublishTypingStatus:
    """Tests for publish_typing_status."""

    @pytest.mark.asyncio
    async def test_publish_typing_excludes_typer(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify typing status not sent to the person typing."""
        await publish_typing_status(
            conversation_id="01BOOKING",
            user_id="01TYPER",
            recipient_ids=["01TYPER", "01OTHER"],
            is_typing=True,
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should NOT include the typer
        assert "01TYPER" not in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_typing_status_event_structure(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify typing status event structure."""
        await publish_typing_status(
            conversation_id="01BOOKING",
            user_id="01TYPER",
            recipient_ids=["01OTHER"],
            is_typing=True,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "typing_status"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["user_id"] == "01TYPER"
        assert event["payload"]["is_typing"] is True

    @pytest.mark.asyncio
    async def test_publish_typing_status_is_typing_false(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify typing stopped event."""
        await publish_typing_status(
            conversation_id="01BOOKING",
            user_id="01TYPER",
            recipient_ids=["01OTHER"],
            is_typing=False,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["payload"]["is_typing"] is False


class TestPublishReactionUpdate:
    """Tests for publish_reaction_update."""

    @pytest.mark.asyncio
    async def test_publish_reaction_update_sends_to_all(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify reaction update sent to all participants including reactor."""
        await publish_reaction_update(
            conversation_id="01BOOKING",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="👍",
            action="added",
            recipient_ids=["01OTHER"],
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both reactor (for multi-device) and other
        assert "01REACTOR" in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_reaction_update_event_structure(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify reaction update event structure."""
        await publish_reaction_update(
            conversation_id="01BOOKING",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="👍",
            action="added",
            recipient_ids=["01OTHER"],
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "reaction_update"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["emoji"] == "👍"
        assert event["payload"]["action"] == "added"

    @pytest.mark.asyncio
    async def test_publish_reaction_removed(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify reaction removed event."""
        await publish_reaction_update(
            conversation_id="01BOOKING",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="❤️",
            action="removed",
            recipient_ids=["01OTHER"],
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["payload"]["action"] == "removed"


class TestPublishMessageEdited:
    """Tests for publish_message_edited."""

    @pytest.mark.asyncio
    async def test_publish_message_edited_sends_to_all(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify edit notification sent to all participants."""
        edited_at = datetime.now(timezone.utc)
        await publish_message_edited(
            conversation_id="01BOOKING",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=edited_at,
            recipient_ids=["01OTHER"],
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both editor and other
        assert "01EDITOR" in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_message_edited_event_structure(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify edit event structure."""
        edited_at = datetime.now(timezone.utc)
        await publish_message_edited(
            conversation_id="01BOOKING",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=edited_at,
            recipient_ids=["01OTHER"],
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "message_edited"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["new_content"] == "Updated content"
        assert event["payload"]["editor_id"] == "01EDITOR"


class TestPublishReadReceipt:
    """Tests for publish_read_receipt."""

    @pytest.mark.asyncio
    async def test_publish_read_receipt_excludes_reader(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify read receipt not sent to the reader."""
        await publish_read_receipt(
            conversation_id="01BOOKING",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2"],
            recipient_ids=["01READER", "01OTHER"],
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should NOT include the reader
        assert "01READER" not in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_read_receipt_event_structure(
        self, mock_pubsub_manager: AsyncMock
    ) -> None:
        """Verify read receipt event structure."""
        await publish_read_receipt(
            conversation_id="01BOOKING",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2", "01MSG3"],
            recipient_ids=["01OTHER"],
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "read_receipt"
        assert event["payload"]["conversation_id"] == "01BOOKING"
        assert event["payload"]["reader_id"] == "01READER"
        assert event["payload"]["message_ids"] == ["01MSG1", "01MSG2", "01MSG3"]
        assert "read_at" in event["payload"]
