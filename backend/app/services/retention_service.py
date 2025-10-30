# backend/app/services/retention_service.py
"""
RetentionService — chunked purge for soft-deleted records.

This service scans configured tables for rows that have been soft-deleted
(`deleted_at` populated) and permanently removes entries older than the
configured retention window. After each table purge the associated cache
namespaces are invalidated to ensure stale data is not served.

Usage:
    service = RetentionService(db_session, cache_service=CacheService(db_session))
    summary = service.purge_soft_deleted(older_than_days=45, chunk_size=500)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, Iterable, List, Optional

from sqlalchemy import Table
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..metrics import retention_metrics
from ..repositories.retention_repository import RetentionRepository
from .base import BaseService
from .cache_service import CacheService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RetentionTableConfig:
    """Configuration for a table that supports soft delete purging."""

    table_name: str
    primary_key: str
    deleted_at_column: str = "deleted_at"
    cache_prefixes: tuple[str, ...] = ()


class RetentionService(BaseService):
    """
    Service responsible for removing soft-deleted rows in small batches.

    Each configured table is processed independently. The service:
    1. Determines rows with `deleted_at` older than the cutoff timestamp.
    2. Deletes rows in batches (`chunk_size`) inside a transaction.
    3. Clears cache namespaces related to the table when deletions occurred.
    4. Returns a summary dictionary with counts per table.
    """

    _TABLES: tuple[_RetentionTableConfig, ...] = (
        _RetentionTableConfig(
            table_name="availability_slots",
            primary_key="id",
            cache_prefixes=("avail:", "week:", "conf:", "public_availability:", "slot:"),
        ),
        _RetentionTableConfig(
            table_name="bookings",
            primary_key="id",
            cache_prefixes=(
                "booking_stats:",
                "booking:get_student_bookings:",
                "booking:get_instructor_bookings:",
                "bookings:date:",
                "user_bookings:",
                "instructor_stats:",
            ),
        ),
        _RetentionTableConfig(
            table_name="instructor_services",
            primary_key="id",
            cache_prefixes=(
                "catalog:services:",
                "catalog:top-services:",
                "catalog:all-services",
                "catalog:kids-available",
                "svc:",
            ),
        ),
        _RetentionTableConfig(
            table_name="favorites",
            primary_key="id",
            cache_prefixes=("favorites:",),
        ),
        _RetentionTableConfig(
            table_name="user_favorites",
            primary_key="id",
            cache_prefixes=("favorites:",),
        ),
    )

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheService] = None,
        retention_repository: Optional[RetentionRepository] = None,
    ) -> None:
        super().__init__(db, cache=cache_service)
        self.cache_service = cache_service
        self.retention_repository = retention_repository or RetentionRepository(db)

    @BaseService.measure_operation("purge_soft_deleted")
    def purge_soft_deleted(
        self,
        *,
        older_than_days: int = 30,
        chunk_size: int = 1000,
        dry_run: bool = False,
    ) -> Dict[str, Dict[str, int | str]]:
        """
        Permanently delete soft-deleted rows older than the retention window.

        Args:
            older_than_days: Minimum age (in days) of soft-deleted rows to purge.
            chunk_size: Maximum number of rows to delete per transaction.
            dry_run: When True count matching rows without deleting.

        Returns:
            Dictionary keyed by table name with `eligible`, `deleted`, and
            `chunks` counts. Includes `cutoff` and `dry_run` metadata fields.
        """
        if older_than_days < 0:
            raise ValueError("older_than_days must be non-negative")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        summary: Dict[str, Dict[str, int | str]] = {}
        summary["_meta"] = {
            "cutoff": cutoff.isoformat(),
            "chunk_size": chunk_size,
            "dry_run": int(dry_run),
        }

        for config in self._TABLES:
            if not self.retention_repository.has_table(config.table_name):
                logger.debug("Skipping table %s (not present in database)", config.table_name)
                continue

            table, deleted_column, pk_column = self._resolve_columns(config)
            if table is None or deleted_column is None or pk_column is None:
                logger.warning(
                    "Skipping table %s — required columns missing (pk=%s, deleted_at=%s)",
                    config.table_name,
                    config.primary_key,
                    config.deleted_at_column,
                )
                continue

            eligible = self._count_eligible_rows(table, deleted_column, cutoff)
            table_result: Dict[str, int | str] = {"eligible": eligible, "deleted": 0, "chunks": 0}

            if eligible == 0:
                summary[config.table_name] = table_result
                continue

            logger.info(
                "Retention purge %s — %s eligible rows older than %s",
                config.table_name,
                eligible,
                cutoff.isoformat(),
            )

            if dry_run:
                summary[config.table_name] = table_result
                continue

            deleted, chunks = self._purge_table_chunks(
                table=table,
                pk_column=pk_column,
                deleted_column=deleted_column,
                cutoff=cutoff,
                chunk_size=chunk_size,
            )

            table_result["deleted"] = deleted
            table_result["chunks"] = chunks
            summary[config.table_name] = table_result

            if deleted > 0:
                self._invalidate_prefixes(config.cache_prefixes)

        return summary

    def _resolve_columns(
        self, config: _RetentionTableConfig
    ) -> tuple[Optional[Table], Optional[ColumnElement], Optional[ColumnElement]]:
        """Load the table metadata and return soft delete/primary key columns."""
        table = self.retention_repository.reflect_table(config.table_name)
        if table is None:  # pragma: no cover - guarded by has_table
            return None, None, None

        deleted_col = table.c.get(config.deleted_at_column)
        pk_col = table.c.get(config.primary_key)

        return table, deleted_col, pk_col

    def _count_eligible_rows(
        self,
        table: Table,
        deleted_column: ColumnElement,
        cutoff: datetime,
    ) -> int:
        """Return the number of rows eligible for deletion."""
        return self.retention_repository.count_soft_deleted(table, deleted_column, cutoff)

    def _fetch_batch_ids(
        self,
        table: Table,
        pk_column: ColumnElement,
        deleted_column: ColumnElement,
        cutoff: datetime,
        chunk_size: int,
    ) -> List[object]:
        """Fetch a batch of primary keys eligible for deletion."""
        return self.retention_repository.fetch_soft_deleted_ids(
            table=table,
            pk_column=pk_column,
            deleted_column=deleted_column,
            cutoff=cutoff,
            limit=chunk_size,
        )

    def _purge_table_chunks(
        self,
        *,
        table: Table,
        pk_column: ColumnElement,
        deleted_column: ColumnElement,
        cutoff: datetime,
        chunk_size: int,
    ) -> tuple[int, int]:
        """Delete rows in batches and return total deleted rows and chunk count."""
        total_deleted = 0
        chunks = 0

        while True:
            ids = self._fetch_batch_ids(
                table=table,
                pk_column=pk_column,
                deleted_column=deleted_column,
                cutoff=cutoff,
                chunk_size=chunk_size,
            )
            if not ids:
                break

            try:
                with retention_metrics.time_chunk(table.name):
                    with self.transaction():
                        deleted_rows = self.retention_repository.delete_rows(table, pk_column, ids)
                retention_metrics.inc_total(table.name, deleted_rows)
            except Exception:
                retention_metrics.inc_error(table.name)
                raise

            total_deleted += deleted_rows
            chunks += 1

            logger.info(
                "Purged %s rows from %s (chunk %s)",
                len(ids),
                table.name,
                chunks,
            )

        return total_deleted, chunks

    def _invalidate_prefixes(self, prefixes: Iterable[str]) -> None:
        """Clear cache namespaces for the provided prefixes."""
        if not self.cache_service:
            return

        for prefix in prefixes:
            try:
                self.cache_service.clear_prefix(prefix)
            except Exception as exc:  # pragma: no cover - cache backend issues
                logger.warning("Failed to clear cache prefix %s: %s", prefix, exc)
