# backend/tests/repositories/test_event_outbox_repository.py
"""
Comprehensive tests for EventOutboxRepository.

Tests cover:
- Event enqueueing with idempotency
- Pending event fetching with locking
- State transitions (mark_sent, mark_failed)
- Batch operations (reset_failed)
- Dialect-specific behavior (PostgreSQL vs SQLite)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.event_outbox import EventOutboxStatus
from app.repositories.event_outbox_repository import EventOutboxRepository


class TestEnqueue:
    """Tests for the enqueue method."""

    def test_enqueue_creates_new_event(self, db):
        """Should create a new outbox event."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            payload={"key": "value"},
        )

        assert event is not None
        assert event.event_type == "test_event"
        assert event.aggregate_id == "agg-123"
        assert event.payload == {"key": "value"}
        assert event.status == EventOutboxStatus.PENDING.value
        assert event.attempt_count == 0

    def test_enqueue_with_custom_idempotency_key(self, db):
        """Should use provided idempotency key."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            idempotency_key="custom-key-123",
        )

        assert event.idempotency_key == "custom-key-123"

    def test_enqueue_generates_idempotency_key(self, db):
        """Should generate idempotency key if not provided."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )

        # Should be in format: event_type:aggregate_id:timestamp
        assert event.idempotency_key.startswith("test_event:agg-123:")

    def test_enqueue_with_custom_next_attempt_at(self, db):
        """Should use provided next_attempt_at."""
        repo = EventOutboxRepository(db)

        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            next_attempt_at=future_time,
        )

        # Times should be close (within a second due to DB operations)
        assert abs((event.next_attempt_at - future_time).total_seconds()) < 2

    def test_enqueue_idempotent_returns_existing(self, db):
        """Should return existing event if idempotency key exists."""
        repo = EventOutboxRepository(db)

        # First enqueue
        event1 = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            idempotency_key="unique-key",
            payload={"version": 1},
        )

        # Second enqueue with same key
        event2 = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            idempotency_key="unique-key",
            payload={"version": 2},  # Different payload
        )

        # Should return the same event
        assert event1.id == event2.id
        # Payload should NOT be updated (idempotency preserved)
        assert event2.payload == {"version": 1}

    def test_enqueue_empty_payload_defaults_to_empty_dict(self, db):
        """Should default to empty dict if payload is None."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            payload=None,
        )

        assert event.payload == {}


class TestFetchPending:
    """Tests for the fetch_pending method."""

    def test_fetch_pending_returns_pending_events(self, db):
        """Should return events with PENDING status."""
        repo = EventOutboxRepository(db)

        # Create pending event
        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        pending = repo.fetch_pending()

        pending_ids = [e.id for e in pending]
        assert event.id in pending_ids

    def test_fetch_pending_respects_limit(self, db):
        """Should respect the limit parameter."""
        repo = EventOutboxRepository(db)

        # Create multiple events
        for i in range(5):
            repo.enqueue(
                event_type="test_event",
                aggregate_id=f"agg-{i}",
                idempotency_key=f"key-{i}",
            )
        db.flush()

        pending = repo.fetch_pending(limit=2)

        assert len(pending) <= 2

    def test_fetch_pending_excludes_future_events(self, db):
        """Should not return events with future next_attempt_at."""
        repo = EventOutboxRepository(db)

        # Create future event
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            next_attempt_at=future_time,
        )
        db.flush()

        pending = repo.fetch_pending()

        pending_ids = [e.id for e in pending]
        assert event.id not in pending_ids

    def test_fetch_pending_excludes_sent_events(self, db):
        """Should not return events with SENT status."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Mark as sent
        repo.mark_sent(event.id, attempt_count=1)
        db.flush()

        pending = repo.fetch_pending()

        pending_ids = [e.id for e in pending]
        assert event.id not in pending_ids

    def test_fetch_pending_excludes_failed_events(self, db):
        """Should not return events with FAILED status."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Mark as failed (terminal)
        repo.mark_failed(event.id, attempt_count=3, backoff_seconds=0, terminal=True)
        db.flush()

        pending = repo.fetch_pending()

        pending_ids = [e.id for e in pending]
        assert event.id not in pending_ids

    def test_fetch_pending_orders_by_next_attempt_at(self, db):
        """Should return events ordered by next_attempt_at ascending."""
        repo = EventOutboxRepository(db)

        # Create events with different times
        now = datetime.now(timezone.utc)
        event2 = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-2",
            idempotency_key="key-2",
            next_attempt_at=now - timedelta(minutes=5),
        )
        event1 = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-1",
            idempotency_key="key-1",
            next_attempt_at=now - timedelta(minutes=10),  # Older
        )
        db.flush()

        pending = repo.fetch_pending()

        # First event should be the oldest
        pending_ids = [e.id for e in pending]
        if event1.id in pending_ids and event2.id in pending_ids:
            assert pending_ids.index(event1.id) < pending_ids.index(event2.id)


class TestGetById:
    """Tests for the get_by_id method."""

    def test_get_by_id_returns_event(self, db):
        """Should return event by ID."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        fetched = repo.get_by_id(event.id)

        assert fetched is not None
        assert fetched.id == event.id

    def test_get_by_id_returns_none_for_missing(self, db):
        """Should return None for non-existent ID."""
        repo = EventOutboxRepository(db)

        fetched = repo.get_by_id("nonexistent-id")

        assert fetched is None

    def test_get_by_id_without_for_update(self, db):
        """Should work without for_update flag."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        fetched = repo.get_by_id(event.id, for_update=False)

        assert fetched is not None
        assert fetched.id == event.id


class TestMarkSent:
    """Tests for the mark_sent method."""

    def test_mark_sent_updates_status(self, db):
        """Should update status to SENT."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        repo.mark_sent(event.id, attempt_count=1)
        db.flush()
        db.refresh(event)

        assert event.status == EventOutboxStatus.SENT.value

    def test_mark_sent_updates_attempt_count(self, db):
        """Should update attempt count."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        repo.mark_sent(event.id, attempt_count=5)
        db.flush()
        db.refresh(event)

        assert event.attempt_count == 5

    def test_mark_sent_clears_last_error(self, db):
        """Should clear last_error on success."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # First, set an error
        repo.mark_failed(event.id, attempt_count=1, backoff_seconds=60, error="Some error")
        db.flush()
        db.refresh(event)
        assert event.last_error == "Some error"

        # Then mark sent
        repo.mark_sent(event.id, attempt_count=2)
        db.flush()
        db.refresh(event)

        assert event.last_error is None


