from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.retention_service import RetentionService, _RetentionTableConfig

TABLE_NAME = "retention_service_unit"


def _create_retention_table(db: Session) -> None:
    column_type = "TIMESTAMPTZ" if db.bind.dialect.name == "postgresql" else "TIMESTAMP"
    db.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
    db.execute(
        text(
            f"CREATE TABLE {TABLE_NAME} ("
            "id TEXT PRIMARY KEY,"
            f"deleted_at {column_type}"
            ")"
        )
    )
    db.commit()


def _drop_retention_table(db: Session) -> None:
    db.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
    db.commit()


def _insert_rows(db: Session, rows: Iterable[tuple[str, datetime]]) -> None:
    stmt = text(f"INSERT INTO {TABLE_NAME} (id, deleted_at) VALUES (:id, :deleted_at)")
    for row_id, deleted_at in rows:
        db.execute(stmt, {"id": row_id, "deleted_at": deleted_at})
    db.commit()


def _count_rows(db: Session, older_than: datetime) -> int:
    stmt = text(
        f"SELECT COUNT(*) FROM {TABLE_NAME} "
        "WHERE deleted_at IS NOT NULL AND deleted_at < :cutoff"
    )
    return int(db.execute(stmt, {"cutoff": older_than}).scalar() or 0)


def _total_rows(db: Session) -> int:
    stmt = text(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    return int(db.execute(stmt).scalar() or 0)


def test_retention_service_chunking_and_cache(monkeypatch, db: Session) -> None:
    _create_retention_table(db)
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=30)
        old_ts = now - timedelta(days=45)
        recent_ts = now - timedelta(days=10)

        _insert_rows(
            db,
            [
                ("old-1", old_ts),
                ("old-2", old_ts),
                ("old-3", old_ts),
                ("recent-1", recent_ts),
            ],
        )

        cache_mock = Mock()
        cache_mock.clear_prefix = Mock(return_value=1)

        config = (
            _RetentionTableConfig(
                table_name=TABLE_NAME,
                primary_key="id",
                cache_prefixes=("unit:",),
            ),
        )
        monkeypatch.setattr(RetentionService, "_TABLES", config)

        service = RetentionService(db, cache_service=cache_mock)

        dry_summary = service.purge_soft_deleted(older_than_days=30, chunk_size=2, dry_run=True)
        assert dry_summary[TABLE_NAME]["eligible"] == 3
        assert dry_summary[TABLE_NAME]["deleted"] == 0
        assert _count_rows(db, cutoff) == 3
        cache_mock.clear_prefix.assert_not_called()

        cache_mock.clear_prefix.reset_mock()
        summary = service.purge_soft_deleted(older_than_days=30, chunk_size=2, dry_run=False)
        assert summary[TABLE_NAME]["deleted"] == 3
        assert summary[TABLE_NAME]["chunks"] == 2
        assert _count_rows(db, cutoff) == 0
        cache_mock.clear_prefix.assert_called_once_with("unit:")
        assert _total_rows(db) == 1  # recent row remains

    finally:
        _drop_retention_table(db)


def test_retention_service_rejects_invalid_chunk_size(db: Session) -> None:
    service = RetentionService(db)
    with pytest.raises(ValueError):
        service.purge_soft_deleted(chunk_size=0)
    with pytest.raises(ValueError):
        service.purge_soft_deleted(older_than_days=-1)
