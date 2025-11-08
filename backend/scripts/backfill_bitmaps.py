#!/usr/bin/env python3
"""
Utility to backfill bitmap availability for instructors who lack recent history.

Copies the current week's bitmap backward one week at a time to cover a
configurable number of days (default: 56).
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import logging
import os
from typing import Dict, Optional

from sqlalchemy.orm import Session

# Ensure backend modules are importable when executed as a script
try:
    from app.database import SessionLocal
    from app.repositories.availability_day_repository import AvailabilityDayRepository
    from app.repositories.factory import RepositoryFactory
except ModuleNotFoundError:  # pragma: no cover
    raise

logger = logging.getLogger(__name__)


def backfill_bitmaps_range(session: Session, days: int) -> Dict[str, int]:
    """
    Copy the current week's bitmap backward to cover the requested number of days.

    Returns a mapping of instructor_id -> days backfilled.
    """

    days = max(0, days)
    if days == 0:
        return {}

    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    weeks_needed = (days + 6) // 7

    repo = AvailabilityDayRepository(session)
    user_repo = RepositoryFactory.create_user_repository(session)
    instructor_ids = user_repo.list_instructor_ids()

    stats: Dict[str, int] = {}

    for instructor_id in instructor_ids:
        source_week = repo.get_week(instructor_id, current_monday)
        if not source_week:
            continue

        backfilled_days = 0
        for week_offset in range(1, weeks_needed + 1):
            target_monday = current_monday - timedelta(weeks=week_offset)
            existing_week = repo.get_week(instructor_id, target_monday)

            if existing_week and len(existing_week) == 7 and all(existing_week.values()):
                continue

            items = []
            for day_offset in range(7):
                src_day = current_monday + timedelta(days=day_offset)
                dst_day = target_monday + timedelta(days=day_offset)
                bits = source_week.get(src_day) or bytes(6)
                items.append((dst_day, bits))

            written = repo.upsert_week(instructor_id, items)
            backfilled_days += written

        if backfilled_days:
            stats[instructor_id] = backfilled_days

    return stats


def _cli() -> None:  # pragma: no cover - thin wrapper over backfill function
    parser = argparse.ArgumentParser(description="Backfill instructor bitmap availability for recent weeks.")
    parser.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("BITMAP_BACKFILL_DAYS", "56") or "56"),
        help="Number of days to backfill (default pulled from BITMAP_BACKFILL_DAYS or 56)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed logging; only print summary lines.",
    )

    args = parser.parse_args()
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    session: Optional[Session] = None
    try:
        session = SessionLocal()
        stats = backfill_bitmaps_range(session, args.days)
        if stats:
            session.commit()
            for instructor_id, days_written in sorted(stats.items()):
                print(f"{instructor_id}: backfilled {days_written} day(s)")
        else:
            session.rollback()
            print("No instructors required bitmap backfill.")
    except Exception as exc:  # pragma: no cover - CLI safety
        if session is not None:
            session.rollback()
        raise SystemExit(f"Bitmap backfill failed: {exc}") from exc
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":  # pragma: no cover
    _cli()


__all__ = ["backfill_bitmaps_range"]
