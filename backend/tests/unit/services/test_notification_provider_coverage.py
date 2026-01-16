from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import notification_provider


class StubSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class StubDeliveryRepo:
    def __init__(self, session):
        self.session = session
        self.records = []

    def record_delivery(self, event_type, idempotency_key, payload):
        record = SimpleNamespace(
            id="rec1",
            attempt_count=2,
            payload=payload,
        )
        self.records.append((event_type, idempotency_key, payload))
        return record


class StubOutboxRepo:
    def __init__(self, session):
        self.session = session
        self.calls = []

    def mark_sent_by_key(self, idempotency_key, attempt):
        self.calls.append((idempotency_key, attempt))


def test_should_raise_env_tokens(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_PROVIDER_RAISE_ON", "booking.created")
    assert notification_provider._should_raise("booking.created", "key") is True
    assert notification_provider._should_raise("other", "key") is False

    monkeypatch.setenv("NOTIFICATION_PROVIDER_RAISE_ON", "*")
    assert notification_provider._should_raise("anything", "key") is True


def test_managed_session_commit_and_rollback():
    session = StubSession()

    with notification_provider._managed_session(lambda: session) as managed:
        assert managed is session

    assert session.committed is True
    assert session.closed is True

    session_error = StubSession()
    with pytest.raises(RuntimeError):
        with notification_provider._managed_session(lambda: session_error):
            raise RuntimeError("boom")

    assert session_error.rolled_back is True
    assert session_error.closed is True


def test_send_requires_idempotency_key():
    provider = notification_provider.NotificationProvider(session_factory=lambda: StubSession())
    with pytest.raises(ValueError):
        provider.send(event_type="booking.created", payload={})


def test_send_simulates_provider_failure(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_PROVIDER_RAISE_ON", "booking.created")
    provider = notification_provider.NotificationProvider(session_factory=lambda: StubSession())
    with pytest.raises(notification_provider.NotificationProviderTemporaryError):
        provider.send(
            event_type="booking.created",
            payload={},
            idempotency_key="key-1",
        )


def test_send_suppresses_past_availability(monkeypatch):
    provider = notification_provider.NotificationProvider(session_factory=lambda: StubSession())
    monkeypatch.setattr(
        notification_provider.settings,
        "suppress_past_availability_events",
        True,
        raising=False,
    )

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = provider.send(
        event_type="availability.updated",
        payload={"affected_dates": [yesterday]},
        idempotency_key="key-2",
    )

    assert result.attempt_count == 0
    assert result.event_type == "availability.updated"


def test_send_records_delivery_and_outbox(monkeypatch):
    session = StubSession()

    def session_factory():
        return session

    monkeypatch.setattr(
        "app.services.notification_provider.NotificationDeliveryRepository",
        StubDeliveryRepo,
    )
    monkeypatch.setattr(
        "app.services.notification_provider.EventOutboxRepository",
        StubOutboxRepo,
    )
    monkeypatch.setattr(
        notification_provider.settings,
        "instant_deliver_in_tests",
        True,
        raising=False,
    )

    provider = notification_provider.NotificationProvider(session_factory=session_factory)
    result = provider.send(
        event_type="booking.created",
        payload={"hello": "world"},
        idempotency_key="key-3",
    )

    assert result.attempt_count == 2
    assert result.stored_payload["hello"] == "world"
    assert session.committed is True
    assert session.closed is True


def test_payload_contains_past_date():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert notification_provider.NotificationProvider._payload_contains_past_date(
        {"dates": [yesterday]}
    )

    future = (date.today() + timedelta(days=1)).isoformat()
    assert (
        notification_provider.NotificationProvider._payload_contains_past_date(
            {"dates": [future]}
        )
        is False
    )

    assert (
        notification_provider.NotificationProvider._payload_contains_past_date({"dates": ["bad"]})
        is False
    )
