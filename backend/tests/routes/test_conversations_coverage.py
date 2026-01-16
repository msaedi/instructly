from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routes.v1 import conversations as conversations_routes
from app.schemas.conversation import (
    CreateConversationRequest,
    SendMessageRequest,
    TypingRequest,
    UpdateConversationStateRequest,
)


@dataclass
class DummyMessage:
    id: str
    content: str
    sender_id: str
    created_at: datetime


@dataclass
class DummyConversation:
    id: str
    student: object | None
    instructor: object | None
    instructor_id: str
    messages: list[DummyMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DummyCreateConversationResult:
    success: bool
    error: str | None
    conversation_id: str | None
    created: bool


@dataclass
class DummyTypingContext:
    participant_ids: list[str]


@dataclass
class DummyMessageDetails:
    id: str
    content: str
    sender_id: str
    message_type: str
    booking_id: str | None
    created_at: datetime
    edited_at: str | None
    is_deleted: bool
    delivered_at: str | None
    read_by: list[dict]
    reactions: list[dict]
    booking_details: dict | None


@dataclass
class DummyMessagesResult:
    conversation_found: bool
    messages: list[DummyMessageDetails]
    has_more: bool
    next_cursor: str | None


@dataclass
class DummySendMessageResult:
    message: object | None
    participant_ids: list[str]


def test_safe_truncate_and_build_booking_summary():
    assert conversations_routes._safe_truncate("short", 10) == "short"
    assert conversations_routes._safe_truncate("123456", 5) == "1234…"

    booking = SimpleNamespace(
        id="booking1",
        booking_date=date(2025, 1, 1),
        start_time=time(9, 30),
        instructor_service=SimpleNamespace(name="Piano"),
    )
    summary = conversations_routes._build_booking_summary(booking)
    assert summary.start_time == "09:30"
    assert summary.service_name == "Piano"

    booking_string_time = SimpleNamespace(
        id="booking2",
        booking_date=date(2025, 1, 1),
        start_time="14:45:00",
        instructor_service=None,
    )
    summary_string = conversations_routes._build_booking_summary(booking_string_time)
    assert summary_string.start_time == "14:45"
    assert summary_string.service_name == "Lesson"


def test_list_conversations_skips_missing_user_and_last_message(test_student, test_instructor):
    now = datetime.now(timezone.utc)
    message_old = DummyMessage(
        id="msg1",
        content="hello",
        sender_id=test_instructor.id,
        created_at=now,
    )
    message_new = DummyMessage(
        id="msg2",
        content="x" * 150,
        sender_id=test_student.id,
        created_at=now + timedelta(minutes=1),
    )

    conv_missing = DummyConversation(
        id="conv_missing",
        student=None,
        instructor=test_instructor,
        instructor_id=test_instructor.id,
        messages=[],
    )
    conv_with = DummyConversation(
        id="conv_with",
        student=test_student,
        instructor=test_instructor,
        instructor_id=test_instructor.id,
        messages=[message_old, message_new],
    )

    booking = SimpleNamespace(
        id="booking1",
        booking_date=date(2025, 1, 1),
        start_time=time(10, 0),
        instructor_service=SimpleNamespace(name="Guitar"),
    )

    class StubService:
        def list_conversations_for_user(self, *_args, **_kwargs):
            return [conv_missing, conv_with], "cursor"

        def batch_get_upcoming_bookings(self, *_args, **_kwargs):
            return {"conv_with": [booking]}

        def batch_get_states(self, *_args, **_kwargs):
            return {"conv_with": "archived"}

        def batch_get_unread_counts(self, *_args, **_kwargs):
            return {"conv_with": 2}

    response = conversations_routes.list_conversations(
        current_user=test_instructor,
        service=StubService(),
    )

    assert response.next_cursor == "cursor"
    assert len(response.conversations) == 1
    item = response.conversations[0]
    assert item.id == "conv_with"
    assert item.last_message is not None
    assert item.last_message.content.endswith("…")
    assert item.state == "archived"
    assert item.unread_count == 2
    assert item.next_booking is not None


def test_get_conversation_missing_participant(test_instructor):
    conversation = DummyConversation(
        id="conv1",
        student=None,
        instructor=test_instructor,
        instructor_id=test_instructor.id,
    )

    class StubService:
        def get_conversation_by_id(self, *_args, **_kwargs):
            return conversation

        def get_upcoming_bookings_for_conversation(self, _conversation):
            return []

        def get_conversation_user_state(self, *_args, **_kwargs):
            return "active"

    with pytest.raises(HTTPException) as excinfo:
        conversations_routes.get_conversation(
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_instructor,
            service=StubService(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_create_conversation_error_paths(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    class StubServiceNotFound:
        def create_conversation_with_message(self, *_args, **_kwargs):
            return DummyCreateConversationResult(
                success=False,
                error="Instructor not found",
                conversation_id=None,
                created=False,
            )

    with pytest.raises(HTTPException) as excinfo:
        await conversations_routes.create_conversation(
            request=CreateConversationRequest(instructor_id="01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            current_user=test_student,
            service=StubServiceNotFound(),
        )
    assert excinfo.value.status_code == 404

    class StubServiceBadRequest:
        def create_conversation_with_message(self, *_args, **_kwargs):
            return DummyCreateConversationResult(
                success=False,
                error="Student not allowed",
                conversation_id=None,
                created=False,
            )

    with pytest.raises(HTTPException) as excinfo:
        await conversations_routes.create_conversation(
            request=CreateConversationRequest(instructor_id="01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            current_user=test_student,
            service=StubServiceBadRequest(),
        )
    assert excinfo.value.status_code == 400


def test_update_conversation_state_errors(test_student):
    class StubServiceMissing:
        def get_conversation_by_id(self, *_args, **_kwargs):
            return None

    with pytest.raises(HTTPException) as excinfo:
        conversations_routes.update_conversation_state(
            request=UpdateConversationStateRequest(state="archived"),
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=StubServiceMissing(),
        )
    assert excinfo.value.status_code == 404

    class StubServiceInvalid:
        def get_conversation_by_id(self, *_args, **_kwargs):
            return DummyConversation(
                id="conv1",
                student=test_student,
                instructor=None,
                instructor_id="inst1",
            )

        def set_conversation_user_state(self, *_args, **_kwargs):
            raise ValueError("invalid state")

    with pytest.raises(HTTPException) as excinfo:
        conversations_routes.update_conversation_state(
            request=UpdateConversationStateRequest(state="archived"),
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=StubServiceInvalid(),
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_send_typing_indicator_not_found(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    class StubService:
        def get_typing_context(self, *_args, **_kwargs):
            return None

    with pytest.raises(HTTPException) as excinfo:
        await conversations_routes.send_typing_indicator(
            request=TypingRequest(is_typing=True),
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=StubService(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_send_typing_indicator_publish_error(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_publish(*_args, **_kwargs):
        raise RuntimeError("publish failed")

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "app.routes.v1.conversations.publish_typing_status_direct",
        fake_publish,
    )

    class StubService:
        def get_typing_context(self, *_args, **_kwargs):
            return DummyTypingContext(participant_ids=["u1", "u2"])

    response = await conversations_routes.send_typing_indicator(
        request=TypingRequest(is_typing=False),
        conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        current_user=test_student,
        service=StubService(),
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_get_messages_builds_booking_details(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    message_details = DummyMessageDetails(
        id="msg1",
        content="hello",
        sender_id=test_student.id,
        message_type="user",
        booking_id="booking1",
        created_at=datetime.now(timezone.utc),
        edited_at=None,
        is_deleted=False,
        delivered_at=None,
        read_by=[{"user_id": "user_2", "read_at": ""}],
        reactions=[{"user_id": "user_3", "emoji": "👍"}],
        booking_details={
            "id": "booking1",
            "date": "2025-01-01",
            "start_time": "09:00",
            "service_name": "Piano",
        },
    )

    class StubService:
        def get_messages_with_details(self, *_args, **_kwargs):
            return DummyMessagesResult(
                conversation_found=True,
                messages=[message_details],
                has_more=False,
                next_cursor=None,
            )

    response = await conversations_routes.get_messages(
        conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        current_user=test_student,
        service=StubService(),
    )
    assert len(response.messages) == 1
    message = response.messages[0]
    assert message.booking_details is not None
    assert message.read_by[0].user_id == "user_2"
    assert message.reactions[0].emoji == "👍"


@pytest.mark.asyncio
async def test_get_messages_not_found(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    class StubService:
        def get_messages_with_details(self, *_args, **_kwargs):
            return DummyMessagesResult(
                conversation_found=False,
                messages=[],
                has_more=False,
                next_cursor=None,
            )

    with pytest.raises(HTTPException) as excinfo:
        await conversations_routes.get_messages(
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=StubService(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_send_message_publish_error(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_publish(*_args, **_kwargs):
        raise RuntimeError("publish failed")

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "app.routes.v1.conversations.publish_new_message_direct",
        fake_publish,
    )

    message = SimpleNamespace(
        id="msg1",
        content="hello",
        sender_id=test_student.id,
        created_at=datetime.now(timezone.utc),
        booking_id=None,
        delivered_at=None,
        message_type="user",
    )

    class StubService:
        def send_message_with_context(self, *_args, **_kwargs):
            return DummySendMessageResult(message=message, participant_ids=["u1", "u2"])

    response = await conversations_routes.send_message(
        request=SendMessageRequest(content="hello"),
        conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        current_user=test_student,
        service=StubService(),
    )
    assert response.id == "msg1"


@pytest.mark.asyncio
async def test_send_message_not_found(monkeypatch, test_student):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    class StubService:
        def send_message_with_context(self, *_args, **_kwargs):
            return DummySendMessageResult(message=None, participant_ids=[])

    with pytest.raises(HTTPException) as excinfo:
        await conversations_routes.send_message(
            request=SendMessageRequest(content="hello"),
            conversation_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            current_user=test_student,
            service=StubService(),
        )
    assert excinfo.value.status_code == 404
