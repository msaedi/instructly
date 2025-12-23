# backend/app/tasks/retention_tasks.py
"""
Celery tasks for data retention operations.

Provides a scheduled task that runs the RetentionService purge workflow with
environment-driven defaults and structured logging for observability.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from app.database import SessionLocal
from app.services.cache_service import CacheService, CacheServiceSyncAdapter
from app.services.retention_service import RetentionService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%s; falling back to %s", name, value, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


DEFAULT_DAYS = _env_int("RETENTION_PURGE_DAYS", 30)
DEFAULT_CHUNK = _env_int("RETENTION_PURGE_CHUNK", 1000)
DEFAULT_DRY_RUN = _env_bool("RETENTION_PURGE_DRY_RUN", False)


@celery_app.task(
    name="retention.purge_soft_deleted",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def purge_soft_deleted_task(
    self: Any,
    days: Optional[int] = None,
    chunk_size: Optional[int] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Dict[str, int | str]]:
    """
    Chunked purge of soft-deleted rows; logs per-table counts and clears cache prefixes.
    """
    days_to_use = DEFAULT_DAYS if days is None else days
    chunk_to_use = DEFAULT_CHUNK if chunk_size is None else chunk_size
    dry_run_to_use = DEFAULT_DRY_RUN if dry_run is None else dry_run

    db = SessionLocal()
    cache_service = CacheServiceSyncAdapter(CacheService(db))
    service = RetentionService(db, cache_service=cache_service)

    try:
        result = service.purge_soft_deleted(
            older_than_days=days_to_use,
            chunk_size=chunk_to_use,
            dry_run=dry_run_to_use,
        )
        logger.info(
            "Retention purge completed",
            extra={
                "days": days_to_use,
                "chunk_size": chunk_to_use,
                "dry_run": dry_run_to_use,
                "result": result,
            },
        )
        return result
    except Exception as exc:
        logger.exception(
            "Retention purge failed",
            extra={
                "days": days_to_use,
                "chunk_size": chunk_to_use,
                "dry_run": dry_run_to_use,
            },
        )
        raise self.retry(exc=exc)
    finally:
        db.close()
