from __future__ import annotations

from unittest.mock import patch

import pytest

import app.tasks.retention_tasks as tasks


def test_env_int_and_bool(monkeypatch):
    monkeypatch.delenv("RETENTION_PURGE_DAYS", raising=False)
    assert tasks._env_int("RETENTION_PURGE_DAYS", 10) == 10

    monkeypatch.setenv("RETENTION_PURGE_DAYS", "bad")
    assert tasks._env_int("RETENTION_PURGE_DAYS", 5) == 5

    monkeypatch.setenv("RETENTION_PURGE_DRY_RUN", "true")
    assert tasks._env_bool("RETENTION_PURGE_DRY_RUN", False) is True

    monkeypatch.setenv("RETENTION_PURGE_DRY_RUN", "0")
    assert tasks._env_bool("RETENTION_PURGE_DRY_RUN", True) is False


def test_purge_soft_deleted_task_success(monkeypatch):
    class _Session:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    session = _Session()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    class _RetentionService:
        def __init__(self, _db, cache_service=None):
            self.cache_service = cache_service

        def purge_soft_deleted(self, **_kwargs):
            return {"bookings": {"count": 1}}

    monkeypatch.setattr(tasks, "RetentionService", _RetentionService)
    monkeypatch.setattr(tasks, "CacheService", lambda _db: object())
    monkeypatch.setattr(tasks, "CacheServiceSyncAdapter", lambda cache: cache)

    result = tasks.purge_soft_deleted_task.run(days=1, chunk_size=2, dry_run=True)

    assert result["bookings"]["count"] == 1
    assert session.closed is True


def test_purge_soft_deleted_task_retries_on_error(monkeypatch):
    class _Session:
        def close(self):
            return None

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _Session())

    class _RetentionService:
        def __init__(self, _db, cache_service=None):
            pass

        def purge_soft_deleted(self, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "RetentionService", _RetentionService)
    monkeypatch.setattr(tasks, "CacheService", lambda _db: object())
    monkeypatch.setattr(tasks, "CacheServiceSyncAdapter", lambda cache: cache)

    with patch.object(tasks.purge_soft_deleted_task, "retry", side_effect=RuntimeError("retry")):
        with pytest.raises(RuntimeError, match="retry"):
            tasks.purge_soft_deleted_task.run(days=1)