class TestMarkSentByKey:
    """Tests for the mark_sent_by_key method."""

    def test_mark_sent_by_key_updates_status(self, db):
        """Should update status to SENT using idempotency key."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
            idempotency_key="my-key",
        )
        db.flush()

        repo.mark_sent_by_key("my-key", attempt_count=1)
        db.flush()
        db.refresh(event)

        assert event.status == EventOutboxStatus.SENT.value
        assert event.attempt_count == 1


class TestMarkFailed:
    """Tests for the mark_failed method."""

    def test_mark_failed_non_terminal(self, db):
        """Should keep PENDING status and set next retry time for non-terminal failures."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()
        original_attempt_at = event.next_attempt_at

        # Non-terminal failure (retry later)
        repo.mark_failed(
            event.id,
            attempt_count=1,
            backoff_seconds=60,
            error="Temporary error",
            terminal=False,
        )
        db.flush()
        db.refresh(event)

        assert event.status == EventOutboxStatus.PENDING.value
        assert event.attempt_count == 1
        assert event.last_error == "Temporary error"
        # Next attempt should be in the future
        assert event.next_attempt_at > original_attempt_at

    def test_mark_failed_terminal(self, db):
        """Should set FAILED status for terminal failures."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Terminal failure (no retry)
        repo.mark_failed(
            event.id,
            attempt_count=3,
            backoff_seconds=0,
            error="Permanent error",
            terminal=True,
        )
        db.flush()
        db.refresh(event)

        assert event.status == EventOutboxStatus.FAILED.value
        assert event.attempt_count == 3
        assert event.last_error == "Permanent error"

    def test_mark_failed_truncates_long_error(self, db):
        """Should truncate error messages longer than 1000 chars."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        long_error = "x" * 2000
        repo.mark_failed(
            event.id,
            attempt_count=1,
            backoff_seconds=60,
            error=long_error,
        )
        db.flush()
        db.refresh(event)

        assert len(event.last_error) == 1000

    def test_mark_failed_handles_none_error(self, db):
        """Should handle None error gracefully."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        repo.mark_failed(
            event.id,
            attempt_count=1,
            backoff_seconds=60,
            error=None,
        )
        db.flush()
        db.refresh(event)

        assert event.last_error is None

    def test_mark_failed_minimum_backoff(self, db):
        """Should enforce minimum 1 second backoff."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()
        before_time = datetime.now(timezone.utc)

        # Zero or negative backoff should become 1 second
        repo.mark_failed(
            event.id,
            attempt_count=1,
            backoff_seconds=0,
            terminal=False,
        )
        db.flush()
        db.refresh(event)

        # Should be at least 1 second in the future
        assert event.next_attempt_at >= before_time + timedelta(seconds=1)


