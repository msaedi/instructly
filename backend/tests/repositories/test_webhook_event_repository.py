from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.webhook_event_repository import WebhookEventRepository


def test_list_events_filters_and_orders(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    older = repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old"},
        status="received",
        received_at=now - timedelta(hours=2),
    )
    newer = repo.create(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_new"},
        status="failed",
        received_at=now - timedelta(minutes=5),
    )
    repo.create(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_1"},
        status="received",
        received_at=now - timedelta(minutes=1),
    )

    filtered = repo.list_events(
        source="stripe",
        status="failed",
        event_type="payment_intent.failed",
        since_hours=24,
        limit=10,
    )
    assert [event.id for event in filtered] == [newer.id]

    ordered = repo.list_events(source="stripe", since_hours=24, limit=10)
    assert [event.id for event in ordered][:2] == [newer.id, older.id]


def test_list_events_respects_time_window(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old_time"},
        status="received",
        received_at=now - timedelta(days=2),
    )
    recent = repo.create(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_new_time"},
        status="failed",
        received_at=now - timedelta(hours=1),
    )

    results = repo.list_events(
        start_time=now - timedelta(hours=2),
        end_time=now,
        limit=10,
    )
    assert [event.id for event in results] == [recent.id]


def test_list_events_without_source_returns_multiple_sources(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_any_1"},
        status="received",
        received_at=now - timedelta(minutes=10),
    )
    repo.create(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_any_1"},
        status="received",
        received_at=now - timedelta(minutes=5),
    )

    results = repo.list_events(since_hours=24, limit=10)
    sources = {event.source for event in results}
    assert {"stripe", "checkr"}.issubset(sources)


def test_count_events_respects_cutoff(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_recent"},
        status="received",
        received_at=now - timedelta(minutes=30),
    )
    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old"},
        status="received",
        received_at=now - timedelta(hours=3),
    )

    assert repo.count_events(since_hours=1) == 1
    assert repo.count_events(since_hours=5) == 2


def test_count_events_respects_time_window(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_recent_window"},
        status="received",
        received_at=now - timedelta(minutes=30),
    )
    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old_window"},
        status="received",
        received_at=now - timedelta(days=1),
    )

    assert repo.count_events(start_time=now - timedelta(hours=1), end_time=now) == 1


def test_summarize_by_status_and_source(db):
    repo = WebhookEventRepository(db)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_1"},
        status="processed",
        received_at=datetime.now(timezone.utc),
    )
    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_2"},
        status="processed",
        received_at=datetime.now(timezone.utc),
    )
    repo.create(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_1"},
        status="failed",
        received_at=datetime.now(timezone.utc),
    )

    by_status = repo.summarize_by_status(since_hours=24)
    assert by_status["processed"] == 2
    assert by_status["failed"] == 1

    by_source = repo.summarize_by_source(since_hours=24)
    assert by_source["stripe"] == 2
    assert by_source["checkr"] == 1


def test_summarize_by_status_with_time_window(db):
    repo = WebhookEventRepository(db)
    now = datetime.now(timezone.utc)

    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_recent_summary"},
        status="processed",
        received_at=now - timedelta(minutes=10),
    )
    repo.create(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_old_summary"},
        status="processed",
        received_at=now - timedelta(days=1),
    )

    by_status = repo.summarize_by_status(
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    assert by_status["processed"] == 1


def test_get_failed_events_filters_by_source(db):
    repo = WebhookEventRepository(db)

    repo.create(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_fail"},
        status="failed",
        received_at=datetime.now(timezone.utc),
    )
    repo.create(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_fail"},
        status="failed",
        received_at=datetime.now(timezone.utc),
    )

    failed = repo.get_failed_events(source="stripe", since_hours=24, limit=10)
    assert len(failed) == 1
    assert failed[0].source == "stripe"


def test_get_failed_events_without_source_includes_multiple_sources(db):
    repo = WebhookEventRepository(db)

    repo.create(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_fail_all"},
        status="failed",
        received_at=datetime.now(timezone.utc),
    )
    repo.create(
        source="checkr",
        event_type="report.completed",
        payload={"id": "chk_fail_all"},
        status="failed",
        received_at=datetime.now(timezone.utc),
    )

    failed = repo.get_failed_events(since_hours=24, limit=10)
    sources = {event.source for event in failed}
    assert {"stripe", "checkr"}.issubset(sources)


def test_find_by_source_and_event_id(db):
    repo = WebhookEventRepository(db)

    event = repo.create(
        source="checkr",
        event_type="report.completed",
        event_id="evt_abc123",
        payload={"test": True},
        status="received",
        received_at=datetime.now(timezone.utc),
    )

    found = repo.find_by_source_and_event_id("checkr", "evt_abc123")
    assert found is not None
    assert found.id == event.id

    not_found = repo.find_by_source_and_event_id("stripe", "evt_abc123")
    assert not_found is None

    not_found = repo.find_by_source_and_event_id("checkr", "evt_different")
    assert not_found is None


def test_find_by_source_and_idempotency_key(db):
    repo = WebhookEventRepository(db)
    event = repo.create(
        source="hundredms",
        event_type="peer.join.success",
        payload={"type": "peer.join.success"},
        status="received",
        idempotency_key="peer.join.success:room_1:session_1:peer_1",
        received_at=datetime.now(timezone.utc),
    )

    found = repo.find_by_source_and_idempotency_key(
        "hundredms",
        "peer.join.success:room_1:session_1:peer_1",
    )
    assert found is not None
    assert found.id == event.id

    not_found = repo.find_by_source_and_idempotency_key("stripe", "peer.join.success:room_1:session_1:peer_1")
    assert not_found is None


def test_claim_for_processing_claims_received_and_failed_only(db):
    repo = WebhookEventRepository(db)
    received = repo.create(
        source="hundredms",
        event_type="session.open.success",
        payload={"id": "evt_received"},
        status="received",
        received_at=datetime.now(timezone.utc),
    )
    failed = repo.create(
        source="hundredms",
        event_type="session.open.success",
        payload={"id": "evt_failed"},
        status="failed",
        processing_error="boom",
        received_at=datetime.now(timezone.utc),
    )
    processed = repo.create(
        source="hundredms",
        event_type="session.open.success",
        payload={"id": "evt_processed"},
        status="processed",
        received_at=datetime.now(timezone.utc),
    )

    assert repo.claim_for_processing(received.id) is True
    assert repo.claim_for_processing(failed.id) is True
    assert repo.claim_for_processing(processed.id) is False

    db.refresh(received)
    db.refresh(failed)
    db.refresh(processed)

    assert received.status == "processing"
    assert failed.status == "processing"
    assert processed.status == "processed"


def test_get_event_returns_none(db):
    repo = WebhookEventRepository(db)
    assert repo.get_event("01HZZZZZZZZZZZZZZZZZZZZZZ") is None


def test_get_event_raises_repository_exception(db, monkeypatch):
    repo = WebhookEventRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "get", _raise)

    with pytest.raises(RepositoryException):
        repo.get_event("01HZZZZZZZZZZZZZZZZZZZZZZ")


def test_summarize_by_status_raises_repository_exception(db, monkeypatch):
    repo = WebhookEventRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)

    with pytest.raises(RepositoryException):
        repo.summarize_by_status(since_hours=24)


def test_summarize_by_source_raises_repository_exception(db, monkeypatch):
    repo = WebhookEventRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)

    with pytest.raises(RepositoryException):
        repo.summarize_by_source(since_hours=24)
