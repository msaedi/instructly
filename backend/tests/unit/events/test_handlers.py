# backend/tests/unit/events/test_handlers.py
"""
Comprehensive tests for event handlers.

Tests cover:
- _load_booking helper function (lines 17-18)
- Booking not found scenarios for all handlers (lines 41-42, 58-59)
- Event handler registration
- Event processing dispatch

This file extends coverage beyond test_event_handlers_coverage.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.events import handlers
from app.events.handlers import (
    EVENT_HANDLERS,
    _load_booking,
    handle_booking_cancelled,
    handle_booking_created,
    handle_booking_reminder,
    process_event,
)


class TestLoadBooking:
    """Tests for the _load_booking helper function (lines 17-18)."""

    def test_load_booking_calls_repository(self, db, test_booking):
        """Lines 17-18: Should call BookingRepository.get_booking_with_details."""
        # This exercises the actual _load_booking function
        result = _load_booking(db, test_booking.id)

        assert result is not None
        assert result.id == test_booking.id

    def test_load_booking_returns_none_for_missing(self, db):
        """Should return None when booking doesn't exist."""
        result = _load_booking(db, "nonexistent-booking-id")

        assert result is None

    def test_load_booking_uses_booking_repository(self, monkeypatch):
        """Should use BookingRepository for loading."""
        mock_repo = MagicMock()
        mock_booking = SimpleNamespace(id="test-id")
        mock_repo.get_booking_with_details.return_value = mock_booking

        mock_db = MagicMock()

        with patch("app.events.handlers.BookingRepository", return_value=mock_repo):
            result = _load_booking(mock_db, "test-id")

        mock_repo.get_booking_with_details.assert_called_once_with("test-id")
        assert result == mock_booking


class TestHandleBookingCancelledMissing:
    """Tests for handle_booking_cancelled when booking is not found (lines 41-42)."""

    def test_booking_cancelled_missing_booking(self, monkeypatch):
        """Lines 41-42: Should log warning and return early when booking not found."""
        called = {"notification_sent": False}

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_cancellation_notification(self, booking, cancelled_by=None):
                called["notification_sent"] = True

        # Mock _load_booking to return None
        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: None)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        # Should not raise, just log and return
        handle_booking_cancelled(
            json.dumps({"booking_id": "missing-booking-123"}),
            db=MagicMock(),
        )

        # Notification should NOT be sent
        assert called["notification_sent"] is False

    def test_booking_cancelled_missing_logs_warning(self, monkeypatch, caplog):
        """Should log a warning when booking not found for cancellation."""
        import logging

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: None)

        with caplog.at_level(logging.WARNING):
            handle_booking_cancelled(
                json.dumps({"booking_id": "missing-booking-456"}),
                db=MagicMock(),
            )

        assert "not found for cancellation" in caplog.text


class TestHandleBookingReminderMissing:
    """Tests for handle_booking_reminder when booking is not found (lines 58-59)."""

    def test_booking_reminder_missing_booking(self, monkeypatch):
        """Lines 58-59: Should log warning and return early when booking not found."""
        called = {"reminder_sent": False}

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_reminder(self, booking, reminder_type):
                called["reminder_sent"] = True

        # Mock _load_booking to return None
        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: None)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        # Should not raise, just log and return
        handle_booking_reminder(
            json.dumps({"booking_id": "missing-booking-789"}),
            db=MagicMock(),
        )

        # Reminder should NOT be sent
        assert called["reminder_sent"] is False

    def test_booking_reminder_missing_logs_warning(self, monkeypatch, caplog):
        """Should log a warning when booking not found for reminder."""
        import logging

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: None)

        with caplog.at_level(logging.WARNING):
            handle_booking_reminder(
                json.dumps({"booking_id": "missing-reminder-booking"}),
                db=MagicMock(),
            )

        assert "not found for reminder" in caplog.text


class TestHandleBookingCancelledWithCancelledBy:
    """Tests for handle_booking_cancelled with cancelled_by parameter."""

    def test_passes_cancelled_by_instructor(self, monkeypatch):
        """Should pass cancelled_by='instructor' to notification service."""
        called = {"cancelled_by": None}
        booking = SimpleNamespace(id="b1")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_cancellation_notification(self, booking, cancelled_by=None):
                called["cancelled_by"] = cancelled_by

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_cancelled(
            json.dumps({"booking_id": "b1", "cancelled_by": "instructor"}),
            db=MagicMock(),
        )

        assert called["cancelled_by"] == "instructor"

    def test_passes_cancelled_by_system(self, monkeypatch):
        """Should pass cancelled_by='system' for auto-cancellations."""
        called = {"cancelled_by": None}
        booking = SimpleNamespace(id="b2")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_cancellation_notification(self, booking, cancelled_by=None):
                called["cancelled_by"] = cancelled_by

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_cancelled(
            json.dumps({"booking_id": "b2", "cancelled_by": "system"}),
            db=MagicMock(),
        )

        assert called["cancelled_by"] == "system"

    def test_handles_missing_cancelled_by(self, monkeypatch):
        """Should handle payload without cancelled_by field."""
        called = {"cancelled_by": "sentinel"}
        booking = SimpleNamespace(id="b3")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_cancellation_notification(self, booking, cancelled_by=None):
                called["cancelled_by"] = cancelled_by

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_cancelled(
            json.dumps({"booking_id": "b3"}),  # No cancelled_by
            db=MagicMock(),
        )

        assert called["cancelled_by"] is None