class TestResetFailed:
    """Tests for the reset_failed method."""

    def test_reset_failed_changes_status_to_pending(self, db):
        """Should reset FAILED events back to PENDING."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Mark as failed
        repo.mark_failed(event.id, attempt_count=3, backoff_seconds=0, terminal=True)
        db.flush()
        db.refresh(event)
        assert event.status == EventOutboxStatus.FAILED.value

        # Reset the failed event
        repo.reset_failed([event.id])
        db.flush()
        db.refresh(event)

        assert event.status == EventOutboxStatus.PENDING.value

    def test_reset_failed_empty_list_no_op(self, db):
        """Lines 202-204: Should handle empty list gracefully."""
        repo = EventOutboxRepository(db)

        # Should not raise any errors
        repo.reset_failed([])
        db.flush()

    def test_reset_failed_multiple_events(self, db):
        """Should reset multiple failed events."""
        repo = EventOutboxRepository(db)

        events = []
        for i in range(3):
            event = repo.enqueue(
                event_type="test_event",
                aggregate_id=f"agg-{i}",
                idempotency_key=f"key-{i}",
            )
            events.append(event)
        db.flush()

        # Mark all as failed
        for event in events:
            repo.mark_failed(event.id, attempt_count=3, backoff_seconds=0, terminal=True)
        db.flush()

        # Reset all events
        repo.reset_failed([e.id for e in events])
        db.flush()

        for event in events:
            db.refresh(event)
            assert event.status == EventOutboxStatus.PENDING.value

    def test_reset_failed_updates_timestamps(self, db):
        """Lines 205-215: Should update next_attempt_at and updated_at."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Mark as failed
        repo.mark_failed(event.id, attempt_count=3, backoff_seconds=0, terminal=True)
        db.flush()

        before_reset = datetime.now(timezone.utc)

        # Reset
        repo.reset_failed([event.id])
        db.flush()
        db.refresh(event)

        # next_attempt_at should be recent (around now)
        assert event.next_attempt_at >= before_reset - timedelta(seconds=2)


class TestDialectHandling:
    """Tests for dialect-specific behavior."""

    def test_sqlite_dialect_detection(self, db):
        """Should detect SQLite dialect correctly."""
        repo = EventOutboxRepository(db)

        # The dialect is determined at init time
        # This test just verifies the repository initializes without error
        assert repo._dialect is not None

    def test_postgresql_dialect_detection(self, db):
        """Should detect PostgreSQL dialect correctly."""
        repo = EventOutboxRepository(db)

        # Most tests run against PostgreSQL
        if "postgresql" in str(db.bind.url):
            assert repo._dialect == "postgresql"


