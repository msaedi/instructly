"""
Bug-hunting edge-case tests for conversation_service.py targeting uncovered lines/branches.

Covers lines: 148, 214->217, 233, 242, 307->310, 311->317, 652,
714->712, 732->735
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest

from app.services.conversation_service import ConversationService


class _Conversation:
    def __init__(
        self,
        conversation_id: str,
        student_id: str,
        instructor_id: str,
        last_message_at: Optional[datetime] = None,
    ):
        self.id = conversation_id
        self.student_id = student_id
        self.instructor_id = instructor_id
        self.last_message_at = last_message_at

    def is_participant(self, user_id: str) -> bool:
        return user_id in (self.student_id, self.instructor_id)


class _Message:
    def __init__(
        self,
        message_id: str,
        content: str,
        sender_id: str,
        message_type: str = "user",
        booking_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        edited_at: Optional[datetime] = None,
        is_deleted: bool = False,
        delivered_at: Optional[datetime] = None,
        read_by: Any = None,
        reaction_list: Any = None,
        instructor_service: Any = None,
    ):
        self.id = message_id
        self.content = content
        self.sender_id = sender_id
        self.message_type = message_type
        self.booking_id = booking_id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.edited_at = edited_at
        self.is_deleted = is_deleted
        self.delivered_at = delivered_at
        self.read_by = read_by
        self.reaction_list = reaction_list


@pytest.fixture
def db():
    db = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture
def service(db):
    conv_repo = Mock()
    msg_repo = Mock()
    booking_repo = Mock()
    notification_service = Mock()
    svc = ConversationService(
        db,
        conversation_repository=conv_repo,
        message_repository=msg_repo,
        booking_repository=booking_repo,
        notification_service=notification_service,
    )
    svc.conversation_state_repository = Mock()
    return svc


# ---------------------------------------------------------------------------
# L148: get_or_create_conversation — delegates to repository
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetOrCreateConversation:
    """Test get_or_create_conversation delegates to repository."""

    def test_delegates_to_repo(self, service):
        """L148: calls conversation_repository.get_or_create."""
        conv = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_or_create.return_value = (conv, True)

        result_conv, created = service.get_or_create_conversation("s1", "i1")
        assert result_conv == conv
        assert created is True
        service.conversation_repository.get_or_create.assert_called_once_with(
            student_id="s1", instructor_id="i1"
        )


# ---------------------------------------------------------------------------
# L214->217: list_conversations_for_user — no last_message_at on last conv
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestListConversationsForUserEdge:
    """Test list_conversations_for_user edge cases."""

    def test_no_last_message_at_cursor_is_none(self, service):
        """L214->217: last conversation has no last_message_at => cursor is None."""
        conv1 = _Conversation("conv-1", "s1", "i1", last_message_at=None)
        conv2 = _Conversation("conv-2", "s2", "i2", last_message_at=None)
        # Return 2 items for limit=1 (triggers has_more)
        service.conversation_repository.find_for_user_excluding_states.return_value = [
            conv1, conv2
        ]

        conversations, next_cursor = service.list_conversations_for_user(
            "user-1", state_filter="active", limit=1
        )
        assert len(conversations) == 1
        # No last_message_at => cursor should be None
        assert next_cursor is None

    def test_archived_filter(self, service):
        """L187-194: archived filter delegates to find_for_user_with_state."""
        service.conversation_repository.find_for_user_with_state.return_value = []

        conversations, cursor = service.list_conversations_for_user(
            "user-1", state_filter="archived", limit=20
        )
        assert conversations == []
        service.conversation_repository.find_for_user_with_state.assert_called_once_with(
            user_id="user-1", state="archived", limit=21, cursor=None
        )

    def test_trashed_filter(self, service):
        """L195-202: trashed filter delegates to find_for_user_with_state."""
        service.conversation_repository.find_for_user_with_state.return_value = []

        conversations, cursor = service.list_conversations_for_user(
            "user-1", state_filter="trashed", limit=20
        )
        assert conversations == []
        service.conversation_repository.find_for_user_with_state.assert_called_once_with(
            user_id="user-1", state="trashed", limit=21, cursor=None
        )

    def test_unknown_filter_returns_empty(self, service):
        """L203-205: unknown filter returns empty."""
        conversations, cursor = service.list_conversations_for_user(
            "user-1", state_filter="unknown_filter", limit=20
        )
        assert conversations == []
        assert cursor is None


# ---------------------------------------------------------------------------
# L233: set_conversation_user_state — valid state
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSetConversationUserState:
    """Test set_conversation_user_state valid states."""

    def test_set_archived(self, service):
        """L231-237: valid 'archived' state calls repo."""
        service.set_conversation_user_state("conv-1", "user-1", "archived")
        service.conversation_state_repository.set_state.assert_called_once_with(
            "user-1", "archived", conversation_id="conv-1"
        )

    def test_set_trashed(self, service):
        service.set_conversation_user_state("conv-1", "user-1", "trashed")
        service.conversation_state_repository.set_state.assert_called_once()

    def test_set_active(self, service):
        service.set_conversation_user_state("conv-1", "user-1", "active")
        service.conversation_state_repository.set_state.assert_called_once()


# ---------------------------------------------------------------------------
# L242: get_unread_count — delegates
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetUnreadCount:
    """Test get_unread_count delegates to repository."""

    def test_delegates_to_repo(self, service):
        """L242: calls conversation_repository.get_unread_count."""
        service.conversation_repository.get_unread_count.return_value = 5
        result = service.get_unread_count("conv-1", "user-1")
        assert result == 5


# ---------------------------------------------------------------------------
# L307->310, 311->317: get_messages — pagination edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetMessagesPaginationEdge:
    """Test get_messages pagination edge cases."""

    def test_exact_limit_no_more(self, service):
        """Exactly limit messages => has_more=False, no cursor."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation
        messages = [_Message(f"m{i}", f"content {i}", "s1") for i in range(3)]
        service.message_repository.find_by_conversation.return_value = messages

        results, has_more, cursor = service.get_messages(
            "conv-1", "s1", limit=3
        )
        assert has_more is False
        assert cursor is None
        assert len(results) == 3

    def test_has_more_with_cursor(self, service):
        """L306-314: more than limit => has_more=True, cursor set."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation
        messages = [_Message(f"m{i}", f"content {i}", "s1") for i in range(4)]
        service.message_repository.find_by_conversation.return_value = messages

        results, has_more, cursor = service.get_messages(
            "conv-1", "s1", limit=3
        )
        assert has_more is True
        assert cursor is not None
        assert len(results) == 3


# ---------------------------------------------------------------------------
# L652: get_typing_context — successful case
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetTypingContext:
    """Test get_typing_context edge cases."""

    def test_returns_context_for_participant(self, service):
        """L652-654: user is a participant => return TypingContext."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation

        ctx = service.get_typing_context("conv-1", "s1")
        assert ctx is not None
        assert ctx.conversation_id == "conv-1"
        assert "s1" in ctx.participant_ids
        assert "i1" in ctx.participant_ids


