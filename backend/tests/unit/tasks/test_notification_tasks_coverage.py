"""
Unit tests for notification_tasks targeting coverage improvements.

Coverage focus:
- _next_backoff helper function
- _format_display_name helper
- _format_booking_date helper
- _format_booking_time helper
- _resolve_service_name helper
- deliver_event task logic paths
- dispatch_pending task

Strategy: Mock external dependencies (Celery, DB, notification provider)
"""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.tasks.notification_tasks import (
    BACKOFF_SECONDS,
    MAX_DELIVERY_ATTEMPTS,
    _format_booking_date,
    _format_booking_time,
    _format_display_name,
    _next_backoff,
    _resolve_service_name,
)


class TestNextBackoff:
    """Tests for _next_backoff helper."""

    def test_first_attempt(self):
        """Test backoff for first attempt."""
        result = _next_backoff(1)
        assert result == BACKOFF_SECONDS[0]  # 30 seconds

    def test_second_attempt(self):
        """Test backoff for second attempt."""
        result = _next_backoff(2)
        assert result == BACKOFF_SECONDS[1]  # 120 seconds

    def test_third_attempt(self):
        """Test backoff for third attempt."""
        result = _next_backoff(3)
        assert result == BACKOFF_SECONDS[2]  # 600 seconds

    def test_fourth_attempt(self):
        """Test backoff for fourth attempt."""
        result = _next_backoff(4)
        assert result == BACKOFF_SECONDS[3]  # 1800 seconds

    def test_fifth_attempt(self):
        """Test backoff for fifth attempt."""
        result = _next_backoff(5)
        assert result == BACKOFF_SECONDS[4]  # 7200 seconds

    def test_beyond_max_attempts(self):
        """Test backoff caps at last value."""
        result = _next_backoff(10)
        assert result == BACKOFF_SECONDS[-1]

    def test_zero_attempt(self):
        """Test backoff for zero attempt (edge case)."""
        result = _next_backoff(0)
        assert result == BACKOFF_SECONDS[0]

    def test_negative_attempt(self):
        """Test backoff for negative attempt (edge case)."""
        result = _next_backoff(-1)
        assert result == BACKOFF_SECONDS[0]


class TestFormatDisplayName:
    """Tests for _format_display_name helper."""

    def test_full_name(self):
        """Test with both first and last name."""
        user = MagicMock()
        user.first_name = "John"
        user.last_name = "Doe"

        result = _format_display_name(user)

        assert result == "John D."

    def test_first_name_only(self):
        """Test with only first name."""
        user = MagicMock()
        user.first_name = "Jane"
        user.last_name = ""

        result = _format_display_name(user)

        assert result == "Jane"

    def test_last_name_only(self):
        """Test with only last name (unusual case)."""
        user = MagicMock()
        user.first_name = ""
        user.last_name = "Smith"

        result = _format_display_name(user)

        assert result == "Someone"

    def test_no_name(self):
        """Test with no name."""
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""

        result = _format_display_name(user)

        assert result == "Someone"

    def test_none_user(self):
        """Test with None user."""
        result = _format_display_name(None)

        assert result == "Someone"

    def test_whitespace_names(self):
        """Test with whitespace names."""
        user = MagicMock()
        user.first_name = "  Alice  "
        user.last_name = "  Brown  "

        result = _format_display_name(user)

        assert result == "Alice B."

    def test_none_names(self):
        """Test with None name attributes."""
        user = MagicMock()
        user.first_name = None
        user.last_name = None

        result = _format_display_name(user)

        assert result == "Someone"


class TestFormatBookingDate:
    """Tests for _format_booking_date helper."""

    def test_standard_date(self):
        """Test with standard date."""
        booking = MagicMock()
        booking.booking_date = date(2026, 1, 15)

        result = _format_booking_date(booking)

        assert result == "January 15"

    def test_date_with_leading_zero_day(self):
        """Test date formatting removes leading zeros."""
        booking = MagicMock()
        booking.booking_date = date(2026, 3, 5)

        result = _format_booking_date(booking)

        assert result == "March 5"

    def test_no_booking_date(self):
        """Test with missing booking_date."""
        booking = MagicMock(spec=[])  # No booking_date attribute

        result = _format_booking_date(booking)

        assert result == ""

    def test_none_booking_date(self):
        """Test with None booking_date."""
        booking = MagicMock()
        booking.booking_date = None

        result = _format_booking_date(booking)

        assert result == ""

    def test_string_booking_date(self):
        """Test with string booking_date (edge case)."""
        booking = MagicMock()
        booking.booking_date = "2026-01-20"

        result = _format_booking_date(booking)

        assert result == "2026-01-20"


