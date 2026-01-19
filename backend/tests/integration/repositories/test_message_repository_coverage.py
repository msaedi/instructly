from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.conversation import Conversation
from app.models.message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
    Message,
    MessageNotification,
)
from app.repositories.message_repository import MessageRepository


@pytest.fixture
def message_repo(db):
    return MessageRepository(db)


@pytest.fixture
def conversation(db, test_student, test_instructor_with_availability):
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    return conv


def _create_message(
    db,
    repo: MessageRepository,
    conversation_id: str,
    sender_id: str,
    content: str,
    created_at: datetime | None = None,
) -> Message:
    message = repo.create_conversation_message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=content,
    )
    if created_at:
        message.created_at = created_at
    db.commit()
    return message


def test_get_unread_messages_by_conversation(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    first = _create_message(db, message_repo, conversation.id, test_student.id, "Hi")
    second = _create_message(
        db, message_repo, conversation.id, test_student.id, "Unread"
    )
    notification = (
        db.query(MessageNotification)
        .filter(MessageNotification.message_id == first.id)
        .first()
    )
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    db.commit()

    unread = message_repo.get_unread_messages_by_conversation(
        conversation.id, test_instructor_with_availability.id
    )
    assert [msg.id for msg in unread] == [second.id]


def test_mark_messages_as_read_updates_notifications_and_read_by(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    message = _create_message(
        db, message_repo, conversation.id, test_student.id, "Read me"
    )
    count = message_repo.mark_messages_as_read(
        [message.id], test_instructor_with_availability.id
    )
    assert count == 1
    db.commit()

    db.refresh(message)
    assert any(
        entry.get("user_id") == test_instructor_with_availability.id
        for entry in (message.read_by or [])
    )

    none_count = message_repo.mark_messages_as_read(
        ["missing-message"], test_instructor_with_availability.id
    )
    assert none_count == 0
    message_repo._update_message_read_by([], test_instructor_with_availability.id)
    db.commit()
    db.refresh(message)
    assert len(message.read_by or []) == 1
    message_repo._update_message_read_by([message.id], test_instructor_with_availability.id)
    db.commit()
    db.refresh(message)
    assert len(message.read_by or []) == 1


def test_mark_unread_messages_read_atomic_returns_ids(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    first = _create_message(db, message_repo, conversation.id, test_student.id, "First")
    second = _create_message(
        db, message_repo, conversation.id, test_student.id, "Second"
    )

    result = message_repo.mark_unread_messages_read_atomic(
        conversation.id, test_instructor_with_availability.id
    )
    assert result.rowcount == 2
    assert set(result.message_ids) == {first.id, second.id}

    notifications = (
        db.query(MessageNotification)
        .filter(MessageNotification.user_id == test_instructor_with_availability.id)
        .all()
    )
    assert all(notification.is_read for notification in notifications)

    result_empty = message_repo.mark_unread_messages_read_atomic(
        conversation.id, test_instructor_with_availability.id
    )
    assert result_empty.rowcount == 0
    assert result_empty.message_ids == []


def test_unread_count_and_read_receipts(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg = _create_message(db, message_repo, conversation.id, test_student.id, "Hello")
    assert (
        message_repo.get_unread_count_for_user(test_instructor_with_availability.id)
        == 1
    )

    notification = (
        db.query(MessageNotification)
        .filter(MessageNotification.message_id == msg.id)
        .first()
    )
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    db.commit()

    receipts = message_repo.get_read_receipts_for_message_ids([msg.id])
    assert receipts[0][0] == msg.id


def test_reactions_and_counts(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg = _create_message(db, message_repo, conversation.id, test_student.id, "React")

    assert message_repo.add_reaction(msg.id, test_instructor_with_availability.id, "👍")
    db.commit()
    assert message_repo.add_reaction(msg.id, test_instructor_with_availability.id, "👍")
    db.commit()
    assert message_repo.has_user_reaction(
        msg.id, test_instructor_with_availability.id, "👍"
    )

    counts = message_repo.get_reaction_counts_for_message_ids([msg.id])
    assert counts[0][2] == 1

    user_reactions = message_repo.get_user_reactions_for_message_ids(
        [msg.id], test_instructor_with_availability.id
    )
    assert user_reactions == [(msg.id, "👍")]

    assert message_repo.remove_reaction(
        msg.id, test_instructor_with_availability.id, "👍"
    )
    db.commit()
    assert not message_repo.has_user_reaction(
        msg.id, test_instructor_with_availability.id, "👍"
    )
    assert (
        message_repo.remove_reaction(msg.id, test_instructor_with_availability.id, "👍")
        is False
    )


def test_apply_edit_and_soft_delete(
    db,
    message_repo,
    conversation,
    test_student,
):
    msg = _create_message(db, message_repo, conversation.id, test_student.id, "Original")
    edited_at = message_repo.apply_message_edit(msg.id, "Updated")
    assert edited_at is not None

    deleted = message_repo.soft_delete_message(msg.id, test_student.id)
    assert deleted is not None
    db.commit()
    db.refresh(msg)
    assert msg.is_deleted is True

    assert message_repo.apply_message_edit("missing", "Nope") is None
    assert message_repo.soft_delete_message("missing", test_student.id) is None


def test_messages_after_id_and_find_by_conversation(
    db,
    message_repo,
    conversation,
    test_student,
):
    first = Message(
        id=generate_ulid(),
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="First",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        delivered_at=datetime.now(timezone.utc),
    )
    second = Message(
        id=generate_ulid(),
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Second",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        delivered_at=datetime.now(timezone.utc),
    )
    db.add_all([first, second])
    db.commit()

    after = message_repo.get_messages_after_id_for_conversations(
        [conversation.id], first.id
    )
    assert [m.id for m in after] == [second.id]

    messages = message_repo.find_by_conversation(conversation.id, limit=1)
    assert messages[0].id == second.id
    assert message_repo.get_messages_after_id_for_conversations([], first.id) == []


def test_find_by_conversation_with_cursor_and_booking_filter(
    db,
    message_repo,
    conversation,
    test_student,
    test_booking,
):
    first = message_repo.create_conversation_message(
        conversation.id,
        test_student.id,
        "First",
        booking_id=test_booking.id,
    )
    second = message_repo.create_conversation_message(
        conversation.id,
        test_student.id,
        "Second",
        booking_id=None,
    )
    first.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    second.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    filtered = message_repo.find_by_conversation(
        conversation.id, booking_id_filter=test_booking.id
    )
    assert [msg.id for msg in filtered] == [first.id]

    before = message_repo.find_by_conversation(
        conversation.id, before_cursor=second.id, limit=10
    )
    assert [msg.id for msg in before] == [first.id]

    missing_cursor = message_repo.find_by_conversation(
        conversation.id, before_cursor="missing", limit=10
    )
    assert [msg.id for msg in missing_cursor] == [second.id, first.id]


def test_create_conversation_message_creates_notification(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg = message_repo.create_conversation_message(
        conversation.id,
        test_student.id,
        "Message",
    )
    db.commit()

    notification = (
        db.query(MessageNotification)
        .filter(MessageNotification.message_id == msg.id)
        .first()
    )
    assert notification is not None
    assert notification.user_id == test_instructor_with_availability.id
    system_msg = message_repo.create_conversation_message(
        conversation.id,
        None,
        "System",
    )
    db.commit()
    system_notification = (
        db.query(MessageNotification)
        .filter(MessageNotification.message_id == system_msg.id)
        .first()
    )
    assert system_notification is None


def test_has_recent_reschedule_message(db, message_repo, conversation, test_student):
    msg = Message(
        id=generate_ulid(),
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Reschedule",
        message_type=MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
        created_at=datetime.now(timezone.utc),
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    assert message_repo.has_recent_reschedule_message(conversation.id) is True


def test_add_reaction_missing_message_raises(
    db,
    message_repo,
    test_student,
):
    with pytest.raises(RepositoryException):
        message_repo.add_reaction("missing", test_student.id, "🔥")


def test_message_repository_error_paths():
    db = Mock()
    db.query.side_effect = RuntimeError("boom")
    db.execute.side_effect = RuntimeError("boom")
    db.add.side_effect = RuntimeError("boom")
    db.flush.side_effect = RuntimeError("boom")
    repo = MessageRepository(db)

    with pytest.raises(RepositoryException):
        repo.get_unread_messages_by_conversation("conv", "user")

    with pytest.raises(RepositoryException):
        repo.mark_messages_as_read(["msg"], "user")

    with pytest.raises(RepositoryException):
        repo.mark_unread_messages_read_atomic("conv", "user")

    with pytest.raises(RepositoryException):
        repo.get_unread_count_for_user("user")

    with pytest.raises(RepositoryException):
        repo.get_read_receipts_for_message_ids(["msg"])

    with pytest.raises(RepositoryException):
        repo.get_reaction_counts_for_message_ids(["msg"])

    with pytest.raises(RepositoryException):
        repo.get_user_reactions_for_message_ids(["msg"], "user")

    with pytest.raises(RepositoryException):
        repo.has_user_reaction("msg", "user", "👍")

    with pytest.raises(RepositoryException):
        repo.apply_message_edit("msg", "content")

    with pytest.raises(RepositoryException):
        repo.soft_delete_message("msg", "user")

    with pytest.raises(RepositoryException):
        repo.remove_reaction("msg", "user", "👍")

    with pytest.raises(RepositoryException):
        repo.get_messages_after_id_for_conversations(["conv"], "msg")

    with pytest.raises(RepositoryException):
        repo.find_by_conversation("conv")

    assert repo.has_recent_reschedule_message("conv") is False

    with pytest.raises(RepositoryException):
        repo.create_conversation_message("conv", "user", "content")
