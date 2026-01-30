from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import PermissionName
from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.conversation import Conversation
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService
from app.services.permission_service import PermissionService


@pytest.fixture
def message_service(db):
    return MessageService(db)


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


def _create_message(db, repo: MessageRepository, conversation_id: str, sender_id: str, content: str) -> str:
    message = repo.create_conversation_message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=content,
    )
    db.commit()
    return message.id


def test_get_stream_context_fetches_missed_messages(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    PermissionService(db).grant_permission(
        test_student.id, PermissionName.VIEW_MESSAGES.value
    )

    first_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "First"
    )
    second_id = _create_message(
        db,
        message_repo,
        conversation.id,
        test_instructor_with_availability.id,
        "Second",
    )

    context = message_service.get_stream_context(
        test_student.id, last_event_id=first_id
    )
    assert context.has_permission is True
    assert [m.id for m in context.missed_messages] == [second_id]

    no_perm_context = message_service.get_stream_context(
        test_student.id, last_event_id=first_id, has_permission=False
    )
    assert no_perm_context.missed_messages == []


def test_get_message_by_id_and_context_access(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
    test_instructor_2,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Hello"
    )

    assert message_service.get_message_by_id(msg_id, test_student.id) is not None
    assert message_service.get_message_by_id(msg_id, test_instructor_2.id) is None

    ctx = message_service.get_message_with_context(msg_id, test_student.id)
    assert ctx.conversation_id == conversation.id
    assert set(ctx.participant_ids) == {
        test_student.id,
        test_instructor_with_availability.id,
    }

    ctx_denied = message_service.get_message_with_context(msg_id, test_instructor_2.id)
    assert ctx_denied.message is None
    assert ctx_denied.participant_ids == []


def test_mark_read_paths(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Unread"
    )

    count = message_service.mark_conversation_messages_as_read(
        conversation.id, test_instructor_with_availability.id
    )
    assert count == 1

    msg = message_repo.get_by_id(msg_id)
    assert msg is not None
    assert any(
        entry.get("user_id") == test_instructor_with_availability.id
        for entry in (msg.read_by or [])
    )

    msg_id_2 = _create_message(
        db, message_repo, conversation.id, test_student.id, "Unread 2"
    )
    result = message_service.mark_messages_read_with_context(
        None, [msg_id_2], test_instructor_with_availability.id
    )
    assert result.count == 1
    assert result.conversation_id == conversation.id


def test_mark_read_with_conversation_context(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Unread"
    )

    result = message_service.mark_messages_read_with_context(
        conversation.id, None, test_instructor_with_availability.id
    )
    assert result.count == 1
    assert result.conversation_id == conversation.id
    assert msg_id in result.marked_message_ids
    assert set(result.participant_ids) == {
        test_student.id,
        test_instructor_with_availability.id,
    }


def test_delete_message_rules(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Delete me"
    )

    with pytest.raises(ForbiddenException):
        message_service.delete_message(msg_id, test_instructor_with_availability.id)

    assert message_service.delete_message(msg_id, test_student.id) is True
    msg = message_repo.get_by_id(msg_id)
    assert msg is not None
    db.refresh(msg)
    assert msg.is_deleted is True

    expired_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Expired delete"
    )
    expired_msg = message_repo.get_by_id(expired_id)
    assert expired_msg is not None
    expired_msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    with pytest.raises(ValidationException):
        message_service.delete_message(expired_id, test_student.id)


def test_delete_message_with_context_expired(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Delete me"
    )
    msg = message_repo.get_by_id(msg_id)
    assert msg is not None
    msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    with pytest.raises(ValidationException):
        message_service.delete_message_with_context(msg_id, test_student.id)


def test_edit_message_paths(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Original"
    )

    with pytest.raises(ValidationException):
        message_service.edit_message(msg_id, test_student.id, " ")

    with pytest.raises(ForbiddenException):
        message_service.edit_message(msg_id, test_instructor_with_availability.id, "Nope")

    assert message_service.edit_message(msg_id, test_student.id, "Original") is True
    assert message_service.edit_message(msg_id, test_student.id, "Updated") is True

    msg = message_repo.get_by_id(msg_id)
    assert msg is not None
    msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    with pytest.raises(ValidationException):
        message_service.edit_message_with_context(msg_id, test_student.id, "Too late")


def test_edit_message_with_context_noop(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "Same"
    )
    result = message_service.edit_message_with_context(msg_id, test_student.id, "Same")
    assert result.success is True


def test_reaction_toggle_and_context(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
    test_instructor_2,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "React"
    )

    assert message_service.add_reaction(
        msg_id, test_instructor_with_availability.id, "👍"
    )
    assert message_service.repository.has_user_reaction(
        msg_id, test_instructor_with_availability.id, "👍"
    )
    assert message_service.add_reaction(
        msg_id, test_instructor_with_availability.id, "👍"
    )
    assert not message_service.repository.has_user_reaction(
        msg_id, test_instructor_with_availability.id, "👍"
    )

    with pytest.raises(ForbiddenException):
        message_service.add_reaction(msg_id, test_instructor_2.id, "🔥")

    ctx_result = message_service.add_reaction_with_context(
        msg_id, test_instructor_with_availability.id, "🔥"
    )
    assert ctx_result.action == "added"

    ctx_removed = message_service.remove_reaction_with_context(
        msg_id, test_instructor_with_availability.id, "🔥"
    )
    assert ctx_removed.success is True

    with pytest.raises(NotFoundException):
        message_service.remove_reaction_with_context(
            "missing-message", test_student.id, "🔥"
        )


def test_remove_reaction_forbidden(
    db,
    message_service,
    message_repo,
    conversation,
    test_student,
    test_instructor_2,
):
    msg_id = _create_message(
        db, message_repo, conversation.id, test_student.id, "React"
    )
    with pytest.raises(ForbiddenException):
        message_service.remove_reaction(msg_id, test_instructor_2.id, "👀")
