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
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Dict, Iterable, List, Optional, TypedDict

from sqlalchemy import Table, and_, delete, func, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings, settings
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking
from app.services.retention_metrics import (
    availability_days_purged_total,
    availability_retention_run_seconds,
)

from ..metrics import retention_metrics as soft_delete_retention_metrics
from ..repositories.retention_repository import RetentionRepository
from .base import BaseService
from .cache_service import CacheServiceSyncAdapter

logger = logging.getLogger(__name__)
_DEFAULT_SETTINGS = settings


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
            table_name="availability_days",
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
        cache_service: Optional[CacheServiceSyncAdapter] = None,
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
                with soft_delete_retention_metrics.time_chunk(table.name):
                    with self.transaction():
                        deleted_rows = self.retention_repository.delete_rows(table, pk_column, ids)
                soft_delete_retention_metrics.inc_total(table.name, deleted_rows)
            except Exception:
                soft_delete_retention_metrics.inc_error(table.name)
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

    @BaseService.measure_operation("purge_availability_days")
    def purge_availability_days(
        self,
        session: Optional[Session] = None,
        *,
        today: Optional[date] = None,
    ) -> "RetentionResult":
        """
        Delete orphaned AvailabilityDay rows according to bitmap retention policy.

        Rows are purged only when:
            * availability_retention_enabled is true
            * day_date is in the past
            * day_date is older than both the TTL window and the keep-recent buffer
            * no bookings exist for the instructor on that date
        """

        runtime_settings = _get_runtime_settings()
        ttl_days = max(0, runtime_settings.availability_retention_days)
        keep_recent_days = max(0, runtime_settings.availability_retention_keep_recent_days)
        dry_run = bool(runtime_settings.availability_retention_dry_run)
        base_today = today or datetime.now(timezone.utc).date()
        result: RetentionResult = {
            "inspected_days": 0,
            "purged_days": 0,
            "ttl_days": ttl_days,
            "keep_recent_days": keep_recent_days,
            "dry_run": dry_run,
            "cutoff_date": base_today,
        }

        if not runtime_settings.availability_retention_enabled:
            return result

        db = session or self.db
        ttl_cutoff = base_today - timedelta(days=ttl_days)
        keep_recent_cutoff = base_today - timedelta(days=keep_recent_days)
        effective_cutoff = min(ttl_cutoff, keep_recent_cutoff)
        result["cutoff_date"] = effective_cutoff

        has_booking = (
            select(Booking.id)
            .where(
                and_(
                    Booking.instructor_id == AvailabilityDay.instructor_id,
                    Booking.booking_date == AvailabilityDay.day_date,
                )
            )
            .exists()
        )

        candidates_subquery = (
            select(
                AvailabilityDay.instructor_id.label("instructor_id"),
                AvailabilityDay.day_date.label("day_date"),
            )
            .where(
                and_(
                    AvailabilityDay.day_date < base_today,
                    AvailabilityDay.day_date < ttl_cutoff,
                    AvailabilityDay.day_date <= keep_recent_cutoff,
                    ~has_booking,
                )
            )
            .subquery()
        )

        purged = 0
        with availability_retention_run_seconds.time():
            inspected = db.execute(
                select(func.count()).select_from(candidates_subquery)
            ).scalar_one()
            if inspected and not dry_run:
                delete_statement = delete(AvailabilityDay).where(
                    tuple_(AvailabilityDay.instructor_id, AvailabilityDay.day_date).in_(
                        select(candidates_subquery.c.instructor_id, candidates_subquery.c.day_date)
                    )
                )
                delete_result = db.execute(delete_statement)
                purged = delete_result.rowcount or 0
                if purged:
                    db.commit()
        result["inspected_days"] = inspected

        result["purged_days"] = purged

        logger.info(
            "availability_retention: inspected=%s purged=%s cutoff=%s ttl=%s keep_recent=%s dry_run=%s",
            inspected,
            purged,
            effective_cutoff.isoformat(),
            ttl_days,
            keep_recent_days,
            dry_run,
        )

        site_mode_label = (runtime_settings.site_mode or "unknown").strip() or "unknown"
        try:
            availability_days_purged_total.labels(site_mode=site_mode_label).inc(purged)
        except Exception:
            logger.debug("availability_retention: metrics not registered")

        return result


def _get_runtime_settings() -> Settings:
    """Resolve settings with support for test-time monkeypatching."""
    if settings is not _DEFAULT_SETTINGS:
        return settings
    try:
        from app.core import config as config_module

        return getattr(config_module, "settings", settings)
    except Exception:
        return settings


class RetentionResult(TypedDict):
    inspected_days: int
    purged_days: int
    ttl_days: int
    keep_recent_days: int
    dry_run: bool
    cutoff_date: date
