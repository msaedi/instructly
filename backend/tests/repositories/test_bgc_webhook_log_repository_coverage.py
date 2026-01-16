from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.instructor import BGCWebhookLog
from app.repositories.bgc_webhook_log_repository import BGCWebhookLogRepository


def test_record_trims_excess(db, monkeypatch):
    db.query(BGCWebhookLog).delete()
    db.commit()

    monkeypatch.setattr("app.repositories.bgc_webhook_log_repository.MAX_LOG_ENTRIES", 1)
    monkeypatch.setattr("app.repositories.bgc_webhook_log_repository.TRIM_BATCH", 1)

    repo = BGCWebhookLogRepository(db)
    suffix = generate_ulid().lower()

    repo.record(
        event_type="report.completed",
        resource_id=f"r1-{suffix}",
        delivery_id=f"d1-{suffix}",
        http_status=200,
        payload={"ok": True},
        signature=None,
    )
    repo.record(
        event_type="report.completed",
        resource_id=f"r2-{suffix}",
        delivery_id=f"d2-{suffix}",
        http_status=200,
        payload={"ok": True},
        signature=None,
    )
    db.commit()

    count = db.query(BGCWebhookLog).count()
    assert count <= 1


def test_list_filtered_and_cursor(db):
    db.query(BGCWebhookLog).delete()
    db.commit()

    repo = BGCWebhookLogRepository(db)
    suffix = generate_ulid().lower()
    entry = repo.record(
        event_type="report.completed",
        resource_id=f"r1-{suffix}",
        delivery_id=f"d1-{suffix}",
        http_status=200,
        payload={"ok": True},
        signature=f"sig-{suffix}",
    )
    repo.record(
        event_type="report.completed",
        resource_id=f"r1b-{suffix}",
        delivery_id=f"d1b-{suffix}",
        http_status=200,
        payload={"ok": True},
        signature=f"sigb-{suffix}",
    )
    repo.record(
        event_type="report.failed",
        resource_id=f"r2-{suffix}",
        delivery_id=f"d2-{suffix}",
        http_status=500,
        payload={"ok": False},
        signature=f"sig2-{suffix}",
    )
    db.commit()

    rows, cursor = repo.list_filtered(limit=1, events=["report.completed"])
    assert rows
    assert rows[0].event_type == "report.completed"
    assert cursor is not None

    if cursor:
        next_rows, _next_cursor = repo.list_filtered(limit=1, cursor=cursor)
        assert all(row.id != entry.id for row in next_rows)

    rows, _cursor = repo.list_filtered(
        limit=10, event_prefixes=["report."], status_codes=[500], search=f"sig2-{suffix}"
    )
    assert rows[0].http_status == 500


def test_count_errors_since(db):
    db.query(BGCWebhookLog).delete()
    db.commit()

    repo = BGCWebhookLogRepository(db)
    repo.record(
        event_type="report.failed",
        resource_id=f"r3-{generate_ulid().lower()}",
        delivery_id=f"d3-{generate_ulid().lower()}",
        http_status=500,
        payload={"ok": False},
        signature=None,
    )
    db.commit()

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert repo.count_errors_since(since=since) >= 1


def test_list_filtered_raises_when_lookup_fails(db, monkeypatch):
    repo = BGCWebhookLogRepository(db)
    repo.record(
        event_type="report.completed",
        resource_id=f"r-{generate_ulid().lower()}",
        delivery_id=f"d-{generate_ulid().lower()}",
        http_status=200,
        payload={"ok": True},
        signature=None,
    )
    repo.record(
        event_type="report.completed",
        resource_id=f"r-{generate_ulid().lower()}",
        delivery_id=f"d-{generate_ulid().lower()}",
        http_status=200,
        payload={"ok": True},
        signature=None,
    )
    db.commit()

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "get", _raise)

    rows, cursor = repo.list_filtered(limit=1)
    assert rows and cursor is not None
    with pytest.raises(RepositoryException):
        repo.list_filtered(limit=1, cursor=cursor)


def test_record_raises_repository_exception(db, monkeypatch):
    repo = BGCWebhookLogRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "flush", _raise)
    with pytest.raises(RepositoryException):
        repo.record(
            event_type="report.completed",
            resource_id="res",
            delivery_id="del",
            http_status=200,
            payload={"ok": True},
            signature=None,
        )


def test_list_filtered_query_error(db, monkeypatch):
    repo = BGCWebhookLogRepository(db)

    class FailingQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def all(self):
            raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", lambda *_args, **_kwargs: FailingQuery())
    with pytest.raises(RepositoryException):
        repo.list_filtered(limit=1)


def test_count_errors_since_error(db, monkeypatch):
    repo = BGCWebhookLogRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    with pytest.raises(RepositoryException):
        repo.count_errors_since(since=datetime.now(timezone.utc))


def test_trim_excess_handles_db_error(db, monkeypatch):
    repo = BGCWebhookLogRepository(db)
    rolled_back = {"called": False}

    class FailingQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def offset(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def all(self):
            raise SQLAlchemyError("boom")

    original_rollback = repo.db.rollback

    def _rollback():
        rolled_back["called"] = True
        return original_rollback()

    monkeypatch.setattr(repo.db, "query", lambda *_args, **_kwargs: FailingQuery())
    monkeypatch.setattr(repo.db, "rollback", _rollback)

    repo._trim_excess()
    assert rolled_back["called"] is True
