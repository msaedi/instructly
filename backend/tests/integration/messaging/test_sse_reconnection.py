# backend/tests/integration/messaging/test_sse_reconnection.py
"""Integration-style tests for SSE reconnection and Redis fallback."""

from contextlib import asynccontextmanager
import json

import pytest

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.messaging import sse_stream
from app.services.messaging.sse_stream import create_sse_stream, fetch_messages_after


@pytest.mark.asyncio
async def test_reconnection_catches_up(
    db,
    test_booking,
    test_student,
    test_instructor_with_availability,
    monkeypatch,
) -> None:
    """Messages sent during disconnect are delivered on reconnect via Last-Event-ID."""
    conversation_repo = ConversationRepository(db)
    repo = MessageRepository(db)
    conversation, _created = conversation_repo.get_or_create(
        student_id=str(test_student.id), instructor_id=str(test_instructor_with_availability.id)
    )

    msg1 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="First",
    )
    msg2 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="Second",
    )
    msg3 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_student.id),
        booking_id=str(test_booking.id),
        content="Third",
    )
    msg4 = repo.create_conversation_message(
        conversation_id=conversation.id,
        sender_id=str(test_instructor_with_availability.id),
        booking_id=str(test_booking.id),
        content="Fourth",
    )
    db.commit()

    @asynccontextmanager
    async def fake_subscribe(user_id: str):
        class _DummyPubSub:
            pass

        yield _DummyPubSub()

    async def fake_stream_with_heartbeat(*args, **kwargs):
        if False:  # pragma: no cover - marker to make this an async generator
            yield {}
        return

    monkeypatch.setattr(sse_stream.pubsub_manager, "subscribe", fake_subscribe)
    monkeypatch.setattr(sse_stream, "stream_with_heartbeat", fake_stream_with_heartbeat)

    # Pre-fetch missed messages (as the route handler now does)
    missed_messages = fetch_messages_after(db, str(test_student.id), str(msg1.id))

    events = []
    async for event in create_sse_stream(
        user_id=str(test_student.id),
        missed_messages=missed_messages,
    ):
        events.append(event)

    new_message_events = [e for e in events if e["event"] == "new_message"]
    new_message_ids = [e["id"] for e in new_message_events]
    assert new_message_ids == [str(msg2.id), str(msg3.id), str(msg4.id)]

    contents = [json.loads(e["data"])["message"]["content"] for e in new_message_events]
    assert contents == ["Second", "Third", "Fourth"]

    # Final event should be the connected acknowledgement
    assert events[-1]["event"] == "connected"


@pytest.mark.asyncio
async def test_redis_failure_recovery(db, test_booking, test_student, monkeypatch) -> None:
    """Stream yields an error event if Redis subscription fails."""

    @asynccontextmanager
    async def failing_subscribe(*args, **kwargs):
        raise RuntimeError("Redis down")
        yield  # pragma: no cover

    monkeypatch.setattr(sse_stream.pubsub_manager, "subscribe", failing_subscribe)

    events = []
    async for event in create_sse_stream(
        user_id=str(test_student.id),
        missed_messages=None,
    ):
        events.append(event)

    assert events[0]["event"] == "connected"
    assert any(evt["event"] == "error" for evt in events)
