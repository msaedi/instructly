from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.webhook_event import WebhookEvent
from app.services.webhook_ledger_service import WebhookLedgerService


def test_log_received_creates_event(db):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_1"},
        headers={"Authorization": "secret", "X-Request-Id": "req"},
        event_id="evt_1",
    )

    assert event.id is not None
    assert event.status == "received"
    assert event.headers
    assert event.headers.get("Authorization") == "***"
    assert event.headers.get("X-Request-Id") == "req"

    fetched = db.query(WebhookEvent).filter(WebhookEvent.id == event.id).first()
    assert fetched is not None
    assert fetched.event_id == "evt_1"


def test_mark_processed_updates_status(db):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_2"},
    )

    service.mark_processed(event, duration_ms=123, related_entity_type="booking", related_entity_id="bk_1")

    assert event.status == "processed"
    assert event.processed_at is not None
    assert event.processing_duration_ms == 123
    assert event.related_entity_type == "booking"


def test_mark_failed_captures_error(db):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_3"},
    )

    service.mark_failed(event, error="boom", duration_ms=12)

    assert event.status == "failed"
    assert event.processing_error == "boom"
    assert event.processing_duration_ms == 12


def test_replay_creates_new_event(db):
    service = WebhookLedgerService(db)
    original = service.log_received(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_1"},
        event_id="chk_1",
    )

    replay = service.create_replay(original)

    assert replay.replay_of == original.id
    assert replay.status == "received"
    assert original.replay_count == 1


def test_sanitize_headers_removes_secrets(db):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_4"},
        headers={"stripe-signature": "sig", "X-Test": "ok"},
    )

    assert event.headers["stripe-signature"] == "***"
    assert event.headers["X-Test"] == "ok"


def test_get_failed_webhooks_filters_correctly(db):
    service = WebhookLedgerService(db)
    failed_stripe = service.log_received(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_5"},
    )
    service.mark_failed(failed_stripe, error="fail")

    failed_checkr = service.log_received(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_2"},
    )
    service.mark_failed(failed_checkr, error="fail")

    old_event = service.log_received(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_old"},
    )
    old_event.received_at = datetime.now(timezone.utc) - timedelta(hours=30)
    service.mark_failed(old_event, error="old")

    recent_failed = service.get_failed_events(source="stripe", since_hours=24, limit=10)

    assert failed_stripe in recent_failed
    assert old_event not in recent_failed


def test_list_events_filters_and_orders(db):
    service = WebhookLedgerService(db)
    now = datetime.now(timezone.utc)

    older = service.log_received(
        source="stripe-order",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old"},
    )
    older.received_at = now - timedelta(hours=2)

    newer = service.log_received(
        source="stripe-order",
        event_type="payment_intent.failed",
        payload={"id": "evt_new"},
    )
    newer.received_at = now - timedelta(minutes=5)
    service.mark_failed(newer, error="boom")

    db.flush()

    results = service.list_events(
        source="stripe-order",
        status="failed",
        event_type="payment_intent.failed",
        since_hours=24,
        limit=10,
    )

    assert [event.id for event in results] == [newer.id]

    ordered = service.list_events(source="stripe-order", since_hours=24, limit=10)
    assert [event.id for event in ordered][:2] == [newer.id, older.id]


def test_count_and_summaries(db):
    service = WebhookLedgerService(db)

    service.log_received(
        source="stripe-summary",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_sum_1"},
    )
    failed = service.log_received(
        source="checkr-summary",
        event_type="report.completed",
        payload={"id": "chk_sum_1"},
    )
    service.mark_failed(failed, error="failure")

    assert service.count_events(since_hours=24) == 2

    by_status = service.summarize_by_status(since_hours=24)
    assert by_status["received"] == 1
    assert by_status["failed"] == 1

    by_source = service.summarize_by_source(since_hours=24)
    assert by_source["stripe-summary"] == 1
    assert by_source["checkr-summary"] == 1


def test_get_event_returns_none_for_missing(db):
    service = WebhookLedgerService(db)
    assert service.get_event("01HZZZZZZZZZZZZZZZZZZZZZZ") is None
