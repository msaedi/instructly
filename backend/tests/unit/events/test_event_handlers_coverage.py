from __future__ import annotations

import json
from types import SimpleNamespace

from app.events import handlers


def test_handle_booking_created_missing(monkeypatch) -> None:
    called = {"notifications": 0}

    class _NotificationService:
        def __init__(self, _db) -> None:
            called["notifications"] += 1

        def send_booking_confirmation(self, _booking) -> None:
            called["notifications"] += 1

    monkeypatch.setattr(handlers, "_load_booking", lambda _db, _id: None)
    monkeypatch.setattr(handlers, "NotificationService", _NotificationService)

    handlers.handle_booking_created(json.dumps({"booking_id": "b1"}), db=object())
    assert called["notifications"] == 0


def test_handle_booking_created_success(monkeypatch) -> None:
    called = {"sent": False}

    booking = SimpleNamespace(id="b2")

    class _NotificationService:
        def __init__(self, _db) -> None:
            pass

        def send_booking_confirmation(self, value) -> None:
            called["sent"] = value is booking

    monkeypatch.setattr(handlers, "_load_booking", lambda _db, _id: booking)
    monkeypatch.setattr(handlers, "NotificationService", _NotificationService)

    handlers.handle_booking_created(json.dumps({"booking_id": "b2"}), db=object())
    assert called["sent"] is True


def test_handle_booking_cancelled_success(monkeypatch) -> None:
    called = {"cancel": None}
    booking = SimpleNamespace(id="b3")

    class _NotificationService:
        def __init__(self, _db) -> None:
            pass

        def send_cancellation_notification(self, booking, cancelled_by=None) -> None:
            called["cancel"] = (booking, cancelled_by)

    monkeypatch.setattr(handlers, "_load_booking", lambda _db, _id: booking)
    monkeypatch.setattr(handlers, "NotificationService", _NotificationService)

    handlers.handle_booking_cancelled(
        json.dumps({"booking_id": "b3", "cancelled_by": "student"}),
        db=object(),
    )
    assert called["cancel"] == (booking, "student")


def test_handle_booking_reminder_default_type(monkeypatch) -> None:
    called = {"reminder": None}
    booking = SimpleNamespace(id="b4")

    class _NotificationService:
        def __init__(self, _db) -> None:
            pass

        def send_booking_reminder(self, booking, reminder_type) -> None:
            called["reminder"] = (booking, reminder_type)

    monkeypatch.setattr(handlers, "_load_booking", lambda _db, _id: booking)
    monkeypatch.setattr(handlers, "NotificationService", _NotificationService)

    handlers.handle_booking_reminder(json.dumps({"booking_id": "b4"}), db=object())
    assert called["reminder"] == (booking, "24h")


def test_process_event_handles_unknown() -> None:
    assert handlers.process_event("other", "{}", db=object()) is False
    assert handlers.process_event("event:Missing", "{}", db=object()) is True


def test_process_event_dispatch(monkeypatch) -> None:
    called = {"payload": None}

    def _handler(payload: str, _db) -> None:
        called["payload"] = payload

    monkeypatch.setattr(handlers, "EVENT_HANDLERS", {"event:BookingCreated": _handler})

    assert handlers.process_event("event:BookingCreated", "{}", db=object()) is True
    assert called["payload"] == "{}"
