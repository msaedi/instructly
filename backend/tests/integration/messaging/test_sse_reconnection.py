# backend/tests/integration/messaging/test_sse_reconnection.py
"""Integration-style tests for SSE reconnection and Broadcaster-based streaming."""

from contextlib import asynccontextmanager
import json
from unittest.mock import MagicMock

import pytest

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
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

    # Mock Broadcaster to return immediately (no real Redis subscription)
    mock_broadcast = MagicMock()

    @asynccontextmanager
    async def fake_subscribe(channel: str):
        """Fake subscriber that yields nothing (simulates disconnect/reconnect scenario)."""

        class _EmptySubscriber:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        yield _EmptySubscriber()

    mock_broadcast.subscribe = fake_subscribe

    def mock_get_broadcast():
        return mock_broadcast

    monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", mock_get_broadcast)

    # Pre-fetch missed messages (as the route handler now does)
    missed_messages = await fetch_messages_after(db, str(test_student.id), str(msg1.id))

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
async def test_broadcaster_failure_recovery(db, test_booking, test_student, monkeypatch) -> None:
    """Stream yields an error event if Broadcaster subscription fails."""

    def mock_get_broadcast():
        raise RuntimeError("Broadcast not initialized")

    monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", mock_get_broadcast)

    events = []
    async for event in create_sse_stream(
        user_id=str(test_student.id),
        missed_messages=None,
    ):
        events.append(event)

    assert events[0]["event"] == "connected"
    assert any(evt["event"] == "error" for evt in events)


@pytest.mark.asyncio
async def test_sse_stream_heartbeat_on_timeout(db, test_student, monkeypatch) -> None:
    """Stream sends heartbeat when no messages arrive within timeout."""
    import asyncio

    mock_broadcast = MagicMock()

    @asynccontextmanager
    async def fake_subscribe(channel: str):
        """Fake subscriber that yields nothing for a while, triggering heartbeats."""

        class _SlowSubscriber:
            """Async iterator that waits before ending (simulating idle connection)."""

            def __aiter__(self):
                return self

            async def __anext__(self):
                # Wait longer than heartbeat interval to trigger heartbeats
                # The reader task will be cancelled when we break from the main loop
                await asyncio.sleep(10)  # Long sleep - will be cancelled
                raise StopAsyncIteration

        yield _SlowSubscriber()

    mock_broadcast.subscribe = fake_subscribe

    def mock_get_broadcast():
        return mock_broadcast

    monkeypatch.setattr("app.services.messaging.sse_stream.get_broadcast", mock_get_broadcast)
    # Use a very short heartbeat for testing
    monkeypatch.setattr("app.services.messaging.sse_stream.HEARTBEAT_INTERVAL", 0.05)

    events = []
    async for event in create_sse_stream(
        user_id=str(test_student.id),
        missed_messages=None,
    ):
        events.append(event)
        # Stop after getting some events to prevent infinite loop
        if len(events) >= 4:
            break

    # Should have: connected + heartbeats
    assert events[0]["event"] == "connected"
    heartbeat_events = [e for e in events if e["event"] == "heartbeat"]
    assert len(heartbeat_events) >= 1, "Should have at least one heartbeat event"