# ---------------------------------------------------------------------------
# L714->712, L732->735: get_messages_with_details — booking_id not in bookings_by_id
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetMessagesWithDetailsEdge:
    """Test get_messages_with_details edge cases."""

    def test_message_with_missing_booking(self, service):
        """L721: booking_id not in bookings_by_id => no booking_details."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation

        msg = _Message(
            message_id="m1",
            content="hello",
            sender_id="s1",
            message_type="booking",
            booking_id="b999",
            read_by=None,
            reaction_list=None,
        )
        service.message_repository.find_by_conversation.return_value = [msg]
        service.booking_repository.get_by_id.return_value = None  # booking not found

        result = service.get_messages_with_details("conv-1", "s1")
        assert result.conversation_found is True
        assert len(result.messages) == 1
        assert result.messages[0].booking_details is None

    def test_deleted_message_content_replaced(self, service):
        """L757: is_deleted => content replaced."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation

        msg = _Message(
            message_id="m1",
            content="secret",
            sender_id="s1",
            message_type="user",
            is_deleted=True,
            read_by=[],
            reaction_list=[],
        )
        service.message_repository.find_by_conversation.return_value = [msg]

        result = service.get_messages_with_details("conv-1", "s1")
        assert result.messages[0].content == "This message was deleted"
        assert result.messages[0].is_deleted is True

    def test_user_message_with_booking_id_not_fetched(self, service):
        """L709: user message type with booking_id is NOT fetched (only non-user types)."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation

        msg = _Message(
            message_id="m1",
            content="hi",
            sender_id="s1",
            message_type="user",  # user type with booking_id
            booking_id="b1",
            read_by=[],
            reaction_list=[],
        )
        service.message_repository.find_by_conversation.return_value = [msg]

        result = service.get_messages_with_details("conv-1", "s1")
        # booking_id is present but booking_details should be None
        # because user messages are excluded from booking fetch
        assert result.messages[0].booking_id == "b1"
        assert result.messages[0].booking_details is None

    def test_read_by_invalid_entries_filtered(self, service):
        """L743-747: read_by entries that aren't dicts or lack user_id are filtered."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation

        msg = _Message(
            message_id="m1",
            content="hi",
            sender_id="s1",
            read_by=["not_a_dict", {"no_user_id_key": "val"}, {"user_id": "u1"}],
            reaction_list=[],
        )
        service.message_repository.find_by_conversation.return_value = [msg]

        result = service.get_messages_with_details("conv-1", "s1")
        assert len(result.messages[0].read_by) == 1
        assert result.messages[0].read_by[0]["user_id"] == "u1"


