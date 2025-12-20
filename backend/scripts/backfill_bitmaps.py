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
from typing import Dict, List, Optional, Tuple

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

    Optimized version: uses bulk_upsert_all for single database round-trip.
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

    if not instructor_ids:
        return {}

    # Pre-load all source weeks for all instructors in one query
    current_week_end = current_monday + timedelta(days=6)
    earliest_target_monday = current_monday - timedelta(weeks=weeks_needed)

    from app.models.availability_day import AvailabilityDay

    # Load all bitmap data from earliest target to current week end
    all_bitmap_rows = (
        session.query(
            AvailabilityDay.instructor_id,
            AvailabilityDay.day_date,
            AvailabilityDay.bits
        )
        .filter(
            AvailabilityDay.instructor_id.in_(instructor_ids),
            AvailabilityDay.day_date >= earliest_target_monday,
            AvailabilityDay.day_date <= current_week_end,
        )
        .all()
    )

    # Build lookup: {instructor_id: {date: bits}}
    bitmap_by_instructor: Dict[str, Dict[date, bytes]] = {}
    for instructor_id, day_date, bits in all_bitmap_rows:
        if instructor_id not in bitmap_by_instructor:
            bitmap_by_instructor[instructor_id] = {}
        if bits is not None:
            bitmap_by_instructor[instructor_id][day_date] = bits

    # Collect ALL items for bulk upsert
    all_items: List[Tuple[str, date, bytes]] = []
    stats: Dict[str, int] = {}

    for instructor_id in instructor_ids:
        instructor_bitmaps = bitmap_by_instructor.get(instructor_id, {})

        # Check if source week exists
        source_week = {}
        for day_offset in range(7):
            src_day = current_monday + timedelta(days=day_offset)
            if src_day in instructor_bitmaps:
                source_week[src_day] = instructor_bitmaps[src_day]

        if not source_week:
            continue

        backfilled_days = 0
        for week_offset in range(1, weeks_needed + 1):
            target_monday = current_monday - timedelta(weeks=week_offset)

            # Check existing coverage from pre-loaded data
            existing_count = 0
            for day_offset in range(7):
                target_day = target_monday + timedelta(days=day_offset)
                if target_day in instructor_bitmaps and instructor_bitmaps[target_day]:
                    existing_count += 1

            if existing_count == 7:
                continue

            for day_offset in range(7):
                src_day = current_monday + timedelta(days=day_offset)
                dst_day = target_monday + timedelta(days=day_offset)
                bits = source_week.get(src_day) or bytes(6)
                all_items.append((instructor_id, dst_day, bits))
                backfilled_days += 1

        if backfilled_days:
            stats[instructor_id] = backfilled_days

    # Single native PostgreSQL UPSERT for all data (1 statement)
    if all_items:
        repo.bulk_upsert_native(all_items)

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
