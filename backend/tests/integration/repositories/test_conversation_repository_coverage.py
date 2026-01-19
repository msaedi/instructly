from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy.exc import IntegrityError

from app.core.ulid_helper import generate_ulid
from app.models.conversation import Conversation
from app.models.conversation_user_state import ConversationUserState
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository


def test_find_by_pair_self_returns_none(db, test_student):
    repo = ConversationRepository(db)
    assert repo.find_by_pair(test_student.id, test_student.id) is None


def test_find_for_user_excluding_states(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)

    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    state = ConversationUserState(
        id=generate_ulid(),
        user_id=test_student.id,
        conversation_id=conv.id,
        state="archived",
        state_changed_at=datetime.now(timezone.utc),
    )
    db.add(state)
    db.commit()

    results = repo.find_for_user_excluding_states(
        test_student.id, ["archived"], limit=10
    )
    assert results == []


def test_find_for_user_with_state(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)

    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    state = ConversationUserState(
        id=generate_ulid(),
        user_id=test_student.id,
        conversation_id=conv.id,
        state="trashed",
        state_changed_at=datetime.now(timezone.utc),
    )
    db.add(state)
    db.commit()

    results = repo.find_for_user_with_state(test_student.id, "trashed")
    assert len(results) == 1
    assert results[0].id == conv.id

    cursor_time = (conv.last_message_at + timedelta(seconds=1)).isoformat()
    results_cursor = repo.find_for_user_with_state(
        test_student.id, "trashed", cursor=cursor_time
    )
    assert [c.id for c in results_cursor] == [conv.id]

    invalid_cursor = repo.find_for_user_with_state(
        test_student.id, "trashed", cursor="bad-cursor"
    )
    assert [c.id for c in invalid_cursor] == [conv.id]


def test_find_for_user_invalid_cursor_and_offset(
    db, test_student, test_instructor_with_availability, test_instructor_2
):
    repo = ConversationRepository(db)
    conv_old = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    conv_new = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add_all([conv_old, conv_new])
    db.commit()

    results = repo.find_for_user(test_student.id, cursor="not-a-date")
    assert [c.id for c in results][:2] == [conv_new.id, conv_old.id]

    offset_results = repo.find_for_user(test_student.id, offset=1, limit=1)
    assert [c.id for c in offset_results] == [conv_old.id]


def test_find_for_user_include_messages_and_valid_cursor(
    db, test_student, test_instructor_with_availability
):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    cursor_time = (conv.last_message_at + timedelta(seconds=1)).isoformat()
    results = repo.find_for_user(
        test_student.id, include_messages=True, cursor=cursor_time
    )
    assert [c.id for c in results] == [conv.id]


def test_find_for_user_excluding_states_invalid_cursor(
    db, test_student, test_instructor_with_availability
):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    results = repo.find_for_user_excluding_states(
        test_student.id, ["archived"], cursor="bad-cursor"
    )
    assert [c.id for c in results] == [conv.id]


def test_find_for_user_excluding_states_valid_cursor(
    db, test_student, test_instructor_with_availability
):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    cursor_time = (conv.last_message_at + timedelta(seconds=1)).isoformat()
    results = repo.find_for_user_excluding_states(
        test_student.id, ["archived"], cursor=cursor_time
    )
    assert [c.id for c in results] == [conv.id]


def test_update_last_message_at_and_count(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()

    updated = repo.update_last_message_at(conv.id)
    assert updated is not None
    assert updated.last_message_at is not None
    assert repo.count_for_user(test_student.id) == 1

    assert repo.update_last_message_at("missing") is None


def test_get_with_participant_info(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()

    loaded = repo.get_with_participant_info(conv.id)
    assert loaded is not None
    assert loaded.student is not None
    assert loaded.instructor is not None
    assert (
        repo.find_by_booking_participants(
            test_student.id, test_instructor_with_availability.id
        )
        is not None
    )
    assert (
        repo.find_by_user_pair_ids(
            test_student.id, test_instructor_with_availability.id
        )
        is not None
    )


def test_unread_count_and_batch_unread_counts(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()

    msg = Message(
        conversation_id=conv.id,
        sender_id=test_student.id,
        content="Unread",
        read_by=[],
        created_at=datetime.now(timezone.utc),
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()

    count = repo.get_unread_count(conv.id, test_instructor_with_availability.id)
    assert count == 1

    batch = repo.batch_get_unread_counts(
        [conv.id], test_instructor_with_availability.id
    )
    assert batch[conv.id] == 1
    assert repo.batch_get_unread_counts([], test_instructor_with_availability.id) == {}


def test_get_participant_first_names(db, test_student, test_instructor_with_availability):
    repo = ConversationRepository(db)
    names = repo.get_participant_first_names(
        [test_student.id, test_instructor_with_availability.id]
    )
    assert names[test_student.id] == test_student.first_name
    assert names[test_instructor_with_availability.id] == test_instructor_with_availability.first_name
    assert repo.get_participant_first_names([]) == {}


def test_get_or_create_integrity_error_returns_existing(
    db, test_student, test_instructor_with_availability, monkeypatch
):
    repo = ConversationRepository(db)
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()

    call_count = {"count": 0}

    def fake_find_by_pair(student_id, instructor_id):
        call_count["count"] += 1
        if call_count["count"] < 3:
            return None
        return conv

    def fake_create(**_kwargs):
        raise IntegrityError("stmt", {}, Exception("boom"))

    monkeypatch.setattr(repo, "find_by_pair", fake_find_by_pair)
    monkeypatch.setattr(repo, "create", fake_create)

    found, created = repo.get_or_create(test_student.id, test_instructor_with_availability.id)
    assert found.id == conv.id
    assert created is False


def test_conversation_repository_fallback_branches():
    db = Mock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    query = Mock()
    db.query.return_value = query
    query.filter.return_value = query
    query.group_by.return_value = query
    query.all.return_value = [("conv", 2)]
    query.scalar.return_value = 1

    repo = ConversationRepository(db)
    assert repo.get_unread_count("conv", "user") == 1
    assert repo.batch_get_unread_counts(["conv"], "user") == {"conv": 2}

    db_error = Mock()
    db_error.query.side_effect = RuntimeError("boom")
    repo_error = ConversationRepository(db_error)
    assert repo_error.get_participant_first_names(["u1"]) == {"u1": None}
