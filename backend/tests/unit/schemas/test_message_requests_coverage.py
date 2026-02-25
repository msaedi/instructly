"""Tests for app/schemas/message_requests.py — coverage gap L29."""
from __future__ import annotations

import pytest

from app.schemas.message_requests import MarkMessagesReadRequest


@pytest.mark.unit
class TestMarkMessagesReadRequestCoverage:
    """Cover the model_validator that checks mutual exclusivity."""

    def test_both_fields_raises(self) -> None:
        """L29: providing both conversation_id AND message_ids raises ValueError."""
        with pytest.raises(Exception, match="not both"):
            MarkMessagesReadRequest(
                conversation_id="conv-001",
                message_ids=["msg-001", "msg-002"],
            )

    def test_neither_field_raises(self) -> None:
        """L27: providing neither raises ValueError."""
        with pytest.raises(Exception, match="must be provided"):
            MarkMessagesReadRequest()

    def test_only_conversation_id_ok(self) -> None:
        req = MarkMessagesReadRequest(conversation_id="conv-001")
        assert req.conversation_id == "conv-001"
        assert req.message_ids is None

    def test_only_message_ids_ok(self) -> None:
        req = MarkMessagesReadRequest(message_ids=["msg-001"])
        assert req.message_ids == ["msg-001"]
        assert req.conversation_id is None

    def test_empty_message_ids_raises(self) -> None:
        """Empty list is falsy, so it should require conversation_id."""
        with pytest.raises(Exception, match="must be provided"):
            MarkMessagesReadRequest(message_ids=[])

    def test_conversation_id_empty_string_raises(self) -> None:
        """Empty string is falsy, so it should be rejected."""
        with pytest.raises(Exception, match="must be provided"):
            MarkMessagesReadRequest(conversation_id="")

    def test_both_fields_empty_raises(self) -> None:
        """Both empty string and empty list are falsy."""
        with pytest.raises(Exception, match="must be provided"):
            MarkMessagesReadRequest(conversation_id="", message_ids=[])
