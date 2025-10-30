"""Utilities to create bookings safely under PostgreSQL exclusion constraints."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus

ACTIVE_STATUSES: Dict[str, BookingStatus] = {
    status.name: status for status in (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
}


def _active_status_values() -> Iterable[str]:
    return [status.value for status in ACTIVE_STATUSES.values()]


def _minutes_between(start: time, end: time) -> int:
    start_dt = datetime.combine(date(2000, 1, 1), start)
    end_dt = datetime.combine(date(2000, 1, 1), end)
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(minutes=1)
    return int((end_dt - start_dt).total_seconds() // 60)


def _bump_time(base: time, minutes: int) -> time:
    dt = datetime.combine(date(2000, 1, 1), base) + timedelta(minutes=minutes)
    return dt.time()


def _conflicts_for_instructor(
    session: Session,
    *,
    instructor_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> list[Booking]:
    return (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(_active_status_values()),
        )
        .all()
    )


def _conflicts_for_student(
    session: Session,
    *,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> list[Booking]:
    return (
        session.query(Booking)
        .filter(
            Booking.student_id == student_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(_active_status_values()),
        )
        .all()
    )


def exists_overlap(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> bool:
    """Return True if the proposed span overlaps active bookings for instructor or student."""
    return bool(
        _conflicts_for_instructor(
            session,
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
        )
        or _conflicts_for_student(
            session,
            student_id=student_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
        )
    )


def cancel_exact_duplicate(
    session: Session,
    instructor_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> None:
    """Mark exact-span instructor duplicates as cancelled to bypass exclusion constraints."""
    duplicates = (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.booking_date == booking_date,
            Booking.start_time == start_time,
            Booking.end_time == end_time,
            Booking.cancelled_at.is_(None),
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for dup in duplicates:
        dup.cancelled_at = now
        if dup.status != BookingStatus.CANCELLED:
            dup.status = BookingStatus.CANCELLED
    if duplicates:
        session.flush()


def create_booking_pg_safe(
    session: Session,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: str | BookingStatus = BookingStatus.CONFIRMED,
    allow_overlap: bool = False,
    cancel_duplicate: bool = False,
    offset_index: Optional[int] = None,
    max_shifts: int = 120,
    **extra_fields: Any,
) -> Booking:
    """
    Create a booking that respects overlap exclusion constraints by default.

    Behaviour:
        - If allow_overlap=True, the raw times are used without adjustment.
        - If status is CANCELLED, cancelled_at is set ensuring exclusion constraint ignores row.
        - If offset_index is provided, shift start/end forward by offset_index minutes before validation.
        - Otherwise, shift by +1 minute until both instructor and student windows are free (up to max_shifts attempts).
        - When cancel_duplicate=True, exact instructor duplicates are marked cancelled once detected.
    """

    if isinstance(status, str):
        status = BookingStatus(status)

    initial_offset = offset_index or 0
    if initial_offset:
        start_time = _bump_time(start_time, initial_offset)
        end_time = _bump_time(end_time, initial_offset)

    duration_minutes = _minutes_between(start_time, end_time)
    attempts = 0
    max_attempts = max_shifts if max_shifts > 0 else 1

    if not allow_overlap and status not in (BookingStatus.CANCELLED,):
        while True:
            instructor_conflicts = _conflicts_for_instructor(
                session,
                instructor_id=instructor_id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
            )
            student_conflicts = _conflicts_for_student(
                session,
                student_id=student_id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
            )

            if not instructor_conflicts and not student_conflicts:
                break

            if cancel_duplicate and instructor_conflicts:
                same_span = [
                    conflict
                    for conflict in instructor_conflicts
                    if conflict.start_time == start_time and conflict.end_time == end_time
                ]
                if same_span:
                    cancel_exact_duplicate(session, instructor_id, booking_date, start_time, end_time)
                    break

            start_dt = datetime.combine(booking_date, start_time) + timedelta(minutes=1)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            start_time = start_dt.time()
            end_time = end_dt.time()
            attempts += 1
            if attempts >= max_attempts:
                raise RuntimeError("Unable to resolve booking overlap after several adjustments")

    booking_kwargs = {
        "student_id": student_id,
        "instructor_id": instructor_id,
        "instructor_service_id": instructor_service_id,
        "booking_date": booking_date,
        "start_time": start_time,
        "end_time": end_time,
        "status": status,
        **extra_fields,
    }

    if status == BookingStatus.CANCELLED and booking_kwargs.get("cancelled_at") is None:
        booking_kwargs["cancelled_at"] = datetime.now(timezone.utc)

    booking = Booking(**booking_kwargs)
    session.add(booking)
    session.flush()
    return booking


def seed_series_pg_safe(
    session: Session,
    items: Iterable[Dict[str, Any]],
    *,
    base_time: Tuple[time, time],
    step_minutes: int = 1,
    start_offset: int = 0,
    shared_kwargs: Optional[Dict[str, Any]] = None,
) -> list[Booking]:
    """
    Seed a series of bookings with deterministic minute offsets to avoid overlap.

    Args:
        session: Database session
        items: Iterable of booking kwargs (student_id, instructor_id, etc.)
        base_time: Tuple of (start_time, end_time) used as the baseline window
        step_minutes: Minute increment applied per item (default 1)
        start_offset: Initial offset multiplier applied before the first item
        shared_kwargs: Optional kwargs merged into each booking payload

    Returns:
        List of created Booking instances.
    """

    base_start, base_end = base_time
    shared = shared_kwargs.copy() if shared_kwargs else {}
    bookings: list[Booking] = []

    for index, item in enumerate(items):
        offset = (start_offset + index) * step_minutes
        payload = {**shared, **item}
        booking = create_booking_pg_safe(
            session,
            start_time=base_start,
            end_time=base_end,
            offset_index=offset,
            **payload,
        )
        bookings.append(booking)

    return bookings
