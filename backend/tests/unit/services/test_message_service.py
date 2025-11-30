"""
Tests for Message Service.

Tests all messaging bugs that were fixed during Phase 4:
- Reaction SSE notifications
- Read receipt persistence
- SSE payload format
"""

from unittest.mock import patch

from app.services.message_service import MessageService


class TestMessageServiceReactions:
    """Tests for reaction functionality."""

    def test_add_reaction_sends_sse_to_both_users(self, db, test_booking):
        """Reactions should broadcast to both instructor and student."""
        service = MessageService(db)

        # Create a message
        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        # Mock the notify_user_channel method to verify SSE calls
        with patch.object(service.repository, 'notify_user_channel') as mock_notify:
            # Student adds reaction
            service.add_reaction(
                message_id=message.id,
                user_id=test_booking.student_id,
                emoji="👍"
            )
            db.commit()

            # Should notify both users
            assert mock_notify.call_count == 2

            # Check that both user channels were notified
            notified_users = [call[0][0] for call in mock_notify.call_args_list]
            assert test_booking.student_id in notified_users
            assert test_booking.instructor_id in notified_users

    def test_add_reaction_includes_conversation_id(self, db, test_booking):
        """SSE payload must include conversation_id for routing."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Hello"
        )
        db.commit()

        # Mock the notify_user_channel method
        with patch.object(service.repository, 'notify_user_channel') as mock_notify:
            service.add_reaction(
                message_id=message.id,
                user_id=test_booking.student_id,
                emoji="👍"
            )
            db.commit()

            # Check that notifications were sent
            assert mock_notify.call_count == 2

            # Check first notification payload includes conversation_id
            first_call_args = mock_notify.call_args_list[0]
            payload = first_call_args[0][1]  # Second argument is the payload

            assert 'conversation_id' in payload
            assert payload['conversation_id'] == test_booking.id
            assert payload['type'] == 'reaction_update'
            assert payload['message_id'] == message.id
            assert payload['emoji'] == '👍'
            assert payload['action'] == 'added'

    def test_add_reaction_includes_all_required_fields(self, db, test_booking):
        """SSE payload should have all required fields."""
        service = MessageService(db)

        message = service.send_message(
            booking_id=test_booking.id,
            sender_id=test_booking.instructor_id,
            content="Test message"
        )
        db.commit()

        with patch.object(service.repository, 'notify_user_channel') as mock_notify:
            service.add_reaction(
                message_id=message.id,
                user_id=test_booking.student_id,
                emoji="❤️"
            )
            db.commit()

            # Get payload from first call
            payload = mock_notify.call_args_list[0][0][1]

            # Verify all required fields
            assert payload['type'] == 'reaction_update'
            assert payload['conversation_id'] == test_booking.id
            assert payload['message_id'] == message.id
            assert payload['emoji'] == '❤️'
            assert payload['user_id'] == test_booking.student_id
            assert payload['action'] in ['added', 'removed']

    def test_remove_reaction_sends_sse(self, db, test_booking):
        """Removing reactions should also send SSE notifications."""
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
        with patch.object(service.repository, 'notify_user_channel') as mock_notify:
            service.remove_reaction(
                message_id=message.id,
                user_id=test_booking.student_id,
                emoji="👍"
            )
            db.commit()

            # Should notify both users
            assert mock_notify.call_count == 2

            # Verify action is "removed"
            payload = mock_notify.call_args_list[0][0][1]
            assert payload['action'] == 'removed'


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
