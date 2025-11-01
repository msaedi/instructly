"""
Shared seeding helpers for safety checks.

Provides booking creation utilities that respect the PostgreSQL exclusion
constraints by shifting proposed spans when conflicts are detected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import logging
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.utils.bitset import windows_from_bits

logger = logging.getLogger(__name__)


@dataclass
class SlotSearchDiagnostics:
    instructor_id: str
    student_id: str
    examined_start: date
    examined_end: date
    durations_order: Sequence[int]
    bitmap_days: int = 0
    instructor_conflicts: int = 0
    student_conflicts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instructor_id": self.instructor_id,
            "student_id": self.student_id,
            "examined_start": self.examined_start.isoformat(),
            "examined_end": self.examined_end.isoformat(),
            "durations_minutes": list(self.durations_order),
            "bitmap_days": self.bitmap_days,
            "instructor_conflicts": self.instructor_conflicts,
            "student_conflicts": self.student_conflicts,
        }

_ACTIVE_STATUSES: Mapping[str, BookingStatus] = {
    status.name: status
    for status in (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
}


def _active_status_values() -> Iterable[str]:
    return (status.value for status in _ACTIVE_STATUSES.values())


def _minutes_between(start: time, end: time) -> int:
    start_dt = datetime.combine(date(2000, 1, 1), start)
    end_dt = datetime.combine(date(2000, 1, 1), end)
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(minutes=1)
    return int((end_dt - start_dt).total_seconds() // 60)


def _shift_time(base: time, minutes: int) -> time:
    shifted = datetime.combine(date(2000, 1, 1), base) + timedelta(minutes=minutes)
    return shifted.time()


def _detect_conflicts(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> Tuple[int, int]:
    active_values = tuple(_active_status_values())
    instructor_conflicts = (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(active_values),
        )
        .count()
    )
    student_conflicts = (
        session.query(Booking)
        .filter(
            Booking.student_id == student_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(active_values),
        )
        .count()
    )
    return instructor_conflicts, student_conflicts


def _has_conflict(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    diagnostics: Optional[SlotSearchDiagnostics] = None,
) -> bool:
    instructor_conflicts, student_conflicts = _detect_conflicts(
        session,
        instructor_id=instructor_id,
        student_id=student_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
    )
    if diagnostics is not None:
        diagnostics.instructor_conflicts += instructor_conflicts
        diagnostics.student_conflicts += student_conflicts
    return (instructor_conflicts + student_conflicts) > 0


def _time_str_to_minutes(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    if hours == 24 and minutes == 0 and seconds == 0:
        return 24 * 60
    return hours * 60 + minutes


def _minutes_to_time(value: int) -> time:
    if value >= 24 * 60:
        return time(23, 59, 59)
    hours = value // 60
    minutes = value % 60
    return time(hours, minutes)


def _generate_candidate_span_minutes(
    window_start_minutes: int,
    window_end_minutes: int,
    duration_minutes: int,
    step_minutes: int,
) -> Iterable[Tuple[int, int]]:
    span_minutes = window_end_minutes - window_start_minutes
    if span_minutes < duration_minutes:
        return

    step = max(1, step_minutes)
    max_offset = span_minutes - duration_minutes
    for offset in range(0, max_offset + 1, step):
        start_minutes = window_start_minutes + offset
        end_minutes = start_minutes + duration_minutes
        if end_minutes > window_end_minutes:
            break
        yield start_minutes, end_minutes


def find_free_slot_in_bitmap(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    base_date: date,
    lookback_days: int = 90,
    horizon_days: int = 21,
    day_start_hour: int = 9,
    day_end_hour: int = 18,
    step_minutes: int = 15,
    durations_minutes: Optional[Sequence[int]] = None,
) -> Tuple[Optional[Tuple[date, time, time]], SlotSearchDiagnostics]:
    """
    Locate the first available span in the instructor's bitmap availability.

    Searches backward first (up to lookback_days), then forward (up to horizon_days),
    attempting durations in the supplied order until a conflict-free window is found.
    """

    lookback = max(0, lookback_days)
    horizon = max(0, horizon_days)
    durations = [int(d) for d in (durations_minutes or (60, 45, 30)) if int(d) > 0]
    if not durations:
        durations = [30]

    search_start = base_date - timedelta(days=lookback)
    search_end = base_date + timedelta(days=horizon)
    diagnostics = SlotSearchDiagnostics(
        instructor_id=instructor_id,
        student_id=student_id,
        examined_start=search_start,
        examined_end=search_end - timedelta(days=1) if horizon > 0 else base_date,
        durations_order=durations,
    )

    repo = AvailabilityDayRepository(session)
    day_start_minutes = max(0, day_start_hour) * 60
    day_end_minutes = min(24 * 60, max(day_start_minutes + 1, day_end_hour * 60))
    step = max(1, step_minutes)
    processed_dates: set[date] = set()

    def _attempt_for_date(target_date: date) -> Optional[Tuple[date, time, time]]:
        if target_date in processed_dates:
            return None
        processed_dates.add(target_date)

        bits = repo.get_day_bits(instructor_id, target_date)
        if bits is None:
            return None

        diagnostics.bitmap_days += 1
        windows = windows_from_bits(bits)
        if not windows:
            return None

        for start_str, end_str in windows:
            window_start_minutes = _time_str_to_minutes(start_str)
            window_end_minutes = _time_str_to_minutes(end_str)

            if window_end_minutes <= day_start_minutes or window_start_minutes >= day_end_minutes:
                continue

            clamped_start = max(window_start_minutes, day_start_minutes)
            clamped_end = min(window_end_minutes, day_end_minutes)
            available_span = clamped_end - clamped_start
            if available_span <= 0:
                continue

            for duration in durations:
                if available_span < duration:
                    continue

                for start_minutes, end_minutes in _generate_candidate_span_minutes(
                    clamped_start,
                    clamped_end,
                    duration,
                    step,
                ):
                    start_time = _minutes_to_time(start_minutes)
                    end_time = _minutes_to_time(end_minutes)
                    if _has_conflict(
                        session,
                        instructor_id=instructor_id,
                        student_id=student_id,
                        booking_date=target_date,
                        start_time=start_time,
                        end_time=end_time,
                        diagnostics=diagnostics,
                    ):
                        continue
                    logger.debug(
                        "bitmap_slot_search_summary %s",
                        json.dumps(
                            {
                                **diagnostics.to_dict(),
                                "slot_found": True,
                                "direction": "backward" if target_date < base_date else "forward",
                                "booking_date": target_date.isoformat(),
                                "start_time": start_time.isoformat(),
                                "end_time": end_time.isoformat(),
                                "duration_minutes": duration,
                            }
                        ),
                    )
                    return target_date, start_time, end_time
        return None

    for day_offset in range(1, lookback + 1):
        candidate_date = base_date - timedelta(days=day_offset)
        slot = _attempt_for_date(candidate_date)
        if slot:
            return slot, diagnostics

    for day_offset in range(0, horizon + 1):
        candidate_date = base_date + timedelta(days=day_offset)
        slot = _attempt_for_date(candidate_date)
        if slot:
            return slot, diagnostics

    logger.debug(
        "bitmap_slot_search_summary %s",
        json.dumps({**diagnostics.to_dict(), "slot_found": False}),
    )
    return None, diagnostics


def create_booking_safe(
    session: Session,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: BookingStatus | str = BookingStatus.CONFIRMED,
    max_attempts: int = 32,
    shift_minutes: int = 15,
    **extra_fields: Any,
) -> Optional[Booking]:
    """
    Attempt to create a booking while avoiding instructor/student overlaps.

    The span is shifted forward by `shift_minutes` (default 15) until it no longer
    conflicts. Returns None if a free window cannot be found within `max_attempts`.
    """

    if isinstance(status, str):
        status = BookingStatus(status)

    duration_minutes = _minutes_between(start_time, end_time)
    attempts = 0
    current_start = start_time
    current_end = end_time

    while attempts < max_attempts:
        if not _has_conflict(
            session,
            instructor_id=instructor_id,
            student_id=student_id,
            booking_date=booking_date,
            start_time=current_start,
            end_time=current_end,
        ):
            break

        attempts += 1
        next_start_dt = datetime.combine(booking_date, current_start) + timedelta(minutes=shift_minutes)
        next_end_dt = next_start_dt + timedelta(minutes=duration_minutes)

        if next_start_dt.date() != booking_date or next_end_dt.date() != booking_date:
            logger.warning(
                "Skipping seeded booking due to day overflow while avoiding overlap",
                extra={
                    "instructor_id": instructor_id,
                    "student_id": student_id,
                    "booking_date": booking_date.isoformat(),
                    "attempts": attempts,
                },
            )
            return None

        current_start = next_start_dt.time()
        current_end = next_end_dt.time()
    else:
        logger.warning(
            "Failed to seed booking after max attempts",
            extra={
                "instructor_id": instructor_id,
                "student_id": student_id,
                "booking_date": booking_date.isoformat(),
                "max_attempts": max_attempts,
            },
        )
        return None

    booking = Booking(
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=current_start,
        end_time=current_end,
        status=status,
        **extra_fields,
    )
    session.add(booking)
    session.flush()

    return booking


def create_review_booking_pg_safe(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    instructor_service_id: str,
    base_date: date,
    location_type: str,
    meeting_location: str,
    service_name: str,
    hourly_rate,
    total_price,
    student_note: str,
    completed_at: datetime,
    duration_minutes: int = 60,
    lookback_days: int = 90,
    horizon_days: int = 21,
    day_start_hour: int = 9,
    day_end_hour: int = 18,
    step_minutes: int = 15,
    durations_minutes: Optional[Sequence[int]] = None,
    **extra_fields: Any,
) -> Optional[Booking]:
    """
    Seed helper that finds a free slot in bitmap availability before creation.
    """

    slot, diagnostics = find_free_slot_in_bitmap(
        session,
        instructor_id=instructor_id,
        student_id=student_id,
        base_date=base_date,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        step_minutes=step_minutes,
        durations_minutes=durations_minutes or (duration_minutes, 45, 30),
    )

    if not slot:
        context = {
            **diagnostics.to_dict(),
            "status": "skipped",
            "base_date": base_date.isoformat(),
            "lookback_days": lookback_days,
            "horizon_days": horizon_days,
            "day_start_hour": day_start_hour,
            "day_end_hour": day_end_hour,
            "step_minutes": step_minutes,
            "durations_attempted": list(durations_minutes or (duration_minutes, 45, 30)),
            "reason": "no_free_slot_within_span",
            "slot_found": False,
        }
        logger.warning("review_booking_skipped %s", json.dumps(context))
        return None

    booking_date, start_time, end_time = slot
    context = {
        **diagnostics.to_dict(),
        "status": "created",
        "base_date": base_date.isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "booking_date": booking_date.isoformat(),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_minutes": _minutes_between(start_time, end_time),
        "day_start_hour": day_start_hour,
        "day_end_hour": day_end_hour,
        "step_minutes": step_minutes,
        "durations_attempted": list(durations_minutes or (duration_minutes, 45, 30)),
        "slot_found": True,
    }
    logger.info("review_booking_seeded %s", json.dumps(context))
    return create_booking_safe(
        session,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.COMPLETED,
        location_type=location_type,
        meeting_location=meeting_location,
        service_name=service_name,
        hourly_rate=hourly_rate,
        total_price=total_price,
        duration_minutes=duration_minutes,
        student_note=student_note,
        completed_at=completed_at,
        **extra_fields,
    )


__all__ = [
    "SlotSearchDiagnostics",
    "create_booking_safe",
    "find_free_slot_in_bitmap",
    "create_review_booking_pg_safe",
]
