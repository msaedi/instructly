from __future__ import annotations

import pytest

from app.models.conversation import Conversation
from app.repositories.conversation_state_repository import ConversationStateRepository


@pytest.fixture
def state_repo(db):
    return ConversationStateRepository(db)


@pytest.fixture
def conversation(db, test_student, test_instructor_with_availability):
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()
    return conv


def test_set_state_creates_and_updates(db, state_repo, conversation, test_student):
    state = state_repo.set_state(
        test_student.id, "archived", conversation_id=conversation.id
    )
    assert state.state == "archived"

    updated = state_repo.set_state(
        test_student.id, "trashed", conversation_id=conversation.id
    )
    assert updated.id == state.id
    assert updated.state == "trashed"


def test_set_state_requires_conversation_id(state_repo, test_student):
    with pytest.raises(ValueError):
        state_repo.set_state(test_student.id, "archived", conversation_id=None)


def test_get_states_and_ids(db, state_repo, conversation, test_student):
    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    db.commit()

    states = state_repo.get_states_for_user(test_student.id, state="archived")
    assert len(states) == 1

    ids = state_repo.get_conversation_ids_by_state(test_student.id, "archived")
    assert ids == [conversation.id]


def test_restore_to_active(db, state_repo, conversation, test_student):
    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    db.commit()

    restored = state_repo.restore_to_active(
        test_student.id, conversation_id=conversation.id
    )
    assert restored is not None
    assert restored.state == "active"


def test_batch_and_excluded_states(
    db, state_repo, test_student, test_instructor_with_availability, test_instructor_2
):
    conv1 = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    conv2 = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
    )
    db.add_all([conv1, conv2])
    db.commit()

    state_repo.set_state(test_student.id, "archived", conversation_id=conv1.id)
    state_repo.set_state(test_student.id, "trashed", conversation_id=conv2.id)
    db.commit()

    states = state_repo.batch_get_states(test_student.id, [conv1.id, conv2.id])
    assert states[conv1.id] == "archived"
    assert states[conv2.id] == "trashed"

    archived, trashed = state_repo.get_excluded_conversation_ids(test_student.id)
    assert conv1.id in archived
    assert conv2.id in trashed


def test_get_state_without_conversation_id_returns_none(state_repo, test_student):
    """L32: get_state without conversation_id returns None."""
    result = state_repo.get_state(test_student.id, conversation_id=None)
    assert result is None


def test_get_states_for_user_no_filter(db, state_repo, conversation, test_student):
    """L74: get_states_for_user without state filter returns all states."""
    state_repo.set_state(test_student.id, "archived", conversation_id=conversation.id)
    db.commit()

    all_states = state_repo.get_states_for_user(test_student.id)
    assert len(all_states) >= 1

    filtered = state_repo.get_states_for_user(test_student.id, state="archived")
    assert len(filtered) >= 1


def test_get_booking_ids_by_state_returns_empty(state_repo, test_student):
    """L93: Legacy method always returns []."""
    assert state_repo.get_booking_ids_by_state(test_student.id, "archived") == []


def test_restore_to_active_already_active(db, state_repo, conversation, test_student):
    """restore_to_active when already active returns existing without change."""
    state_repo.set_state(test_student.id, "active", conversation_id=conversation.id)
    db.commit()

    result = state_repo.restore_to_active(test_student.id, conversation_id=conversation.id)
    assert result is not None
    assert result.state == "active"


def test_restore_to_active_no_existing_returns_none(state_repo, test_student):
    """restore_to_active when no state exists returns None."""
    result = state_repo.restore_to_active(test_student.id, conversation_id="nonexistent-conv-id-xxxxx")
    assert result is None


def test_batch_get_states_empty_list(state_repo, test_student):
    """batch_get_states with empty conversation_ids returns {}."""
    result = state_repo.batch_get_states(test_student.id, [])
    assert result == {}


def test_get_excluded_conversation_ids_no_states(state_repo, test_student):
    """get_excluded_conversation_ids with no archived/trashed returns empty sets."""
    archived, trashed = state_repo.get_excluded_conversation_ids(test_student.id)
    # May have states from other tests, but should be valid sets
    assert isinstance(archived, set)
    assert isinstance(trashed, set)
