# tests/unit/services/test_system_message_service.py
"""Unit tests for SystemMessageService."""

from datetime import date, time
from unittest.mock import Mock

import pytest

from app.models.message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED,
    MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED,
    MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
    MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
)
from app.services.system_message_service import SystemMessageService


class TestSystemMessageService:
    """Test SystemMessageService."""

    @pytest.fixture
    def mock_conversation_repo(self):
        repo = Mock()
        mock_conversation = Mock()
        mock_conversation.id = "conv_01ABC123DEF456GHI789JKL"
        repo.get_or_create.return_value = (mock_conversation, False)
        repo.update_last_message_at.return_value = None
        return repo

    @pytest.fixture
    def mock_message_repo(self):
        return Mock()

    @pytest.fixture
    def service(self, db, mock_conversation_repo, mock_message_repo):
        svc = SystemMessageService(db)
        svc.conversation_repository = mock_conversation_repo
        svc.message_repository = mock_message_repo
        return svc

    def test_create_booking_created_message(self, service, mock_message_repo, mock_conversation_repo):
        """Creates system message when booking is created."""
        service.create_booking_created_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            service_name="Piano Lesson",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
        )

        mock_message_repo.create_conversation_message.assert_called_once()
        call_args = mock_message_repo.create_conversation_message.call_args

        assert call_args.kwargs["conversation_id"] == "conv_01ABC123DEF456GHI789JKL"
        assert call_args.kwargs["sender_id"] is None  # System message
        assert call_args.kwargs["booking_id"] == "booking_01ABC123DEF456GHI789"
        assert call_args.kwargs["message_type"] == MESSAGE_TYPE_SYSTEM_BOOKING_CREATED
        assert "Piano Lesson" in call_args.kwargs["content"]
        assert "Dec 10" in call_args.kwargs["content"]
        assert "5pm" in call_args.kwargs["content"]

        # Verify conversation's last_message_at was updated
        mock_conversation_repo.update_last_message_at.assert_called_once()

    def test_create_booking_cancelled_message(self, service, mock_message_repo):
        """Creates system message when booking is cancelled."""
        service.create_booking_cancelled_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
        )

        mock_message_repo.create_conversation_message.assert_called_once()
        call_args = mock_message_repo.create_conversation_message.call_args

        assert call_args.kwargs["message_type"] == MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED
        assert "❌" in call_args.kwargs["content"]
        assert "cancelled" in call_args.kwargs["content"].lower()

    def test_create_booking_cancelled_message_by_student(self, service, mock_message_repo):
        """Includes 'by student' when student cancels."""
        service.create_booking_cancelled_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
            cancelled_by="student",
        )

        call_args = mock_message_repo.create_conversation_message.call_args
        assert "by student" in call_args.kwargs["content"].lower()

    def test_create_booking_cancelled_message_by_instructor(self, service, mock_message_repo):
        """Includes 'by instructor' when instructor cancels."""
        service.create_booking_cancelled_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
            cancelled_by="instructor",
        )

        call_args = mock_message_repo.create_conversation_message.call_args
        assert "by instructor" in call_args.kwargs["content"].lower()

    def test_create_booking_rescheduled_message(self, service, mock_message_repo):
        """Creates system message when booking is rescheduled."""
        service.create_booking_rescheduled_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            old_date=date(2025, 12, 10),
            old_time=time(17, 0),
            new_date=date(2025, 12, 12),
            new_time=time(18, 0),
        )

        mock_message_repo.create_conversation_message.assert_called_once()
        call_args = mock_message_repo.create_conversation_message.call_args

        assert call_args.kwargs["message_type"] == MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED
        assert "🔄" in call_args.kwargs["content"]
        assert "Dec 10" in call_args.kwargs["content"]
        assert "Dec 12" in call_args.kwargs["content"]

    def test_create_booking_rescheduled_same_day(self, service, mock_message_repo):
        """Rescheduling to same day only shows time change."""
        service.create_booking_rescheduled_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            old_date=date(2025, 12, 10),
            old_time=time(17, 0),
            new_date=date(2025, 12, 10),  # Same day
            new_time=time(18, 0),
        )

        call_args = mock_message_repo.create_conversation_message.call_args
        content = call_args.kwargs["content"]

        # Should show time change, not date change twice
        assert "5pm" in content
        assert "6pm" in content
        # Both old and new times should be in format with arrows
        assert "→" in content

    def test_create_booking_completed_message(self, service, mock_message_repo):
        """Creates system message when booking is completed."""
        service.create_booking_completed_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            booking_date=date(2025, 12, 10),
            service_name="Piano Lesson",
        )

        mock_message_repo.create_conversation_message.assert_called_once()
        call_args = mock_message_repo.create_conversation_message.call_args

        assert call_args.kwargs["message_type"] == MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED
        assert "✅" in call_args.kwargs["content"]
        assert "completed" in call_args.kwargs["content"].lower()
        assert "Piano Lesson" in call_args.kwargs["content"]

    def test_create_booking_completed_message_without_service_name(self, service, mock_message_repo):
        """Completed message works without service name."""
        service.create_booking_completed_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            booking_date=date(2025, 12, 10),
            service_name=None,
        )

        call_args = mock_message_repo.create_conversation_message.call_args
        assert "✅" in call_args.kwargs["content"]
        assert "completed" in call_args.kwargs["content"].lower()
        assert "Dec 10" in call_args.kwargs["content"]

    def test_creates_conversation_if_not_exists(self, service, mock_conversation_repo):
        """Creates conversation if this is the first interaction."""
        mock_conversation_repo.get_or_create.return_value = (Mock(id="new_conv_id"), True)

        service.create_booking_created_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            service_name="Piano Lesson",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
        )

        mock_conversation_repo.get_or_create.assert_called_once_with(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
        )

    def test_updates_conversation_last_message_at(self, service, mock_conversation_repo):
        """Updates conversation's last_message_at after creating system message."""
        service.create_booking_created_message(
            student_id="student_01ABC123DEF456GHI789JK",
            instructor_id="instructor_01ABC123DEF456GH",
            booking_id="booking_01ABC123DEF456GHI789",
            service_name="Piano Lesson",
            booking_date=date(2025, 12, 10),
            start_time=time(17, 0),
        )

        mock_conversation_repo.update_last_message_at.assert_called_once()


class TestTimeFormatting:
    """Test time formatting helper."""

    @pytest.fixture
    def service(self, db):
        return SystemMessageService(db)

    def test_format_time_am(self, service):
        """Formats morning times correctly."""
        assert service._format_time(time(9, 0)) == "9am"
        assert service._format_time(time(9, 30)) == "9:30am"
        assert service._format_time(time(11, 45)) == "11:45am"

    def test_format_time_pm(self, service):
        """Formats afternoon/evening times correctly."""
        assert service._format_time(time(13, 0)) == "1pm"
        assert service._format_time(time(17, 0)) == "5pm"
        assert service._format_time(time(17, 30)) == "5:30pm"

    def test_format_time_noon_midnight(self, service):
        """Handles noon and midnight correctly."""
        assert service._format_time(time(0, 0)) == "12am"
        assert service._format_time(time(12, 0)) == "12pm"

    def test_format_time_noon_with_minutes(self, service):
        """Handles noon with minutes."""
        assert service._format_time(time(12, 30)) == "12:30pm"

    def test_format_time_midnight_with_minutes(self, service):
        """Handles midnight with minutes."""
        assert service._format_time(time(0, 30)) == "12:30am"