class TestFormatBookingTime:
    """Tests for _format_booking_time helper."""

    def test_standard_time(self):
        """Test with standard time."""
        booking = MagicMock()
        booking.start_time = time(14, 30)

        result = _format_booking_time(booking)

        assert result == "2:30 PM"

    def test_morning_time(self):
        """Test with morning time."""
        booking = MagicMock()
        booking.start_time = time(9, 0)

        result = _format_booking_time(booking)

        assert result == "9:00 AM"

    def test_noon_time(self):
        """Test with noon time."""
        booking = MagicMock()
        booking.start_time = time(12, 0)

        result = _format_booking_time(booking)

        assert result == "12:00 PM"

    def test_midnight_time(self):
        """Test with midnight time."""
        booking = MagicMock()
        booking.start_time = time(0, 0)

        result = _format_booking_time(booking)

        # Should strip leading zero
        assert "12:00 AM" in result or result == "12:00 AM"

    def test_no_start_time(self):
        """Test with missing start_time."""
        booking = MagicMock(spec=[])

        result = _format_booking_time(booking)

        assert result == ""

    def test_none_start_time(self):
        """Test with None start_time."""
        booking = MagicMock()
        booking.start_time = None

        result = _format_booking_time(booking)

        assert result == ""

    def test_string_start_time(self):
        """Test with string start_time."""
        booking = MagicMock()
        booking.start_time = "10:00:00"

        result = _format_booking_time(booking)

        assert result == "10:00:00"


class TestResolveServiceName:
    """Tests for _resolve_service_name helper."""

    def test_service_name_on_booking(self):
        """Test with service_name directly on booking."""
        booking = MagicMock()
        booking.service_name = "Guitar Lessons"

        result = _resolve_service_name(booking)

        assert result == "Guitar Lessons"

    def test_service_name_from_instructor_service(self):
        """Test fallback to instructor_service.name."""
        booking = MagicMock()
        booking.service_name = ""
        booking.instructor_service = MagicMock()
        booking.instructor_service.name = "Piano Lessons"

        result = _resolve_service_name(booking)

        assert result == "Piano Lessons"

    def test_default_when_no_name(self):
        """Test default value when no name found."""
        booking = MagicMock()
        booking.service_name = ""
        booking.instructor_service = None

        result = _resolve_service_name(booking)

        assert result == "Lesson"

    def test_whitespace_service_name(self):
        """Test with whitespace-only service_name."""
        booking = MagicMock()
        booking.service_name = "   "
        booking.instructor_service = None

        result = _resolve_service_name(booking)

        assert result == "Lesson"

    def test_none_service_name(self):
        """Test with None service_name."""
        booking = MagicMock()
        booking.service_name = None
        booking.instructor_service = MagicMock()
        booking.instructor_service.name = "Drums"

        result = _resolve_service_name(booking)

        assert result == "Drums"

    def test_whitespace_instructor_service_name(self):
        """Test with whitespace instructor_service.name."""
        booking = MagicMock()
        booking.service_name = ""
        booking.instructor_service = MagicMock()
        booking.instructor_service.name = "  "

        result = _resolve_service_name(booking)

        assert result == "Lesson"

    def test_strips_whitespace(self):
        """Test that service name is stripped."""
        booking = MagicMock()
        booking.service_name = "  Violin Lessons  "

        result = _resolve_service_name(booking)

        assert result == "Violin Lessons"


class TestConstants:
    """Tests for module constants."""

    def test_max_delivery_attempts(self):
        """Test MAX_DELIVERY_ATTEMPTS is reasonable."""
        assert MAX_DELIVERY_ATTEMPTS == 5

    def test_backoff_seconds_length(self):
        """Test BACKOFF_SECONDS has entries for all attempts."""
        assert len(BACKOFF_SECONDS) == 5

    def test_backoff_seconds_increasing(self):
        """Test backoff values are increasing."""
        for i in range(1, len(BACKOFF_SECONDS)):
            assert BACKOFF_SECONDS[i] > BACKOFF_SECONDS[i - 1]


