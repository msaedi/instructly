"""Unit tests for MessageService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.services.message_service import MessageService


class _Conversation:
    def __init__(self, conversation_id: str, student_id: str, instructor_id: str):
        self.id = conversation_id
        self.student_id = student_id
        self.instructor_id = instructor_id


class _FakeConversationRepo:
    store: dict[str, _Conversation] = {}

    def __init__(self, _db):
        pass

    def get_by_id(self, conversation_id: str):
        return self.store.get(conversation_id)


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


class TestMessageService:
    def test_get_stream_context_fetches_missed_messages(self, service):
        service.conversation_repository.find_for_user.return_value = [
            SimpleNamespace(id="conv-1"),
            SimpleNamespace(id="conv-2"),
        ]
        service.repository.get_messages_after_id_for_conversations.return_value = ["m1", "m2"]

        ctx = service.get_stream_context(
            user_id="user-1",
            last_event_id="m0",
            has_permission=True,
        )

        assert ctx.has_permission is True
        assert ctx.missed_messages == ["m1", "m2"]
        service.repository.get_messages_after_id_for_conversations.assert_called_once_with(
            ["conv-1", "conv-2"], "m0", 100
        )

    def test_get_message_by_id_missing_returns_none(self, service):
        service.repository.get_by_id.return_value = None

        assert service.get_message_by_id("m1", "user-1") is None

    def test_user_has_message_access(self, service, monkeypatch):
        from app.services import message_service as message_module

        _FakeConversationRepo.store = {
            "conv-1": _Conversation("conv-1", "student-1", "instructor-1"),
        }
        monkeypatch.setattr(message_module, "ConversationRepository", _FakeConversationRepo)

        msg = SimpleNamespace(conversation_id="conv-1")

        assert service._user_has_message_access(msg, "student-1") is True
        assert service._user_has_message_access(msg, "other-user") is False

    def test_mark_messages_as_read_empty_list(self, service):
        assert service.mark_messages_as_read([], "user-1") == 0

    def test_mark_conversation_messages_as_read_no_unread(self, service):
        service.repository.get_unread_messages_by_conversation.return_value = []

        assert service.mark_conversation_messages_as_read("conv-1", "user-1") == 0

    def test_delete_message_missing_returns_false(self, service):
        service.repository.get_by_id.return_value = None

        assert service.delete_message("m1", "user-1") is False

    def test_delete_message_expired_window_raises(self, service, monkeypatch):
        from app.core.config import settings

        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service.repository.get_by_id.return_value = message
        service.repository.soft_delete_message.return_value = True
        monkeypatch.setattr(settings, "message_edit_window_minutes", 0)

        with pytest.raises(ValidationException):
            service.delete_message("m1", "user-1")

    def test_delete_message_should_fail_when_window_expired(self, service, monkeypatch):
        from app.core.config import settings

        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service.repository.get_by_id.return_value = message
        monkeypatch.setattr(settings, "message_edit_window_minutes", 0)

        with pytest.raises(ValidationException):
            service.delete_message("m1", "user-1")

    def test_edit_message_should_fail_when_window_expired(self, service, monkeypatch):
        from app.core.config import settings

        message = SimpleNamespace(
            id="m1",
            sender_id="user-1",
            content="original",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service.repository.get_by_id.return_value = message
        service.repository.apply_message_edit.return_value = datetime.now(timezone.utc)
        monkeypatch.setattr(settings, "message_edit_window_minutes", 0)

        with pytest.raises(ValidationException):
            service.edit_message("m1", "user-1", "updated")

    def test_add_reaction_message_not_found(self, service):
        service.repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException):
            service.add_reaction("m1", "user-1", "thumbs_up")

    def test_remove_reaction_message_not_found(self, service):
        service.repository.get_by_id.return_value = None

        assert service.remove_reaction("m1", "user-1", "thumbs_up") is False

    def test_remove_reaction_success(self, service):
        service.repository.get_by_id.return_value = SimpleNamespace(conversation_id="conv-1")
        service.repository.remove_reaction.return_value = True
        service._user_has_message_access = Mock(return_value=True)

        assert service.remove_reaction("m1", "user-1", "thumbs_up") is True

    def test_edit_message_not_found(self, service):
        service.repository.get_by_id.return_value = None

        assert service.edit_message("m1", "user-1", "hello") is False

    def test_get_message_with_context_not_found(self, service):
        service.repository.get_by_id.return_value = None

        ctx = service.get_message_with_context("m1", "user-1")
        assert ctx.message is None
        assert ctx.participant_ids == []

    def test_get_message_with_context_includes_participants(self, service):
        message = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = message
        service._user_has_message_access = Mock(return_value=True)
        service._get_conversation_participants = Mock(return_value=["student-1", "instructor-1"])

        ctx = service.get_message_with_context("m1", "student-1")

        assert ctx.message == message
        assert ctx.conversation_id == "conv-1"
        assert ctx.participant_ids == ["student-1", "instructor-1"]

    def test_mark_messages_read_with_context_conversation(self, service):
        service.repository.mark_unread_messages_read_atomic.return_value = SimpleNamespace(
            rowcount=2, message_ids=["m1", "m2"]
        )
        service._get_conversation_participants = Mock(return_value=["s1", "i1"])

        result = service.mark_messages_read_with_context("conv-1", None, "user-1")

        assert result.count == 2
        assert result.marked_message_ids == ["m1", "m2"]
        assert result.conversation_id == "conv-1"
        assert result.participant_ids == ["s1", "i1"]

    def test_mark_messages_read_with_context_message_ids(self, service):
        service.repository.mark_messages_as_read.return_value = 1
        service.repository.get_by_id.return_value = SimpleNamespace(conversation_id="conv-2")
        service._get_conversation_participants = Mock(return_value=["s2", "i2"])

        result = service.mark_messages_read_with_context(None, ["m1"], "user-1")

        assert result.count == 1
        assert result.marked_message_ids == ["m1"]
        assert result.conversation_id == "conv-2"
        assert result.participant_ids == ["s2", "i2"]

    def test_edit_message_with_context_empty_content(self, service):
        with pytest.raises(ValidationException):
            service.edit_message_with_context("m1", "user-1", "   ")

    def test_edit_message_with_context_forbidden(self, service):
        message = SimpleNamespace(
            sender_id="user-1",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message

        with pytest.raises(ForbiddenException):
            service.edit_message_with_context("m1", "other-user", "updated")

    def test_delete_message_with_context_not_found(self, service):
        service.repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException):
            service.delete_message_with_context("m1", "user-1")

    def test_delete_message_with_context_forbidden(self, service):
        message = SimpleNamespace(
            sender_id="user-1",
            conversation_id="conv-1",
            created_at=datetime.now(timezone.utc),
        )
        service.repository.get_by_id.return_value = message

        with pytest.raises(ForbiddenException):
            service.delete_message_with_context("m1", "other-user")

    def test_add_reaction_with_context_toggle(self, service):
        message = SimpleNamespace(conversation_id="conv-1")
        service.repository.get_by_id.return_value = message
        service._user_has_message_access = Mock(return_value=True)
        service.repository.has_user_reaction.return_value = True
        service._get_conversation_participants = Mock(return_value=["s1", "i1"])

        result = service.add_reaction_with_context("m1", "user-1", "thumbs_up")

        assert result.action == "removed"
        service.repository.remove_reaction.assert_called_once_with("m1", "user-1", "thumbs_up")

    def test_add_reaction_with_context_not_found(self, service):
        service.repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException):
            service.add_reaction_with_context("m1", "user-1", "thumbs_up")

    def test_add_reaction_with_context_forbidden(self, service):
        service.repository.get_by_id.return_value = SimpleNamespace(conversation_id="conv-1")
        service._user_has_message_access = Mock(return_value=False)

        with pytest.raises(ForbiddenException):
            service.add_reaction_with_context("m1", "user-1", "thumbs_up")

    def test_remove_reaction_with_context_forbidden(self, service):
        service.repository.get_by_id.return_value = SimpleNamespace(conversation_id="conv-1")
        service._user_has_message_access = Mock(return_value=False)

        with pytest.raises(ForbiddenException):
            service.remove_reaction_with_context("m1", "user-1", "thumbs_up")
