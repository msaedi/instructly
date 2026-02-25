"""
Bug-hunting edge-case tests for message_service.py targeting uncovered lines/branches.

Covers lines: 123->129, 243-244, 344-345, 356->361, 368,
394->397, 429->433, 435->448, 442->448, 444->448
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import ForbiddenException
from app.services.message_service import MessageService


@pytest.fixture
def db():
    db = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture
def service(db):
    svc = MessageService(db)
    svc.repository = Mock()
    svc.conversation_repository = Mock()
    return svc


# ---------------------------------------------------------------------------
# L123->129: get_stream_context — no conversations for user
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetStreamContextEdgeCases:
    """Test get_stream_context edge cases."""

    def test_no_conversations_returns_empty_missed(self, service):
        """L123: conversation_ids empty => missed_messages stays empty."""
        service.conversation_repository.find_for_user.return_value = []

        ctx = service.get_stream_context(
            user_id="user-1",
            last_event_id="m0",
            has_permission=True,
        )
        assert ctx.has_permission is True
        assert ctx.missed_messages == []
        # Should NOT call get_messages_after_id_for_conversations
        service.repository.get_messages_after_id_for_conversations.assert_not_called()

    def test_no_last_event_id_returns_empty_missed(self, service):
        """has_permission True but no last_event_id => empty missed."""
        ctx = service.get_stream_context(
            user_id="user-1",
            last_event_id=None,
            has_permission=True,
        )
        assert ctx.has_permission is True
        assert ctx.missed_messages == []

    def test_no_permission_returns_empty(self, service):
        """has_permission False => empty missed messages."""
        ctx = service.get_stream_context(
            user_id="user-1",
            last_event_id="m0",
            has_permission=False,
        )
        assert ctx.has_permission is False
        assert ctx.missed_messages == []

    def test_permission_check_via_db(self, service, monkeypatch):
        """L107-114: has_permission is None => queries PermissionService."""

        mock_perm_svc = Mock()
        mock_perm_svc.return_value.user_has_permission.return_value = False

        # Patch the import inside the method
        monkeypatch.setattr(
            "app.services.message_service.PermissionService",
            mock_perm_svc,
            raising=False,
        )
        # Need to inject into the local import path
        import app.services.permission_service as perm_mod
        monkeypatch.setattr(perm_mod, "PermissionService", mock_perm_svc, raising=False)

        ctx = service.get_stream_context(
            user_id="user-1",
            last_event_id="m0",
            has_permission=None,
        )
        # Should have called permission check
        assert ctx.has_permission is False


# ---------------------------------------------------------------------------
# L243-244: delete_message — non-fatal error in window check
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDeleteMessageWindowCheckError:
    """Test delete_message when window check encounters a non-ValidationException."""

    def test_delete_succeeds_when_window_check_errors_non_fatally(self, service, monkeypatch):
        """L243-244: non-ValidationException in window check is caught silently."""
        from app.core.config import settings

        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message
        service.repository.soft_delete_message.return_value = True

        # Make settings not have message_edit_window_minutes to trigger AttributeError
        # which is caught as a non-fatal error
        monkeypatch.delattr(settings, "message_edit_window_minutes", raising=False)

        result = service.delete_message("m1", "user-1")
        assert result is True

    def test_delete_forbidden_for_other_user(self, service):
        """L227-228: sender_id != user_id raises ForbiddenException."""
        message = SimpleNamespace(
            id="m1",
            sender_id="other-user",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message

        with pytest.raises(ForbiddenException):
            service.delete_message("m1", "user-1")


# ---------------------------------------------------------------------------
# L344-345: edit_message — non-fatal error in window check
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEditMessageWindowCheckError:
    """Test edit_message when window check encounters a non-ValidationException."""

    def test_edit_succeeds_when_window_check_errors_non_fatally(self, service, monkeypatch):
        """L344-345: non-ValidationException in window check is caught silently."""
        from app.core.config import settings

        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            content="original",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message
        service.repository.apply_message_edit.return_value = datetime.now(timezone.utc)

        monkeypatch.delattr(settings, "message_edit_window_minutes", raising=False)

        result = service.edit_message("m1", "user-1", "updated")
        assert result is True

    def test_edit_no_op_same_content(self, service):
        """L329-330: content unchanged => return True."""
        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            content="same",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message

        result = service.edit_message("m1", "user-1", "same")
        assert result is True


# ---------------------------------------------------------------------------
# L356->361: _user_has_message_access — no conversation_id
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestUserHasMessageAccessEdge:
    """Test _user_has_message_access edge cases."""

    def test_no_conversation_id_returns_false(self, service):
        """L356->361: message.conversation_id is None/falsy."""
        msg = SimpleNamespace(conversation_id=None)
        assert service._user_has_message_access(msg, "user-1") is False

    def test_conversation_not_found_returns_false(self, service, monkeypatch):
        """conversation_id exists but conversation not found."""
        from app.repositories.conversation_repository import ConversationRepository
        from app.services import message_service as msg_mod

        mock_repo_cls = Mock(spec=ConversationRepository)
        mock_repo = Mock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo
        monkeypatch.setattr(msg_mod, "ConversationRepository", mock_repo_cls)

        msg = SimpleNamespace(conversation_id="conv-1")
        assert service._user_has_message_access(msg, "user-1") is False


# ---------------------------------------------------------------------------
# L368: _get_conversation_participants — conversation not found
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetConversationParticipants:
    """Test _get_conversation_participants edge cases."""

    def test_conversation_not_found_returns_empty(self, service):
        """L367-368: conversation is None => return []."""
        service.conversation_repository.get_by_id.return_value = None
        result = service._get_conversation_participants("conv-1")
        assert result == []

    def test_conversation_found_returns_participants(self, service):
        """L366-367: conversation found => return [student_id, instructor_id]."""
        conv = SimpleNamespace(student_id="s1", instructor_id="i1")
        service.conversation_repository.get_by_id.return_value = conv
        result = service._get_conversation_participants("conv-1")
        assert result == ["s1", "i1"]


# ---------------------------------------------------------------------------
# L394->397: get_message_with_context — no conversation_id
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetMessageWithContextEdge:
    """Test get_message_with_context edge cases."""

    def test_message_no_conversation_id(self, service):
        """L394-395: message.conversation_id is None => participants empty."""
        message = SimpleNamespace(conversation_id=None)
        service.repository.get_by_id.return_value = message
        service._user_has_message_access = Mock(return_value=True)

        ctx = service.get_message_with_context("m1", "user-1")
        assert ctx.message == message
        assert ctx.conversation_id is None
        assert ctx.participant_ids == []

    def test_no_access_returns_none_message(self, service):
        """L389-390: no access => message=None."""
        message = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = message
        service._user_has_message_access = Mock(return_value=False)

        ctx = service.get_message_with_context("m1", "user-1")
        assert ctx.message is None


# ---------------------------------------------------------------------------
# L429->433: mark_messages_read_with_context — conversation path, no marked IDs
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMarkMessagesReadWithContextEdge:
    """Test mark_messages_read_with_context edge cases."""

    def test_conversation_no_marked_ids(self, service):
        """L429: marked_message_ids is empty => skip log."""
        service.repository.mark_unread_messages_read_atomic.return_value = SimpleNamespace(
            rowcount=0, message_ids=[]
        )
        service._get_conversation_participants = Mock(return_value=["s1", "i1"])

        result = service.mark_messages_read_with_context("conv-1", None, "user-1")
        assert result.count == 0
        assert result.marked_message_ids == []

    def test_neither_conversation_nor_message_ids(self, service):
        """L435->448: both conversation_id and message_ids are None => return empty."""
        result = service.mark_messages_read_with_context(None, None, "user-1")
        assert result.count == 0
        assert result.marked_message_ids == []
        assert result.conversation_id is None
        assert result.participant_ids == []

    def test_message_ids_first_msg_no_conversation(self, service):
        """L442-444: first message has no conversation_id."""
        service.repository.mark_messages_as_read.return_value = 1
        service.repository.get_by_id.return_value = SimpleNamespace(conversation_id=None)

        result = service.mark_messages_read_with_context(None, ["m1"], "user-1")
        assert result.count == 1
        assert result.conversation_id is None
        assert result.participant_ids == []

    def test_message_ids_empty_list(self, service):
        """L435: message_ids is empty list => skip to return."""
        result = service.mark_messages_read_with_context(None, [], "user-1")
        assert result.count == 0

    def test_message_ids_first_msg_not_found(self, service):
        """L443: first_msg is None => no conversation_id."""
        service.repository.mark_messages_as_read.return_value = 1
        service.repository.get_by_id.return_value = None

        result = service.mark_messages_read_with_context(None, ["m1"], "user-1")
        assert result.count == 1
        assert result.conversation_id is None


# ---------------------------------------------------------------------------
# add_reaction — toggle behavior
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestAddReactionToggle:
    """Test add_reaction toggle behavior."""

    def test_add_reaction_existing_toggles_remove(self, service):
        """L268-271: existing reaction is removed (toggle)."""
        msg = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = msg
        service._user_has_message_access = Mock(return_value=True)
        service.repository.has_user_reaction.return_value = True
        service.repository.remove_reaction.return_value = True

        result = service.add_reaction("m1", "user-1", "heart")
        assert result is True
        service.repository.remove_reaction.assert_called_once()

    def test_add_reaction_new_adds(self, service):
        """L272-273: new reaction is added."""
        msg = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = msg
        service._user_has_message_access = Mock(return_value=True)
        service.repository.has_user_reaction.return_value = False
        service.repository.add_reaction.return_value = True

        result = service.add_reaction("m1", "user-1", "heart")
        assert result is True
        service.repository.add_reaction.assert_called_once()

    def test_add_reaction_forbidden(self, service):
        """L263: no access raises ForbiddenException."""
        msg = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = msg
        service._user_has_message_access = Mock(return_value=False)

        with pytest.raises(ForbiddenException):
            service.add_reaction("m1", "user-1", "heart")


# ---------------------------------------------------------------------------
# remove_reaction — edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestRemoveReactionEdge:
    """Test remove_reaction edge cases."""

    def test_remove_reaction_forbidden(self, service):
        """L300-301: no access raises ForbiddenException."""
        msg = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = msg
        service._user_has_message_access = Mock(return_value=False)

        with pytest.raises(ForbiddenException):
            service.remove_reaction("m1", "user-1", "heart")
