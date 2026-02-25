from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.ulid_helper import generate_ulid
from app.models.event_outbox import NotificationDelivery
from app.repositories import notification_delivery_repository as nd_repo
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository


def test_record_delivery_postgres_idempotent(db):
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "postgresql"
    key = f"key-{generate_ulid()}"

    row = repo.record_delivery("event.test", key, payload={"a": 1})
    assert row.attempt_count == 1

    row = repo.record_delivery("event.test", key, payload={"b": 2})
    assert row.attempt_count == 2
    assert row.payload["b"] == 2


def test_record_delivery_sqlite_branch(db, monkeypatch):
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "sqlite"
    monkeypatch.setattr(nd_repo, "sqlite_insert", pg_insert)
    key = f"key-sqlite-{generate_ulid()}"

    row = repo.record_delivery("event.test", key, payload={"a": 1})
    assert row.attempt_count == 2

    row = repo.record_delivery("event.test", key, payload={"b": 2})
    assert row.attempt_count == 3


def test_record_delivery_generic_fallback(db, monkeypatch):
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "other"
    key = f"key-generic-{generate_ulid()}"

    existing = NotificationDelivery(
        id=generate_ulid(),
        event_type="event.test",
        idempotency_key=key,
        payload={"a": 1},
        attempt_count=1,
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(existing)
    db.commit()

    class _Result:
        rowcount = 0
        inserted_primary_key = None

    monkeypatch.setattr(repo.db, "execute", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(repo, "get_by_idempotency_key", lambda _key: existing)

    row = repo.record_delivery("event.test", key, payload={"b": 2})
    assert row.attempt_count == 2
    assert row.payload["b"] == 2


def test_get_by_idempotency_key_and_reset(db):
    repo = NotificationDeliveryRepository(db)
    key = f"key-reset-{generate_ulid()}"
    row = repo.record_delivery("event.test", key, payload={"x": 1})
    assert repo.get_by_idempotency_key(key).id == row.id

    repo.reset()
    assert repo.get_by_idempotency_key(key) is None


def test_record_delivery_generic_insert_success(db, monkeypatch):
    """L107,112: Generic fallback with successful insert and rowcount > 0."""
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "other"
    key = f"key-generic-insert-{generate_ulid()}"

    row = repo.record_delivery("event.test", key, payload={"c": 3})
    assert row is not None
    assert row.idempotency_key == key


def test_record_delivery_generic_missing_after_conflict_raises(db, monkeypatch):
    """L112: Generic fallback where insert rowcount=0 and get_by returns None -> RuntimeError."""
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "other"
    key = f"key-generic-missing-{generate_ulid()}"

    class _Result:
        rowcount = 0
        inserted_primary_key = None

    monkeypatch.setattr(repo.db, "execute", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(repo, "get_by_idempotency_key", lambda _key: None)

    import pytest

    with pytest.raises(RuntimeError, match="missing after update"):
        repo.record_delivery("event.test", key, payload={"d": 4})


def test_record_delivery_postgres_conflict_missing_raises(db, monkeypatch):
    """L67: PostgreSQL path where conflict returns None and get_by also returns None."""
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "postgresql"
    key = f"key-pg-miss-{generate_ulid()}"

    # Force execute to return None (simulating ON CONFLICT DO NOTHING with no RETURNING)
    def fake_execute(stmt):
        class _Result:
            def scalar_one_or_none(self):
                return None
        return _Result()

    monkeypatch.setattr(repo.db, "execute", fake_execute)
    monkeypatch.setattr(repo, "get_by_idempotency_key", lambda _key: None)

    import pytest

    with pytest.raises(RuntimeError, match="Failed to load notification delivery after conflict"):
        repo.record_delivery("event.test", key, payload={"e": 5})


def test_record_delivery_sqlite_missing_raises(db, monkeypatch):
    """L89: SQLite path where get_by_idempotency_key returns None after insert."""
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "sqlite"
    key = f"key-sqlite-miss-{generate_ulid()}"

    monkeypatch.setattr(nd_repo, "sqlite_insert", pg_insert)

    def fake_get_by(_key):
        return None

    monkeypatch.setattr(repo, "get_by_idempotency_key", fake_get_by)

    import pytest

    with pytest.raises(RuntimeError, match="Failed to load notification delivery after SQLite conflict"):
        repo.record_delivery("event.test", key, payload={"f": 6})