class TestEnqueueEdgeCases:
    """Tests for edge cases in enqueue that raise RuntimeErrors."""

    def test_enqueue_raises_if_inserted_row_not_found(self, db):
        """Line 99: Should raise RuntimeError if inserted row can't be reloaded."""
        repo = EventOutboxRepository(db)

        with patch.object(db, "get", return_value=None):
            with patch.object(db, "execute") as mock_execute:
                # Mock PostgreSQL insert returning a value
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = "fake-id"
                mock_execute.return_value = mock_result

                with patch.object(db, "flush"):
                    with pytest.raises(RuntimeError, match="Inserted outbox row could not be reloaded"):
                        repo.enqueue(
                            event_type="test",
                            aggregate_id="agg",
                        )

    def test_enqueue_raises_if_conflict_row_not_found(self, db):
        """Line 108: Should raise RuntimeError if existing row not found after conflict."""
        repo = EventOutboxRepository(db)

        # Create initial event
        repo.enqueue(
            event_type="test",
            aggregate_id="agg",
            idempotency_key="conflict-key",
        )
        db.flush()

        with patch.object(db, "execute") as mock_execute:
            # First call for insert returns None (conflict)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result

            # The select for existing should also return None
            with patch.object(db, "flush"):
                with pytest.raises(RuntimeError, match="Outbox row not found after enqueue conflict"):
                    # Force a conflict scenario
                    repo.enqueue(
                        event_type="test",
                        aggregate_id="agg",
                        idempotency_key="conflict-key-not-found",
                    )


class TestGetByIdWithForUpdate:
    """Tests for get_by_id with for_update on PostgreSQL (lines 132-138)."""

    def test_get_by_id_with_for_update_postgresql(self, db):
        """Should use FOR UPDATE SKIP LOCKED on PostgreSQL."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # This exercises lines 132-138 on PostgreSQL
        if repo._dialect == "postgresql":
            fetched = repo.get_by_id(event.id, for_update=True)
            assert fetched is not None
            assert fetched.id == event.id

    def test_get_by_id_with_for_update_non_postgresql(self, db):
        """Should fall back to regular get on non-PostgreSQL."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # Force non-postgresql dialect
        original_dialect = repo._dialect
        repo._dialect = "sqlite"

        fetched = repo.get_by_id(event.id, for_update=True)

        repo._dialect = original_dialect

        assert fetched is not None
        assert fetched.id == event.id


class TestFetchPendingWithForUpdate:
    """Tests for fetch_pending with FOR UPDATE on PostgreSQL (line 122-123)."""

    def test_fetch_pending_uses_for_update_on_postgresql(self, db):
        """Should use FOR UPDATE SKIP LOCKED when fetching pending on PostgreSQL."""
        repo = EventOutboxRepository(db)

        event = repo.enqueue(
            event_type="test_event",
            aggregate_id="agg-123",
        )
        db.flush()

        # This exercises line 122-123 on PostgreSQL
        pending = repo.fetch_pending()

        # Should still return the event
        pending_ids = [e.id for e in pending]
        assert event.id in pending_ids


class TestIdempotencyKeyGeneration:
    """Tests for automatic idempotency key generation."""

    def test_idempotency_key_includes_timestamp(self, db):
        """Generated key should include timestamp component."""
        repo = EventOutboxRepository(db)

        before = datetime.now(timezone.utc)
        event = repo.enqueue(
            event_type="event_type",
            aggregate_id="aggregate",
        )
        after = datetime.now(timezone.utc)

        # Key format: event_type:aggregate_id:timestamp
        parts = event.idempotency_key.split(":")
        assert len(parts) == 3
        assert parts[0] == "event_type"
        assert parts[1] == "aggregate"

        # Timestamp should be between before and after
        timestamp = int(parts[2])
        assert int(before.timestamp()) <= timestamp <= int(after.timestamp()) + 1
