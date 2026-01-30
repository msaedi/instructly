from __future__ import annotations

import pytest

from app.core.ulid_helper import generate_ulid
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository


def test_record_delivery_generic_insert_returns_row(db):
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "other"
    key = f"key-generic-{generate_ulid()}"

    row = repo.record_delivery("event.test", key, payload={"a": 1})

    assert row.attempt_count == 1
    fetched = repo.get_by_idempotency_key(key)
    assert fetched is not None
    assert fetched.id == row.id


def test_record_delivery_generic_missing_existing_raises(db, monkeypatch):
    repo = NotificationDeliveryRepository(db)
    repo._dialect = "other"

    class _Result:
        rowcount = 0
        inserted_primary_key = None

    monkeypatch.setattr(repo.db, "execute", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(repo, "get_by_idempotency_key", lambda _key: None)

    with pytest.raises(RuntimeError, match="Notification delivery record missing after update"):
        repo.record_delivery("event.test", f"key-{generate_ulid()}")
