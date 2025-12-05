# backend/tests/unit/services/messaging/test_publisher.py
"""Unit tests for publisher functions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.messaging.publisher import (
    publish_message_deleted,
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


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_conversation_participants():
    """Mock the _get_conversation_participants helper to return controlled participants."""
    with patch("app.services.messaging.publisher._get_conversation_participants") as mock:
        yield mock


class TestPublishNewMessage:
    """Tests for publish_new_message."""

    @pytest.mark.asyncio
    async def test_publish_new_message_sends_to_all_participants(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify message published to sender and all recipients."""
        # Mock participants from DB
        mock_conversation_participants.return_value = ["01SENDER", "01RECIPIENT"]

        await publish_new_message(
            db=mock_db,
            message_id="01MSG",
            content="Hello",
            sender_id="01SENDER",
            conversation_id="01CONVERSATION",
            created_at=datetime.now(timezone.utc),
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both sender and recipient
        assert "01SENDER" in user_ids
        assert "01RECIPIENT" in user_ids

    @pytest.mark.asyncio
    async def test_publish_new_message_event_structure(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify event structure is correct."""
        mock_conversation_participants.return_value = ["01SENDER", "01RECIPIENT"]
        created_at = datetime.now(timezone.utc)

        await publish_new_message(
            db=mock_db,
            message_id="01MSG",
            content="Hello world",
            sender_id="01SENDER",
            conversation_id="01CONVERSATION",
            created_at=created_at,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "new_message"
        assert event["schema_version"] == 1
        assert event["payload"]["message"]["id"] == "01MSG"
        assert event["payload"]["message"]["content"] == "Hello world"
        assert event["payload"]["conversation_id"] == "01CONVERSATION"

    @pytest.mark.asyncio
    async def test_publish_new_message_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_new_message(
            db=mock_db,
            message_id="01MSG",
            content="Hello",
            sender_id="01SENDER",
            conversation_id="01CONVERSATION",
            created_at=datetime.now(timezone.utc),
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()


class TestPublishTypingStatus:
    """Tests for publish_typing_status."""

    @pytest.mark.asyncio
    async def test_publish_typing_excludes_typer(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify typing status not sent to the person typing."""
        mock_conversation_participants.return_value = ["01TYPER", "01OTHER"]

        await publish_typing_status(
            db=mock_db,
            conversation_id="01CONVERSATION",
            user_id="01TYPER",
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
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify typing status event structure."""
        mock_conversation_participants.return_value = ["01TYPER", "01OTHER"]

        await publish_typing_status(
            db=mock_db,
            conversation_id="01CONVERSATION",
            user_id="01TYPER",
            is_typing=True,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "typing_status"
        assert event["payload"]["conversation_id"] == "01CONVERSATION"
        assert event["payload"]["user_id"] == "01TYPER"
        assert event["payload"]["is_typing"] is True

    @pytest.mark.asyncio
    async def test_publish_typing_status_is_typing_false(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify typing stopped event."""
        mock_conversation_participants.return_value = ["01TYPER", "01OTHER"]

        await publish_typing_status(
            db=mock_db,
            conversation_id="01CONVERSATION",
            user_id="01TYPER",
            is_typing=False,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["payload"]["is_typing"] is False

    @pytest.mark.asyncio
    async def test_publish_typing_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_typing_status(
            db=mock_db,
            conversation_id="01CONVERSATION",
            user_id="01TYPER",
            is_typing=True,
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()


class TestPublishReactionUpdate:
    """Tests for publish_reaction_update."""

    @pytest.mark.asyncio
    async def test_publish_reaction_update_sends_to_all(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify reaction update sent to all participants including reactor."""
        mock_conversation_participants.return_value = ["01REACTOR", "01OTHER"]

        await publish_reaction_update(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="👍",
            action="added",
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both reactor (for multi-device) and other
        assert "01REACTOR" in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_reaction_update_event_structure(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify reaction update event structure."""
        mock_conversation_participants.return_value = ["01REACTOR", "01OTHER"]

        await publish_reaction_update(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="👍",
            action="added",
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "reaction_update"
        assert event["payload"]["conversation_id"] == "01CONVERSATION"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["emoji"] == "👍"
        assert event["payload"]["action"] == "added"

    @pytest.mark.asyncio
    async def test_publish_reaction_removed(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify reaction removed event."""
        mock_conversation_participants.return_value = ["01REACTOR", "01OTHER"]

        await publish_reaction_update(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="❤️",
            action="removed",
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["payload"]["action"] == "removed"

    @pytest.mark.asyncio
    async def test_publish_reaction_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_reaction_update(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            user_id="01REACTOR",
            emoji="👍",
            action="added",
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()


class TestPublishMessageEdited:
    """Tests for publish_message_edited."""

    @pytest.mark.asyncio
    async def test_publish_message_edited_sends_to_all(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify edit notification sent to all participants."""
        mock_conversation_participants.return_value = ["01EDITOR", "01OTHER"]
        edited_at = datetime.now(timezone.utc)

        await publish_message_edited(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=edited_at,
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both editor and other
        assert "01EDITOR" in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_message_edited_event_structure(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify edit event structure."""
        mock_conversation_participants.return_value = ["01EDITOR", "01OTHER"]
        edited_at = datetime.now(timezone.utc)

        await publish_message_edited(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=edited_at,
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "message_edited"
        assert event["payload"]["conversation_id"] == "01CONVERSATION"
        assert event["payload"]["message_id"] == "01MSG"
        assert event["payload"]["new_content"] == "Updated content"
        assert event["payload"]["editor_id"] == "01EDITOR"

    @pytest.mark.asyncio
    async def test_publish_message_edited_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_message_edited(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            new_content="Updated content",
            editor_id="01EDITOR",
            edited_at=datetime.now(timezone.utc),
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()


class TestPublishReadReceipt:
    """Tests for publish_read_receipt."""

    @pytest.mark.asyncio
    async def test_publish_read_receipt_excludes_reader(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify read receipt not sent to the reader."""
        mock_conversation_participants.return_value = ["01READER", "01OTHER"]

        await publish_read_receipt(
            db=mock_db,
            conversation_id="01CONVERSATION",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2"],
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should NOT include the reader
        assert "01READER" not in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_read_receipt_event_structure(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify read receipt event structure."""
        mock_conversation_participants.return_value = ["01READER", "01OTHER"]

        await publish_read_receipt(
            db=mock_db,
            conversation_id="01CONVERSATION",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2", "01MSG3"],
        )

        call_args = mock_pubsub_manager.publish_to_users.call_args
        event = call_args[0][1]

        assert event["type"] == "read_receipt"
        assert event["payload"]["conversation_id"] == "01CONVERSATION"
        assert event["payload"]["reader_id"] == "01READER"
        assert event["payload"]["message_ids"] == ["01MSG1", "01MSG2", "01MSG3"]
        assert "read_at" in event["payload"]

    @pytest.mark.asyncio
    async def test_publish_read_receipt_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_read_receipt(
            db=mock_db,
            conversation_id="01CONVERSATION",
            reader_id="01READER",
            message_ids=["01MSG1", "01MSG2"],
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()


class TestPublishMessageDeleted:
    """Tests for publish_message_deleted."""

    @pytest.mark.asyncio
    async def test_publish_message_deleted_sends_to_all(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify delete notification sent to all participants."""
        mock_conversation_participants.return_value = ["01DELETER", "01OTHER"]

        await publish_message_deleted(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            deleted_by="01DELETER",
        )

        mock_pubsub_manager.publish_to_users.assert_called_once()
        call_args = mock_pubsub_manager.publish_to_users.call_args
        user_ids = call_args[0][0]

        # Should include both deleter and other
        assert "01DELETER" in user_ids
        assert "01OTHER" in user_ids

    @pytest.mark.asyncio
    async def test_publish_message_deleted_no_publish_if_conversation_not_found(
        self, mock_pubsub_manager: AsyncMock, mock_db: MagicMock, mock_conversation_participants
    ) -> None:
        """Verify no publish happens if conversation not found."""
        mock_conversation_participants.return_value = []  # Conversation not found

        await publish_message_deleted(
            db=mock_db,
            conversation_id="01CONVERSATION",
            message_id="01MSG",
            deleted_by="01DELETER",
        )

        mock_pubsub_manager.publish_to_users.assert_not_called()
