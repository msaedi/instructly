#!/usr/bin/env python3
"""
Read-only script to dump bitmap availability rows for an instructor.

Usage:
    python backend/scripts/ops/dump_bitmap_rows.py --db-url <URL> --instructor-id <ID> [--days-back N] [--days-forward N]

Example:
    python backend/scripts/ops/dump_bitmap_rows.py --db-url $DATABASE_URL --instructor-id 01K8YGPXNZ096E3VS0SDF4JZP3 --days-back 21 --days-forward 21
"""

from argparse import ArgumentParser
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import List, Tuple

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text


def _sanitize_instructor_id(value: str) -> str:
    cleaned = value.strip().strip(",").strip()
    if not cleaned:
        raise ValueError("Instructor ID must be a non-empty string.")
    return cleaned


def fetch_bitmap_rows(
    db_url: str,
    instructor_id: str,
    days_back: int = 21,
    days_forward: int = 21,
) -> List[Tuple[date, str, int, date]]:
    engine = create_engine(db_url)

    start_date = date.today() - timedelta(days=days_back)
    end_date = date.today() + timedelta(days=days_forward)

    with engine.connect() as conn:  # type: ignore[assignment]
        rows = conn.execute(
            text(
                """
                SELECT
                    day_date,
                    CASE
                        WHEN bits IS NULL THEN 'NULL'
                        WHEN octet_length(bits) = 0 THEN 'EMPTY'
                        ELSE 'HAS_BITS'
                    END AS has_bits,
                    COALESCE(octet_length(bits), 0) AS bytes,
                    updated_at
                FROM availability_days
                WHERE instructor_id = :instructor_id
                  AND day_date BETWEEN :start_date AND :end_date
                ORDER BY day_date
                """
            ),
            {
                "instructor_id": instructor_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).fetchall()

    return rows


def dump_bitmap_rows(db_url: str, instructor_id: str, days_back: int = 21, days_forward: int = 21) -> None:
    """Dump bitmap rows as CSV (prints to stdout)."""
    sanitized_id = _sanitize_instructor_id(instructor_id)
    rows = fetch_bitmap_rows(db_url, sanitized_id, days_back, days_forward)
    if not rows:
        raise RuntimeError("No bitmap rows found for the specified instructor and date range.")

    print("day_date,has_bits,bytes,updated_at")
    for day_date, has_bits, bytes_count, updated_at in rows:
        updated_str = updated_at.isoformat() if updated_at else "NULL"
        print(f"{day_date},{has_bits},{bytes_count},{updated_str}")


if __name__ == "__main__":
    parser = ArgumentParser(description="Dump bitmap availability rows for an instructor")
    parser.add_argument(
        "--db-url",
        required=True,
        help="Database URL to use for the query (no implicit fallbacks).",
    )
    parser.add_argument(
        "--instructor-id",
        required=True,
        help="Instructor ID (ULID)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=21,
        help="Number of days to look back (default: 21)",
    )
    parser.add_argument(
        "--days-forward",
        type=int,
        default=21,
        help="Number of days to look forward (default: 21)",
    )

    args = parser.parse_args()
    try:
        dump_bitmap_rows(args.db_url, args.instructor_id, args.days_back, args.days_forward)
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