class TestHandleBookingReminderTypes:
    """Tests for handle_booking_reminder with different reminder types."""

    def test_reminder_type_1h(self, monkeypatch):
        """Should pass reminder_type='1h' for 1-hour reminders."""
        called = {"reminder_type": None}
        booking = SimpleNamespace(id="r1")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_reminder(self, booking, reminder_type):
                called["reminder_type"] = reminder_type

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_reminder(
            json.dumps({"booking_id": "r1", "reminder_type": "1h"}),
            db=MagicMock(),
        )

        assert called["reminder_type"] == "1h"

    def test_reminder_type_defaults_to_24h(self, monkeypatch):
        """Should default to '24h' if reminder_type not provided."""
        called = {"reminder_type": None}
        booking = SimpleNamespace(id="r2")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_reminder(self, booking, reminder_type):
                called["reminder_type"] = reminder_type

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_reminder(
            json.dumps({"booking_id": "r2"}),  # No reminder_type
            db=MagicMock(),
        )

        assert called["reminder_type"] == "24h"

    def test_reminder_type_none_defaults_to_24h(self, monkeypatch):
        """Should default to '24h' if reminder_type is None."""
        called = {"reminder_type": None}
        booking = SimpleNamespace(id="r3")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_reminder(self, booking, reminder_type):
                called["reminder_type"] = reminder_type

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        handle_booking_reminder(
            json.dumps({"booking_id": "r3", "reminder_type": None}),
            db=MagicMock(),
        )

        assert called["reminder_type"] == "24h"


class TestEventHandlersRegistry:
    """Tests for the EVENT_HANDLERS registry."""

    def test_booking_created_registered(self):
        """BookingCreated handler should be registered."""
        assert "event:BookingCreated" in EVENT_HANDLERS
        assert EVENT_HANDLERS["event:BookingCreated"] == handle_booking_created

    def test_booking_cancelled_registered(self):
        """BookingCancelled handler should be registered."""
        assert "event:BookingCancelled" in EVENT_HANDLERS
        assert EVENT_HANDLERS["event:BookingCancelled"] == handle_booking_cancelled

    def test_booking_reminder_registered(self):
        """BookingReminder handler should be registered."""
        assert "event:BookingReminder" in EVENT_HANDLERS
        assert EVENT_HANDLERS["event:BookingReminder"] == handle_booking_reminder


class TestProcessEvent:
    """Tests for the process_event function."""

    def test_non_event_job_returns_false(self):
        """Should return False for non-event job types."""
        result = process_event("background:task", "{}", db=MagicMock())
        assert result is False

    def test_unknown_event_returns_true(self):
        """Should return True (consumed) for unknown event types."""
        result = process_event("event:UnknownEvent", "{}", db=MagicMock())
        assert result is True

    def test_dispatches_to_handler(self, monkeypatch):
        """Should dispatch to registered handler."""
        called = {"dispatched": False}

        def mock_handler(payload, db):
            called["dispatched"] = True

        monkeypatch.setattr(handlers, "EVENT_HANDLERS", {"event:Test": mock_handler})

        result = process_event("event:Test", '{"test": true}', db=MagicMock())

        assert result is True
        assert called["dispatched"] is True

    def test_passes_payload_to_handler(self, monkeypatch):
        """Should pass payload string to handler."""
        received_payload = {"value": None}

        def mock_handler(payload, db):
            received_payload["value"] = payload

        monkeypatch.setattr(handlers, "EVENT_HANDLERS", {"event:Test": mock_handler})

        test_payload = '{"key": "value"}'
        process_event("event:Test", test_payload, db=MagicMock())

        assert received_payload["value"] == test_payload

    def test_passes_db_to_handler(self, monkeypatch):
        """Should pass db session to handler."""
        received_db = {"value": None}

        def mock_handler(payload, db):
            received_db["value"] = db

        monkeypatch.setattr(handlers, "EVENT_HANDLERS", {"event:Test": mock_handler})

        mock_db = MagicMock()
        process_event("event:Test", "{}", db=mock_db)

        assert received_db["value"] is mock_db


class TestHandlerLogging:
    """Tests for handler logging behavior."""

    def test_booking_created_logs_success(self, monkeypatch, caplog):
        """Should log info when booking confirmation sent."""
        import logging

        booking = SimpleNamespace(id="log-test-1")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_confirmation(self, booking):
                pass

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        with caplog.at_level(logging.INFO):
            handle_booking_created(
                json.dumps({"booking_id": "log-test-1"}),
                db=MagicMock(),
            )

        assert "Sent booking confirmation" in caplog.text

    def test_booking_cancelled_logs_success(self, monkeypatch, caplog):
        """Should log info when cancellation notification sent."""
        import logging

        booking = SimpleNamespace(id="log-test-2")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_cancellation_notification(self, booking, cancelled_by=None):
                pass

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        with caplog.at_level(logging.INFO):
            handle_booking_cancelled(
                json.dumps({"booking_id": "log-test-2"}),
                db=MagicMock(),
            )

        assert "Sent cancellation notification" in caplog.text

    def test_booking_reminder_logs_success(self, monkeypatch, caplog):
        """Should log info when reminder sent."""
        import logging

        booking = SimpleNamespace(id="log-test-3")

        class MockNotificationService:
            def __init__(self, db):
                pass

            def send_booking_reminder(self, booking, reminder_type):
                pass

        monkeypatch.setattr(handlers, "_load_booking", lambda db, id: booking)
        monkeypatch.setattr(handlers, "NotificationService", MockNotificationService)

        with caplog.at_level(logging.INFO):
            handle_booking_reminder(
                json.dumps({"booking_id": "log-test-3"}),
                db=MagicMock(),
            )

        assert "Sent" in caplog.text and "reminder" in caplog.text

    def test_unknown_event_logs_warning(self, caplog):
        """Should log warning for unknown event types."""
        import logging

        with caplog.at_level(logging.WARNING):
            process_event("event:NonexistentEvent", "{}", db=MagicMock())

        assert "No handler for event type" in caplog.text
