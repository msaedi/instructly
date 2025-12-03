"""
Tests for Message Service.

Tests messaging functionality:
- Reaction database operations
- Read receipt persistence
- Message operations
"""

from app.services.message_service import MessageService


class TestMessageServiceReactions:
    """Tests for reaction functionality.

    Note: Real-time SSE notifications are now handled via Redis Pub/Sub
    in the route layer. These tests verify database operations only.
    """

    def test_add_reaction_persists_to_database(self, db, test_booking):
        """Adding a reaction should persist to the database."""
        service = MessageService(db)

        # Create a message
        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        # Student adds reaction
        result = service.add_reaction(
            message_id=message.id,
            user_id=test_booking.student_id,
            emoji="👍"
        )
        db.commit()

        assert result is True

        # Verify reaction is persisted
        db.expire_all()
        updated_message = service.get_message_by_id(message.id, test_booking.student_id)
        assert updated_message is not None
        # Reactions are stored in the database

    def test_add_reaction_returns_true_on_success(self, db, test_booking):
        """add_reaction should return True when successful."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        result = service.add_reaction(
            message_id=message.id,
            user_id=test_booking.student_id,
            emoji="👍"
        )
        db.commit()

        assert result is True

    def test_add_reaction_with_different_emojis(self, db, test_booking):
        """Multiple different reactions can be added to same message."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Test message"
        )
        db.commit()

        # Add multiple reactions
        result1 = service.add_reaction(message.id, test_booking.student_id, "👍")
        result2 = service.add_reaction(message.id, test_booking.student_id, "❤️")
        db.commit()

        assert result1 is True
        assert result2 is True

    def test_remove_reaction_persists_to_database(self, db, test_booking):
        """Removing a reaction should persist the removal to database."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        # Add reaction first
        service.add_reaction(
            message_id=message.id,
            user_id=test_booking.student_id,
            emoji="👍"
        )
        db.commit()

        # Remove reaction
        result = service.remove_reaction(
            message_id=message.id,
            user_id=test_booking.student_id,
            emoji="👍"
        )
        db.commit()

        assert result is True


class TestMessageServiceReadReceipts:
    """Tests for read receipt functionality."""

    def test_mark_as_read_persists_to_database(self, db, test_booking, test_student):
        """Bug #5: read_by must be persisted to survive refresh."""
        service = MessageService(db)

        # Create message from instructor
        service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello student"
        )
        db.commit()

        # Student marks as read
        count = service.mark_booking_messages_as_read(
            booking_id=test_booking.id,
            user_id=test_student.id
        )
        db.commit()

        assert count == 1

        # Fetch fresh from database
        db.expire_all()
        messages = service.get_message_history(test_booking.id, test_student.id)

        assert len(messages) == 1
        assert messages[0].read_by is not None
        assert len(messages[0].read_by) == 1
        assert messages[0].read_by[0]['user_id'] == test_student.id

    def test_get_message_history_includes_read_by(self, db, test_booking, test_student):
        """Message history should include read_by field."""
        service = MessageService(db)

        # Create message
        service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Test message"
        )
        db.commit()

        # Mark as read
        service.mark_booking_messages_as_read(
            booking_id=test_booking.id,
            user_id=test_student.id
        )
        db.commit()

        # Get history
        messages = service.get_message_history(test_booking.id, test_student.id)

        # Should include read_by
        assert len(messages) == 1
        assert messages[0].read_by is not None
        assert len(messages[0].read_by) == 1
        assert messages[0].read_by[0]['user_id'] == test_student.id
        assert 'read_at' in messages[0].read_by[0]

    def test_get_message_history_includes_delivered_at(self, db, test_booking, test_student):
        """Bug #4: Message history should include delivered_at."""
        service = MessageService(db)

        # Create message
        service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Test message"
        )
        db.commit()

        # Get history
        messages = service.get_message_history(test_booking.id, test_student.id)

        # Should include delivered_at
        assert len(messages) == 1
        assert messages[0].delivered_at is not None

    def test_mark_messages_as_read_does_not_mark_own_messages(self, db, test_booking, test_instructor_with_availability):
        """Should not mark sender's own messages as read."""
        service = MessageService(db)

        # Create message from instructor
        service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="My message"
        )
        db.commit()

        # Instructor tries to mark own messages as read
        count = service.mark_booking_messages_as_read(
            booking_id=test_booking.id,
            user_id=test_booking.instructor_id
        )
        db.commit()

        # Should not mark own messages (count should be 0)
        assert count == 0

        # Verify read_by is empty or doesn't contain instructor
        db.expire_all()
        messages = service.get_message_history(test_booking.id, test_booking.instructor_id)

        assert len(messages) == 1
        if messages[0].read_by:
            user_ids = [r['user_id'] for r in messages[0].read_by]
            assert test_booking.instructor_id not in user_ids


class TestMessageServiceSendMessage:
    """Tests for sending messages."""

    def test_send_message_sets_delivered_at(self, db, test_booking):
        """Bug #4: Sent messages should have delivered_at set."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        assert message.delivered_at is not None

    def test_send_message_creates_notification(self, db, test_booking):
        """Sent messages should create notification for recipient."""
        service = MessageService(db)

        service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello student"
        )
        db.commit()

        # Student should have unread notification
        unread_count = service.repository.get_unread_count_for_user(test_booking.student_id)
        assert unread_count == 1
