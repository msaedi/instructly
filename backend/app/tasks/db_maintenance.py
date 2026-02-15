# backend/app/tasks/db_maintenance.py
"""
Periodic database maintenance tasks.

Keeps query-planner statistics fresh on high-churn tables so the
optimizer chooses the right indexes (especially partial indexes).
"""

import logging

from celery import shared_task
from sqlalchemy import text

from app.database import get_db_session

logger = logging.getLogger(__name__)

# Tables whose statistics go stale frequently due to high insert/delete churn.
_HIGH_CHURN_TABLES = ("background_jobs",)


@shared_task(name="db_maintenance.analyze_high_churn_tables", ignore_result=True)
def analyze_high_churn_tables() -> None:
    """Run ANALYZE on high-churn tables to refresh query-planner statistics."""
    with get_db_session() as db:
        for table in _HIGH_CHURN_TABLES:
            try:
                db.execute(text(f"ANALYZE {table}"))  # repo-pattern-ignore: maintenance SQL
                logger.info("[DB-MAINT] ANALYZE %s completed", table)
            except Exception:
                logger.warning("[DB-MAINT] ANALYZE %s failed", table, exc_info=True)
