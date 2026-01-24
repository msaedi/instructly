from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.auth import get_password_hash
from app.models.conversation import Conversation
from app.models.message import MESSAGE_TYPE_SYSTEM_BOOKING_CREATED
from app.models.user import User
from app.repositories.conversation_state_repository import ConversationStateRepository
from app.repositories.message_repository import MessageRepository
from app.services.conversation_service import ConversationService

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def conversation_service(db):
    return ConversationService(db, notification_service=MagicMock())


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


def _create_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: str,
    offset_index: int,
):
    extra_fields = {
        "service_name": "Test Service",
        "hourly_rate": 50.0,
        "total_price": 50.0,
        "duration_minutes": 60,
        "meeting_location": "Test Location",
        "service_area": "Manhattan",
        "location_type": "neutral_location",
    }
    extra_fields.update(booking_timezone_fields(booking_date, start_time, end_time))
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
        offset_index=offset_index,
        **extra_fields,
    )
    return booking


def test_list_conversations_filters_and_pagination(
    db, conversation_service, test_student, test_instructor_with_availability, test_instructor_2
):
    try:  # pragma: no cover - allow running from backend/ root
        from backend.tests.conftest import unique_email
    except ModuleNotFoundError:  # pragma: no cover
        from tests.conftest import unique_email

    def _make_instructor(label: str) -> User:
        user = User(
            email=unique_email(f"test.instructor.{label}"),
            hashed_password=get_password_hash("TestPassword123!"),
            first_name="Extra",
            last_name="Instructor",
            phone="+12125550099",
            zip_code="10001",
            is_active=True,
        )
        db.add(user)
        db.flush()
        return user

    archived_instructor = _make_instructor("archived")
    trashed_instructor = _make_instructor("trashed")

    conv_active = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        last_message_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    conv_active_2 = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_2.id,
        last_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    conv_archived = Conversation(
        student_id=test_student.id,
        instructor_id=archived_instructor.id,
        last_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    conv_trashed = Conversation(
        student_id=test_student.id,
        instructor_id=trashed_instructor.id,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add_all([conv_active, conv_active_2, conv_archived, conv_trashed])
    db.commit()

    state_repo = ConversationStateRepository(db)
    state_repo.set_state(test_student.id, "archived", conversation_id=conv_archived.id)
    state_repo.set_state(test_student.id, "trashed", conversation_id=conv_trashed.id)
    db.commit()

    active_convs, next_cursor = conversation_service.list_conversations_for_user(
        test_student.id, state_filter="active", limit=1
    )
    assert len(active_convs) == 1
    assert next_cursor is not None

    archived_convs, _ = conversation_service.list_conversations_for_user(
        test_student.id, state_filter="archived"
    )
    assert [c.id for c in archived_convs] == [conv_archived.id]

    trashed_convs, _ = conversation_service.list_conversations_for_user(
        test_student.id, state_filter="trashed"
    )
    assert [c.id for c in trashed_convs] == [conv_trashed.id]

    empty_convs, empty_cursor = conversation_service.list_conversations_for_user(
        test_student.id, state_filter="unknown"
    )
    assert empty_convs == []
    assert empty_cursor is None


def test_get_messages_pagination(
    db, conversation_service, message_repo, conversation, test_student
):
    _msg1 = message_repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="One",
    )
    msg2 = message_repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Two",
    )
    msg3 = message_repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Three",
    )
    db.commit()

    messages, has_more, next_cursor = conversation_service.get_messages(
        conversation.id, test_student.id, limit=2
    )
    assert has_more is True
    assert next_cursor is not None
    assert [m.id for m in messages] == [msg2.id, msg3.id]


def test_send_message_auto_tags_booking_id(
    db,
    conversation_service,
    conversation,
    test_student,
    test_instructor_with_availability,
    test_booking,
):
    message = conversation_service.send_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Hello there",
    )
    assert message is not None
    assert message.booking_id == test_booking.id

    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=1),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status="CONFIRMED",
        offset_index=1,
    )
    db.commit()

    message_multi = conversation_service.send_message(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="No tag",
    )
    assert message_multi is not None
    assert message_multi.booking_id is None


def test_create_conversation_with_message_and_invalid_instructor(
    db, conversation_service, test_student, test_instructor_with_availability
):
    result = conversation_service.create_conversation_with_message(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        initial_message="Hi",
    )
    assert result.success is True
    assert result.created is True
    assert result.conversation_id

    invalid = conversation_service.create_conversation_with_message(
        student_id=test_student.id,
        instructor_id=test_student.id,
        initial_message="Invalid",
    )
    assert invalid.success is False
    assert invalid.error is not None


def test_get_messages_with_details_includes_booking(
    db,
    conversation_service,
    message_repo,
    conversation,
    test_student,
    test_booking,
):
    assert test_booking.id
    message = message_repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=None,
        content="System",
        message_type=MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
        booking_id=test_booking.id,
    )
    message.is_deleted = True
    message.deleted_at = datetime.now(timezone.utc)
    message.deleted_by = test_student.id
    db.commit()

    result = conversation_service.get_messages_with_details(
        conversation_id=conversation.id,
        user_id=test_student.id,
        limit=5,
    )
    assert result.conversation_found is True
    assert result.messages
    assert result.messages[0].booking_details is not None
    assert result.messages[0].content == "This message was deleted"


def test_send_message_with_context_notifications(
    db,
    conversation_service,
    conversation,
    test_student,
    test_booking,
):
    notification_mock = MagicMock()
    conversation_service.notification_service = notification_mock

    result = conversation_service.send_message_with_context(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Ping",
    )
    assert result.message is not None
    assert set(result.participant_ids) == {
        conversation.student_id,
        conversation.instructor_id,
    }
    notification_mock.send_message_notification.assert_called_once()

    conversation_service.send_message_with_context(
        conversation_id=conversation.id,
        sender_id=test_student.id,
        content="Invalid booking",
        explicit_booking_id="missing-booking",
    )
    assert notification_mock.send_message_notification.call_count == 1