# ---------------------------------------------------------------------------
# _determine_booking_id edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetermineBookingIdEdge:
    """Test _determine_booking_id edge cases."""

    def test_explicit_booking_not_matching(self, service):
        """L414-417: explicit booking provided but doesn't match conversation pair."""
        conversation = _Conversation("conv-1", "s1", "i1")
        booking = SimpleNamespace(id="b1", student_id="other-s", instructor_id="i1")
        service.booking_repository.get_by_id.return_value = booking

        result = service._determine_booking_id(conversation, "b1")
        assert result is None

    def test_explicit_booking_not_found(self, service):
        """L414: booking not found => return None."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.booking_repository.get_by_id.return_value = None

        result = service._determine_booking_id(conversation, "b1")
        assert result is None

    def test_multiple_upcoming_returns_none(self, service):
        """L428-429: multiple upcoming bookings => return None."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.booking_repository.find_upcoming_for_pair.return_value = [
            SimpleNamespace(id="b1"),
            SimpleNamespace(id="b2"),
        ]

        result = service._determine_booking_id(conversation, None)
        assert result is None

    def test_zero_upcoming_returns_none(self, service):
        """L428-429: zero upcoming bookings => return None."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.booking_repository.find_upcoming_for_pair.return_value = []

        result = service._determine_booking_id(conversation, None)
        assert result is None

    def test_one_upcoming_auto_tags(self, service):
        """L425-426: exactly one upcoming booking => auto-tag."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.booking_repository.find_upcoming_for_pair.return_value = [
            SimpleNamespace(id="b1"),
        ]

        result = service._determine_booking_id(conversation, None)
        assert result == "b1"


# ---------------------------------------------------------------------------
# _send_message_notifications edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSendMessageNotificationsEdge:
    """Test _send_message_notifications edge cases."""

    def test_no_booking_id_skips(self, service):
        """L881-886: no booking_id => skip notification."""
        conversation = _Conversation("conv-1", "s1", "i1")
        message = SimpleNamespace(id="m1", booking_id=None)
        service._send_message_notifications(conversation, message, "s1", "hi")
        service.notification_service.send_message_notification.assert_not_called()

    def test_no_notification_service_creates_one(self, service):
        """L871-872: notification_service is None => creates one."""
        service.notification_service = None
        conversation = _Conversation("conv-1", "s1", "i1")
        message = SimpleNamespace(id="m1", booking_id=None)

        with patch("app.services.conversation_service.NotificationService") as MockNS:
            MockNS.return_value = Mock()
            service._send_message_notifications(conversation, message, "s1", "hi")
            # Since booking_id is None, notification should be skipped
            MockNS.return_value.send_message_notification.assert_not_called()


# ---------------------------------------------------------------------------
# validate_instructor — not an instructor
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateInstructorEdge:
    """Test validate_instructor when user is not an instructor."""

    def test_user_not_instructor(self, service):
        """L574-575: user exists but is_instructor is False."""
        mock_user = SimpleNamespace(id="u1", is_instructor=False)
        with patch(
            "app.services.conversation_service.RepositoryFactory.create_user_repository"
        ) as factory:
            factory.return_value.get_by_id.return_value = mock_user
            ok, error = service.validate_instructor("u1")

        assert ok is False
        assert error == "Target user is not an instructor"


# ---------------------------------------------------------------------------
# send_message_with_context — non-participant
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSendMessageWithContextEdge:
    """Test send_message_with_context edge cases."""

    def test_non_participant_returns_none_message(self, service):
        """L802-807: user not a participant => return None message."""
        service.conversation_repository.get_by_id.return_value = None

        result = service.send_message_with_context("conv-1", "user-1", "hello")
        assert result.message is None
        assert result.participant_ids == []

    def test_sender_is_instructor(self, service):
        """L831-835: sender is instructor => recipient is student."""
        conversation = _Conversation("conv-1", "s1", "i1")
        service.conversation_repository.get_by_id.return_value = conversation
        message = SimpleNamespace(id="m1", created_at=datetime.now(timezone.utc), booking_id=None)
        service.message_repository.create_conversation_message.return_value = message
        service._determine_booking_id = Mock(return_value=None)

        result = service.send_message_with_context("conv-1", "i1", "hello")
        assert result.message == message
        # restore_to_active should be called with student_id
        service.conversation_state_repository.restore_to_active.assert_called_once_with(
            user_id="s1", conversation_id="conv-1"
        )


# ---------------------------------------------------------------------------
# create_conversation_with_message — error case
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCreateConversationWithMessageEdge:
    """Test create_conversation_with_message edge cases."""

    def test_invalid_instructor_returns_error(self, service):
        """L600-606: invalid instructor returns error result."""
        with patch.object(service, "validate_instructor", return_value=(False, "Not found")):
            result = service.create_conversation_with_message("s1", "bad-id")

        assert result.success is False
        assert result.error == "Not found"
        assert result.conversation_id == ""

    def test_no_initial_message(self, service):
        """L615: no initial_message => conversation created without message."""
        conv = _Conversation("conv-1", "s1", "i1")
        with patch.object(service, "validate_instructor", return_value=(True, None)):
            service.conversation_repository.get_or_create.return_value = (conv, True)

            result = service.create_conversation_with_message("s1", "i1")

        assert result.success is True
        assert result.conversation_id == "conv-1"
        assert result.created is True
        service.message_repository.create_conversation_message.assert_not_called()
