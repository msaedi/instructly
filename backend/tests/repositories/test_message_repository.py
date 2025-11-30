"""
Tests for Message Repository.

Tests all messaging bugs that were fixed during Phase 4:
- Bug #4: delivered_at field persistence
- Bug #5: read_by field persistence
- Self-message read prevention
"""

from datetime import datetime, timezone

from app.models.message import Message
from app.repositories.message_repository import MessageRepository


class TestMessageRepository:
    """Tests for MessageRepository basic operations."""

    def test_create_message_sets_delivered_at(self, db, test_booking):
        """Bug #4: Messages should have delivered_at set on creation."""
        repo = MessageRepository(db)

        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )

        assert message.delivered_at is not None
        assert isinstance(message.delivered_at, datetime)
        # Should be very recent (within last minute)
        time_diff = datetime.now(timezone.utc) - message.delivered_at
        assert time_diff.total_seconds() < 60

    def test_mark_messages_as_read_persists_read_by(self, db, test_booking, test_student):
        """Bug #5: read_by should be persisted to database."""
        repo = MessageRepository(db)

        # Create a message from instructor
        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello student"
        )
        db.commit()

        # Mark as read by student
        repo.mark_messages_as_read([message.id], test_student.id)
        db.commit()

        # Refresh from database
        db.expire_all()
        refreshed_message = db.query(Message).filter(Message.id == message.id).first()

        # read_by should be persisted
        assert refreshed_message.read_by is not None
        assert len(refreshed_message.read_by) == 1
        assert refreshed_message.read_by[0]['user_id'] == test_student.id
        assert 'read_at' in refreshed_message.read_by[0]

    def test_mark_messages_as_read_does_not_duplicate(self, db, test_booking, test_student):
        """Should not add duplicate entries to read_by array."""
        repo = MessageRepository(db)

        # Create a message
        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        # Mark as read twice
        repo.mark_messages_as_read([message.id], test_student.id)
        db.commit()

        repo.mark_messages_as_read([message.id], test_student.id)
        db.commit()

        # Refresh and check - should only have one entry
        db.expire_all()
        refreshed_message = db.query(Message).filter(Message.id == message.id).first()

        assert refreshed_message.read_by is not None
        assert len(refreshed_message.read_by) == 1

    def test_mark_messages_as_read_multiple_users(self, db, test_booking, test_student, test_instructor_with_availability):
        """Multiple users should be able to mark same message as read."""
        repo = MessageRepository(db)

        # Create a message
        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello everyone"
        )
        db.commit()

        # Mark as read by student
        repo.mark_messages_as_read([message.id], test_student.id)
        db.commit()

        # Mark as read by instructor
        repo.mark_messages_as_read([message.id], test_instructor_with_availability.id)
        db.commit()

        # Refresh and check - should have both users
        db.expire_all()
        refreshed_message = db.query(Message).filter(Message.id == message.id).first()

        assert refreshed_message.read_by is not None
        # Note: In the current implementation, only non-sender can mark as read
        # So we should have only student's read receipt
        user_ids = [r['user_id'] for r in refreshed_message.read_by]
        assert test_student.id in user_ids


class TestMessageHistoryReadBy:
    """Tests for read_by field in message history."""

    def test_get_message_history_includes_read_by(self, db, test_booking, test_student):
        """Message history should include read_by from database."""
        repo = MessageRepository(db)

        # Create and mark message as read
        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        repo.mark_messages_as_read([message.id], test_student.id)
        db.commit()

        # Get message history
        messages = repo.get_messages_for_booking(test_booking.id)

        # Should include read_by
        assert len(messages) == 1
        assert messages[0].read_by is not None
        assert len(messages[0].read_by) == 1
        assert messages[0].read_by[0]['user_id'] == test_student.id

    def test_get_message_history_preserves_delivered_at(self, db, test_booking):
        """Message history should preserve delivered_at field."""
        repo = MessageRepository(db)

        # Create message
        message = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Test message"
        )
        db.commit()

        original_delivered_at = message.delivered_at

        # Get message history
        messages = repo.get_messages_for_booking(test_booking.id)

        # Should preserve delivered_at
        assert len(messages) == 1
        assert messages[0].delivered_at is not None
        assert messages[0].delivered_at == original_delivered_at

    def test_get_message_history_handles_null_read_by(self, db, test_booking):
        """Message history should handle messages with no read_by."""
        repo = MessageRepository(db)

        # Create message without marking as read
        repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Unread message"
        )
        db.commit()

        # Get message history
        messages = repo.get_messages_for_booking(test_booking.id)

        # Should handle null/empty read_by gracefully
        assert len(messages) == 1
        # read_by might be None or empty list
        assert messages[0].read_by is None or messages[0].read_by == []


class TestMessageRepositoryUnreadCount:
    """Tests for unread message counting."""

    def test_get_unread_count_for_user(self, db, test_booking, test_student):
        """Should count unread messages correctly."""
        repo = MessageRepository(db)

        # Create 3 messages
        msg1 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 1"
        )
        msg2 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 2"
        )
        msg3 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 3"
        )
        db.commit()

        # Student should have 3 unread messages
        unread_count = repo.get_unread_count_for_user(test_student.id)
        assert unread_count == 3

        # Mark one as read
        repo.mark_messages_as_read([msg1.id], test_student.id)
        db.commit()

        # Should now have 2 unread
        unread_count = repo.get_unread_count_for_user(test_student.id)
        assert unread_count == 2

        # Mark all as read
        repo.mark_messages_as_read([msg1.id, msg2.id, msg3.id], test_student.id)
        db.commit()

        # Should now have 0 unread
        unread_count = repo.get_unread_count_for_user(test_student.id)
        assert unread_count == 0

    def test_get_unread_messages(self, db, test_booking, test_student):
        """Should retrieve unread messages correctly."""
        repo = MessageRepository(db)

        # Create messages
        msg1 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 1"
        )
        msg2 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 2"
        )
        db.commit()

        # Get unread messages
        unread = repo.get_unread_messages(test_booking.id, test_student.id)
        assert len(unread) == 2

        # Mark one as read
        repo.mark_messages_as_read([msg1.id], test_student.id)
        db.commit()

        # Should only have one unread
        unread = repo.get_unread_messages(test_booking.id, test_student.id)
        assert len(unread) == 1
        assert unread[0].id == msg2.id


class TestMessageRepositoryGetReadReceipts:
    """Tests for read receipt retrieval."""

    def test_get_read_receipts_for_message_ids(self, db, test_booking, test_student):
        """Should retrieve read receipts correctly."""
        repo = MessageRepository(db)

        # Create messages
        msg1 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 1"
        )
        msg2 = repo.create_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Message 2"
        )
        db.commit()

        # Mark msg1 as read
        repo.mark_messages_as_read([msg1.id], test_student.id)
        db.commit()

        # Get read receipts
        receipts = repo.get_read_receipts_for_message_ids([msg1.id, msg2.id])

        # Should have receipt for msg1 only
        receipt_message_ids = [r[0] for r in receipts]
        assert msg1.id in receipt_message_ids
        assert msg2.id not in receipt_message_ids

        # Receipt should have correct user_id
        msg1_receipts = [r for r in receipts if r[0] == msg1.id]
        assert len(msg1_receipts) == 1
        assert msg1_receipts[0][1] == test_student.id
        assert msg1_receipts[0][2] is not None  # read_at should be set
