# backend/app/tasks/db_maintenance.py
"""
Periodic database maintenance tasks.

Keeps query-planner statistics fresh on high-churn tables so the
optimizer chooses the right indexes (especially partial indexes).
Also handles stale data cleanup (e.g. abandoned 2FA setup secrets).
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, TypeVar, cast

from celery import shared_task
from sqlalchemy import text

from app.database import get_db_session

logger = logging.getLogger(__name__)

# SECURITY: Table names MUST be hardcoded — never populate from config or user input.
# f"ANALYZE {table}" uses text() which does not parameterize table names.
_HIGH_CHURN_TABLES = ("background_jobs",)

_TaskFunc = TypeVar("_TaskFunc", bound=Callable[..., Any])


def _typed_shared_task(*args: Any, **kwargs: Any) -> Callable[[_TaskFunc], _TaskFunc]:
    """Typed wrapper for Celery's shared_task decorator."""
    return cast(Callable[[_TaskFunc], _TaskFunc], shared_task(*args, **kwargs))


@_typed_shared_task(name="db_maintenance.analyze_high_churn_tables", ignore_result=True)
def analyze_high_churn_tables() -> None:
    """Run ANALYZE on high-churn tables to refresh query-planner statistics."""
    with get_db_session() as db:
        for table in _HIGH_CHURN_TABLES:
            try:
                db.execute(text(f"ANALYZE {table}"))  # repo-pattern-ignore: maintenance SQL
                logger.info("[DB-MAINT] ANALYZE %s completed", table)
            except Exception:
                logger.warning("[DB-MAINT] ANALYZE %s failed", table, exc_info=True)


@_typed_shared_task(name="db_maintenance.cleanup_stale_2fa_setups", ignore_result=True)
def cleanup_stale_2fa_setups() -> None:
    """Purge 2FA secrets from abandoned setup flows (>1 hour old, not yet enabled)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    with get_db_session() as db:
        try:
            result = db.execute(  # repo-pattern-ignore: bulk maintenance SQL
                text(
                    "UPDATE users "
                    "SET totp_secret = NULL, two_factor_setup_at = NULL "
                    "WHERE totp_enabled = false "
                    "AND totp_secret IS NOT NULL "
                    "AND two_factor_setup_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            db.commit()
            count = result.rowcount
            if count:
                logger.info("[DB-MAINT] Cleared %d stale 2FA setups", count)
        except Exception:
            logger.warning("[DB-MAINT] cleanup_stale_2fa_setups failed", exc_info=True)