class TestSessionScope:
    """Tests for _session_scope context manager."""

    def test_session_scope_commits_on_success(self):
        """Test session is committed on success."""
        from app.tasks.notification_tasks import _session_scope

        with patch("app.tasks.notification_tasks.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            with _session_scope():
                pass

            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    def test_session_scope_rollback_on_error(self):
        """Test session is rolled back on error."""
        from app.tasks.notification_tasks import _session_scope

        with patch("app.tasks.notification_tasks.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            with pytest.raises(ValueError):
                with _session_scope():
                    raise ValueError("Test error")

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()


class TestSendBookingRemindersRollback:
    """Tests for session rollback isolation in send_booking_reminders."""

    @patch("app.tasks.notification_tasks._send_reminder_notifications")
    @patch("app.tasks.notification_tasks._session_scope")
    def test_rollback_isolates_24h_reminder_failure(
        self, mock_scope, mock_send
    ):
        """First 24h booking fails; second still processes."""
        from app.tasks.notification_tasks import send_booking_reminders

        mock_session = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        booking1 = MagicMock()
        booking1.id = "01AAAA"
        booking1.reminder_24h_sent = False
        booking2 = MagicMock()
        booking2.id = "01BBBB"
        booking2.reminder_24h_sent = False

        # Query returns 24h bookings, empty 1h
        mock_session.query.return_value.options.return_value.filter.return_value.all.side_effect = [
            [booking1, booking2],  # 24h bookings
            [],  # 1h bookings
        ]

        # First call raises, second succeeds
        mock_send.side_effect = [RuntimeError("DB error"), True]

        result = send_booking_reminders()

        mock_session.rollback.assert_called_once()
        assert result["reminders_24h_sent"] == 2  # Only second booking counted
        assert booking2.reminder_24h_sent is True

    @patch("app.tasks.notification_tasks._send_reminder_notifications")
    @patch("app.tasks.notification_tasks._session_scope")
    def test_rollback_isolates_1h_reminder_failure(
        self, mock_scope, mock_send
    ):
        """First 1h booking fails; second still processes."""
        from app.tasks.notification_tasks import send_booking_reminders

        mock_session = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        booking1 = MagicMock()
        booking1.id = "01CCCC"
        booking1.reminder_1h_sent = False
        booking2 = MagicMock()
        booking2.id = "01DDDD"
        booking2.reminder_1h_sent = False

        # Query returns empty 24h bookings, then 1h bookings
        mock_session.query.return_value.options.return_value.filter.return_value.all.side_effect = [
            [],  # 24h bookings
            [booking1, booking2],  # 1h bookings
        ]

        # First call raises, second succeeds
        mock_send.side_effect = [RuntimeError("DB error"), True]

        result = send_booking_reminders()

        mock_session.rollback.assert_called_once()
        assert result["reminders_1h_sent"] == 2
        assert booking2.reminder_1h_sent is True


class TestDispatchPending:
    """Tests for dispatch_pending task."""

    def test_dispatch_pending_schedules_events(self):
        """Test dispatch_pending schedules delivery tasks."""
        from app.tasks.notification_tasks import dispatch_pending

        with patch("app.tasks.notification_tasks._session_scope") as mock_scope:
            with patch("app.tasks.notification_tasks.EventOutboxRepository") as mock_repo_class:
                with patch("app.tasks.notification_tasks.enqueue_task") as mock_enqueue:
                    mock_session = MagicMock()
                    mock_scope.return_value.__enter__.return_value = mock_session

                    mock_repo = MagicMock()
                    mock_repo_class.return_value = mock_repo

                    # Simulate 3 pending events
                    mock_events = [MagicMock(id="event-1"), MagicMock(id="event-2"), MagicMock(id="event-3")]
                    mock_repo.fetch_pending.return_value = mock_events

                    result = dispatch_pending()

                    assert result == 3
                    assert mock_enqueue.call_count == 3
                    for call in mock_enqueue.call_args_list:
                        assert call.args[0] == "outbox.deliver_event"

    def test_dispatch_pending_no_events(self):
        """Test dispatch_pending with no pending events."""
        from app.tasks.notification_tasks import dispatch_pending

        with patch("app.tasks.notification_tasks._session_scope") as mock_scope:
            with patch("app.tasks.notification_tasks.EventOutboxRepository") as mock_repo_class:
                mock_session = MagicMock()
                mock_scope.return_value.__enter__.return_value = mock_session

                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo
                mock_repo.fetch_pending.return_value = []

                result = dispatch_pending()

                assert result == 0


class TestDeliverEvent:
    """Target terminal failure bookkeeping in deliver_event."""

    def test_deliver_event_generic_error_terminal_marks_failed_without_retry(self):
        from app.tasks.notification_tasks import deliver_event

        event = MagicMock(
            id="event-terminal",
            event_type="booking.created",
            payload={"booking_id": "booking-1"},
            idempotency_key="booking:booking-1:created",
            attempt_count=MAX_DELIVERY_ATTEMPTS - 1,
        )
        session = MagicMock()
        repo = MagicMock()
        repo.get_by_id.return_value = event

        with patch("app.tasks.notification_tasks.SessionLocal", return_value=session):
            with patch("app.tasks.notification_tasks.EventOutboxRepository", return_value=repo):
                with patch("app.tasks.notification_tasks.NotificationProvider") as provider_cls:
                    provider_cls.return_value.send.side_effect = RuntimeError("provider exploded")
                    with patch("app.tasks.notification_tasks.PrometheusMetrics") as metrics:
                        with patch("app.tasks.notification_tasks.logger") as mock_logger:
                            with patch.object(
                                deliver_event,
                                "retry",
                                side_effect=AssertionError("retry should not be called"),
                            ) as retry_mock:
                                with pytest.raises(RuntimeError, match="provider exploded"):
                                    deliver_event.run(event.id)

        repo.mark_failed.assert_called_once_with(
            event.id,
            attempt_count=MAX_DELIVERY_ATTEMPTS,
            backoff_seconds=BACKOFF_SECONDS[-1],
            error="provider exploded",
            terminal=True,
        )
        metrics.record_notification_attempt.assert_called_once_with(event.event_type)
        metrics.record_notification_outcome.assert_called_once_with(event.event_type, "failed")
        retry_mock.assert_not_called()
        mock_logger.exception.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()


class TestReminderFalseReturn:
    """False reminder sends should not mark delivery flags."""

    @patch("app.tasks.notification_tasks._send_reminder_notifications")
    @patch("app.tasks.notification_tasks._session_scope")
    def test_send_booking_reminders_false_1h_result_does_not_mark_sent(
        self, mock_scope, mock_send
    ):
        from app.tasks.notification_tasks import send_booking_reminders

        mock_session = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        booking = MagicMock()
        booking.id = "01REMINDER"
        booking.reminder_1h_sent = False

        mock_session.query.return_value.options.return_value.filter.return_value.all.side_effect = [
            [],
            [booking],
        ]
        mock_send.return_value = False

        result = send_booking_reminders()

        assert result["reminders_24h_sent"] == 0
        assert result["reminders_1h_sent"] == 0
        assert booking.reminder_1h_sent is False
        mock_session.rollback.assert_not_called()


def test_send_booking_reminders_uses_exact_utc_windows_across_dst(
    db, test_student, test_instructor_with_availability, test_booking, monkeypatch
):
    from app.tasks.notification_tasks import send_booking_reminders

    fixed_now = datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr("app.tasks.notification_tasks.datetime", FrozenDateTime)

    def _make_booking(booking_start_utc: datetime) -> Booking:
        return Booking(
            id=generate_ulid(),
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=booking_start_utc.date(),
            start_time=booking_start_utc.time().replace(tzinfo=None),
            end_time=(booking_start_utc + timedelta(hours=1)).time().replace(tzinfo=None),
            booking_start_utc=booking_start_utc,
            booking_end_utc=booking_start_utc + timedelta(hours=1),
            lesson_timezone="America/New_York",
            instructor_tz_at_booking="America/New_York",
            student_tz_at_booking="America/New_York",
            service_name="DST Reminder Lesson",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

    booking_24h = _make_booking(fixed_now + timedelta(hours=24) - timedelta(minutes=5))
    booking_1h = _make_booking(fixed_now + timedelta(hours=1) - timedelta(minutes=5))
    outside_window = _make_booking(fixed_now + timedelta(hours=24, minutes=65))
    db.add_all([booking_24h, booking_1h, outside_window])
    db.commit()

    @contextmanager
    def _scope():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    with (
        patch("app.tasks.notification_tasks._session_scope", _scope),
        patch("app.tasks.notification_tasks._send_reminder_notifications", return_value=True) as mock_send,
    ):
        result = send_booking_reminders()

    db.refresh(booking_24h)
    db.refresh(booking_1h)
    db.refresh(outside_window)

    assert result == {"reminders_24h_sent": 2, "reminders_1h_sent": 2}
    assert booking_24h.reminder_24h_sent is True
    assert booking_1h.reminder_1h_sent is True
    assert outside_window.reminder_24h_sent is False
    assert [call.args[1].id for call in mock_send.call_args_list] == [booking_24h.id, booking_1h.id]
