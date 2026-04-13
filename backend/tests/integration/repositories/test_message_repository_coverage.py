from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.conversation import Conversation
from app.models.message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
    Message,
    MessageNotification,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_state_repository import ConversationStateRepository
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


def _make_conversation(
    db,
    *,
    student_id: str,
    instructor_id: str,
    last_message_at: datetime | None = None,
) -> Conversation:
    conversation = Conversation(
        student_id=student_id,
        instructor_id=instructor_id,
        last_message_at=last_message_at,
    )
    db.add(conversation)
    db.commit()
    return conversation


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


def test_create_conversation_message_updates_conversation_last_message_at(
    db,
    message_repo,
    conversation,
    test_student,
):
    previous_last_message_at = datetime.now(timezone.utc) - timedelta(hours=1)
    conversation.last_message_at = previous_last_message_at
    db.commit()

    message = message_repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Hello",
    )
    db.commit()
    db.refresh(conversation)

    assert conversation.last_message_at == message.created_at
    assert conversation.last_message_at != previous_last_message_at


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


def test_message_aggregate_queries_are_scoped_and_include_soft_deleted_latest(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor,
    test_instructor_2,
):
    other_conversation = _make_conversation(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
    )
    empty_conversation = _make_conversation(
        db,
        student_id=test_instructor.id,
        instructor_id=test_instructor_2.id,
    )

    older = _create_message(
        db,
        message_repo,
        conversation.id,
        test_student.id,
        "Older visible",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    newest_deleted = _create_message(
        db,
        message_repo,
        conversation.id,
        test_student.id,
        "Newest deleted",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    other_message = _create_message(
        db,
        message_repo,
        other_conversation.id,
        test_student.id,
        "Other conversation",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )

    deleted = message_repo.soft_delete_message(newest_deleted.id, test_student.id)
    assert deleted is not None
    db.commit()

    assert message_repo.count_for_conversation(conversation.id) == 2
    assert message_repo.count_for_conversation(other_conversation.id) == 1
    assert message_repo.count_for_conversation("missing-conversation") == 0

    assert message_repo.get_last_message_at_for_conversation(conversation.id) == newest_deleted.created_at
    assert message_repo.get_last_message_at_for_conversation(other_conversation.id) == other_message.created_at
    assert message_repo.get_last_message_at_for_conversation(empty_conversation.id) is None

    db.refresh(older)
    assert older.is_deleted is False


def test_batch_get_latest_messages_excludes_soft_deleted_rows(
    db,
    message_repo,
    test_student,
    test_instructor,
    test_instructor_with_availability,
    test_instructor_2,
):
    mixed_conversation = _make_conversation(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
    )
    active_conversation = _make_conversation(
        db,
        student_id=test_instructor.id,
        instructor_id=test_instructor_with_availability.id,
    )
    deleted_only_conversation = _make_conversation(
        db,
        student_id=test_instructor.id,
        instructor_id=test_instructor_2.id,
    )
    empty_conversation = _make_conversation(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
    )

    visible_mixed = _create_message(
        db,
        message_repo,
        mixed_conversation.id,
        test_student.id,
        "Mixed visible",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    deleted_mixed = _create_message(
        db,
        message_repo,
        mixed_conversation.id,
        test_student.id,
        "Mixed deleted",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    visible_active = _create_message(
        db,
        message_repo,
        active_conversation.id,
        test_instructor.id,
        "Active visible",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    deleted_only = _create_message(
        db,
        message_repo,
        deleted_only_conversation.id,
        test_instructor.id,
        "Deleted only",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=30),
    )

    assert message_repo.soft_delete_message(deleted_mixed.id, test_student.id) is not None
    assert message_repo.soft_delete_message(deleted_only.id, test_instructor.id) is not None
    db.commit()

    assert message_repo.batch_get_latest_messages([]) == {}

    latest_messages = message_repo.batch_get_latest_messages(
        [
            mixed_conversation.id,
            active_conversation.id,
            deleted_only_conversation.id,
            empty_conversation.id,
        ]
    )

    assert set(latest_messages) == {mixed_conversation.id, active_conversation.id}
    assert latest_messages[mixed_conversation.id].id == visible_mixed.id
    assert latest_messages[active_conversation.id].id == visible_active.id


def test_messages_after_id_fallback_stays_within_requested_conversations(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_2,
):
    other_conversation = _make_conversation(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
    )

    requested_one = _create_message(db, message_repo, conversation.id, test_student.id, "Requested one")
    requested_two = _create_message(db, message_repo, conversation.id, test_student.id, "Requested two")
    other_message = _create_message(
        db,
        message_repo,
        other_conversation.id,
        test_student.id,
        "Other conversation",
    )

    results = message_repo.get_messages_after_id_for_conversations(
        [conversation.id],
        "00000000000000000000000000",
        limit=10,
    )

    assert [message.conversation_id for message in results] == [conversation.id, conversation.id]
    assert [message.id for message in results] == sorted([requested_one.id, requested_two.id])
    assert other_message.id not in [message.id for message in results]


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


def test_add_reaction_integrity_error_is_idempotent():
    db = Mock()
    repo = MessageRepository(db)

    message_query = Mock()
    message_query.filter.return_value = message_query
    message_query.first.return_value = object()

    reaction_query = Mock()
    reaction_query.filter.return_value = reaction_query
    reaction_query.first.return_value = None

    db.query.side_effect = [message_query, reaction_query]
    db.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    assert repo.add_reaction("msg", "user", "🔥") is True
    db.add.assert_called_once()


def test_conversation_model_is_fixed_two_party_and_repository_has_no_participant_mutators(
    conversation,
    test_student,
    test_instructor_with_availability,
):
    assert conversation.student_id == test_student.id
    assert conversation.instructor_id == test_instructor_with_availability.id
    assert conversation.is_participant(test_student.id) is True
    assert conversation.is_participant(test_instructor_with_availability.id) is True
    assert conversation.get_other_user_id(test_student.id) == test_instructor_with_availability.id

    public_methods = {name for name in dir(MessageRepository) if not name.startswith("_")}
    assert "add_participant" not in public_methods
    assert "remove_participant" not in public_methods
    assert "replace_participant" not in public_methods


def test_same_user_archive_then_trash_latest_state_wins(
    db,
    message_repo,
    conversation,
    test_student,
):
    _create_message(db, message_repo, conversation.id, test_student.id, "Stateful conversation")

    state_repo = ConversationStateRepository(db)
    conversation_repo = ConversationRepository(db)

    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    state_repo.set_state(test_student.id, "trashed", conversation_id=conversation.id)
    db.commit()

    active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_student.id, ["archived", "trashed"], limit=20
        )
    }
    archived_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "archived")
    }
    trashed_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "trashed")
    }

    assert conversation.id not in active_ids
    assert conversation.id not in archived_ids
    assert conversation.id in trashed_ids


