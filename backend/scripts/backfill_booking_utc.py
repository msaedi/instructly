"""
Backfill booking_start_utc and booking_end_utc for existing bookings.

Uses instructor's timezone to interpret existing date/time fields.
This is a one-time migration script.

Usage:
    python -m scripts.backfill_booking_utc
"""

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.booking import Booking


def backfill_booking_utc(db: Session, dry_run: bool = True) -> int:
    """
    Backfill UTC timestamps for existing bookings.

    Args:
        db: Database session
        dry_run: If True, don't commit changes

    Returns:
        Number of bookings updated
    """
    bookings = db.query(Booking).filter(Booking.booking_start_utc.is_(None)).all()

    print(f"Found {len(bookings)} bookings to backfill")

    updated = 0
    errors: list[tuple[str, str]] = []

    for booking in bookings:
        try:
            instructor_tz_str = "America/New_York"
            if booking.instructor and booking.instructor.timezone:
                instructor_tz_str = booking.instructor.timezone

            instructor_tz = pytz.timezone(instructor_tz_str)

            student_tz_str = "America/New_York"
            if booking.student and booking.student.timezone:
                student_tz_str = booking.student.timezone

            start_date = booking.booking_date
            end_date = booking.booking_date
            if booking.end_time == time(0, 0) and booking.start_time != time(0, 0):
                end_date = booking.booking_date + timedelta(days=1)

            local_start = instructor_tz.localize(
                datetime.combine(  # tz-pattern-ok: backfill script uses pytz.localize
                    start_date, booking.start_time
                )
            )
            local_end = instructor_tz.localize(
                datetime.combine(  # tz-pattern-ok: backfill script uses pytz.localize
                    end_date, booking.end_time
                )
            )

            booking.booking_start_utc = local_start.astimezone(timezone.utc)
            booking.booking_end_utc = local_end.astimezone(timezone.utc)
            booking.lesson_timezone = instructor_tz_str
            booking.instructor_tz_at_booking = instructor_tz_str
            booking.student_tz_at_booking = student_tz_str

            updated += 1

            if not dry_run:
                print(
                    f"  Updated booking {booking.id}: "
                    f"{booking.booking_date} {booking.start_time} ({instructor_tz_str}) "
                    f"-> {booking.booking_start_utc}"
                )

        except Exception as e:
            errors.append((booking.id, str(e)))
            print(f"  ERROR booking {booking.id}: {e}")

    if not dry_run:
        db.commit()
        print(f"\nCommitted {updated} updates")
    else:
        print(f"\nDRY RUN: Would update {updated} bookings")
        db.rollback()

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for booking_id, error in errors:
            print(f"  {booking_id}: {error}")

    return updated


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill booking UTC timestamps")
    parser.add_argument(
        "--execute", action="store_true", help="Actually execute (default is dry run)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        backfill_booking_utc(db, dry_run=not args.execute)
    finally:
        db.close()


if __name__ == "__main__":
    main()
