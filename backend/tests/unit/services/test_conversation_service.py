"""Unit tests for ConversationService."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.services.conversation_service import ConversationService


class _Conversation:
    def __init__(self, conversation_id: str, student_id: str, instructor_id: str, last_message_at=None):
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
        booking_id: str | None = None,
        created_at: datetime | None = None,
        edited_at: datetime | None = None,
        is_deleted: bool = False,
        delivered_at: datetime | None = None,
        read_by=None,
        reaction_list=None,
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


class TestConversationService:
    def test_list_conversations_sets_next_cursor(self, service):
        conv1 = _Conversation(
            conversation_id="conv-1",
            student_id="s1",
            instructor_id="i1",
            last_message_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        conv2 = _Conversation(
            conversation_id="conv-2",
            student_id="s2",
            instructor_id="i2",
            last_message_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        service.conversation_repository.find_for_user_excluding_states.return_value = [
            conv2,
            conv1,
        ]

        conversations, next_cursor = service.list_conversations_for_user(
            "user-1", state_filter="active", limit=1
        )

        assert conversations == [conv2]
        assert next_cursor == conv2.last_message_at.isoformat()

    def test_set_conversation_user_state_invalid(self, service):
        with pytest.raises(ValueError):
            service.set_conversation_user_state("conv-1", "user-1", "paused")

    def test_get_conversation_user_state_defaults_active(self, service):
        service.conversation_state_repository.get_state.return_value = None

        assert service.get_conversation_user_state("conv-1", "user-1") == "active"

    def test_get_messages_empty_when_no_access(self, service):
        service.conversation_repository.get_by_id.return_value = None

        messages, has_more, next_cursor = service.get_messages("conv-1", "user-1")

        assert messages == []
        assert has_more is False
        assert next_cursor is None

    def test_get_messages_pagination_and_cursor(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        service.conversation_repository.get_by_id.return_value = conversation
        messages = [
            _Message("m3", "newest", "student-1"),
            _Message("m2", "middle", "student-1"),
            _Message("m1", "oldest", "student-1"),
        ]
        service.message_repository.find_by_conversation.return_value = messages

        results, has_more, next_cursor = service.get_messages("conv-1", "student-1", limit=2)

        assert has_more is True
        assert next_cursor == "m2"
        assert [msg.id for msg in results] == ["m2", "m3"]

    def test_send_message_returns_none_if_not_participant(self, service):
        service.conversation_repository.get_by_id.return_value = None

        assert service.send_message("conv-1", "user-1", "hello") is None

    def test_send_message_auto_restores_recipient(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        service.conversation_repository.get_by_id.return_value = conversation
        message = SimpleNamespace(id="m1", created_at=datetime.now(timezone.utc))
        service.message_repository.create_conversation_message.return_value = message
        service._determine_booking_id = Mock(return_value=None)

        result = service.send_message("conv-1", "student-1", "hello")

        assert result == message
        service.conversation_state_repository.restore_to_active.assert_called_once_with(
            user_id="instructor-1",
            conversation_id="conv-1",
        )

    def test_determine_booking_id_explicit_valid(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        booking = SimpleNamespace(id="b1", student_id="student-1", instructor_id="instructor-1")
        service.booking_repository.get_by_id.return_value = booking

        booking_id = service._determine_booking_id(conversation, "b1")

        assert booking_id == "b1"

    def test_booking_matches_conversation_false(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        booking = SimpleNamespace(id="b2", student_id="student-2", instructor_id="instructor-1")

        assert service._booking_matches_conversation(booking, conversation) is False

    def test_get_next_booking_for_conversation(self, service):
        booking = SimpleNamespace(id="b1")
        service.get_upcoming_bookings_for_conversation = Mock(return_value=[booking])

        assert service.get_next_booking_for_conversation(SimpleNamespace()) == booking

        service.get_upcoming_bookings_for_conversation = Mock(return_value=[])
        assert service.get_next_booking_for_conversation(SimpleNamespace()) is None

    def test_validate_instructor_missing_user(self, service):
        repo = Mock()
        repo.get_by_id.return_value = None
        with patch("app.services.conversation_service.RepositoryFactory.create_user_repository") as factory:
            factory.return_value = repo
            ok, error = service.validate_instructor("user-1")

        assert ok is False
        assert error == "Instructor not found"

    def test_get_typing_context_none(self, service):
        service.conversation_repository.get_by_id.return_value = None

        assert service.get_typing_context("conv-1", "user-1") is None

    def test_get_messages_with_details_builds_booking_details(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        service.conversation_repository.get_by_id.return_value = conversation

        msg1 = _Message(
            message_id="m1",
            content="booking",
            sender_id="student-1",
            message_type="booking",
            booking_id="b1",
            read_by=[{"user_id": "reader-1", "read_at": "2024-01-01"}],
            reaction_list=[SimpleNamespace(user_id="u1", emoji="thumbs_up")],
        )
        msg2 = _Message(
            message_id="m2",
            content="booking",
            sender_id="student-1",
            message_type="booking",
            booking_id="b2",
        )
        service.message_repository.find_by_conversation.return_value = [msg2, msg1]

        booking1 = SimpleNamespace(
            id="b1",
            booking_date=date(2024, 1, 1),
            start_time="09:30:00",
            instructor_service=SimpleNamespace(name="Guitar"),
        )
        booking2 = SimpleNamespace(
            id="b2",
            booking_date=date(2024, 1, 2),
            start_time=time(10, 0),
            instructor_service=None,
        )
        service.booking_repository.get_by_id.side_effect = (
            lambda booking_id: {"b1": booking1, "b2": booking2}.get(booking_id)
        )

        result = service.get_messages_with_details("conv-1", "student-1", limit=5)

        assert result.conversation_found is True
        assert result.next_cursor is None
        assert len(result.messages) == 2
        assert result.messages[0].booking_id == "b1"
        assert result.messages[0].booking_details["service_name"] == "Guitar"
        assert result.messages[0].booking_details["start_time"] == "09:30"
        assert result.messages[1].booking_id == "b2"
        assert result.messages[1].booking_details["service_name"] == "Lesson"
        assert result.messages[1].booking_details["start_time"] == "10:00"
        assert result.messages[0].reactions == [{"user_id": "u1", "emoji": "thumbs_up"}]
        assert result.messages[0].read_by == [{"user_id": "reader-1", "read_at": "2024-01-01"}]

    def test_send_message_notifications_booking_not_found(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        message = SimpleNamespace(id="m1", booking_id="b1")
        service.booking_repository.get_by_id.return_value = None

        service._send_message_notifications(conversation, message, "student-1", "hi")

        service.notification_service.send_message_notification.assert_not_called()

    def test_send_message_notifications_handles_exception(self, service):
        conversation = _Conversation("conv-1", "student-1", "instructor-1")
        message = SimpleNamespace(id="m1", booking_id="b1")
        booking = SimpleNamespace(id="b1")
        service.booking_repository.get_by_id.return_value = booking
        service.notification_service.send_message_notification.side_effect = Exception("boom")

        service._send_message_notifications(conversation, message, "student-1", "hi")

        service.notification_service.send_message_notification.assert_called_once()