def test_same_user_trash_then_archive_latest_state_wins(
    db,
    message_repo,
    conversation,
    test_student,
):
    _create_message(db, message_repo, conversation.id, test_student.id, "Stateful conversation")

    state_repo = ConversationStateRepository(db)
    conversation_repo = ConversationRepository(db)

    state_repo.set_state(test_student.id, "trashed", conversation_id=conversation.id)
    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    db.commit()

    active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_student.id, ["archived", "trashed"], limit=20
        )
    }
    archived_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "archived")
    }
    trashed_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "trashed")
    }

    assert conversation.id not in active_ids
    assert conversation.id in archived_ids
    assert conversation.id not in trashed_ids


def test_archive_state_is_per_user_isolated(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    _create_message(db, message_repo, conversation.id, test_student.id, "Archive isolation")

    state_repo = ConversationStateRepository(db)
    conversation_repo = ConversationRepository(db)

    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    db.commit()

    student_active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_student.id, ["archived", "trashed"], limit=20
        )
    }
    instructor_active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_instructor_with_availability.id, ["archived", "trashed"], limit=20
        )
    }
    student_archived_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "archived")
    }
    instructor_archived_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_with_state(
            test_instructor_with_availability.id, "archived"
        )
    }

    assert conversation.id not in student_active_ids
    assert conversation.id in instructor_active_ids
    assert conversation.id in student_archived_ids
    assert conversation.id not in instructor_archived_ids


def test_trash_state_is_per_user_isolated(
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    _create_message(db, message_repo, conversation.id, test_student.id, "Trash isolation")

    state_repo = ConversationStateRepository(db)
    conversation_repo = ConversationRepository(db)

    state_repo.set_state(test_student.id, "trashed", conversation_id=conversation.id)
    db.commit()

    student_active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_student.id, ["archived", "trashed"], limit=20
        )
    }
    instructor_active_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_excluding_states(
            test_instructor_with_availability.id, ["archived", "trashed"], limit=20
        )
    }
    student_trashed_ids = {
        conv.id for conv in conversation_repo.find_for_user_with_state(test_student.id, "trashed")
    }
    instructor_trashed_ids = {
        conv.id
        for conv in conversation_repo.find_for_user_with_state(
            test_instructor_with_availability.id, "trashed"
        )
    }

    assert conversation.id not in student_active_ids
    assert conversation.id in instructor_active_ids
    assert conversation.id in student_trashed_ids
    assert conversation.id not in instructor_trashed_ids


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
        repo.count_for_conversation("conv")

    with pytest.raises(RepositoryException):
        repo.batch_get_latest_messages(["conv"])

    with pytest.raises(RepositoryException):
        repo.get_last_message_at_for_conversation("conv")

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
